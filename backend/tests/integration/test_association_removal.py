# ruff: noqa: F811
"""A confirmed scope is subtracted by a new version, with its old evidence pinned."""

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

from rpb.adapters.first_publication_worker import FirstPublicationWorker
from rpb.adapters.knowledge_build_tables import (
    graph_extractions,
    publication_events,
    vector_members,
)
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_tables import runs, slots


@pytest.mark.parametrize(
    "case",
    [
        "all",
        "partial",
        "conflict",
        "new_conflict",
        "rollback",
        "cancel",
        "stale_base",
        "tampered",
        "retained_drift",
        "legacy",
    ],
)
def test_removal_published_scope(subject, accepted_full_text_run, tmp_path, case, monkeypatch):
    client, headers, root, app, engine, _ = subject
    first = accepted_full_text_run[0]
    _, project, _, _ = first
    worker = FirstPublicationWorker(app.state.run_store, tmp_path, FakePort, EmptyGraph())

    def legacy_proof(conn, clause, multiparams, params, options):
        if getattr(clause, "is_insert", False) and clause.table is versions:
            proof = dict(clause.compile().params["ready_proof"])
            proof.pop("source_dependency_digests", None)
            clause = clause.values(ready_proof=proof)
        return clause, multiparams, params

    if case == "legacy":
        sa.event.listen(engine, "before_execute", legacy_proof, retval=True)
    try:
        base, manifest, second = published_baseline_and_second_run(
            subject, first, tmp_path, EmptyGraph()
        )
        if case != "conflict":
            assert worker.run_once()
            with engine.connect() as conn:
                base = conn.scalar(sa.select(heads.c.version_id))
                manifest = conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == base))
    finally:
        if case == "legacy":
            sa.event.remove(engine, "before_execute", legacy_proof)
    removal_worker = worker
    if case == "partial":
        from rpb.adapters.association_removal_worker import AssociationRemovalWorker
        from rpb.adapters.runs import RunStore

        # Reopen the service with only the local exclusion worker installed.
        store = RunStore(app.state.term_store)
        assert not getattr(store, "first_publication_enabled", False)
        removal_worker = AssociationRemovalWorker(store, tmp_path)
        app.state.run_store.first_publication_enabled = False
        app.state.run_store.association_removal_enabled = store.association_removal_enabled
    cw = root + "/construction-workspace"
    workspace = client.get(cw).json()["data"]
    revision = workspace["revision"]

    def preview(selection):
        return post(
            client,
            headers,
            cw + "/association-clear-preview",
            {"expected_revision": revision, "selection": selection},
        )

    selected = {"kind": "paper", "id": manifest["papers"][0]["project_paper_id"]}
    assert preview({"scope": "selected", "targets": []}).status_code == 422
    assert preview({"scope": "selected", "targets": [selected, selected]}).status_code == 422
    assert (
        preview(
            {"scope": "selected", "targets": [{"kind": "paper", "id": str(uuid4())}]}
        ).status_code
        == 404
    )
    response = preview(
        {"scope": "selected", "targets": [selected]}
        if case in {"partial", "legacy", "retained_drift"}
        else {"scope": "all", "kind": "all"}
    )
    assert response.status_code == 200, response.text
    info = response.json()["data"]
    assert info["target"] == {"type": "construction_workspace", "id": workspace["id"]}
    assert info["will_be_empty"] == (case not in {"partial", "legacy", "retained_drift"})
    assert info["base_knowledge_version_id"] == str(base)
    assert {r["run_id"] for r in info["conflicting_runs"]} == (
        {second["id"]} if case == "conflict" else set()
    )
    body = {
        "expected_revision": revision,
        "confirmation_token": info["confirmation_token"],
        "acknowledged_risk_ids": [r["id"] for r in info["risks"]],
    }
    confirm = cw + "/association-clear-confirm"
    assert client.post(confirm, json=body).status_code == 403
    assert (
        post(
            client, headers, confirm, body | {"confirmation_token": "edited.claim"}, str(uuid4())
        ).status_code
        == 409
    )
    assert (
        post(
            client, headers | {"X-Expected-Actor": str(uuid4())}, confirm, body, str(uuid4())
        ).status_code
        == 401
    )
    assert (
        post(
            client, headers, confirm, body | {"acknowledged_risk_ids": []}, str(uuid4())
        ).status_code
        == 409
    )
    assert client.get(cw + "/pending-revisions").json()["data"]["items"] == []
    overlapping_preview = preview({"scope": "selected", "targets": [selected]}).json()["data"]
    equivalent = preview(
        {
            "scope": "selected",
            "targets": [{"kind": t["kind"], "id": t["id"]} for t in info["targets"]],
        }
    )
    assert equivalent.status_code == 200
    if case == "new_conflict":
        # The changed conflict signature is sufficient to invalidate an otherwise current preview.
        with engine.begin() as conn:
            payload = dict(second)
            payload.update(
                id=str(uuid4()),
                status="running",
                input_snapshot={"base_knowledge_version_id": str(base), "mode": "retrieval"},
            )
            conn.execute(
                runs.insert().values(
                    id=UUID(payload["id"]),
                    project_id=project,
                    owner_id=UUID(second["owner_id"]),
                    status="running",
                    revision=UUID(payload["revision"]),
                    payload=payload,
                    created_at=sa.func.now(),
                )
            )
        assert post(client, headers, confirm, body, str(uuid4())).status_code == 409
        return
    key = str(uuid4())
    accepted = post(client, headers, confirm, body, key)
    assert accepted.status_code == 202, accepted.text
    data = accepted.json()["data"]
    identity = UUID(data["run"]["id"])
    assert post(client, headers, confirm, body, key).json()["data"] == data
    assert post(
        client,
        headers,
        confirm,
        body | {"confirmation_token": equivalent.json()["data"]["confirmation_token"]},
        str(uuid4()),
    ).json()["data"]["run"]["id"] == str(identity)
    assert (
        client.get(cw + "/pending-revisions").json()["data"]["items"] == data["pending_revisions"]
    )
    assert post(client, headers, confirm, body, str(uuid4())).json()["data"]["run"]["id"] == str(
        identity
    )
    assert all(
        x["operation"] == "exclude" and x["changes"] == {} and x["assigned_run_id"] == str(identity)
        for x in data["pending_revisions"]
    )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(heads.c.version_id)) == base
        if case == "conflict":
            assert (
                conn.scalar(sa.select(runs.c.status).where(runs.c.id == UUID(second["id"])))
                == "cancelled"
            )
    if case in {"all", "partial"}:
        from rpb.adapters.immutable_files import ImmutableFileStore
        from rpb.adapters.knowledge_paper_tables import paper_revisions

        excluded = {t["id"] for t in info["targets"]}
        blocked_files = {
            UUID(oid)
            for p in manifest["papers"]
            if p["project_paper_id"] in excluded
            for oid in p["objects"].values()
        }
        read = ImmutableFileStore.read

        def read_retained_only(self, project, attempt, oid, expected):
            assert oid not in blocked_files, "opened excluded evidence"
            return read(self, project, attempt, oid, expected)

        monkeypatch.setattr(ImmutableFileStore, "read", read_retained_only)
        with engine.connect() as conn:
            candidate_id = conn.scalar(
                sa.select(paper_revisions.c.candidate_id).where(
                    paper_revisions.c.id == UUID(info["targets"][0]["asset_revision"])
                )
            )
        cls_url = root + "/material-sources/" + str(candidate_id) + "/classification"
        cls = client.get(cls_url).json()["data"]
        assert (
            post(
                client,
                headers,
                cls_url + "/correct",
                {
                    "expected_revision": cls["revision"],
                    "content_revision": cls["source"]["content_revision"],
                    "classification": "private",
                    "basis": "withdraw removed source",
                    "explicit_confirmation": True,
                },
                str(uuid4()),
            ).status_code
            == 200
        )
    if case == "retained_drift":
        from rpb.adapters.knowledge_paper_tables import paper_revisions

        with engine.connect() as conn:
            retained_id = conn.scalar(
                sa.select(paper_revisions.c.candidate_id).where(
                    paper_revisions.c.id == UUID(manifest["papers"][1]["paper_revision_id"])
                )
            )
        cls_url = root + "/material-sources/" + str(retained_id) + "/classification"
        for value in ("private", "public"):
            cls = client.get(cls_url).json()["data"]
            assert (
                post(
                    client,
                    headers,
                    cls_url + "/correct",
                    {
                        "expected_revision": cls["revision"],
                        "content_revision": cls["source"]["content_revision"],
                        "classification": value,
                        "basis": "test retained permission revision",
                        "explicit_confirmation": True,
                    },
                    str(uuid4()),
                ).status_code
                == 200
            )
    if case in {"stale_base", "tampered"}:
        with engine.begin() as conn:
            queued = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            if case == "stale_base":
                queued["removal"]["base_version"] = str(uuid4())
            else:
                queued["removal"]["targets"] = queued["removal"]["targets"][:1]
            conn.execute(runs.update().where(runs.c.id == identity).values(payload=queued))
    if case == "cancel":
        assert (
            post(
                client,
                headers,
                root + "/construction-runs/" + str(identity) + "/cancel",
                {
                    "expected_revision": data["run"]["revision"],
                    "attempt_id": data["task"]["attempt_id"],
                },
                str(uuid4()),
            ).status_code
            == 200
        )
        assert not removal_worker.run_once()
    else:

        def fault(conn, cursor, statement, *args):
            if statement.startswith("UPDATE knowledge_project_heads"):
                raise RuntimeError("injected removal rollback")

        if case == "rollback":
            sa.event.listen(engine, "after_cursor_execute", fault)
        try:
            assert removal_worker.run_once()
        finally:
            if case == "rollback":
                sa.event.remove(engine, "after_cursor_execute", fault)
    with engine.connect() as conn:
        current = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        latest = conn.scalar(sa.select(heads.c.version_id))
        assert conn.scalar(sa.select(slots.c.occupant_run_id)) is None
        assert conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == base)) == manifest
        if case in {"rollback", "cancel", "stale_base", "tampered", "retained_drift"}:
            assert latest == base and current["status"] == (
                "cancelled" if case == "cancel" else "failed"
            )
            assert not conn.scalar(
                sa.select(versions.c.id).where(versions.c.source_run_id == identity)
            )
            return
        assert current["completion"]["outcome"] == "published", current.get("error")
        assert latest != base
        row = conn.execute(sa.select(versions).where(versions.c.id == latest)).mappings().one()
        keep = manifest["papers"][1:] if case in {"partial", "legacy", "retained_drift"} else []
        assert row["manifest"]["papers"] == keep and row["base_version_id"] == base
        assert (
            conn.scalar(
                sa.select(publication_events.c.version_id).where(
                    publication_events.c.version_id == latest
                )
            )
            == latest
        )
        for table, field in (
            (vector_members, "vector_view_id"),
            (graph_extractions, "graph_view_id"),
        ):
            count = conn.scalar(
                sa.select(sa.func.count())
                .select_from(table)
                .where(table.c.view_id == UUID(row["manifest"][field]))
            )
            assert bool(count) == bool(keep)

    listed = client.get(cw + "/pending-revisions").json()["data"]["items"]
    assert {r["published_version_id"] for r in listed} == {str(latest)}
    assert all(r["inclusion_status"] == "published" for r in listed)

    def papers(v):
        return client.get(root + "/papers", params={"knowledge_version_id": str(v)}).json()["data"][
            "items"
        ]

    assert len(papers(latest)) == len(keep) and len(papers(base)) == len(manifest["papers"])

    if case == "all":
        already_completed = post(
            client,
            headers,
            confirm,
            {
                "expected_revision": revision,
                "confirmation_token": overlapping_preview["confirmation_token"],
                "acknowledged_risk_ids": [r["id"] for r in overlapping_preview["risks"]],
            },
            str(uuid4()),
        ).json()["data"]
        assert already_completed["run"]["id"] == str(identity)
        assert already_completed["run"]["status"] == "succeeded"
        assert [r["target_id"] for r in already_completed["pending_revisions"]] == [selected["id"]]
        # Ordinary retrieval of the same identity cannot restore a human exclusion,
        # even if a later Run otherwise passes every candidate and ingestion step.
        url, rid = second_preview(
            client, headers, root, app.state.run_store, engine, second["request"]
        )
        wait = client.get(url + "/ingestion-preview").json()["data"]["waiting_item"]
        command = {
            k: wait["confirmation"][k]
            for k in ("subject_revision", "candidate_revision", "confirmation_token")
        }
        command.update(expected_revision=wait["revision"], acknowledged_risk_ids=["ABSTRACT_ONLY"])
        assert (
            post(
                client,
                headers,
                url + "/waiting-items/" + wait["id"] + "/confirm",
                command,
                str(uuid4()),
            ).status_code
            == 200
        )
        assert worker.run_once()
        with engine.connect() as conn:
            assert conn.scalar(sa.select(runs.c.status).where(runs.c.id == rid)) == "failed"
            assert conn.scalar(sa.select(heads.c.version_id)) == latest
            assert not conn.scalar(sa.select(versions.c.id).where(versions.c.source_run_id == rid))
