"""SC: real isolated commits and HTTP, deterministic provider calls."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_account_auth import csrf, login, register

from rpb.adapters.auth import AccountStore
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.source_tables import audit, configs, tasks
from rpb.adapters.source_worker import SourceWorker
from rpb.adapters.sources import SourceStore
from rpb.bootstrap.business import create_business_app

ORIGIN = "http://127.0.0.1:8000"
BASE = "/api/v1/me/data-source-configs"


class FakeSource:
    def __init__(self):
        self.calls = []
        self.error = None
        self.entered = None
        self.release = None

    def execute(self, config, operation, model, secret, authorize):
        with authorize():
            self.calls.append((config, secret))
        if self.entered:
            self.entered.set()
            assert self.release.wait(10)
        if self.error:
            raise ProviderFailure(self.error)
        return {}


@pytest.fixture
def source(db):
    key = Fernet.generate_key()
    c = TestClient(create_business_app(db[0], ORIGIN, key), base_url=ORIGIN)
    h = csrf(c)
    assert register(c, h, "alice", "alice@example.invalid").status_code == 201
    assert login(c, h, "alice").status_code == 200
    h = csrf(c)
    provider = FakeSource()
    store = SourceStore(AccountStore(db[0]), key)
    yield c, h, SourceWorker(store, provider), provider, key
    c.close()


def create(c, h, **fields):
    return c.post(
        BASE,
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Source",
            "provider": "arxiv",
            "base_url": "https://export.arxiv.org/api",
            "access_mode": "anonymous",
            **fields,
        },
    )


def start(c, h, row, key=None):
    return c.post(
        BASE + "/" + row["id"] + "/test",
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={},
    )


def patch(c, h, row, **fields):
    return c.patch(
        BASE + "/" + row["id"], headers=h, json={"expected_revision": row["revision"], **fields}
    )


def result(c, job):
    return c.get(job["status_url"] + "/result").json()["data"]["payload"]


def test_sc01_crud_defaults_revision_enable_and_secret(source, db):
    c, h, w, p, key = source
    r = create(c, h, name="  Name  ")
    assert r.status_code == 201, r.text
    row = r.json()["data"]
    assert row["name"] == "Name" and row["enabled"] and row["rate_limit_per_minute"] is None
    assert p.calls == [] and row["secret"] == {"configured": False, "hint": None}
    updated = patch(c, h, row, enabled=False, rate_limit_per_minute=1).json()["data"]
    assert not updated["enabled"] and updated["rate_limit_per_minute"] == 1
    assert patch(c, h, row, name="stale").status_code == 412
    reset = patch(c, h, updated, rate_limit_per_minute=None).json()["data"]
    assert reset["rate_limit_per_minute"] is None
    assert c.patch(r.headers["Location"], headers=h, json={"name": "missing"}).status_code == 428
    assert (
        c.request(
            "DELETE",
            r.headers["Location"] + "?expected_revision=" + reset["revision"],
            headers={**h, "Content-Type": "application/json"},
        ).status_code
        == 204
    )
    assert c.get(r.headers["Location"]).status_code == 404
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 4


@pytest.mark.parametrize(
    "provider,mode,secret",
    [
        ("arxiv", "anonymous", None),
        ("openalex", "anonymous", None),
        ("semantic_scholar", "anonymous", None),
        ("openalex", "api_key", "KEY"),
        ("semantic_scholar", "api_key", "KEY"),
        ("ads", "api_key", "KEY"),
    ],
)
def test_sc02_modes_persistence_tasks(source, db, provider, mode, secret):
    c, h, w, p, key = source
    row = create(
        c,
        h,
        provider=provider,
        access_mode=mode,
        **({"secret": {"operation": "set", "value": secret}} if secret else {}),
    ).json()["data"]
    job = start(c, h, row).json()["data"]
    assert job["operation_id"] == "Config.TestSource"
    assert c.get(job["status_url"]).status_code == 200
    assert w.run_once()
    out = result(c, job)
    assert out["status"] == "succeeded" and out["models"] == [] and out["access_mode"] == mode
    assert p.calls[0][1] == (secret or "")
    assert c.get(BASE + "/" + row["id"]).json()["data"]["connection_status"] == "available"
    if secret:
        with db[0].connect() as conn:
            stored = conn.execute(sa.select(configs)).mappings().one()["secret_ciphertext"]
            assert secret.encode() not in stored and Fernet(key).decrypt(stored) == secret.encode()
    events = c.get(job["events_url"])
    assert events.status_code == 200 and "event: done" in events.text
    assert "KEY" not in events.text


@pytest.mark.parametrize(
    "fields",
    [
        {"enabled": None},
        {"enabled": 1},
        {"rate_limit_per_minute": 0},
        {"rate_limit_per_minute": True},
        {"provider": "web"},
        {"provider": "ads", "access_mode": "anonymous"},
        {"base_url": "https://x.invalid/a?key=secret"},
        {"file_url": "https://x.invalid/a.pdf"},
        {"secret": {"operation": "clear", "value": "bad"}},
    ],
)
def test_sc03_rejections_no_mutation(source, db, fields):
    c, h, w, p, key = source
    assert create(c, h, **fields).status_code == 422
    assert c.get(BASE).json()["data"]["items"] == [] and not p.calls


@pytest.mark.parametrize(
    "error",
    [
        "CONFIG_SECRET_UNAVAILABLE",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_RESPONSE_INVALID",
    ],
)
def test_sc04_failure_and_duplicate_no_resend(source, error):
    c, h, w, p, key = source
    row = create(c, h).json()["data"]
    idem = str(uuid4())
    job = start(c, h, row, idem).json()["data"]
    p.error = error
    assert w.run_once()
    assert result(c, job)["reason_code"] == error
    assert start(c, h, row, idem).json()["data"]["task_id"] == job["task_id"]
    assert not w.run_once() and len(p.calls) == 1


def test_sc05_missing_key_and_anonymous_never_send_secret(source):
    c, h, w, p, key = source
    row = create(c, h, provider="ads", access_mode="api_key").json()["data"]
    job = start(c, h, row).json()["data"]
    assert w.run_once()
    assert result(c, job)["reason_code"] == "CONFIG_SECRET_UNAVAILABLE" and not p.calls
    row = create(c, h, provider="openalex", secret={"operation": "set", "value": "PRIVATE"}).json()[
        "data"
    ]
    job = start(c, h, row).json()["data"]
    assert w.run_once()
    assert p.calls[0][1] == ""


def test_sc06_queued_change_and_delete_revoke(source):
    c, h, w, p, key = source
    row = create(c, h).json()["data"]
    job = start(c, h, row).json()["data"]
    row = patch(c, h, row, name="changed").json()["data"]
    assert w.run_once()
    assert result(c, job)["status"] == "failed" and not p.calls
    job = start(c, h, row).json()["data"]
    assert (
        c.request(
            "DELETE",
            BASE + "/" + row["id"] + "?expected_revision=" + row["revision"],
            headers={**h, "Content-Type": "application/json"},
        ).status_code
        == 204
    )
    assert w.run_once()
    assert c.get(job["status_url"]).status_code == 404 and not p.calls


def test_sc07_late_result_does_not_restore_current_revision(source):
    c, h, w, p, key = source
    row = create(c, h).json()["data"]
    job = start(c, h, row).json()["data"]
    p.entered = Event()
    p.release = Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(w.run_once)
        assert p.entered.wait(10)
        changed = patch(c, h, row, name="new").json()["data"]
        p.release.set()
        assert future.result(10)
    assert c.get(BASE + "/" + row["id"]).json()["data"]["connection_status"] == "untested"
    assert result(c, job)["config_revision"] == row["revision"] != changed["revision"]


def test_sc08_scope_csrf_actor_and_restart(source, db):
    c, h, w, p, key = source
    row = create(c, h).json()["data"]
    job = start(c, h, row).json()["data"]
    assert (
        c.patch(
            BASE + "/" + row["id"], json={"expected_revision": row["revision"], "name": "bad"}
        ).status_code
        == 403
    )
    assert c.get(BASE, headers={"X-Expected-Actor": str(uuid4())}).status_code == 401
    other = TestClient(create_business_app(db[0], ORIGIN, key), base_url=ORIGIN)
    hh = csrf(other)
    assert register(other, hh, "bob", "bob@example.invalid").status_code == 201
    assert login(other, hh, "bob").status_code == 200
    for path in [
        BASE + "/" + row["id"],
        job["status_url"],
        job["status_url"] + "/result",
        job["events_url"],
    ]:
        assert other.get(path).status_code == 404
    assert other.get(BASE).json()["data"]["items"] == []
    assert SourceWorker(SourceStore(AccountStore(db[0]), key), p).run_once()
    assert result(c, job)["status"] == "succeeded"
    other.close()


def test_sc09_secret_keep_rotate_clear_and_unavailable_cipher(source, db):
    c, h, w, p, key = source
    row = create(
        c, h, provider="ads", access_mode="api_key", secret={"operation": "set", "value": "ONE"}
    ).json()["data"]
    with db[0].connect() as conn:
        old = conn.scalar(sa.select(configs.c.secret_ciphertext))
    row = patch(c, h, row, name="Renamed").json()["data"]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(configs.c.secret_ciphertext)) == old
    row = patch(c, h, row, secret={"operation": "set", "value": "TWO"}).json()["data"]
    with db[0].connect() as conn:
        assert Fernet(key).decrypt(conn.scalar(sa.select(configs.c.secret_ciphertext))) == b"TWO"
    row = patch(c, h, row, secret={"operation": "clear"}).json()["data"]
    assert not row["secret"]["configured"]
    store = SourceStore(AccountStore(db[0]), None)
    with pytest.raises(Exception) as exc:
        store._secret({"operation": "set", "value": "KEY"}, None)
    assert exc.value.code == "CONFIG_SECRET_UNAVAILABLE"


def test_sc10_concurrent_idempotency_and_conflict(source, db):
    c, h, w, p, key = source
    headers = {**h, "Idempotency-Key": str(uuid4())}
    body = {
        "name": "race",
        "provider": "arxiv",
        "access_mode": "anonymous",
        "base_url": "https://export.arxiv.org/api",
    }
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda _: c.post(BASE, headers=headers, json=body), range(2)))
    assert [r.status_code for r in results] == [201, 201]
    row = results[0].json()["data"]
    assert results[1].json()["data"] == row
    assert c.post(BASE, headers=headers, json={**body, "name": "different"}).status_code == 409
    idem = str(uuid4())
    with ThreadPoolExecutor() as pool:
        jobs = list(pool.map(lambda _: start(c, h, row, idem).json()["data"], range(2)))
    assert jobs[0]["task_id"] == jobs[1]["task_id"]
    with ThreadPoolExecutor() as pool:
        done = list(pool.map(lambda _: w.run_once(), range(2)))
    assert any(done) and len(p.calls) == 1
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(tasks)) == 1


def test_sc11_pacing_survives_worker_restart_and_configuration_recreation(source, db):
    from rpb.adapters.source_tables import dispatch_limits

    c, h, w, p, key = source
    row = create(c, h, rate_limit_per_minute=1).json()["data"]
    job = start(c, h, row).json()["data"]
    assert w.run_once()
    another = create(c, h, name="same service").json()["data"]
    job = start(c, h, another).json()["data"]
    assert SourceWorker(SourceStore(AccountStore(db[0]), key), p).run_once()
    assert result(c, job)["reason_code"] == "PROVIDER_RATE_LIMITED" and len(p.calls) == 1
    with db[0].begin() as conn:
        conn.execute(
            dispatch_limits.update().values(next_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    job = start(c, h, row).json()["data"]
    assert w.run_once()
    assert result(c, job)["status"] == "succeeded" and len(p.calls) == 2


def test_sc12_audit_failure_rolls_back_and_populated_downgrade_preserves(source, db, monkeypatch):
    from sqlalchemy.engine import Connection
    from test_account_storage import migrate

    c, h, w, p, key = source
    execute = Connection.execute

    def fail(self, statement, *a, **k):
        if getattr(statement, "table", None) is audit:
            raise RuntimeError("audit fault")
        return execute(self, statement, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(Connection, "execute", fail)
        assert create(c, h).status_code == 500
    assert c.get(BASE).json()["data"]["items"] == []
    row = create(c, h, secret={"operation": "set", "value": "KEPT"}).json()["data"]
    with pytest.raises(RuntimeError, match="Source downgrade refused"):
        migrate(db[0], db[1], "downgrade", "0007_llm_configuration")
    assert c.get(BASE + "/" + row["id"]).json()["data"] == row
    with db[0].connect() as conn:
        assert Fernet(key).decrypt(conn.scalar(sa.select(configs.c.secret_ciphertext))) == b"KEPT"


def test_sc13_pagination_and_task_schema(source):
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator

    c, h, w, p, key = source
    rows = [create(c, h, name=str(i)).json()["data"] for i in range(3)]
    first = c.get(BASE + "?page_size=2").json()
    assert first["data"]["items"] == rows[::-1][:2] and first["meta"]["has_more"]
    second = c.get(BASE, params={"page_size": 2, "cursor": first["meta"]["next_cursor"]}).json()
    assert second["data"]["items"] == rows[::-1][2:] and not second["meta"]["has_more"]
    assert c.get(BASE, params={"cursor": str(uuid4())}).status_code == 400
    job = start(c, h, rows[0]).json()["data"]
    assert w.run_once()
    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )
    schema = {"$ref": "#/components/schemas/ConnectionTest", "components": spec["components"]}
    Draft202012Validator(schema).validate(result(c, job))
    task_schema = {"$ref": "#/components/schemas/SourceTaskView", "components": spec["components"]}
    Draft202012Validator(task_schema).validate(job)
    Draft202012Validator(task_schema).validate(c.get(job["status_url"]).json()["data"])


def test_sc14_expired_lease_never_repeats_request(source, db):
    c, h, w, p, key = source
    row = create(c, h).json()["data"]
    job = start(c, h, row).json()["data"]
    with db[0].begin() as conn:
        conn.execute(
            tasks.update().values(
                state="running", lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    assert w.run_once() and not w.run_once() and not p.calls
    state = c.get(job["status_url"]).json()["data"]
    assert state["execution_status"] == "failed"


def test_sc15_revocation_before_actual_dispatch(source, db):
    from rpb.adapters.account import accounts

    c, h, w, p, key = source
    row = create(c, h).json()["data"]
    job = start(c, h, row).json()["data"]
    assert job["task_id"]
    original = p.execute

    def revoke(*args):
        with db[0].begin() as conn:
            conn.execute(accounts.update().values(enabled=False))
        return original(*args)

    p.execute = revoke
    assert w.run_once()
    assert not p.calls
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(tasks.c.state)) == "failed"


def test_sc16_private_arxiv_rate_does_not_throttle_other_account(source, db):
    from rpb.adapters.source_tables import dispatch_limits

    c, h, w, p, key = source
    row = create(c, h, rate_limit_per_minute=1).json()["data"]
    start(c, h, row)
    assert w.run_once()
    with db[0].begin() as conn:
        conn.execute(
            dispatch_limits.update()
            .where(dispatch_limits.c.scope == "arxiv-public")
            .values(next_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    other = TestClient(create_business_app(db[0], ORIGIN, key), base_url=ORIGIN)
    hh = csrf(other)
    assert register(other, hh, "other", "other@example.invalid").status_code == 201
    assert login(other, hh, "other").status_code == 200
    hh = csrf(other)
    their = create(other, hh, base_url="https://EXPORT.ARXIV.ORG:443/api").json()["data"]
    theirs = start(other, hh, their).json()["data"]
    assert w.run_once()
    assert result(other, theirs)["status"] == "succeeded"
    with db[0].begin() as conn:
        conn.execute(
            dispatch_limits.update()
            .where(dispatch_limits.c.scope == "arxiv-public")
            .values(next_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    mine = start(c, h, row).json()["data"]
    assert w.run_once()
    assert result(c, mine)["reason_code"] == "PROVIDER_RATE_LIMITED"
    assert len(p.calls) == 2
    other.close()


def test_sc17_duplicate_json_and_nonfinite_rejected(source):
    c, h, w, p, key = source
    for raw in ['{"name":"a","name":"b"}', '{"rate_limit_per_minute":NaN}']:
        response = c.post(
            BASE,
            headers={**h, "Content-Type": "application/json", "Idempotency-Key": str(uuid4())},
            content=raw,
        )
        assert response.status_code == 422
    assert c.get(BASE).json()["data"]["items"] == [] and not p.calls


def test_sc18_both_create_requests_wait_before_single_atomic_commit(source, db):
    import time

    from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
    from rpb.adapters.source_tables import commands

    c, h, w, p, key = source
    headers = {**h, "Idempotency-Key": str(uuid4())}
    body = {
        "name": "once",
        "provider": "arxiv",
        "base_url": "https://export.arxiv.org/api",
        "access_mode": "anonymous",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        with db[0].begin() as holder:
            holder.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            futures = [pool.submit(c.post, BASE, headers=headers, json=body) for _ in range(2)]
            deadline = time.monotonic() + 5
            while True:
                with db[0].connect() as observer:
                    waiting = observer.scalar(
                        sa.text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() AND wait_event='advisory'"
                        )
                    )
                if waiting >= 2:
                    break
                assert time.monotonic() < deadline, "Both requests must contend"
                time.sleep(0.01)
        results = [f.result(10) for f in futures]
    assert [r.status_code for r in results] == [201, 201] and results[0].json()["data"] == results[
        1
    ].json()["data"]
    with db[0].connect() as conn:
        for table in [configs, commands, audit]:
            assert conn.scalar(sa.select(sa.func.count()).select_from(table)) == 1
    assert not p.calls


def test_sc19_failed_task_and_http_config_errors_follow_public_schema(source, db):
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator

    c, h, w, p, key = source
    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )
    row = create(c, h, provider="ads", access_mode="api_key").json()["data"]
    job = start(c, h, row).json()["data"]
    assert w.run_once()
    view = c.get(job["status_url"]).json()["data"]
    assert view["error"]["category"] == "configuration"
    Draft202012Validator(
        {"$ref": "#/components/schemas/SourceTaskView", "components": spec["components"]}
    ).validate(view)
    no_cipher = TestClient(create_business_app(db[0], ORIGIN), base_url=ORIGIN)
    no_cipher.cookies.update(c.cookies)
    response = create(no_cipher, h, secret={"operation": "set", "value": "SECRET"})
    assert response.status_code == 409 and response.json()["error"]["category"] == "configuration"
    Draft202012Validator(
        {"$ref": "#/components/schemas/PublicError", "components": spec["components"]}
    ).validate(response.json()["error"])
    no_cipher.close()
