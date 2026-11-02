# ruff: noqa: F811
"""A real published paper baseline, explicit confirmations and an atomic no-change decision."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_construction_runs import Papers
from test_incremental_vector_view import EmptyGraph
from test_ingestion_preview import FakePort, accepted_full_text_run  # noqa: F401
from test_paper_processing import confirm
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters import no_change
from rpb.adapters.first_publication_worker import FirstPublicationWorker
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import graph_views, publication_events, vector_views
from rpb.adapters.knowledge_paper_tables import version_object_pins, version_paper_pins
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.run_worker import RunWorker
from rpb.adapters.source_tables import dispatch_limits


@pytest.mark.parametrize(
    "case",
    [
        "success",
        "cancel",
        "revoke",
        "pdf_missing",
        "profile_change",
        "tamper",
        "confirmation",
        "late_file",
        "lost_claim",
        "rollback",
        "stale_head",
        "bad_count",
    ],
)
def test_no_change_completion(subject, accepted_full_text_run, tmp_path, monkeypatch, case):
    c, h, root, app, engine, _ = subject
    store = app.state.run_store
    (actor, project, _, first), _, _ = accepted_full_text_run
    worker = FirstPublicationWorker(store, tmp_path, FakePort, EmptyGraph())

    def corrupt_count(conn, clause, multiparams, params, options):
        if getattr(clause, "is_insert", False) and clause.table is versions:
            proof = dict(clause.compile().params["ready_proof"])
            clause = clause.values(
                ready_proof=proof | {"counts": proof["counts"] | {"papers": True}}
            )
        return clause, multiparams, params

    if case == "bad_count":
        sa.event.listen(engine, "before_execute", corrupt_count, retval=True)
    try:
        assert worker.run_once()
    finally:
        if case == "bad_count":
            sa.event.remove(engine, "before_execute", corrupt_count)
    with engine.begin() as conn:
        base = conn.scalar(sa.select(heads.c.version_id))
        manifest = conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == base))
        conn.execute(dispatch_limits.delete())

    def counts():
        with engine.connect() as conn:
            return tuple(
                conn.scalar(sa.select(sa.func.count()).select_from(t))
                for t in (
                    versions,
                    publication_events,
                    vector_views,
                    graph_views,
                    version_object_pins,
                    version_paper_pins,
                )
            )

    before = counts()

    class Matched(Papers):
        def search(self, *args):
            result = super().search(*args)
            result["items"][0]["title"] = first["candidates"][0]["metadata"]["title"]
            return result

    request = {
        k: first["request"][k]
        for k in ("selected_terms", "retrieval_range", "model_selection", "result_limit_per_source")
    }
    path = root + "/construction-runs"
    start = post(c, h, path, request, str(uuid4()))
    identity = UUID(start.json()["data"]["run"]["id"])
    url = path + "/" + str(identity)
    assert RunWorker(store, Matched()).run_once()
    assert confirm(c, h, url)[0].status_code == 200
    detail = c.get(url).json()["data"]
    assert detail["baseline_match_preview"]["base_knowledge_version_id"] == str(base)
    assert detail["waiting_items"][0]["allowed_actions"] == ["confirm_screening"]
    if case == "success":
        # Keep revisions unchanged while changing the scope covered by the issued token.
        wait = detail["waiting_items"][0]
        stale = {
            k: wait["confirmation"][k]
            for k in ("subject_revision", "candidate_revision", "confirmation_token")
        }
        stale.update(expected_revision=wait["revision"], acknowledged_risk_ids=[])
        with engine.begin() as conn:
            original = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            changed = original | {
                "input_snapshot": original["input_snapshot"] | {"result_limit_per_source": 99}
            }
            conn.execute(runs.update().where(runs.c.id == identity).values(payload=changed))
        rejected = post(
            c, h, url + "/waiting-items/" + wait["id"] + "/confirm", stale, str(uuid4())
        )
        assert rejected.status_code == 409
        assert c.get(url).json()["data"]["phase"] == "screening"
        with engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == identity).values(payload=original))
    assert confirm(c, h, url)[0].status_code == 200
    preview = c.get(url + "/ingestion-preview").json()["data"]
    assert preview["valid_papers"] == [] and len(preview["skipped"]) == 1 and not preview["failed"]
    assert preview["waiting_item"]["allowed_actions"] == ["confirm_ingestion_preview"]
    assert not worker.run_once()
    key = str(uuid4())
    accepted, command, body = confirm(c, h, url, key)
    assert accepted.status_code == 200, accepted.text
    assert post(c, h, command, body, key).json()["data"] == accepted.json()["data"]

    class VerifyOnly(FakePort):
        def __init__(self, permit):
            super().__init__(permit)
            if case == "profile_change":
                self.profile.pop("profile_id")
                self.profile["runtime_digest"] = "2" * 64
                self.profile["profile_id"] = content_digest(self.profile)

        def embed(self, text):
            pytest.fail("verification tried to create a new embedding")

    worker.embedding = VerifyOnly
    if case == "pdf_missing":
        (
            tmp_path / str(project) / first["attempt_id"] / manifest["papers"][0]["objects"]["file"]
        ).unlink()
    commits = []
    commit = no_change.commit_no_change

    def interleave(*args):
        commits.append(args)
        detail = c.get(url).json()["data"]
        assert detail["candidate_version"]["state"] == "ready_to_publish"
        if case == "cancel":
            assert (
                post(
                    c,
                    h,
                    url + "/cancel",
                    {
                        "expected_revision": detail["revision"],
                        "attempt_id": detail["task"]["attempt_id"],
                    },
                    str(uuid4()),
                ).status_code
                == 200
            )
        if case == "revoke":
            cid = first["ingestion_confirmation"]["preview"]["valid_papers"][0]
            cls_path = root + "/material-sources/" + cid + "/classification"
            cls = c.get(cls_path).json()["data"]
            assert (
                post(
                    c,
                    h,
                    cls_path + "/correct",
                    dict(
                        expected_revision=cls["revision"],
                        content_revision=cls["source"]["content_revision"],
                        classification="private",
                        basis="Restrict retained source",
                        explicit_confirmation=True,
                    ),
                    str(uuid4()),
                ).status_code
                == 200
            )
        if case == "late_file":
            file = (
                tmp_path
                / str(project)
                / first["attempt_id"]
                / manifest["papers"][0]["objects"]["file"]
            )
            file.chmod(0o600)
            file.write_bytes(b"x" * file.stat().st_size)
        if case == "rollback":

            def fail(conn, cursor, statement, parameters, ctx, many):
                if statement.startswith("UPDATE construction_runs"):
                    raise RuntimeError("failed final update")

            sa.event.listen(engine, "after_cursor_execute", fail)
            try:
                with pytest.raises(RuntimeError, match="failed final update"):
                    commit(*args)
            finally:
                sa.event.remove(engine, "after_cursor_execute", fail)
            with engine.connect() as conn:
                assert conn.scalar(sa.select(slots.c.occupant_run_id)) == identity
                assert (
                    conn.scalar(sa.select(runs.c.status).where(runs.c.id == identity)) == "running"
                )
        if case == "stale_head":
            with engine.begin() as conn:
                conn.execute(heads.delete().where(heads.c.project_id == project))
        if case in {"tamper", "confirmation", "lost_claim"}:
            with engine.begin() as conn:
                run = conn.scalar(
                    sa.select(runs.c.payload).where(runs.c.id == identity).with_for_update()
                )
                if case == "tamper":
                    run["no_change_ready"]["counts"]["chunks"] = 0
                elif case == "lost_claim":
                    run["publication_claim"]["id"] = str(uuid4())
                else:
                    run["ingestion_confirmation"]["candidate_snapshot"] = []
                conn.execute(runs.update().where(runs.c.id == identity).values(payload=run))
        return commit(*args)

    monkeypatch.setattr(no_change, "commit_no_change", interleave)
    assert worker.run_once() and not worker.run_once()
    detail = c.get(url).json()["data"]
    assert detail["published_knowledge_version_id"] is None
    assert counts() == before
    with engine.connect() as conn:
        assert conn.scalar(sa.select(heads.c.version_id)) == (
            None if case == "stale_head" else base
        )
        assert conn.scalar(sa.select(slots.c.occupant_run_id)) == (
            identity if case == "lost_claim" else None
        )
    assert bool(commits) == (case not in {"profile_change", "pdf_missing", "bad_count"})
    if case in {"success", "rollback"}:
        assert detail["status"] == "succeeded"
        assert detail["completion"]["outcome"] == "no_change" and detail["completion"][
            "verified_knowledge_version_id"
        ] == str(base)
        assert detail["completion"]["checked_scope"] == detail["input_snapshot"]
        assert detail["candidate_version"]["closing_reason"]["code"] == "no_change"
        assert detail["candidate_version"]["state"] == "discarded"
        assert commit(*commits[0]) == str(base)
        assert (
            post(
                c,
                h,
                url + "/cancel",
                {
                    "expected_revision": detail["revision"],
                    "attempt_id": detail["task"]["attempt_id"],
                },
                str(uuid4()),
            ).status_code
            == 409
        )
    else:
        assert detail["status"] == (
            {"cancel": "cancelled", "lost_claim": "running"}.get(case, "failed")
        )
        assert detail["completion"] is None
        if detail["status"] == "failed":
            assert detail["candidate_version"]["state"] == "preparing"
            assert detail["candidate_version"]["content_locked"]

    if case == "success":
        from test_incremental_vector_view import second_preview
        from test_project_maintenance import archive, confirmed
        from test_project_maintenance import preview as project_preview

        next_url, next_id = second_preview(c, h, root, store, engine, request)
        assert commit(*commits[0]) == str(base)
        with engine.connect() as conn:
            assert conn.scalar(sa.select(slots.c.occupant_run_id)) == next_id
        wait = c.get(next_url + "/ingestion-preview").json()["data"]["waiting_item"]
        body = {
            k: wait["confirmation"][k]
            for k in ("subject_revision", "candidate_revision", "confirmation_token")
        }
        body.update(expected_revision=wait["revision"], acknowledged_risk_ids=["ABSTRACT_ONLY"])
        assert (
            post(
                c, h, next_url + "/waiting-items/" + wait["id"] + "/confirm", body, str(uuid4())
            ).status_code
            == 200
        )
        worker.embedding = FakePort
        assert worker.run_once()
        with engine.connect() as conn:
            head = conn.scalar(sa.select(heads.c.version_id))
            assert head and head != base
        after = counts()
        assert commit(*commits[0]) == str(base)
        receipt = project_preview(c, h, root, c.get(root).json()["data"]).json()["data"]
        assert archive(c, h, root, confirmed(receipt)).status_code == 200
        assert commit(*commits[0]) == str(base)
        assert counts() == after
        with engine.connect() as conn:
            assert conn.scalar(sa.select(heads.c.version_id)) == head
