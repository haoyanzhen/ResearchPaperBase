"""AU01–08: HTTP against real committed PG, including deterministic registration locks."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from test_account_storage import migrate

from rpb.adapters.account import accounts
from rpb.adapters.auth import (
    ACCOUNT_GOVERNANCE_LOCK,
    AccountStore,
    digest,
    hash_password,
    metadata,
    password_matches,
    sessions,
)
from rpb.bootstrap.business import create_business_app

ORIGIN = "http://127.0.0.1:8000"
PASSWORD = "Secret-passphrase-123"


SPEC = json.loads((Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text())


class ContractClient(TestClient):
    def request(self, *args, **kwargs):
        result = super().request(*args, **kwargs)
        path = result.request.url.path.removeprefix("/api/v1")
        method = result.request.method.lower()
        if path.startswith("/projects/"):
            path = "/projects/{project_id}"
        operation = SPEC["paths"].get(path, {}).get(method)
        if operation:
            body = result.json()
            if result.status_code >= 400:
                assert set(body) == {"error", "meta"}
                schema = {
                    "$ref": "#/components/schemas/PublicError",
                    "components": SPEC["components"],
                }
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(body["error"])
                schema = {"$ref": "#/components/schemas/Meta", "components": SPEC["components"]}
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(body["meta"])
            else:
                schema = operation["responses"][str(result.status_code)]["content"][
                    "application/json"
                ]["schema"] | {"components": SPEC["components"]}
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(body)
            assert result.headers["cache-control"] == "no-store"
        return result


def client(engine, origin=ORIGIN):
    return ContractClient(create_business_app(engine, origin), base_url=origin)


def csrf(c):
    r = c.get("/api/v1/auth/csrf")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    return {"Origin": ORIGIN, "X-CSRF-Token": r.json()["data"]["csrf_token"]}


def register(c, headers, username="Alice", email="alice@example.invalid"):
    return c.post(
        "/api/v1/auth/register",
        headers=headers,
        json={"username": username, "email": email, "password": PASSWORD},
    )


def login(c, headers, identifier="Alice", password=PASSWORD):
    return c.post(
        "/api/v1/auth/login", headers=headers, json={"identifier": identifier, "password": password}
    )


def test_au01_registration_projection_hash_and_first_admin(db):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    r = register(c, h)
    assert r.status_code == 201
    assert r.headers["location"] == "/api/v1/me"
    u = r.json()["data"]
    assert u["username"] == "Alice" and u["is_admin"] and u["enabled"]
    assert u["display_name"] is None and u["last_login_at"] is None
    assert u["created_at"].endswith("Z") and u["updated_at"].endswith("Z")
    UUID(u["id"])
    assert c.get("/api/v1/me").status_code == 401
    with engine.connect() as conn:
        row = conn.execute(sa.select(accounts)).mappings().one()
        assert row["username_key"] == "alice"
        assert PASSWORD not in row["password_hash"]
        assert password_matches(PASSWORD, row["password_hash"])
        assert not password_matches("bad", row["password_hash"])
        assert row["password_hash"] not in r.text
    r = register(c, h, "same@example.invalid", "same@example.invalid")
    assert r.status_code == 201 and not r.json()["data"]["is_admin"]
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


@pytest.mark.parametrize(
    "username,email",
    [
        (" alice ", "b@example.invalid"),
        ("b", " ALICE@example.invalid "),
        ("ALICE@example.invalid", "b@example.invalid"),
    ],
)
def test_au02_normalized_and_cross_namespace_collision(db, username, email):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    assert register(c, h).status_code == 201
    r = register(c, h, username, email)
    assert r.status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1


def test_au02_email_collides_with_username_and_unicode_casefold(db):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    assert register(c, h, "User@Example.invalid", "other@example.invalid").status_code == 201
    assert register(c, h, "second", "user@example.invalid").status_code == 409
    assert register(c, h, " Straße ", "third@example.invalid").status_code == 201
    assert register(c, h, "STRASSE", "fourth@example.invalid").status_code == 409
    assert login(c, h, "strasse").status_code == 200


@pytest.mark.parametrize("collision", [False, True])
def test_au02_concurrent_registration_serializes_first_admin_and_keys(db, collision):
    engine, _ = db
    store = AccountStore(engine)
    seeds = [store.csrf(None), store.csrf(None)]
    with engine.begin() as blocker:
        blocker.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )
        blocker_pid = blocker.scalar(sa.text("SELECT pg_backend_pid()"))
        with ThreadPoolExecutor(max_workers=2) as pool:

            def run(i):
                try:
                    token, ch = seeds[i]
                    return store.register(
                        token,
                        ch,
                        f"user{i}",
                        "same@example.invalid" if collision else f"{i}@example.invalid",
                        PASSWORD,
                    )
                except Exception as exc:
                    return exc

            futures = [pool.submit(run, i) for i in range(2)]
            try:
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        observer.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
                        count = observer.scalar(
                            sa.text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid))"
                            ),
                            {"pid": blocker_pid},
                        )
                        # One may queue behind the other, so count waiting advisory locks too.
                        waiting = observer.scalar(
                            sa.text(
                                "SELECT count(*) FROM pg_locks "
                                "WHERE locktype='advisory' AND NOT granted"
                            )
                        )
                        if count and waiting >= 2:
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("both registration requests did not reach the lock")
                blocker.commit()
                results = [f.result(timeout=10) for f in futures]
            finally:
                if blocker.in_transaction():
                    blocker.rollback()
    good = [r for r in results if isinstance(r, dict)]
    assert len(good) == (1 if collision else 2)
    assert sum(r["is_admin"] for r in good) == 1
    if collision:
        assert [r.status for r in results if not isinstance(r, dict)] == [409]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == len(good)


@pytest.mark.parametrize("identifier", [" alice ", " ALICE@EXAMPLE.INVALID "])
def test_au03_login_identifiers_and_rotation(db, identifier):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    assert register(c, h).status_code == 201
    old = c.cookies["rpb_session"]
    r = login(c, h, identifier)
    assert r.status_code == 200 and r.json()["data"]["user"]["last_login_at"]
    new = c.cookies["rpb_session"]
    assert new != old
    assert c.get("/api/v1/me").status_code == 200
    assert c.post("/api/v1/auth/logout", headers=h, json={}).status_code == 403
    stale = client(engine)
    stale.cookies.set("rpb_session", old)
    assert stale.get("/api/v1/me").status_code == 401
    with engine.connect() as conn:
        hashes = conn.execute(sa.select(sessions.c.token_hash, sessions.c.csrf_hash)).all()
        assert all(
            old not in row and new not in row and h["X-CSRF-Token"] not in row for row in hashes
        )


@pytest.mark.parametrize("identifier,password", [("missing", PASSWORD), ("Alice", "wrong")])
def test_au03_bad_credentials_no_authenticated_session(db, identifier, password):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    register(c, h)
    r = login(c, h, identifier, password)
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    with engine.connect() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(sessions)
                .where(sessions.c.account_id.is_not(None))
            )
            == 0
        )


@pytest.mark.parametrize("origin", [ORIGIN, "https://research.example.invalid"])
def test_au04_cookie_flags(db, origin):
    engine, _ = db
    c = client(engine, origin)
    r = c.get("/api/v1/auth/csrf")
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert ("Secure" in cookie) == origin.startswith("https")
    assert "Domain=" not in cookie


@pytest.mark.parametrize(
    "headers", [{}, {"Origin": "https://evil.invalid"}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}]
)
def test_au04_origin_csrf_rejection_no_account(db, headers):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    if "evil" in headers.get("Origin", ""):
        headers = headers | {"X-CSRF-Token": h["X-CSRF-Token"]}
    r = register(c, headers)
    assert r.status_code == 403
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 0


def test_au05_logout_only_current_session_and_disabled(db):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    register(c, h)
    login(c, h)
    other = client(engine)
    login(other, csrf(other))
    old = c.cookies["rpb_session"]
    assert c.post("/api/v1/auth/logout", headers=csrf(c), json={}).status_code == 200
    assert c.get("/api/v1/me").status_code == 401
    assert other.get("/api/v1/me").status_code == 200
    stale = client(engine)
    stale.cookies.set("rpb_session", old)
    assert stale.get("/api/v1/me").status_code == 401
    with engine.begin() as conn:
        conn.execute(accounts.update().values(enabled=False))
    assert other.get("/api/v1/me").status_code == 401
    fresh = client(engine)
    assert login(fresh, csrf(fresh)).status_code == 401


def test_au05_expiry_and_anonymous(db):
    engine, _ = db
    c = client(engine)
    assert c.get("/api/v1/me").status_code == 401
    h = csrf(c)
    with engine.begin() as conn:
        conn.execute(
            sessions.update().values(
                created_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
    assert register(c, h).status_code == 401
    assert csrf(c)["X-CSRF-Token"] != h["X-CSRF-Token"]


@pytest.mark.parametrize(
    "delta",
    [
        {"username": " "},
        {"username": "x" * 65},
        {"email": "invalid"},
        {"password": "short"},
        {"password": "x" * 129},
        {"is_admin": True},
        {"username": None},
    ],
)
def test_au06_validation_safe_response_and_no_effect(db, delta):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    body = {"username": "Alice", "email": "alice@example.invalid", "password": PASSWORD} | delta
    r = c.post("/api/v1/auth/register", headers=h, json=body)
    assert r.status_code == 422 and r.headers["cache-control"] == "no-store"
    assert PASSWORD not in r.text and "input" not in r.text
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 0


def test_au06_transport_limits(db):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    assert c.post("/api/v1/auth/register", headers=h, content="bad").status_code == 415
    assert (
        c.post(
            "/api/v1/auth/register",
            headers=h | {"Content-Type": "application/json"},
            content=b"x" * 65537,
        ).status_code
        == 413
    )
    assert (
        c.post(
            "/api/v1/auth/register", headers=h | {"Content-Type": "application/json"}, content="{"
        ).status_code
        == 422
    )
    assert c.get("/api/v1/auth/password-reset").status_code == 404


def test_au07_metadata_populated_downgrade_and_failure(db):
    engine, cfg = db
    AccountStore(engine).csrf(None)
    with pytest.raises(RuntimeError, match="contains data"):
        migrate(engine, cfg, "downgrade", "0002_project")
    with engine.begin() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
        conn.execute(sessions.delete())
    migrate(engine, cfg, "downgrade", "0002_project")

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE auth_sessions" in statement:
            raise RuntimeError("injected session migration failure")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            migrate(engine, cfg, "upgrade", "head")
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    with engine.connect() as conn:
        assert not sa.inspect(conn).has_table("auth_sessions")
        assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0002_project"
    migrate(engine, cfg, "upgrade", "head")
    migrate(engine, cfg, "upgrade", "head")


@pytest.mark.parametrize("operation", ["register", "login"])
def test_au08_failure_rolls_back_account_or_session_rotation(db, operation):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    if operation == "login":
        register(c, h)
    old = c.cookies["rpb_session"]

    def fail(conn, cursor, statement, parameters, context, executemany):
        if (operation == "register" and statement.startswith("INSERT INTO accounts")) or (
            operation == "login" and statement.startswith("INSERT INTO auth_sessions")
        ):
            raise RuntimeError("private SQL secret password " + PASSWORD)

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        r = register(c, h) if operation == "register" else login(c, h)
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    assert r.status_code == 500 and PASSWORD not in r.text and "SQL" not in r.text
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == (
            0 if operation == "register" else 1
        )
        assert (
            conn.scalar(sa.select(sessions.c.revoked).where(sessions.c.token_hash == digest(old)))
            is False
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 1


def test_au04_same_pre_session_only_one_login_wins(db):
    engine, _ = db
    store = AccountStore(engine)
    token, ch = store.csrf(None)
    store.register(token, ch, "alice", "alice@example.invalid", PASSWORD)
    from threading import Barrier

    barrier = Barrier(2)

    def invoke():
        barrier.wait(timeout=5)
        try:
            return store.login(token, ch, "alice", PASSWORD)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        results = [f.result(timeout=15) for f in futures]
    assert sum(isinstance(r, tuple) for r in results) == 1
    assert [r.status for r in results if not isinstance(r, tuple)] == [401]
    with engine.connect() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(sessions)
                .where(sessions.c.account_id.is_not(None), sessions.c.revoked.is_(False))
            )
            == 1
        )


@pytest.mark.parametrize(
    "field", ["token_hash", "csrf_hash", "created_at", "expires_at", "revoked"]
)
def test_au07_session_required_facts(db, field):
    from sqlalchemy.exc import IntegrityError

    engine, _ = db
    with pytest.raises(IntegrityError) as error, engine.begin() as conn:
        now = datetime.now(UTC)
        data = dict(
            token_hash="a" * 64,
            csrf_hash="b" * 64,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            revoked=False,
        )
        data[field] = None
        conn.execute(sessions.insert().values(data))
    assert error.value.orig.sqlstate == "23502"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 0


def test_au07_session_account_and_expiry_constraints(db):
    from uuid import uuid4

    from sqlalchemy.exc import IntegrityError

    engine, _ = db
    now = datetime.now(UTC)
    data = dict(
        token_hash="a" * 64,
        csrf_hash="b" * 64,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        revoked=False,
    )
    for invalid, code in [({"account_id": uuid4()}, "23503"), ({"expires_at": now}, "23514")]:
        with pytest.raises(IntegrityError) as error, engine.begin() as conn:
            conn.execute(sessions.insert().values(data | invalid))
        assert error.value.orig.sqlstate == code
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 0


@pytest.mark.parametrize("boundary", ["/api/v1/me", "/api/v1/auth/csrf"])
def test_au05_disabled_session_never_revives_after_reenable(db, boundary):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    register(c, h)
    login(c, h)
    token = c.cookies["rpb_session"]
    with engine.begin() as conn:
        conn.execute(accounts.update().values(enabled=False))
    assert c.get(boundary).status_code == 401
    with engine.begin() as conn:
        assert (
            conn.scalar(sa.select(sessions.c.revoked).where(sessions.c.token_hash == digest(token)))
            is True
        )
        conn.execute(accounts.update().values(enabled=True))
    assert c.get("/api/v1/me").status_code == 401
    assert login(c, csrf(c)).status_code == 200


def test_au04_missing_origin_and_other_session_csrf_rejected(db):
    engine, _ = db
    c, other = client(engine), client(engine)
    h, foreign = csrf(c), csrf(other)
    assert register(c, {"X-CSRF-Token": h["X-CSRF-Token"]}).status_code == 403
    assert register(c, foreign).status_code == 403
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 0


def test_au05_repeated_logout_safe_rejection(db):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    register(c, h)
    login(c, h)
    old = c.cookies["rpb_session"]
    h = csrf(c)
    assert c.post("/api/v1/auth/logout", headers=h, json={}).status_code == 200
    c.cookies.set("rpb_session", old)
    assert c.post("/api/v1/auth/logout", headers=h, json={}).status_code == 401
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.select(sessions.c.revoked).where(sessions.c.token_hash == digest(old)))
            is True
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1


def test_au07_session_writer_downgrade_race_preserves_committed_row(db):
    from threading import Event

    from alembic import command

    engine, cfg = db
    ready, pids = Event(), []
    with engine.connect() as writer:
        tx = writer.begin()
        now = datetime.now(UTC)
        writer.execute(
            sessions.insert().values(
                token_hash="a" * 64,
                csrf_hash="b" * 64,
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        pid = writer.scalar(sa.text("SELECT pg_backend_pid()"))

        def down():
            with engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL lock_timeout='8s'"))
                pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
                cfg.attributes["connection"] = conn
                ready.set()
                command.downgrade(cfg, "0002_project")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(down)
            try:
                assert ready.wait(5)
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if pid in observer.scalar(
                            sa.text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[0]}
                        ):
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("session writer/downgrade interleaving absent")
                tx.commit()
                with pytest.raises(RuntimeError, match="contains data"):
                    future.result(timeout=10)
            finally:
                if tx.is_active:
                    tx.rollback()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sessions.c.token_hash)) == "a" * 64
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0008_source_configuration"
        )


def test_au05_disabled_login_target_does_not_revoke_other_account_session(db):
    engine, _ = db
    c = client(engine)
    h = csrf(c)
    a = register(c, h).json()["data"]["id"]
    b = register(c, h, "Bob", "bob@example.invalid").json()["data"]["id"]
    login(c, h)
    token = c.cookies["rpb_session"]
    h = csrf(c)
    with engine.begin() as conn:
        conn.execute(accounts.update().where(accounts.c.id == UUID(b)).values(enabled=False))
    assert login(c, h, "Bob").status_code == 401
    assert c.get("/api/v1/me").json()["data"]["id"] == a
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.select(sessions.c.revoked).where(sessions.c.token_hash == digest(token)))
            is False
        )
