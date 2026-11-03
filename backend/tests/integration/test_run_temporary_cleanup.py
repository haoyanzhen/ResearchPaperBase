# ruff: noqa: F811
"""Reclaim staged files only after the terminal run has lost its write scope."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_ingestion_preview import accepted_full_text_run  # noqa: F401
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_object_stage import stage_objects
from rpb.adapters.knowledge_paper_tables import object_build_pins, object_lifecycle, objects
from rpb.adapters.run_tables import runs
from rpb.adapters.run_temporary_cleanup import process_one
from rpb.adapters.runs import persist, transition


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_run_temporary_cleanup(subject, accepted_full_text_run, tmp_path, monkeypatch, terminal):
    client, headers, root, app, engine, _ = subject
    (actor, project, identity, run), candidate, _ = accepted_full_text_run
    attempt = UUID(run["attempt_id"])
    staged = stage_objects(
        app.state.run_store, tmp_path, actor, project, identity, attempt, UUID(candidate["id"])
    )
    paths = [tmp_path / str(project) / str(attempt) / item["object_id"] for item in staged]
    url = root + "/construction-runs/" + str(identity)
    cleanup = url + "/temporary-cleanup"

    def body():
        return {
            "expected_revision": client.get(url).json()["data"]["revision"],
            "explicit_confirmation": True,
        }

    assert post(client, headers, cleanup, body(), str(uuid4())).status_code == 409
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        transition(run, terminal, "PROVIDER_RESPONSE_INVALID")
        persist(conn, run)
    if terminal == "failed":
        assert not process_one(engine, tmp_path)
        assert all(path.is_file() for path in paths)
        command = body()
        assert (
            post(
                client, headers, cleanup, command | {"explicit_confirmation": False}, str(uuid4())
            ).status_code
            == 422
        )
        key = str(uuid4())
        accepted = post(client, headers, cleanup, command, key)
        assert accepted.status_code == 202, accepted.text
        assert (
            post(client, headers, cleanup, command, key).json()["data"] == accepted.json()["data"]
        )
        assert post(client, headers, cleanup, command, str(uuid4())).status_code == 412
    before = client.get(url).json()["data"]
    assert before["temporary_cleanup"]["state"] == "queued"
    with monkeypatch.context() as m:
        original = ImmutableFileStore.discard

        def fail_second(files, *args):
            if not all(path.is_file() for path in paths):
                raise OSError("injected failure after deleting first file")
            original(files, *args)

        m.setattr(ImmutableFileStore, "discard", fail_second)
        assert process_one(engine, tmp_path)
    failed = client.get(url).json()["data"]
    assert failed["temporary_cleanup"]["state"] == "failed"
    assert failed["status"] == terminal
    assert failed["task"]["error"] == before["task"]["error"]
    with engine.connect() as conn:
        assert set(conn.scalars(sa.select(object_lifecycle.c.state))) == {"reclaiming"}
        assert not conn.execute(sa.select(object_build_pins)).all()
    assert post(client, headers, cleanup, body(), str(uuid4())).status_code == 202
    assert process_one(engine, tmp_path)
    assert not process_one(engine, tmp_path)
    after = client.get(url).json()["data"]
    assert after["temporary_cleanup"] == dict(
        state="completed", attempts=2, reclaimed_objects=2, retained_objects=0, error=None
    )
    assert after["status"] == terminal
    assert not any(path.exists() for path in paths)
    with engine.connect() as conn:
        assert not conn.execute(sa.select(objects)).all()
    assert client.get(url + "/candidates").json()["data"]["items"][0]["id"] == candidate["id"]


def test_tampered_cleanup_scope_never_deletes_an_unregistered_file(
    subject, accepted_full_text_run, tmp_path
):
    (actor, project, identity, run), candidate, _ = accepted_full_text_run
    _, _, _, app, engine, _ = subject
    attempt = UUID(run["attempt_id"])
    real = stage_objects(
        app.state.run_store, tmp_path, actor, project, identity, attempt, UUID(candidate["id"])
    )
    unrelated_id = uuid4()
    files = ImmutableFileStore(tmp_path)
    digest = files.write(project, attempt, unrelated_id, b"unrelated")
    with engine.begin() as conn:
        transition(run, "cancelled")
        persist(conn, run)
        run["cleanup_pending_objects"] = [
            [str(attempt), real[0]["object_id"]],
            [str(attempt), str(unrelated_id)],
        ]
        conn.execute(runs.update().where(runs.c.id == identity).values(payload=run))
    assert process_one(engine, tmp_path)
    assert files.read(project, attempt, unrelated_id, digest) == b"unrelated"
    assert all(files.read(project, attempt, UUID(obj["object_id"]), obj["sha256"]) for obj in real)
    with engine.connect() as conn:
        after = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        assert after["status"] == "cancelled"
        assert after["temporary_cleanup"]["state"] == "failed"


def test_cleanup_of_published_run_keeps_version_evidence_and_views(
    subject, accepted_full_text_run, tmp_path
):
    from test_incremental_vector_view import EmptyGraph
    from test_ingestion_preview import FakePort

    from rpb.adapters.first_publication_worker import FirstPublicationWorker
    from rpb.adapters.knowledge_build_tables import graph_views, vector_views
    from rpb.adapters.knowledge_tables import heads

    (_, project, identity, _), _, _ = accepted_full_text_run
    client, _, root, app, engine, _ = subject
    worker = FirstPublicationWorker(app.state.run_store, tmp_path, FakePort, EmptyGraph())
    assert worker.run_once()
    with engine.connect() as conn:
        version = conn.scalar(sa.select(heads.c.version_id).where(heads.c.project_id == project))
        assert version
        stored = conn.execute(sa.select(objects)).mappings().all()
        assert len(stored) == 2
        views = [conn.scalar(sa.select(t.c.id)) for t in (vector_views, graph_views)]
    old = client.get(root + "/papers", params={"knowledge_version_id": str(version)}).json()["data"]
    assert process_one(engine, tmp_path)
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        assert run["status"] == "succeeded"
        assert run["temporary_cleanup"] == dict(
            state="completed", attempts=1, reclaimed_objects=0, retained_objects=2, error=None
        )
        assert conn.scalar(sa.select(heads.c.version_id)) == version
        assert views == [conn.scalar(sa.select(t.c.id)) for t in (vector_views, graph_views)]
    assert (
        client.get(root + "/papers", params={"knowledge_version_id": str(version)}).json()["data"]
        == old
    )
    files = ImmutableFileStore(tmp_path)
    assert all(
        files.read(project, item["attempt_id"], item["id"], item["sha256"]) for item in stored
    )


def test_unregistered_write_rollback_cleanup_uses_frozen_candidate_paths_only(
    subject, accepted_full_text_run, tmp_path
):
    from uuid import uuid5

    (_, project, identity, run), candidate, _ = accepted_full_text_run
    _, _, _, _, engine, _ = subject
    attempt = UUID(run["attempt_id"])
    orphan = uuid5(attempt, candidate["id"] + ":text")
    files = ImmutableFileStore(tmp_path)
    files.write(project, attempt, orphan, b"rolled back staging")
    unrelated = uuid4()
    keep = files.write(project, attempt, unrelated, b"private unrelated")
    with engine.begin() as conn:
        transition(run, "cancelled")
        persist(conn, run)
    assert process_one(engine, tmp_path)
    assert not (tmp_path / str(project) / str(attempt) / str(orphan)).exists()
    assert files.read(project, attempt, unrelated, keep)
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))[
                "temporary_cleanup"
            ]["reclaimed_objects"]
            == 1
        )


def test_failed_rebuild_cleanup_reclaims_detached_embeddings_of_inherited_chunk(
    subject, accepted_full_text_run, tmp_path
):
    from test_incremental_vector_view import EmptyGraph, members, published_baseline_and_second_run
    from test_ingestion_preview import FakePort

    from rpb.adapters.first_publication_worker import FirstPublicationWorker
    from rpb.adapters.knowledge_baseline_papers import content_digest
    from rpb.adapters.knowledge_build_tables import embeddings, vector_views

    class ChangedPort(FakePort):
        def __init__(self, permit):
            super().__init__(permit)
            self.profile.pop("profile_id")
            self.profile["runtime_digest"] = "3" * 64
            self.profile["profile_id"] = content_digest(self.profile)

    class FailedGraph(EmptyGraph):
        def extract(self, *args):
            raise RuntimeError("fixture")

    client, headers, root, app, engine, _ = subject
    _, manifest, second = published_baseline_and_second_run(
        subject, accepted_full_text_run[0], tmp_path, EmptyGraph(), graph_mode="rebuild"
    )
    worker = FirstPublicationWorker(app.state.run_store, tmp_path, ChangedPort, FailedGraph())
    assert worker.run_once()
    with engine.connect() as conn:
        original = members(conn, UUID(manifest["vector_view_id"]))
        new = members(
            conn,
            conn.scalar(
                sa.select(vector_views.c.id).where(vector_views.c.run_id == UUID(second["id"]))
            ),
        )
        assert new and original.isdisjoint(new)
    url = root + "/construction-runs/" + second["id"]
    failed = client.get(url).json()["data"]
    assert failed["status"] == "failed"
    assert (
        post(
            client,
            headers,
            url + "/temporary-cleanup",
            {"expected_revision": failed["revision"], "explicit_confirmation": True},
            str(uuid4()),
        ).status_code
        == 202
    )
    assert process_one(engine, tmp_path)  # published Run
    assert process_one(engine, tmp_path)  # failed rebuild
    with engine.connect() as conn:
        assert set(conn.scalars(sa.select(embeddings.c.id))) == original
    assert client.get(url).json()["data"]["temporary_cleanup"]["state"] == "completed"


@pytest.mark.parametrize("first", ["pin", "mark"])
def test_concurrent_cleanup_and_pin_are_mutually_exclusive(
    subject, accepted_full_text_run, tmp_path, first
):
    from concurrent.futures import ThreadPoolExecutor

    from test_project_maintenance import wait_for_blocker

    from rpb.adapters.run_temporary_cleanup import prepare

    (actor, project, identity, run), candidate, _ = accepted_full_text_run
    client, headers, root, app, engine, _ = subject
    attempt = UUID(run["attempt_id"])
    staged = stage_objects(
        app.state.run_store, tmp_path, actor, project, identity, attempt, UUID(candidate["id"])
    )
    obj = UUID(staged[0]["object_id"])
    with engine.begin() as conn:
        transition(run, "failed", "PROVIDER_RESPONSE_INVALID")
        persist(conn, run)
    request = post(
        client,
        headers,
        root + "/construction-runs/" + str(identity) + "/temporary-cleanup",
        {"expected_revision": run["revision"], "explicit_confirmation": True},
        str(uuid4()),
    )
    assert request.status_code == 202
    other = post(
        client,
        headers,
        root + "/construction-runs",
        {"rerun_of": str(identity), "expected_revision": request.json()["data"]["run"]["revision"]},
        str(uuid4()),
    )
    assert other.status_code == 202
    other_run = other.json()["data"]["run"]
    insert = object_build_pins.insert().values(
        project_id=project,
        run_id=UUID(other_run["id"]),
        object_id=obj,
        attempt_id=UUID(other_run["task"]["attempt_id"]),
        slot_epoch=1,
    )

    def pin():
        with engine.begin() as conn:
            conn.execute(insert)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.begin() as conn:
            pid = conn.scalar(sa.text("SELECT pg_backend_pid()"))
            if first == "pin":
                conn.execute(insert)
                pending = pool.submit(process_one, engine, tmp_path)
            else:
                queued = conn.scalar(
                    sa.select(runs.c.payload).where(runs.c.id == identity).with_for_update()
                )
                prepare(conn, queued, tmp_path)
                pending = pool.submit(pin)
            wait_for_blocker(engine, pid)
        if first == "mark":
            with pytest.raises(sa.exc.DBAPIError):
                pending.result(timeout=5)
            assert process_one(engine, tmp_path)
        else:
            assert pending.result(timeout=5)
    path = tmp_path / str(project) / str(attempt) / str(obj)
    assert path.exists() == (first == "pin")
    with engine.connect() as conn:
        result = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        assert result["temporary_cleanup"]["retained_objects"] == (1 if first == "pin" else 0)
    if first == "pin":
        # Cancelling the dependent run releases its last pin and wakes the
        # earlier authorized cleanup, even though the writer is already gone.
        with engine.begin() as conn:
            other_payload = conn.scalar(
                sa.select(runs.c.payload).where(runs.c.id == UUID(other_run["id"]))
            )
            transition(other_payload, "cancelled")
            persist(conn, other_payload)
        assert process_one(engine, tmp_path)
        assert process_one(engine, tmp_path)
        assert not path.exists()
        with engine.connect() as conn:
            result = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            assert result["temporary_cleanup"]["reclaimed_objects"] == 2
            assert result["temporary_cleanup"]["retained_objects"] == 0


def test_cleanup_retries_db_finalization_after_files_are_gone(
    subject, accepted_full_text_run, tmp_path
):
    (actor, project, identity, run), candidate, _ = accepted_full_text_run
    client, headers, root, app, engine, _ = subject
    attempt = UUID(run["attempt_id"])
    stage_objects(
        app.state.run_store, tmp_path, actor, project, identity, attempt, UUID(candidate["id"])
    )
    with engine.begin() as conn:
        transition(run, "cancelled")
        persist(conn, run)

    def fail_metadata(conn, cursor, sql, params, context, many):
        if sql.startswith("DELETE FROM knowledge_paper_objects"):
            conn.exec_driver_sql("SELECT 1/0")

    sa.event.listen(engine, "before_cursor_execute", fail_metadata)
    try:
        assert process_one(engine, tmp_path)
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_metadata)
    url = root + "/construction-runs/" + str(identity)
    detail = client.get(url).json()["data"]
    assert detail["temporary_cleanup"]["state"] == "failed"
    assert detail["temporary_cleanup"]["attempts"] == 1
    assert detail["status"] == "cancelled"
    assert not list((tmp_path / str(project) / str(attempt)).iterdir())
    with engine.connect() as conn:
        assert set(conn.scalars(sa.select(object_lifecycle.c.state))) == {"reclaiming"}
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 2
    assert (
        post(
            client,
            headers,
            url + "/temporary-cleanup",
            {"expected_revision": detail["revision"], "explicit_confirmation": True},
            str(uuid4()),
        ).status_code
        == 202
    )
    assert process_one(engine, tmp_path)
    assert client.get(url).json()["data"]["temporary_cleanup"]["state"] == "completed"


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_upgrade_adopts_legacy_terminal_staging_without_expiring_failed_run(
    subject, accepted_full_text_run, db, tmp_path, terminal
):
    from test_account_storage import migrate

    (actor, project, identity, run), candidate, _ = accepted_full_text_run
    _, _, _, app, engine, _ = subject
    _, cfg = db
    stage_objects(
        app.state.run_store,
        tmp_path,
        actor,
        project,
        identity,
        UUID(run["attempt_id"]),
        UUID(candidate["id"]),
    )
    migrate(engine, cfg, "downgrade", "0018_knowledge_build_views")
    with engine.begin() as conn:
        transition(run, terminal)
        run.pop("temporary_cleanup", None)
        persist(conn, run)
    migrate(engine, cfg, "upgrade", "head")
    with engine.connect() as conn:
        actual = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
    if terminal == "cancelled":
        assert actual["temporary_cleanup"]["state"] == "queued"
        assert process_one(engine, tmp_path)
    else:
        assert "temporary_cleanup" not in actual
        assert not process_one(engine, tmp_path)
        assert len(list((tmp_path / str(project) / run["attempt_id"]).iterdir())) == 2


def test_only_authorized_run_owner_can_schedule_cleanup(subject, accepted_full_text_run, tmp_path):
    from fastapi.testclient import TestClient
    from test_account_auth import ORIGIN, csrf, login, register
    from test_project_commands import create

    (_, _, identity, run), _, _ = accepted_full_text_run
    client, headers, root, app, engine, _ = subject
    with engine.begin() as conn:
        transition(run, "failed", "PROVIDER_RESPONSE_INVALID")
        persist(conn, run)
    command = {"expected_revision": run["revision"], "explicit_confirmation": True}
    suffix = "/construction-runs/" + str(identity) + "/temporary-cleanup"
    assert post(client, {}, root + suffix, command, str(uuid4())).status_code == 403
    other_project = create(client, headers, key=str(uuid4())).json()["data"]["id"]
    assert (
        post(
            client, headers, "/api/v1/projects/" + other_project + suffix, command, str(uuid4())
        ).status_code
        == 404
    )
    with TestClient(app, base_url=ORIGIN) as other:
        other_headers = csrf(other)
        register(other, other_headers, "Other", "other@example.invalid")
        login(other, other_headers, "Other")
        assert post(other, csrf(other), root + suffix, command, str(uuid4())).status_code == 404
    with engine.connect() as conn:
        stored = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        assert stored["revision"] == run["revision"] and "temporary_cleanup" not in stored
    assert not process_one(engine, tmp_path)
