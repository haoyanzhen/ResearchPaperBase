"""AG: requirement-oriented account governance against isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.engine import Connection
from test_account_auth import ORIGIN, PASSWORD, csrf, login, register

from rpb.adapters.account import accounts
from rpb.adapters.admin_accounts import audit, cleanups, commands, previews
from rpb.adapters.auth import AccountStore, password_matches
from rpb.bootstrap.business import create_business_app

BASE = "/api/v1/admin/users"


@pytest.fixture
def admin(db):
    key = Fernet.generate_key()
    app = create_business_app(db[0], ORIGIN, key)
    app.state.test_key = key
    a, b = TestClient(app, base_url=ORIGIN), TestClient(app, base_url=ORIGIN)
    ah, bh = csrf(a), csrf(b)
    root = register(a, ah).json()["data"]
    user = register(b, bh, "Bob", "bob@example.invalid").json()["data"]
    assert login(a, ah).status_code == 200
    assert login(b, bh, "Bob").status_code == 200
    yield a, csrf(a), b, csrf(b), root, user
    a.close()
    b.close()


def prepare(a, h, user, action, **fields):
    response = a.post(
        BASE + "/" + user["id"] + "/action-preview",
        headers=h,
        json={"action": action, "expected_revision": user["revision"], **fields},
    )
    assert response.status_code == 200, response.text
    preview = response.json()["data"]
    return {
        "expected_revision": user["revision"],
        "confirmation_token": preview["confirmation_token"],
        "acknowledged_risk_ids": [r["id"] for r in preview["risks"]],
        **fields,
    }


def update(a, h, user, action, **fields):
    body = prepare(a, h, user, action, **fields)
    return a.patch(BASE + "/" + user["id"], headers=h, json={"action": action, **body})


def remove(a, h, user, body):
    return a.delete(
        BASE + "/" + user["id"], headers={**h, "Content-Type": "application/json"}, params=body
    )


def test_ag01_scope_projection_and_pagination(admin):
    a, ah, b, bh, root, user = admin
    assert b.get(BASE).status_code == 403
    assert (
        b.post(
            BASE + "/" + root["id"] + "/action-preview",
            headers=bh,
            json={
                "action": "change_email",
                "email": "x@x.invalid",
                "expected_revision": root["revision"],
            },
        ).status_code
        == 403
    )
    page = a.get(BASE, params={"page_size": 1}).json()
    assert page["data"]["items"][0]["id"] == user["id"]
    assert set(page["data"]["items"][0]) == {
        "id",
        "revision",
        "username",
        "email",
        "display_name",
        "enabled",
        "is_admin",
        "created_at",
        "updated_at",
        "last_login_at",
    }
    second = a.get(BASE, params={"page_size": 1, "cursor": page["meta"]["next_cursor"]}).json()
    assert second["data"]["items"][0]["id"] == root["id"] and not second["meta"]["has_more"]
    assert a.get(BASE, headers={"X-Expected-Actor": user["id"]}).status_code == 401
    assert a.get(BASE, params={"cursor": "missing"}).status_code == 400


def test_ag02_email_confirmation_revision_and_atomic_audit(admin, db):
    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "change_email", email="new@example.invalid")
    assert (
        a.patch(
            BASE + "/" + user["id"],
            headers=h,
            json={**body, "action": "change_email", "email": "other@example.invalid"},
        ).status_code
        == 409
    )
    assert (
        a.patch(
            BASE + "/" + user["id"],
            headers=h,
            json={**body, "action": "change_email", "acknowledged_risk_ids": []},
        ).status_code
        == 409
    )
    response = a.patch(BASE + "/" + user["id"], headers=h, json={**body, "action": "change_email"})
    assert response.status_code == 200
    changed = response.json()["data"]
    assert changed["email"] == "new@example.invalid" and changed["revision"] != user["revision"]
    assert b.get("/api/v1/me").json()["data"]["email"] == "new@example.invalid"
    assert (
        a.patch(
            BASE + "/" + user["id"], headers=h, json={**body, "action": "change_email"}
        ).status_code
        == 412
    )
    assert update(a, h, changed, "change_email", email=root["email"]).status_code == 409
    with db[0].connect() as conn:
        rows = conn.execute(sa.select(audit)).mappings().all()
        assert (
            len(rows) == 1
            and rows[0]["action"] == "change_email"
            and rows[0]["result"] == "succeeded"
        )


def test_ag03_reset_one_time_replay_and_sessions(admin, db):
    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "reset_password")
    headers = {**h, "Idempotency-Key": str(uuid4())}
    url = BASE + "/" + user["id"] + "/reset-password"
    first = a.post(url, headers=headers, json=body)
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    value = first.json()["data"]
    expires = first.json()["meta"]["idempotency_expires_at"]
    assert expires
    assert (
        a.post(url, headers=headers, json=body).json()["meta"]["idempotency_expires_at"] == expires
    )
    assert value["password_disclosed"] and len(value["new_password"]) >= 12
    replay = a.post(url, headers=headers, json=body).json()["data"]
    assert replay == {
        "reset_completed": True,
        "password_disclosed": False,
        "operation_id": value["operation_id"],
    }
    assert b.get("/api/v1/me").status_code == 401
    assert login(b, csrf(b), "Bob", PASSWORD).status_code == 401
    assert login(b, csrf(b), "Bob", value["new_password"]).status_code == 200
    with db[0].connect() as conn:
        assert password_matches(
            value["new_password"],
            conn.scalar(
                sa.select(accounts.c.password_hash).where(accounts.c.id == UUID(user["id"]))
            ),
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1
        for table in [commands, previews, audit]:
            assert value["new_password"] not in str(conn.execute(sa.select(table)).all())


def test_ag04_disable_reenable_never_resurrects_session(admin):
    a, h, b, bh, root, user = admin
    disabled = update(a, h, user, "disable").json()["data"]
    assert not disabled["enabled"] and b.get("/api/v1/me").status_code == 401
    assert b.get("/api/v1/me").json()["error"]["code"] == "AUTH_ACCOUNT_DISABLED"
    assert b.get("/api/v1/me").json()["error"]["code"] == "AUTH_ACCOUNT_DISABLED"
    assert update(a, h, disabled, "enable").status_code == 200
    assert b.get("/api/v1/me").status_code == 401
    assert login(b, csrf(b), "Bob").status_code == 200


def test_ag05_roles_concurrent_revocation_keeps_admin(admin, db):
    a, h, b, bh, root, user = admin
    granted = update(a, h, user, "grant_admin").json()["data"]
    assert b.get(BASE).status_code == 200
    one = prepare(a, h, granted, "revoke_admin")
    two = prepare(b, bh, root, "revoke_admin")
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(
                a.patch, BASE + "/" + user["id"], headers=h, json={**one, "action": "revoke_admin"}
            ),
            pool.submit(
                b.patch, BASE + "/" + root["id"], headers=bh, json={**two, "action": "revoke_admin"}
            ),
        ]
        assert sorted(f.result().status_code for f in futures) == [200, 403]
    with db[0].connect() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(accounts)
                .where(accounts.c.enabled.is_(True), accounts.c.is_admin.is_(True))
            )
            == 1
        )


@pytest.mark.parametrize("action", ["disable", "delete", "revoke_admin", "grant_admin"])
def test_ag06_cannot_expand_self_or_admin_governance(admin, action):
    a, h, b, bh, root, user = admin
    response = a.post(
        BASE + "/" + root["id"] + "/action-preview",
        headers=h,
        json={"action": action, "expected_revision": root["revision"]},
    )
    assert response.status_code == 409


def test_ag07_expiry_csrf_and_input_no_write(admin, db):
    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "disable")
    url = BASE + "/" + user["id"]
    assert a.patch(url, json={**body, "action": "disable"}).status_code == 403
    with db[0].begin() as conn:
        conn.execute(previews.update().values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert a.patch(url, headers=h, json={**body, "action": "disable"}).status_code == 409
    assert a.post(url + "/action-preview", headers=h, json={"action": "disable"}).status_code == 428
    for patch in [
        {"email": "not an email", "action": "change_email"},
        {"action": "disable", "email": "x@x.invalid"},
        {"action": "disable", "password": "LEAK"},
    ]:
        assert (
            a.post(
                url + "/action-preview",
                headers=h,
                json={"expected_revision": user["revision"], **patch},
            ).status_code
            == 422
        )
    assert b.get("/api/v1/me").json()["data"]["enabled"]


def test_ag08_audit_failure_rolls_back(admin, db, monkeypatch):
    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "disable")
    original = Connection.execute

    def fail(conn, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and getattr(statement, "table", None) is audit:
            raise RuntimeError("audit unavailable")
        return original(conn, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", fail)
        assert (
            a.patch(
                BASE + "/" + user["id"], headers=h, json={**body, "action": "disable"}
            ).status_code
            == 500
        )
    assert b.get("/api/v1/me").json()["data"]["enabled"]


def test_ag09_delete_assets_isolation_and_safe_retry(admin, db):
    a, h, b, bh, root, user = admin
    for client, headers in [(a, h), (b, bh)]:
        assert (
            client.post(
                "/api/v1/projects",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={"name": "Private"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/v1/me/data-source-configs",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={
                    "name": "Private",
                    "provider": "arxiv",
                    "base_url": "https://export.arxiv.org/api",
                    "access_mode": "anonymous",
                },
            ).status_code
            == 201
        )
    body = prepare(a, h, user, "delete")
    assert remove(a, h, user, body).status_code == 200
    assert remove(a, h, user, body).status_code == 200
    assert b.get("/api/v1/me").status_code == 401
    assert len(a.get("/api/v1/projects").json()["data"]["items"]) == 1
    assert len(a.get("/api/v1/me/data-source-configs").json()["data"]["items"]) == 1
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1
        assert conn.scalar(sa.select(cleanups.c.state)) == "completed"
        assert (
            conn.scalar(
                sa.select(sa.func.count()).select_from(audit).where(audit.c.action == "delete")
            )
            == 1
        )


def test_ag10_cleanup_failure_keeps_disabled_and_retryable(admin, db, monkeypatch):
    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "delete")
    original = Connection.execute

    def fail(conn, statement, *args, **kwargs):
        if str(statement).startswith("DELETE FROM projects"):
            raise RuntimeError("cleanup unavailable")
        return original(conn, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", fail)
        assert remove(a, h, user, body).status_code == 500
    assert b.get("/api/v1/me").status_code == 401
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(cleanups.c.state)) == "failed"
        assert (
            conn.scalar(sa.select(accounts.c.enabled).where(accounts.c.id == UUID(user["id"])))
            is False
        )
    current = next(x for x in a.get(BASE).json()["data"]["items"] if x["id"] == user["id"])
    assert (
        a.post(
            BASE + "/" + user["id"] + "/action-preview",
            headers=h,
            json={"action": "enable", "expected_revision": current["revision"]},
        ).status_code
        == 409
    )
    assert remove(a, h, user, body).status_code == 200


def test_ag11_email_username_collision_rejected(admin):
    a, h, b, bh, root, user = admin
    c = TestClient(a.app, base_url=ORIGIN)
    assert (
        register(c, csrf(c), "login@example.invalid", "different@example.invalid").status_code
        == 201
    )
    assert update(a, h, user, "change_email", email="LOGIN@example.invalid").status_code == 409
    assert b.get("/api/v1/me").json()["data"]["email"] == user["email"]
    c.close()


def test_ag12_delete_preview_cannot_expand_to_new_private_asset(admin):
    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "delete")
    response = b.post(
        "/api/v1/projects",
        headers={**bh, "Idempotency-Key": str(uuid4())},
        json={"name": "After preview"},
    )
    assert response.status_code == 201
    assert remove(a, h, user, body).status_code == 409
    assert b.get("/api/v1/me").status_code == 200
    assert len(b.get("/api/v1/projects").json()["data"]["items"]) == 1


def test_ag13_cleanup_failure_recovers_after_lost_preview(admin, db, monkeypatch):
    a, h, b, bh, root, user = admin
    original = Connection.execute

    def fail(conn, statement, *args, **kwargs):
        if str(statement).startswith("DELETE FROM projects"):
            raise RuntimeError("cleanup unavailable")
        return original(conn, statement, *args, **kwargs)

    body = prepare(a, h, user, "delete")
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", fail)
        assert remove(a, h, user, body).status_code == 500
    current = next(x for x in a.get(BASE).json()["data"]["items"] if x["id"] == user["id"])
    fresh = prepare(a, h, current, "delete")
    assert remove(a, h, current, fresh).status_code == 200
    with db[0].connect() as conn:
        assert conn.scalars(
            sa.select(audit.c.result)
            .where(audit.c.action == "delete_cleanup")
            .order_by(audit.c.occurred_at)
        ).all() == ["failed", "resumed", "completed"]


@pytest.mark.parametrize("kind", ["source", "llm"])
@pytest.mark.parametrize("inflight", [False, True])
def test_ag14_disable_enable_never_restores_old_task(admin, db, kind, inflight):
    from threading import Event

    from test_llm_configuration import FakeProvider
    from test_llm_configuration import create as create_llm
    from test_llm_configuration import start as start_llm
    from test_source_configuration import FakeSource
    from test_source_configuration import create as create_source
    from test_source_configuration import start as start_source

    from rpb.adapters.llm import LLMStore
    from rpb.adapters.llm_worker import LLMWorker
    from rpb.adapters.source_worker import SourceWorker
    from rpb.adapters.sources import SourceStore

    a, h, b, bh, root, user = admin
    key = a.app.state.test_key
    if kind == "source":
        config = create_source(b, bh).json()["data"]
        job = start_source(b, bh, config).json()["data"]
        provider = FakeSource()
        worker = SourceWorker(SourceStore(AccountStore(db[0]), key), provider)
    else:
        config = create_llm(b, bh).json()["data"]
        job = start_llm(b, bh, config).json()["data"]
        provider = FakeProvider()
        worker = LLMWorker(LLMStore(AccountStore(db[0]), key), provider)
    if inflight:
        provider.entered, provider.release = Event(), Event()
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run_once) if inflight else None
        if inflight:
            assert provider.entered.wait(10)
        disabled = update(a, h, user, "disable").json()["data"]
        assert update(a, h, disabled, "enable").status_code == 200
        if inflight:
            provider.release.set()
            assert future.result(10)
        else:
            assert not worker.run_once() and provider.calls == []
    assert login(b, csrf(b), "Bob").status_code == 200
    task = b.get(job["status_url"]).json()["data"]
    assert task["execution_status"] == "failed"
    assert task["error"]["code"] == "PERMISSION_RESOURCE_UNAVAILABLE"


def test_ag15_wire_shapes_and_public_errors(admin):
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator, FormatChecker

    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )

    def check(name, value):
        Draft202012Validator(
            {"$ref": "#/components/schemas/" + name, "components": spec["components"]},
            format_checker=FormatChecker(),
        ).validate(value)

    a, h, b, bh, root, user = admin
    response = a.post(
        BASE + "/" + user["id"] + "/action-preview",
        headers=h,
        json={"action": "delete", "expected_revision": user["revision"]},
    )
    preview = response.json()["data"]
    check("AdminAccountPreview", preview)
    assert "idempotency_expires_at" not in response.json()["meta"]
    check("PublicError", b.get(BASE).json()["error"])
    body = {
        "expected_revision": user["revision"],
        "confirmation_token": preview["confirmation_token"],
        "acknowledged_risk_ids": ["account_change"],
    }
    check("AdminAccountCommandResult", remove(a, h, user, body).json()["data"])


def test_ag16_concurrent_reset_same_key_once(admin, db):
    from time import monotonic, sleep

    from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK

    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "reset_password")
    headers = {**h, "Idempotency-Key": str(uuid4())}
    url = BASE + "/" + user["id"] + "/reset-password"
    with ThreadPoolExecutor(2) as pool:
        with db[0].begin() as lock:
            lock.execute(
                sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": ACCOUNT_GOVERNANCE_LOCK}
            )
            futures = [pool.submit(a.post, url, headers=headers, json=body) for _ in range(2)]
            deadline = monotonic() + 10
            waiting = 0
            while monotonic() < deadline:
                with db[0].connect() as observer:
                    waiting = observer.scalar(
                        sa.text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() AND wait_event='advisory'"
                        )
                    )
                if waiting >= 2:
                    break
                sleep(0.02)
            assert waiting >= 2, "both reset requests must wait before one atomic effect"
        responses = [f.result(10) for f in futures]
    assert [r.status_code for r in responses] == [200, 200]
    assert sorted(r.json()["data"]["password_disclosed"] for r in responses) == [False, True]
    assert len({r.json()["data"]["operation_id"] for r in responses}) == 1
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1


def test_ag17_delete_revokes_inflight_and_preserves_global_budget(admin, db):
    from threading import Event

    from test_source_configuration import FakeSource, create, start

    from rpb.adapters.source_tables import dispatch_limits, tasks
    from rpb.adapters.source_worker import SourceWorker
    from rpb.adapters.sources import SourceStore

    a, h, b, bh, root, user = admin
    config = create(b, bh).json()["data"]
    job = start(b, bh, config).json()["data"]
    provider = FakeSource()
    provider.entered, provider.release = Event(), Event()
    worker = SourceWorker(SourceStore(AccountStore(db[0]), a.app.state.test_key), provider)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run_once)
        assert provider.entered.wait(10)
        body = prepare(a, h, user, "delete")
        assert remove(a, h, user, body).status_code == 200
        provider.release.set()
        assert future.result(10)
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(tasks)) == 0
        assert conn.scalar(
            sa.select(dispatch_limits.c.next_at).where(dispatch_limits.c.scope == "arxiv-public")
        )
        assert (
            conn.scalar(
                sa.select(dispatch_limits.c.next_at).where(
                    dispatch_limits.c.scope == "arxiv-user:" + user["id"]
                )
            )
            is None
        )
    assert b.get(job["status_url"]).status_code == 401


def test_ag18_late_cleanup_failure_never_reverts_completed(admin, db, monkeypatch):
    from threading import Event, local

    a, h, b, bh, root, user = admin
    body = prepare(a, h, user, "delete")
    original = Connection.execute
    failed, release = Event(), Event()
    thread = local()
    claimed = Event()

    def interleave(conn, statement, *args, **kwargs):
        text = str(statement)
        if text.startswith("DELETE FROM projects") and not claimed.is_set():
            claimed.set()
            thread.failed = True
            raise RuntimeError("first cleanup fails")
        if "pg_advisory_xact_lock" in text and getattr(thread, "failed", False):
            thread.failed = False
            failed.set()
            assert release.wait(10)
        return original(conn, statement, *args, **kwargs)

    with monkeypatch.context() as patch, ThreadPoolExecutor(1) as pool:
        patch.setattr(Connection, "execute", interleave)
        earlier = pool.submit(remove, a, h, user, body)
        assert failed.wait(10), "failed cleanup must stop before recording failure"
        assert remove(a, h, user, body).status_code == 200
        release.set()
        assert earlier.result(10).status_code == 200
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(cleanups.c.state)) == "completed"
        assert conn.scalars(
            sa.select(audit.c.result).where(audit.c.action == "delete_cleanup")
        ).all() == ["completed"]


def test_ag19_populated_governance_downgrade_preserves_facts(admin, db):
    from test_account_storage import migrate

    a, h, b, bh, root, user = admin
    updated = update(a, h, user, "change_email", email="retained@example.invalid").json()["data"]
    with pytest.raises(RuntimeError, match="Account governance downgrade refused"):
        migrate(db[0], db[1], "downgrade", "0008_source_configuration")
    assert b.get("/api/v1/me").json()["data"]["revision"] == updated["revision"]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(audit.c.action)) == "change_email"
