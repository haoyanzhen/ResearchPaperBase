# ruff: noqa: F811
"""Two-version publication, historical reads, commit guards and transaction rollback."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_incremental_vector_view import (
    EmptyGraph,
    published_baseline_and_second_run,
    second_preview,
)
from test_ingestion_preview import FakePort, accepted_full_text_run  # noqa: F401
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters import first_publication, first_publication_worker
from rpb.adapters.first_publication_worker import FirstPublicationWorker
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import publication_events
from rpb.adapters.knowledge_paper_tables import (
    paper_revisions,
    version_object_pins,
    version_paper_pins,
)
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_tables import runs, slots


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "rollback",
        "head_race",
        "revoked",
        "stale_claim",
        "stale_proof",
        "changed_counts",
        "stale_nested",
        "stale_before_staging",
        "lost_pdf",
    ],
)
def test_incremental_publication(subject, accepted_full_text_run, tmp_path, monkeypatch, case):
    first_run = accepted_full_text_run[0]
    client, headers, root, app, engine, _ = subject
    actor, project, _, first = first_run
    base, before, second = published_baseline_and_second_run(
        subject, first_run, tmp_path, EmptyGraph()
    )
    if case == "success":
        assert client.get(root).json()["data"]["default_knowledge_version_id"] == str(base)
    old = client.get(root + "/papers", params={"knowledge_version_id": str(base)}).json()["data"]
    assert len(old["items"]) == 1
    run_id = UUID(second["id"])

    def totals(conn):
        return tuple(
            conn.scalar(sa.select(sa.func.count()).select_from(t))
            for t in (versions, publication_events, version_paper_pins, version_object_pins)
        )

    with engine.connect() as conn:
        initial_counts = totals(conn)
    old_file = before["papers"][0]["objects"]["file"]
    assert old["items"][0]["document_refs"] == [old_file]
    if case == "lost_pdf":
        (tmp_path / str(project) / first["attempt_id"] / old_file).unlink()
    reached_commit = []
    commit = first_publication.commit_ready

    def interleave(*args):
        reached_commit.append(args)
        if case in {"stale_claim", "stale_proof", "changed_counts"}:
            with engine.begin() as conn:
                current = conn.scalar(
                    sa.select(runs.c.payload).where(runs.c.id == run_id).with_for_update()
                )
                if case == "stale_claim":
                    current["publication_claim"]["id"] = str(uuid4())
                elif case == "changed_counts":
                    ready = current["publication_ready"]
                    ready["proof"]["counts"]["chunks"] = 0
                    ready["readback_digest"] = content_digest(ready["proof"])
                else:
                    current["publication_ready"]["proof"]["vector_view_id"] = before[
                        "vector_view_id"
                    ]
                conn.execute(runs.update().where(runs.c.id == run_id).values(payload=current))
        if case == "head_race":

            def remove_head(conn, cursor, statement, parameters, ctx, many):
                if statement.startswith("UPDATE knowledge_project_heads"):
                    with engine.begin() as other:
                        other.exec_driver_sql("SET LOCAL lock_timeout = '2s'")
                        assert (
                            other.execute(
                                heads.delete().where(heads.c.project_id == project)
                            ).rowcount
                            == 1
                        )

            sa.event.listen(engine, "before_cursor_execute", remove_head)
            try:
                return commit(*args)
            finally:
                sa.event.remove(engine, "before_cursor_execute", remove_head)
        if case == "rollback":

            def fail(conn, cursor, statement, params, ctx, many):
                if statement.startswith("UPDATE knowledge_project_heads"):
                    raise RuntimeError("rollback after switching head")

            sa.event.listen(engine, "after_cursor_execute", fail)
            try:
                with pytest.raises(RuntimeError, match="rollback after switching head"):
                    commit(*args)
            finally:
                sa.event.remove(engine, "after_cursor_execute", fail)
            with engine.connect() as conn:
                assert totals(conn) == initial_counts
                assert conn.scalar(sa.select(heads.c.version_id)) == base
                assert conn.scalar(sa.select(slots.c.occupant_run_id)) == run_id
        if case == "revoked":
            cid = first["ingestion_confirmation"]["preview"]["valid_papers"][0]
            path = root + "/material-sources/" + cid + "/classification"
            cls = client.get(path).json()["data"]
            assert (
                post(
                    client,
                    headers,
                    path + "/correct",
                    dict(
                        expected_revision=cls["revision"],
                        content_revision=cls["source"]["content_revision"],
                        classification="private",
                        basis="revoke retained",
                        explicit_confirmation=True,
                    ),
                    str(uuid4()),
                ).status_code
                == 200
            )
        return commit(*args)

    monkeypatch.setattr(first_publication, "commit_ready", interleave)

    if case == "stale_before_staging":
        build_vector = first_publication_worker.build_vector_view

        def supersede(*args, **kwargs):
            with engine.begin() as conn:
                live = conn.scalar(
                    sa.select(runs.c.payload).where(runs.c.id == run_id).with_for_update()
                )
                live["publication_claim"]["id"] = str(uuid4())
                conn.execute(runs.update().where(runs.c.id == run_id).values(payload=live))
            return build_vector(*args, **kwargs)

        monkeypatch.setattr(first_publication_worker, "build_vector_view", supersede)

    class Graph(EmptyGraph):
        def extract(self, *args):
            if case == "stale_nested":
                with engine.begin() as conn:
                    current = conn.scalar(
                        sa.select(runs.c.payload).where(runs.c.id == run_id).with_for_update()
                    )
                    current["publication_claim"]["id"] = str(uuid4())
                    conn.execute(runs.update().where(runs.c.id == run_id).values(payload=current))
                raise RuntimeError("late response")
            return super().extract(*args)

    worker = FirstPublicationWorker(app.state.run_store, tmp_path, FakePort, Graph())
    assert worker.run_once()
    assert bool(reached_commit) == (
        case not in {"lost_pdf", "stale_nested", "stale_before_staging"}
    )
    assert not worker.run_once()
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
        latest = conn.scalar(sa.select(heads.c.version_id))
        assert conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == base)) == before
        if case == "head_race":
            assert run["status"] == "failed" and run["error"] == "STATE_REVISION_CONFLICT"
            assert latest is None and totals(conn) == initial_counts
            return
        if case in {"stale_claim", "stale_nested", "stale_before_staging"}:
            if case == "stale_before_staging":
                assert not conn.scalar(
                    sa.select(paper_revisions.c.id).where(paper_revisions.c.run_id == run_id)
                )
            assert run["status"] == run["publication_claim"]["state"] == "running"
            assert conn.scalar(sa.select(slots.c.occupant_run_id)) == run_id
            assert latest == base and totals(conn) == initial_counts
            return
        if case in {"revoked", "stale_proof", "changed_counts", "lost_pdf"}:
            assert run["status"] == "failed" and latest == base and totals(conn) == initial_counts
            return
        assert (
            run["status"] == "succeeded"
            and str(latest) == run["published_knowledge_version_id"]
            and latest != base
        )
        assert client.get(root).json()["data"]["default_knowledge_version_id"] == str(latest)
        listing = client.get("/api/v1/projects").json()["data"]["items"]
        assert next(p for p in listing if p["id"] == str(project))[
            "default_knowledge_version_id"
        ] == str(latest)
        record = conn.execute(sa.select(versions).where(versions.c.id == latest)).mappings().one()
        assert record["base_version_id"] == base
        papers = record["manifest"]["papers"]
        assert len(papers) == 2 and before["papers"][0] in papers
        assert record["ready_proof"]["counts"]["papers"] == 2
        assert (
            record["ready_proof"]["counts"]["chunks"]
            == record["ready_proof"]["counts"]["vectors"]
            == record["ready_proof"]["counts"]["extractions"]
            == 2
        )
        assert set(
            conn.scalars(
                sa.select(version_object_pins.c.object_id).where(
                    version_object_pins.c.version_id == latest
                )
            )
        ) == {UUID(oid) for p in papers for oid in p["objects"].values()}
        assert set(
            conn.scalars(
                sa.select(version_paper_pins.c.paper_revision_id).where(
                    version_paper_pins.c.version_id == latest
                )
            )
        ) == {UUID(p["paper_revision_id"]) for p in papers}
        assert totals(conn)[0:2] == (2, 2)
        assert conn.scalar(sa.select(slots.c.occupant_run_id)) is None
    with engine.connect() as conn:
        first_ready = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(first["id"])))[
            "publication_ready"
        ]
    assert commit(
        app.state.run_store,
        actor,
        project,
        UUID(first["id"]),
        UUID(first["attempt_id"]),
        first_ready["proof"]["read_barrier_id"],
    ) == str(base)
    assert commit(*reached_commit[0]) == str(latest)
    assert (
        client.get(root + "/papers", params={"knowledge_version_id": str(base)}).json()["data"]
        == old
    )
    current = client.get(root + "/papers").json()["data"]
    assert current["knowledge_version_id"] == str(latest)
    assert {p["title"] for p in current["items"]} == {old["items"][0]["title"], "graph"}


def test_rebuild_confirmation_rejects_restricted_retained_paper(
    subject, accepted_full_text_run, tmp_path
):
    client, headers, root, app, engine, _ = subject
    store = app.state.run_store
    _, _, _, first = accepted_full_text_run[0]
    worker = FirstPublicationWorker(store, tmp_path, FakePort, EmptyGraph())
    assert worker.run_once()
    with engine.connect() as conn:
        base = conn.scalar(sa.select(heads.c.version_id))
    request = {
        k: first["request"][k]
        for k in ("selected_terms", "retrieval_range", "model_selection", "result_limit_per_source")
    }
    url, identity = second_preview(
        client, headers, root, store, engine, request | {"graph_mode": "rebuild"}
    )
    cid = first["ingestion_confirmation"]["preview"]["valid_papers"][0]
    cls_path = root + "/material-sources/" + cid + "/classification"
    classification = client.get(cls_path).json()["data"]
    assert (
        post(
            client,
            headers,
            cls_path + "/correct",
            {
                "expected_revision": classification["revision"],
                "content_revision": classification["source"]["content_revision"],
                "classification": "private",
                "basis": "Restrict retained material",
                "explicit_confirmation": True,
            },
            str(uuid4()),
        ).status_code
        == 200
    )
    wait = client.get(url + "/ingestion-preview").json()["data"]["waiting_item"]
    assert not wait["allowed_actions"]
    body = {
        k: wait["confirmation"][k]
        for k in ("subject_revision", "candidate_revision", "confirmation_token")
    }
    body.update(expected_revision=wait["revision"], acknowledged_risk_ids=["ABSTRACT_ONLY"])
    rejected = post(
        client, headers, url + "/waiting-items/" + wait["id"] + "/confirm", body, str(uuid4())
    )
    assert (
        rejected.status_code == 409
        and rejected.json()["error"]["code"] == "STATE_OPERATION_NOT_ALLOWED"
    )
    assert not worker.run_once()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.status).where(runs.c.id == identity)) == "waiting_user"
        assert conn.scalar(sa.select(heads.c.version_id)) == base
        assert conn.scalar(sa.select(sa.func.count()).select_from(versions)) == 1
