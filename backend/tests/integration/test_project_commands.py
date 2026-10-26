"""PC01–08 / task004 T01–T10 with committed PG and deterministic interleavings."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from test_account_auth import PASSWORD, client, csrf, login, register
from test_account_storage import migrate

from rpb.adapters.account import accounts
from rpb.adapters.auth import AccountStore
from rpb.adapters.construction import ConstructionInitializer
from rpb.adapters.project import construction_workspaces as cw
from rpb.adapters.project import projects
from rpb.adapters.project_commands import ProjectUnitOfWork, commands, metadata
from rpb.modules.project.application.service import ProjectService

KEY = "create-project-key-0001"
DATA = {"name": "Research", "description": "", "research_scope": ""}


def signed_in(engine, name="Alice"):
    c = client(engine)
    h = csrf(c)
    r = register(c, h, name, name + "@example.invalid")
    assert r.status_code == 201
    login(c, h, name)
    return c, csrf(c)


def create(c, h, body=None, key=KEY):
    return c.post(
        "/api/v1/projects",
        headers=h | ({"Idempotency-Key": key} if key is not None else {}),
        json=body if body is not None else {"name": "Research"},
    )


def counts(engine):
    with engine.connect() as conn:
        return tuple(
            conn.scalar(sa.select(sa.func.count()).select_from(t)) for t in (projects, cw, commands)
        )


def service_subject(engine):
    store = AccountStore(engine)
    token, ch = store.csrf(None)
    store.register(token, ch, "Alice", "alice@example.invalid", PASSWORD)
    _, token = store.login(token, ch, "Alice", PASSWORD)
    token, ch = store.csrf(token)
    return ProjectService(ProjectUnitOfWork(store, ConstructionInitializer)), token, ch


def test_pc01_create_read_real_atomic_facts(db):
    engine, _ = db
    c, h = signed_in(engine)
    r = create(c, h)
    assert r.status_code == 201
    data = r.json()["data"]
    assert r.headers["location"] == f"/api/v1/projects/{data['id']}"
    assert c.get(r.headers["location"]).json()["data"] == data
    assert data["status"] == "active" and data["default_knowledge_version_id"] is None
    assert data["description"] == data["research_scope"] == ""
    assert data["permissions"] == {"access": True, "use": True, "delete": True}
    assert counts(engine) == (1, 1, 1)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.owner_id)) == conn.scalar(sa.select(accounts.c.id))
        assert conn.scalar(sa.select(cw.c.project_id)) == UUID(data["id"])
        assert not {"tasks", "outbox", "knowledge_versions", "construction_runs"} & set(
            sa.inspect(conn).get_table_names()
        )


@pytest.mark.parametrize("first_name", ["First", "Second"])
@pytest.mark.parametrize("same", [True, False])
def test_pc02_concurrent_same_or_conflicting_commands(db, first_name, same):
    engine, _ = db
    service, token, ch = service_subject(engine)
    inserted, release, pids = Event(), Event(), []

    def hold_first(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO projects"):
            pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
            inserted.set()
            assert release.wait(8)

    sa.event.listen(engine, "after_cursor_execute", hold_first)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(service.create, token, ch, KEY, DATA | {"name": first_name})
            try:
                assert inserted.wait(5)
                other = first_name if same else ("Second" if first_name == "First" else "First")
                b = pool.submit(service.create, token, ch, KEY, DATA | {"name": other})
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        observer.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
                        waiting = observer.scalar(
                            sa.text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": pids[0]},
                        )
                        if waiting:
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("second command never waited for the first transaction")
                release.set()
                first = a.result(timeout=10)
                if same:
                    second = b.result(timeout=10)
                    assert str(first[0]["id"]) == str(second[0]["id"])
                else:
                    from rpb.modules.account_config.application.ports import AccountError

                    with pytest.raises(AccountError) as error:
                        b.result(timeout=10)
                    assert error.value.code == "STATE_IDEMPOTENCY_CONFLICT"
            finally:
                release.set()
    finally:
        sa.event.remove(engine, "after_cursor_execute", hold_first)
    assert counts(engine) == (1, 1, 1)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.name)) == first_name


@pytest.mark.parametrize(
    "table", ["projects", "construction_workspaces", "project_create_commands"]
)
def test_pc03_each_write_failure_rolls_back_then_retry(db, table):
    engine, _ = db
    c, h = signed_in(engine)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO " + table):
            raise RuntimeError("private SQL failure")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        r = create(c, h)
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    assert r.status_code == 500 and "SQL" not in r.text and "id" not in r.json().get("data", {})
    assert counts(engine) == (0, 0, 0)
    assert create(c, h).status_code == 201
    assert counts(engine) == (1, 1, 1)


def test_pc03_committed_response_failure_replays(db, monkeypatch):
    import rpb.api.projects as transport

    engine, _ = db
    c, h = signed_in(engine)
    with monkeypatch.context() as patch:

        def fail(*args, **kwargs):
            raise RuntimeError("response lost after commit")

        patch.setattr(transport, "jsonable_encoder", fail)
        assert create(c, h).status_code == 500
    assert counts(engine) == (1, 1, 1)
    with engine.connect() as conn:
        original = conn.scalar(sa.select(projects.c.id))
    r = create(c, h)
    assert r.status_code == 201 and UUID(r.json()["data"]["id"]) == original
    assert counts(engine) == (1, 1, 1)


def test_pc04_other_actor_and_admin_isolation(db):
    engine, _ = db
    admin, a = signed_in(engine)
    user, b = signed_in(engine, "Bob")
    first, second = create(admin, a), create(user, b)
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert admin.get(second.headers["location"]).status_code == 404
    assert user.get(first.headers["location"]).status_code == 404
    assert counts(engine) == (2, 2, 2)
    with engine.begin() as conn:
        conn.execute(
            accounts.update().where(accounts.c.username_key == "bob").values(enabled=False)
        )
    assert create(user, b).status_code == 401
    assert counts(engine) == (2, 2, 2)


@pytest.mark.parametrize("key", [None, "short", "x" * 129, "x" * 15 + "\t", "x" * 15 + "\n"])
def test_pc04_bad_idempotency_key(db, key):
    engine, _ = db
    c, h = signed_in(engine)
    assert create(c, h, key=key).status_code == 400
    assert counts(engine) == (0, 0, 0)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"name": " "},
        {"name": "x" * 201},
        {"name": "Research", "owner_id": "forged"},
        {"name": "Research", "description": "x" * 10001},
        {"name": "Research", "research_scope": "x" * 10001},
        {"name": "Research", "description": None},
        {"name": "Research", "research_scope": None},
        {"name": 3},
        {"name": "Research", "status": "active"},
    ],
)
def test_pc04_bad_body_or_missing_csrf_no_effect(db, body):
    engine, _ = db
    c, h = signed_in(engine)
    assert create(c, h, body).status_code == 422
    assert create(c, {}).status_code == 403
    assert counts(engine) == (0, 0, 0)


def test_pc05_canonical_defaults_current_request_id_and_csrf(db):
    engine, _ = db
    c, h = signed_in(engine)
    first = create(c, h)
    second = create(c, csrf(c), {"research_scope": "", "description": "", "name": "Research"})
    assert first.json()["data"] == second.json()["data"]
    assert first.json()["meta"]["request_id"] != second.json()["meta"]["request_id"]
    assert counts(engine) == (1, 1, 1)


@pytest.mark.parametrize(
    "offset",
    [
        timedelta(hours=12),
        timedelta(hours=24) - timedelta(microseconds=1),
        timedelta(hours=24) + timedelta(microseconds=1),
    ],
)
def test_pc06_retention_real_persistence_at_independent_times(db, offset):
    engine, _ = db
    service, token, ch = service_subject(engine)
    t0 = datetime.now(UTC)
    now = [t0]
    service.clock = lambda: now[0]
    first, expires = service.create(token, ch, KEY, DATA)
    with engine.connect() as conn:
        record = conn.execute(sa.select(commands)).mappings().one()
        assert record["accepted_at"] == t0 and record["expires_at"] == expires
    assert expires >= t0 + timedelta(hours=24)
    now[0] = t0 + offset
    assert now[0] < expires
    second, current_expires = service.create(token, ch, KEY, DATA)
    assert str(first["id"]) == second["id"] and current_expires == expires
    from rpb.modules.account_config.application.ports import AccountError

    with pytest.raises(AccountError) as error:
        service.create(token, ch, KEY, DATA | {"name": "Other"})
    assert error.value.code == "STATE_IDEMPOTENCY_CONFLICT"
    assert counts(engine) == (1, 1, 1)


def test_pc06_http_expiry_matches_durable_receipt(db):
    engine, _ = db
    c, h = signed_in(engine)
    for response in (create(c, h), create(c, h)):
        value = response.json()["meta"]["idempotency_expires_at"]
        assert value.endswith("Z")
        with engine.connect() as conn:
            row = conn.execute(sa.select(commands)).mappings().one()
            assert datetime.fromisoformat(value) == row["expires_at"]
            assert row["expires_at"] >= row["accepted_at"] + timedelta(hours=24)


def test_pc07_migration_metadata_and_populated_downgrade(db):
    engine, cfg = db
    c, h = signed_in(engine)
    create(c, h)
    with pytest.raises(RuntimeError, match="contains data"):
        migrate(engine, cfg, "downgrade", "0003_auth_sessions")
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
    assert counts(engine) == (1, 1, 1)
    migrate(engine, cfg, "upgrade", "head")
    assert counts(engine) == (1, 1, 1)


def test_pc08_current_visibility_before_replay(db):
    engine, _ = db
    c, h = signed_in(engine)
    first = create(c, h)
    with engine.begin() as conn:
        conn.execute(projects.update().values(status="archived"))
    assert c.get(first.headers["location"]).json()["data"]["status"] == "archived"
    assert create(c, h).json()["data"] == first.json()["data"]
    with engine.begin() as conn:
        conn.execute(projects.update().values(status="deleted"))
    assert create(c, h).status_code == 404
    assert c.get(first.headers["location"]).status_code == 404
    assert c.get(f"/api/v1/projects/{uuid4()}").status_code == 404
    assert counts(engine) == (1, 1, 1)


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "actor_id",
        "operation",
        "scope",
        "key",
        "fingerprint",
        "schema_version",
        "project_id",
        "result",
        "accepted_at",
        "expires_at",
    ],
)
def test_pc07_receipt_required_fields_and_rollback(db, field):
    from sqlalchemy.exc import IntegrityError

    engine, _ = db
    c, h = signed_in(engine)
    create(c, h)
    with engine.connect() as conn:
        before = conn.execute(sa.select(commands)).one()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(commands.update().values({field: None}))
    with engine.connect() as conn:
        assert conn.execute(sa.select(commands)).one() == before


@pytest.mark.parametrize(
    "delta",
    [
        {"operation": "Other"},
        {"scope": "Other"},
        {"key": "short"},
        {"key": "a" * 16 + "\n"},
        {"fingerprint": "a"},
        {"result": {}},
        {"result": {"id": None}},
        {"result": {"id": str(uuid4())}},
    ],
)
def test_pc07_receipt_domain_constraints(db, delta):
    from sqlalchemy.exc import IntegrityError

    engine, _ = db
    c, h = signed_in(engine)
    create(c, h)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(commands.update().values(delta))
    assert counts(engine) == (1, 1, 1)


def test_pc07_retention_owner_fk_and_unique_key(db):
    from sqlalchemy.exc import IntegrityError

    engine, _ = db
    c, h = signed_in(engine)
    create(c, h)
    other, _ = signed_in(engine, "Bob")
    with engine.connect() as conn:
        row = dict(conn.execute(sa.select(commands)).mappings().one())
        other_id = conn.scalar(sa.select(accounts.c.id).where(accounts.c.username_key == "bob"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(commands.insert().values(row | {"id": uuid4()}))
    for change in [
        {"expires_at": row["accepted_at"] + timedelta(hours=23)},
        {"actor_id": other_id},
        {"project_id": uuid4()},
    ]:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(commands.update().values(change))
    assert counts(engine) == (1, 1, 1)


def test_pc07_upgrade_failure_restores_previous_schema_and_data(db):
    engine, cfg = db
    c, h = signed_in(engine)
    # Existing identities survive this migration, and metadata registration is not create_all.
    migrate(engine, cfg, "downgrade", "0003_auth_sessions")

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE project_create_commands" in statement:
            raise RuntimeError("injected command migration failure")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            migrate(engine, cfg, "upgrade", "head")
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    with engine.connect() as conn:
        assert not sa.inspect(conn).has_table("project_create_commands")
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0003_auth_sessions"
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1
        assert "uq_projects_id_owner" not in {
            c["name"] for c in sa.inspect(conn).get_unique_constraints("projects")
        }
    migrate(engine, cfg, "upgrade", "head")
    assert create(c, h).status_code == 201


def test_pc03_storage_failure_before_acceptance(db):
    engine, _ = db
    c, h = signed_in(engine)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "pg_advisory_xact_lock" in statement:
            raise RuntimeError("storage unavailable")

    sa.event.listen(engine, "before_cursor_execute", fail)
    try:
        r = create(c, h)
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail)
    assert r.status_code == 500 and r.json()["error"]["code"] == "STORAGE_INTERNAL_FAILURE"
    assert counts(engine) == (0, 0, 0)


def test_pc07_command_writer_blocks_downgrade(db):
    from alembic import command

    engine, cfg = db
    service, token, ch = service_subject(engine)
    inserted, release, pids = Event(), Event(), []

    def hold(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO project_create_commands"):
            pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
            inserted.set()
            assert release.wait(8)

    def down():
        with engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL lock_timeout='8s'"))
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "0003_auth_sessions")

    sa.event.listen(engine, "after_cursor_execute", hold)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(service.create, token, ch, KEY, DATA)
            try:
                assert inserted.wait(5)
                downgrade = pool.submit(down)
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
                        pytest.fail("command writer/downgrade interleaving absent")
                release.set()
                writer.result(timeout=10)
                with pytest.raises(RuntimeError, match="contains data"):
                    downgrade.result(timeout=10)
            finally:
                release.set()
    finally:
        sa.event.remove(engine, "after_cursor_execute", hold)
    assert counts(engine) == (1, 1, 1)


def test_pc07_unknown_persisted_payload_version_refuses_without_rewrite(db):
    engine, _ = db
    c, h = signed_in(engine)
    r = create(c, h)
    with engine.begin() as conn:
        conn.execute(commands.update().values(schema_version=2))
        before = conn.execute(sa.select(commands)).one()
    assert create(c, h).status_code == 500
    assert c.get(r.headers["location"]).status_code == 200
    with engine.connect() as conn:
        assert conn.execute(sa.select(commands)).one() == before
    assert counts(engine) == (1, 1, 1)


@pytest.mark.parametrize("key", ["x" * 16, "x" * 128])
@pytest.mark.parametrize("name", ["x", "中" * 200])
def test_pc04_exact_valid_key_boundaries(db, key, name):
    engine, _ = db
    c, h = signed_in(engine)
    r = create(
        c,
        h,
        {"name": name, "description": "x" * 10000, "research_scope": "x" * 10000},
        key=key,
    )
    assert r.status_code == 201
    assert counts(engine) == (1, 1, 1)
