"""PM01–06: committed metadata/lifecycle behavior with isolated PostgreSQL."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from test_account_auth import client
from test_account_storage import migrate
from test_project_commands import DATA, KEY, counts, create, service_subject, signed_in

from rpb.adapters.account import accounts
from rpb.adapters.project import construction_workspaces as cw
from rpb.adapters.project import projects
from rpb.adapters.project_commands import lifecycle, metadata
from rpb.modules.account_config.application.ports import AccountError


def subject(engine):
    c, h = signed_in(engine)
    r = create(
        c,
        h,
        {"name": "Original", "description": "Keep description", "research_scope": "Keep scope"},
    )
    return c, h, r.json()["data"], r.headers["location"]


def preview(c, h, url, project, action="archive"):
    return c.post(
        url + "/action-preview",
        headers=h,
        json={"action": action, "expected_revision": project["revision"]},
    )


def confirmed(value):
    return {
        "expected_revision": value["subject_revision"],
        "confirmation_token": value["confirmation_token"],
        "acknowledged_risk_ids": [r["id"] for r in value["risks"]],
    }


def archive(c, h, url, body, key="archive-project-key-0001"):
    return c.post(url + "/archive", headers=h | {"Idempotency-Key": key}, json=body)


def delete(c, h, url, body):
    return c.delete(url, headers=h | {"Content-Type": "application/json"}, params=body)


def test_pm01_partial_normalized_edit_noop_and_preserved_container(db):
    engine, _ = db
    c, h, p, url = subject(engine)
    with engine.connect() as conn:
        before = dict(conn.execute(sa.select(projects)).mappings().one())
        container = dict(conn.execute(sa.select(cw)).mappings().one())
    r = c.patch(
        url,
        headers=h,
        json={
            "expected_revision": p["revision"],
            "name": "  " + "N" * 200 + "  ",
            "description": "  a  b\nc  ",
        },
    )
    assert r.status_code == 200
    updated = r.json()["data"]
    assert updated["name"] == "N" * 200 and updated["description"] == "a  b\nc"
    assert updated["research_scope"] == p["research_scope"] and updated["revision"] != p["revision"]
    assert c.get(url).json()["data"] == updated
    assert (
        c.patch(url, headers=h, json={"expected_revision": updated["revision"]}).json()["data"]
        == updated
    )
    r = c.patch(url, headers=h, json={"expected_revision": updated["revision"], "description": ""})
    assert r.json()["data"]["description"] == "" and r.json()["data"]["name"] == updated["name"]
    with engine.connect() as conn:
        after = dict(conn.execute(sa.select(projects)).mappings().one())
        assert dict(conn.execute(sa.select(cw)).mappings().one()) == container
        for field in (
            "id",
            "owner_id",
            "construction_workspace_id",
            "created_at",
            "status",
            "authority_epoch",
        ):
            assert after[field] == before[field]
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 0
    assert counts(engine) == (1, 1, 1)


@pytest.mark.parametrize(
    "change",
    [
        {"name": None},
        {"name": "  "},
        {"name": "x" * 201},
        {"description": None},
        {"description": "x" * 10001},
        {"research_scope": None},
        {"research_scope": "x" * 10001},
        {"owner_id": str(uuid4())},
        {"status": "deleted"},
        {"expected_revision": None},
    ],
)
def test_pm01_reject_invalid_without_write(db, change):
    c, h, p, url = subject(db[0])
    r = c.patch(url, headers=h, json={"expected_revision": p["revision"]} | change)
    assert r.status_code == 422
    assert c.get(url).json()["data"] == p


def test_pm02_permissions_revision_and_states(db):
    engine, _ = db
    c, h, p, url = subject(engine)
    other, oh = signed_in(engine, "Other")
    assert other.patch(url, headers=oh, json={"name": "No"}).status_code == 404
    assert client(engine).patch(url, headers=h, json={"name": "No"}).status_code == 401
    assert c.patch(url, json={"expected_revision": p["revision"], "name": "No"}).status_code == 403
    assert c.patch(url, headers=h, json={"name": "No"}).status_code == 428
    assert (
        c.patch(url, headers=h, json={"expected_revision": "old", "name": "No"}).status_code == 412
    )
    for status, expected in [("archived", 409), ("deleted", 404)]:
        with engine.begin() as conn:
            conn.execute(projects.update().values(status=status))
        assert (
            c.patch(
                url, headers=h, json={"expected_revision": p["revision"], "name": "No"}
            ).status_code
            == expected
        )
    with engine.begin() as conn:
        conn.execute(projects.update().values(status="active"))
        conn.execute(
            accounts.update().where(accounts.c.username_key == "alice").values(enabled=False)
        )
    assert (
        c.patch(url, headers=h, json={"expected_revision": p["revision"], "name": "No"}).status_code
        == 401
    )


def test_pm02_concurrent_updates_have_one_winner(db):
    engine, _ = db
    service, token, csrf = service_subject(engine)
    p, _ = service.create(token, csrf, KEY, DATA)
    identity = p["id"]
    reached, release = Event(), Event()
    pids = []

    def hold(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE projects"):
            pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
            reached.set()
            assert release.wait(8)

    sa.event.listen(engine, "after_cursor_execute", hold)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                service.update, token, csrf, identity, str(p["revision"]), {"name": "Winner"}
            )
            try:
                assert reached.wait(5)
                second = pool.submit(
                    service.update, token, csrf, identity, str(p["revision"]), {"name": "Loser"}
                )
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        observer.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
                        if observer.scalar(
                            sa.text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": pids[0]},
                        ):
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("second writer did not block")
                release.set()
                assert first.result(timeout=8)["name"] == "Winner"
                with pytest.raises(AccountError) as exc:
                    second.result(timeout=8)
                assert exc.value.code == "STATE_REVISION_CONFLICT"
            finally:
                release.set()
    finally:
        sa.event.remove(engine, "after_cursor_execute", hold)
    assert service.read(token, identity)["name"] == "Winner"


@pytest.mark.parametrize("action", ["archive", "delete"])
def test_pm03_preview_has_exact_effects_and_no_business_writes(db, action):
    engine, _ = db
    c, h, p, url = subject(engine)
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            statements.append(statement)

    sa.event.listen(engine, "before_cursor_execute", observe)
    try:
        first = preview(c, h, url, p, action)
        second = preview(c, h | {"Idempotency-Key": "ignored-preview-key"}, url, p, action)
    finally:
        sa.event.remove(engine, "before_cursor_execute", observe)
    assert not statements and first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    value = first.json()["data"]
    assert set(value) == {
        "confirmation_id",
        "action",
        "target",
        "subject_revision",
        "impact_revision",
        "knowledge_version_id",
        "candidate_revision",
        "risks",
        "expires_at",
        "confirmation_token",
        "affected_items",
        "retained_items",
        "blocked_reasons",
    }
    assert value["target"] == {"type": "project", "id": p["id"]}
    assert value["subject_revision"] == value["impact_revision"] == p["revision"]
    assert value["affected_items"] == value["blocked_reasons"] == []
    assert value["knowledge_version_id"] is value["candidate_revision"] is None
    assert {i["scope"] for i in value["retained_items"]} == {
        "existing_content",
        "shared_identity",
        "other_projects",
        "completed_exports",
    }
    assert first.json()["meta"].keys() == {"request_id"}
    assert second.json()["data"]["confirmation_token"] != value["confirmation_token"]
    assert c.get(url).json()["data"] == p and counts(engine) == (1, 1, 1)


@pytest.mark.parametrize("action", ["archive", "delete"])
def test_pm04_transition_audit_and_visibility(db, action):
    engine, _ = db
    c, h, p, url = subject(engine)
    other, oh = signed_in(engine, "Other")
    other_project = create(other, oh).json()["data"]
    value = preview(c, h, url, p, action).json()["data"]
    r = (
        archive(c, h, url, confirmed(value))
        if action == "archive"
        else delete(c, h, url, confirmed(value))
    )
    assert r.status_code == (200 if action == "archive" else 204)
    assert r.headers["cache-control"] == "no-store"
    with engine.connect() as conn:
        row = (
            conn.execute(sa.select(projects).where(projects.c.id == UUID(p["id"]))).mappings().one()
        )
        audit = conn.execute(sa.select(lifecycle)).mappings().one()
        assert row["status"] == ("archived" if action == "archive" else "deleted")
        assert row["authority_epoch"] == 1 and str(row["revision"]) != p["revision"]
        assert (
            audit["subject_revision"] == UUID(p["revision"])
            and audit["actor_id"] == row["owner_id"]
        )
        assert audit["confirmation"]["risks"] == value["risks"]
        assert "confirmation_token" not in audit["confirmation"]
    assert counts(engine) == (2, 2, 2)
    assert other.get("/api/v1/projects/" + other_project["id"]).json()["data"] == other_project
    if action == "archive":
        archived = c.get(url).json()["data"]
        assert archived == r.json()["data"]
        assert preview(c, h, url, archived, "delete").status_code == 409
        assert (
            c.patch(
                url, headers=h, json={"expected_revision": archived["revision"], "name": "No"}
            ).status_code
            == 409
        )
    else:
        assert not r.content
        assert c.get(url).status_code == 404
        assert c.get("/api/v1/projects").json()["data"]["items"] == []
        assert delete(c, h, url, confirmed(value)).status_code == 404
        assert (
            create(
                c,
                h,
                {
                    "name": "Original",
                    "description": "Keep description",
                    "research_scope": "Keep scope",
                },
            ).status_code
            == 404
        )


def test_pm04_confirmation_binding_risks_and_revisions(db):
    c, h, p, url = subject(db[0])
    other = create(c, h, {"name": "Second"}, "second-project-key-0001").json()["data"]
    value = preview(c, h, url, p).json()["data"]
    body = confirmed(value)
    assert archive(c, h, url, {"acknowledged_risk_ids": []}).status_code == 428
    assert (
        archive(
            c, h, url, {"expected_revision": p["revision"], "acknowledged_risk_ids": []}
        ).status_code
        == 409
    )
    for change in [
        {"confirmation_token": "tampered"},
        {"acknowledged_risk_ids": []},
        {"acknowledged_risk_ids": ["archive_readonly", "archive_readonly"]},
        {"acknowledged_risk_ids": ["unknown"]},
    ]:
        assert archive(c, h, url, body | change).status_code == 409
    assert (
        archive(
            c, h, "/api/v1/projects/" + other["id"], body | {"expected_revision": other["revision"]}
        ).status_code
        == 409
    )
    assert delete(c, h, url, body).status_code == 409
    c.patch(url, headers=h, json={"expected_revision": p["revision"], "name": "New"})
    assert archive(c, h, url, body).status_code == 412
    assert c.get(url).json()["data"]["status"] == "active"


def test_pm04_expiry_and_pm05_replay_after_expiry(db):
    engine, _ = db
    service, token, csrf = service_subject(engine)
    now = datetime.now(UTC)
    service.clock = lambda: now
    p, _ = service.create(token, csrf, KEY, DATA)
    value = service.preview(token, csrf, p["id"], str(p["revision"]), "archive")
    args = (
        token,
        csrf,
        p["id"],
        "archive",
        str(p["revision"]),
        value["confirmation_token"],
        ["archive_readonly"],
        "archive-expiry-key-0001",
    )
    service.clock = lambda: now + timedelta(minutes=11)
    with pytest.raises(AccountError) as exc:
        service.change_state(*args)
    assert exc.value.code == "STATE_CONFIRMATION_STALE"
    service.clock = lambda: now
    result, expires = service.change_state(*args)
    service.clock = lambda: now + timedelta(days=3)
    repeated, replay_expiry = service.change_state(*args)
    assert (
        str(result["id"]) == repeated["id"]
        and repeated["status"] == "archived"
        and replay_expiry == expires
    )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 1


def test_pm05_archive_duplicate_conflict_visibility(db):
    engine, _ = db
    c, h, p, url = subject(engine)
    body = confirmed(preview(c, h, url, p).json()["data"])
    first = archive(c, h, url, body)
    assert archive(c, h, url, body).json()["data"] == first.json()["data"]
    assert archive(c, h, url, body | {"confirmation_token": "other"}).status_code == 409
    assert archive(c, h, url, body, key="new-archive-key-0001").status_code == 409
    other, oh = signed_in(engine, "Other")
    assert archive(other, oh, url, body).status_code == 404
    with engine.begin() as conn:
        conn.execute(
            projects.update().where(projects.c.id == UUID(p["id"])).values(status="deleted")
        )
    assert archive(c, h, url, body).status_code == 404


@pytest.mark.parametrize("action", ["archive", "delete"])
@pytest.mark.parametrize("failure_table", ["projects", "project_lifecycle_records"])
def test_pm04_transaction_failure_has_no_partial_state(db, failure_table, action):
    engine, _ = db
    c, h, p, url = subject(engine)
    body = confirmed(preview(c, h, url, p, action).json()["data"])

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(("UPDATE " + failure_table, "INSERT INTO " + failure_table)):
            raise RuntimeError("PRIVATE FAILURE")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        r = archive(c, h, url, body) if action == "archive" else delete(c, h, url, body)
        assert r.status_code == 500 and "PRIVATE" not in r.text
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    assert c.get(url).json()["data"] == p
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 0
    result = archive(c, h, url, body) if action == "archive" else delete(c, h, url, body)
    assert result.status_code == (200 if action == "archive" else 204)


def test_pm06_migration_data_preserved_and_downgrade_guard(db):
    engine, cfg = db
    c, h, p, url = subject(engine)
    migrate(engine, cfg, "downgrade", "0004_project_commands")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.name)) == p["name"]
    migrate(engine, cfg, "upgrade", "head")
    assert c.get(url).json()["data"] == p
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
    archive(c, h, url, confirmed(preview(c, h, url, p).json()["data"]))
    with pytest.raises(RuntimeError, match="contains data"):
        migrate(engine, cfg, "downgrade", "0004_project_commands")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 1
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []


def wait_for_blocker(engine, pid):
    with engine.connect() as observer:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            observer.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
            if observer.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid))"
                ),
                {"pid": pid},
            ):
                return
            time.sleep(0.01)
    pytest.fail("competing transaction never blocked")


@pytest.mark.parametrize("second_action", ["archive", "update", "delete", "downgrade"])
def test_pm04_pm05_pm06_archive_commit_serializes_competitors(db, second_action):
    engine, cfg = db
    service, token, csrf = service_subject(engine)
    p, _ = service.create(token, csrf, KEY, DATA)
    a = service.preview(token, csrf, p["id"], str(p["revision"]), "archive")
    d = service.preview(token, csrf, p["id"], str(p["revision"]), "delete")
    args = (
        token,
        csrf,
        p["id"],
        "archive",
        str(p["revision"]),
        a["confirmation_token"],
        ["archive_readonly"],
        "archive-race-key-0001",
    )
    reached, release = Event(), Event()
    pids = []

    def hold(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO project_lifecycle_records"):
            pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
            reached.set()
            assert release.wait(8)

    sa.event.listen(engine, "after_cursor_execute", hold)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.change_state, *args)
            try:
                assert reached.wait(5)
                if second_action == "archive":
                    second = pool.submit(service.change_state, *args)
                elif second_action == "update":
                    second = pool.submit(
                        service.update,
                        token,
                        csrf,
                        p["id"],
                        str(p["revision"]),
                        {"name": "Forbidden late write"},
                    )
                elif second_action == "delete":
                    second = pool.submit(
                        service.change_state,
                        token,
                        csrf,
                        p["id"],
                        "delete",
                        str(p["revision"]),
                        d["confirmation_token"],
                        ["delete_unavailable"],
                    )
                else:
                    second = pool.submit(migrate, engine, cfg, "downgrade", "0004_project_commands")
                wait_for_blocker(engine, pids[0])
                release.set()
                result = first.result(timeout=8)
                if second_action == "archive":
                    assert second.result(timeout=8)[0]["revision"] == str(result[0]["revision"])
                elif second_action == "downgrade":
                    with pytest.raises(RuntimeError, match="contains data"):
                        second.result(timeout=8)
                else:
                    with pytest.raises(AccountError) as exc:
                        second.result(timeout=8)
                    assert exc.value.code == "STATE_PROJECT_READ_ONLY"
            finally:
                release.set()
    finally:
        sa.event.remove(engine, "after_cursor_execute", hold)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 1
        assert conn.scalar(sa.select(projects.c.authority_epoch)) == 1
        assert conn.scalar(sa.select(projects.c.name)) == DATA["name"]


@pytest.mark.parametrize(
    "change",
    [
        {field: None}
        for field in [
            "id",
            "actor_id",
            "project_id",
            "action",
            "fingerprint",
            "schema_version",
            "subject_revision",
            "confirmation",
            "result",
            "accepted_at",
            "key",
            "expires_at",
        ]
    ]
    + [
        {"action": "restore"},
        {"key": "short"},
        {"fingerprint": "bad"},
        {"confirmation": []},
        {"result": []},
        {"actor_id": uuid4()},
    ],
)
def test_pm06_record_constraints_preserve_audit(db, change):
    engine, _ = db
    c, h, p, url = subject(engine)
    assert archive(c, h, url, confirmed(preview(c, h, url, p).json()["data"])).status_code == 200
    with engine.begin() as conn:
        before = dict(conn.execute(sa.select(lifecycle)).mappings().one())
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(lifecycle.update().values(**change))
        assert dict(conn.execute(sa.select(lifecycle)).mappings().one()) == before


def test_pm06_upgrade_ddl_failure_rolls_back_and_retry(db):
    engine, cfg = db
    c, h, p, url = subject(engine)
    migrate(engine, cfg, "downgrade", "0004_project_commands")

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE project_lifecycle_records" in statement:
            raise RuntimeError("DDL injected failure")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="DDL injected"):
            migrate(engine, cfg, "upgrade", "head")
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    with engine.connect() as conn:
        assert "project_lifecycle_records" not in sa.inspect(conn).get_table_names()
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0004_project_commands"
        )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.name)) == p["name"]
    migrate(engine, cfg, "upgrade", "head")
    assert c.get(url).json()["data"] == p
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []


def test_pm02_metadata_write_failure_rolls_back(db):
    engine, _ = db
    c, h, p, url = subject(engine)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE projects"):
            raise RuntimeError("PRIVATE")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        assert (
            c.patch(
                url, headers=h, json={"expected_revision": p["revision"], "name": "Rollback"}
            ).status_code
            == 500
        )
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    assert c.get(url).json()["data"] == p


def test_pm03_preview_and_delete_reject_foreign_disabled_body_and_unknown_action(db):
    engine, _ = db
    c, h, p, url = subject(engine)
    other, oh = signed_in(engine, "Other")
    assert preview(other, oh, url, p).status_code == 404
    assert preview(c, h, url, p, "restore").status_code == 422
    assert c.post(url + "/action-preview", headers=h, json={"action": "archive"}).status_code == 428
    assert preview(c, h, url, p | {"revision": "old"}).status_code == 412
    assert (
        c.post(
            url + "/action-preview", json={"action": "archive", "expected_revision": p["revision"]}
        ).status_code
        == 403
    )
    body = confirmed(preview(c, h, url, p, "delete").json()["data"])
    assert delete(other, oh, url, body).status_code == 404
    assert (
        c.request("DELETE", url, headers=h, params=body, json={"owner_id": "forged"}).status_code
        == 400
    )
    with engine.begin() as conn:
        conn.execute(
            accounts.update().where(accounts.c.username_key == "alice").values(enabled=False)
        )
    assert preview(c, h, url, p).status_code == 401 and delete(c, h, url, body).status_code == 401
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.status)) == "active"


@pytest.mark.parametrize(
    "field,length", [("name", 200), ("description", 10000), ("research_scope", 10000)]
)
def test_pm01_each_field_trimmed_before_length_check(db, field, length):
    c, h, p, url = subject(db[0])
    r = c.patch(
        url, headers=h, json={"expected_revision": p["revision"], field: "  " + "x" * length + "  "}
    )
    assert r.status_code == 200 and r.json()["data"][field] == "x" * length
    new = r.json()["data"]
    assert (
        c.patch(
            url, headers=h, json={"expected_revision": new["revision"], field: "x" * length}
        ).json()["data"]
        == new
    )


def test_pm05_key_scope_and_pm06_existing_foreign_owner(db):
    engine, _ = db
    c, h, p, url = subject(engine)
    second = create(c, h, {"name": "Second"}, "second-project-key-0001").json()["data"]
    same_key = "same-key-different-projects"
    for project, path in [(p, url), (second, "/api/v1/projects/" + second["id"])]:
        body = confirmed(preview(c, h, path, project).json()["data"])
        assert archive(c, h, path, body, same_key).status_code == 200
    other, oh = signed_in(engine, "Other")
    other_id = UUID(other.get("/api/v1/me").json()["data"]["id"])
    with engine.begin() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 2
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    lifecycle.update()
                    .where(lifecycle.c.project_id == UUID(p["id"]))
                    .values(actor_id=other_id)
                )
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 2
