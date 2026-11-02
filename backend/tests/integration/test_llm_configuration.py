"""LC: committed isolated PG + real HTTP boundary, deterministic fake Provider."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_account_auth import csrf, login, register

from rpb.adapters.auth import AccountStore
from rpb.adapters.llm import LLMStore
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.llm_tables import configs, tasks
from rpb.adapters.llm_worker import LLMWorker
from rpb.bootstrap.business import create_business_app

ORIGIN = "http://127.0.0.1:8000"


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.error = None
        self.entered = None
        self.release = None

    def execute(self, config, operation, model, secret, authorize):
        with authorize():
            self.calls.append((config, operation, model, secret))
        if self.entered:
            self.entered.set()
            assert self.release.wait(10)
        if self.error:
            raise ProviderFailure(self.error)
        return {
            "discovered_models": ["model-a", "model-b"] if operation == "refresh" else [],
            "tested_parameters": config["parameters"] if operation == "test" else None,
            "test_overrides": {},
        }


@pytest.fixture
def llm(db):
    engine, cfg = db
    key = Fernet.generate_key()
    c = TestClient(create_business_app(engine, ORIGIN, key), base_url=ORIGIN)
    h = csrf(c)
    assert register(c, h, "alice", "alice@example.invalid").status_code == 201
    assert login(c, h, "alice").status_code == 200
    h = csrf(c)
    provider = FakeProvider()
    worker = LLMWorker(LLMStore(AccountStore(engine), key), provider)
    yield c, h, worker, provider, key
    c.close()


def create(c, h, **fields):
    return c.post(
        "/api/v1/me/llm-configs",
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={
            "name": "Local",
            "provider": "custom",
            "base_url": "https://example.invalid/v1",
            "secret": {"operation": "set", "value": "SENSITIVE-KEY-123"},
            **fields,
        },
    )


def start(c, h, config, operation="test", key=None, model="model-a"):
    suffix = "test" if operation == "test" else "models/refresh"
    return c.post(
        f"/api/v1/me/llm-configs/{config['id']}/{suffix}",
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={"model_id": model} if operation == "test" else {},
    )


def patch(c, h, config, **values):
    return c.patch(
        "/api/v1/me/llm-configs/" + config["id"],
        headers=h,
        json={"expected_revision": config["revision"], **values},
    )


def test_lc01_private_crud_encrypted_and_partial_patch(llm, db):
    c, h, worker, provider, key = llm
    response = create(c, h, parameters={"temperature": 0, "top_p": 0.5})
    assert response.status_code == 201, response.text
    config = response.json()["data"]
    assert response.json()["meta"]["idempotency_expires_at"].endswith("Z")
    assert "SENSITIVE" not in response.text and config["secret"] == {
        "configured": True,
        "hint": None,
    }
    assert provider.calls == []
    with db[0].connect() as conn:
        row = conn.execute(sa.select(configs)).mappings().one()
        assert row["secret_ciphertext"] != b"SENSITIVE-KEY-123"
        assert Fernet(key).decrypt(row["secret_ciphertext"]) == b"SENSITIVE-KEY-123"
    assert c.get(response.headers["Location"]).json()["data"] == config
    changed = patch(c, h, config, name="new").json()["data"]
    assert (
        changed["parameters"] == config["parameters"] and changed["revision"] != config["revision"]
    )
    assert patch(c, h, config, name="stale").status_code == 412
    assert (
        c.patch(response.headers["Location"], headers=h, json={"name": "missing"}).status_code
        == 428
    )
    assert patch(c, h, changed).json()["data"] == changed
    cleared = patch(c, h, changed, secret={"operation": "clear"}).json()["data"]
    assert cleared["secret"]["configured"] is False
    assert start(c, h, cleared).status_code == 409 and provider.calls == []
    assert (
        c.delete(
            response.headers["Location"],
            headers={**h, "Content-Type": "application/json"},
            params={"expected_revision": cleared["revision"]},
        ).status_code
        == 204
    )
    assert c.get(response.headers["Location"]).status_code == 404


def test_lc02_discovery_not_available_test_then_selection_restore(llm):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    discovery = start(c, h, config, "refresh").json()["data"]
    assert c.get(discovery["status_url"] + "/result").status_code == 409
    assert worker.run_once()
    opts = c.get("/api/v1/me/model-options").json()["data"]["items"]
    assert len(opts) == 2 and not any(x["available"] for x in opts)
    selection = {k: opts[0][k] for k in ("source", "config_id", "model_id")}
    current = c.get("/api/v1/me/model-selection").json()["data"]
    assert (
        c.put(
            "/api/v1/me/model-selection",
            headers=h,
            json={"expected_revision": current["revision"], "selection": selection},
        ).status_code
        == 409
    )
    test = start(c, h, config).json()["data"]
    assert test["execution_status"] == "queued" and len(provider.calls) == 1
    assert worker.run_once()
    assert c.get(test["status_url"]).json()["data"]["execution_status"] == "succeeded"
    saved = c.put(
        "/api/v1/me/model-selection",
        headers=h,
        json={"expected_revision": current["revision"], "selection": selection},
    ).json()["data"]
    assert saved["valid"] and saved["selection"] == selection
    assert c.post("/api/v1/auth/logout", headers=h, json={}).status_code == 200
    assert login(c, csrf(c), "alice").status_code == 200
    assert c.get("/api/v1/me/model-selection").json()["data"] == saved
    h = csrf(c)
    assert patch(c, h, config, parameters={"temperature": 0}).status_code == 200
    invalid = c.get("/api/v1/me/model-selection").json()["data"]
    assert not invalid["valid"] and invalid["selection"] == selection


def test_lc03_idempotent_create_test_and_failure_no_automatic_retry(llm):
    c, h, worker, provider, _ = llm
    key = str(uuid4())
    headers = {**h, "Idempotency-Key": key}
    body = {
        "name": "A",
        "provider": "custom",
        "base_url": "https://example.invalid/v1",
        "secret": {"operation": "set", "value": "KEY"},
    }
    first = c.post("/api/v1/me/llm-configs", headers=headers, json=body)
    assert first.status_code == 201
    assert (
        c.post("/api/v1/me/llm-configs", headers=headers, json=body).json()["data"]
        == first.json()["data"]
    )
    assert (
        c.post("/api/v1/me/llm-configs", headers=headers, json={**body, "name": "B"}).status_code
        == 409
    )
    config = first.json()["data"]
    key = str(uuid4())
    job = start(c, h, config, key=key).json()["data"]
    assert start(c, h, config, key=key).json()["data"] == job
    assert start(c, h, config, key=key, model="other").status_code == 409
    provider.error = "PROVIDER_RATE_LIMITED"
    assert worker.run_once()
    assert c.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    assert start(c, h, config, key=key).json()["data"]["task_id"] == job["task_id"]
    assert not worker.run_once() and len(provider.calls) == 1
    assert (
        c.get(job["status_url"] + "/result").json()["data"]["payload"]["reason_code"]
        == "PROVIDER_RATE_LIMITED"
    )


def test_lc04_late_test_result_never_validates_new_revision(llm):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    provider.entered = Event()
    provider.release = Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(worker.run_once)
        assert provider.entered.wait(5)
        updated = patch(c, h, config, secret={"operation": "set", "value": "ROTATED"})
        assert updated.status_code == 200
        provider.release.set()
        assert future.result()
    assert c.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    assert not any(
        x["available"] for x in c.get("/api/v1/me/model-options").json()["data"]["items"]
    )
    assert provider.calls[0][3] == "SENSITIVE-KEY-123"


def test_lc05_concurrent_claim_and_expired_unknown_never_resend(llm, db):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    with ThreadPoolExecutor() as pool:
        result = list(pool.map(lambda _: worker.run_once(), range(2)))
    assert result.count(True) == 1 and len(provider.calls) == 1
    assert c.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    second = start(c, h, config).json()["data"]
    with db[0].begin() as conn:
        conn.execute(
            tasks.update()
            .where(tasks.c.id == UUID(second["task_id"]))
            .values(state="running", lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert worker.run_once()
    assert c.get(second["status_url"]).json()["data"]["error"]["code"] == "PROVIDER_FAILED"
    assert len(provider.calls) == 1


def test_lc06_task_and_config_isolation_and_auth(llm, db):
    c, h, worker, provider, key = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    other = TestClient(create_business_app(db[0], ORIGIN, key), base_url=ORIGIN)
    oh = csrf(other)
    assert register(other, oh, "bob", "bob@example.invalid").status_code == 201
    assert login(other, oh, "bob").status_code == 200
    oh = csrf(other)
    for url in [
        "/api/v1/me/llm-configs/" + config["id"],
        job["status_url"],
        job["status_url"] + "/result",
        job["events_url"],
    ]:
        assert other.get(url).status_code == 404
    assert start(other, oh, config).status_code == 404
    assert start(c, {**h, "Origin": "https://bad.invalid"}, config).status_code == 403
    assert provider.calls == []


@pytest.mark.parametrize(
    "field",
    [
        {"parameters": {"temperature": True}},
        {"parameters": {"custom_params": {"model": "other"}}},
        {"enabled": False},
        {"base_url": "https://u:p@example.invalid"},
        {"parameters": {"max_output_tokens": 0}},
        {"parameters": {"unknown": 1}},
    ],
)
def test_lc07_invalid_configuration_no_rows(llm, db, field):
    c, h, _, provider, _ = llm
    response = create(c, h, **field)
    assert response.status_code == 422, response.text
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 0
    assert provider.calls == []


def test_lc08_sse_replay_is_stable_and_does_not_dispatch(llm):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    assert worker.run_once()
    first = c.get(job["events_url"])
    assert first.status_code == 200 and first.text.count("event: done") == 1
    assert first.text == c.get(job["events_url"]).text
    assert len(provider.calls) == 1
    final = c.get(job["status_url"]).json()["data"]
    assert c.get(job["events_url"], params={"after_event_id": final["event_cursor"]}).text == ""
    assert c.get(job["events_url"], params={"after_event_id": "not-a-cursor"}).status_code == 400
    assert (
        c.get(
            job["events_url"],
            params={"after_event_id": final["event_cursor"]},
            headers={"Last-Event-ID": "other"},
        ).status_code
        == 400
    )


def test_lc09_dispatch_rechecks_deleted_config_before_any_send(llm):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    original = provider.execute
    entered, release = Event(), Event()

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    provider.execute = delayed
    with ThreadPoolExecutor() as pool:
        future = pool.submit(worker.run_once)
        assert entered.wait(5)
        assert (
            c.delete(
                "/api/v1/me/llm-configs/" + config["id"],
                headers={**h, "Content-Type": "application/json"},
                params={"expected_revision": config["revision"]},
            ).status_code
            == 204
        )
        release.set()
        assert future.result()
    assert provider.calls == []
    assert c.get(job["status_url"]).status_code == 404


def test_lc10_expired_response_never_succeeds_without_sweeper(llm, db):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    provider.entered, provider.release = Event(), Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(worker.run_once)
        assert provider.entered.wait(5)
        with db[0].begin() as conn:
            conn.execute(
                tasks.update()
                .where(tasks.c.id == UUID(job["task_id"]))
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
            )
        provider.release.set()
        assert future.result()
    assert c.get(job["status_url"]).json()["data"]["error"]["code"] == "PROVIDER_FAILED"
    assert not any(
        x["available"] for x in c.get("/api/v1/me/model-options").json()["data"]["items"]
    )
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"name":"a","name":"b"}',
        '{"parameters":{"seed":' + "1" * 5000 + "}}",
        '{"parameters":{"seed":NaN}}',
        '{"secret":null}',
    ],
)
def test_lc11_raw_json_failures_are_safe(llm, raw):
    c, h, _, provider, _ = llm
    r = c.post(
        "/api/v1/me/llm-configs",
        headers={**h, "Idempotency-Key": str(uuid4()), "Content-Type": "application/json"},
        content=raw,
    )
    assert r.status_code == 422
    assert provider.calls == [] and "SENSITIVE" not in r.text


def test_lc12_audit_and_current_test_status(llm, db):
    from rpb.adapters.llm_tables import audit

    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    start(c, h, config)
    provider.error = "PROVIDER_RATE_LIMITED"
    assert worker.run_once()
    current = c.get("/api/v1/me/llm-configs/" + config["id"]).json()["data"]
    assert current["connection_status"] == "unavailable" and current["last_test_at"]
    next_config = patch(c, h, config, secret={"operation": "clear"}).json()["data"]
    assert next_config["connection_status"] == "untested" and next_config["last_test_at"] is None
    with db[0].connect() as conn:
        records = conn.execute(sa.select(audit).order_by(audit.c.occurred_at)).mappings().all()
        assert [r["secret_operation"] for r in records] == ["set", "clear"]
        assert "SENSITIVE" not in str(records)


def test_lc13_machine_schemas_match_actual_responses_and_replay(llm):
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator, FormatChecker

    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )

    def validate(name, value):
        Draft202012Validator(
            {"$ref": "#/components/schemas/" + name, "components": spec["components"]},
            format_checker=FormatChecker(),
        ).validate(value)

    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    validate("LLMView", config)
    page = c.get("/api/v1/me/llm-configs").json()
    validate("PageMeta", page["meta"])
    assert page["data"]["items"] == [config]
    validate("SelectionView", c.get("/api/v1/me/model-selection").json()["data"])
    job = start(c, h, config).json()["data"]
    validate("LLMTaskView", job)
    provider.error = "PROVIDER_RATE_LIMITED"
    worker.run_once()
    validate("LLMTaskView", c.get(job["status_url"]).json()["data"])
    validate("ConnectionResult", c.get(job["status_url"] + "/result").json()["data"])
    for event in c.get(job["events_url"]).text.strip().split("\n\n"):
        kind = next(line[7:] for line in event.splitlines() if line.startswith("event: "))
        data = json.loads(
            next(line[6:] for line in event.splitlines() if line.startswith("data: "))
        )
        validate("DonePayload" if kind == "done" else "StatusPayload", data["payload"])


def test_lc14_pagination_and_patch_replaces_parameters(llm):
    c, h, _, _, _ = llm
    a = create(c, h, parameters={"temperature": 0, "seed": 1}).json()["data"]
    b = create(c, h, name="second").json()["data"]
    first = c.get("/api/v1/me/llm-configs?page_size=1").json()
    assert first["data"]["items"] == [a] and first["meta"]["has_more"]
    second = c.get(
        "/api/v1/me/llm-configs", params={"page_size": 1, "cursor": first["meta"]["next_cursor"]}
    ).json()
    assert second["data"]["items"] == [b] and not second["meta"]["has_more"]
    assert c.get("/api/v1/me/llm-configs?page_size=101").status_code == 422
    assert c.get("/api/v1/me/llm-configs?cursor=bogus").status_code == 400
    changed = patch(c, h, a, parameters={"top_p": 0}).json()["data"]
    assert changed["parameters"] == {"top_p": 0}
    assert patch(c, h, changed, parameters={}).json()["data"]["parameters"] == {}


def test_lc15_queued_restart_and_disabled_actor_no_external_call(llm, db):
    from rpb.adapters.account import accounts

    c, h, worker, provider, key = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    restarted = LLMWorker(LLMStore(AccountStore(db[0]), key), provider)
    assert restarted.run_once()
    assert c.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    start(c, h, config)
    with db[0].begin() as conn:
        conn.execute(accounts.update().values(enabled=False))
    assert restarted.run_once() and len(provider.calls) == 1
    assert c.get(job["status_url"]).status_code == 401


@pytest.mark.parametrize("sweep", [False, True])
def test_lc16_expired_claim_cannot_dispatch_after_preparation(llm, db, sweep):
    c, h, worker, provider, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    original = provider.execute
    entered, release = Event(), Event()

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    provider.execute = delayed
    with ThreadPoolExecutor() as pool:
        future = pool.submit(worker.run_once)
        assert entered.wait(5)
        with db[0].begin() as conn:
            conn.execute(
                tasks.update()
                .where(tasks.c.id == UUID(job["task_id"]))
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
            )
        if sweep:
            assert worker.run_once()
        release.set()
        assert future.result()
    assert provider.calls == []
    assert c.get(job["status_url"]).json()["data"]["execution_status"] == "failed"


def test_lc17_expected_actor_read_guard(llm):
    c, h, _, _, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    for path in [
        "/api/v1/me/llm-configs",
        "/api/v1/me/model-options",
        "/api/v1/me/model-selection",
        "/api/v1/me/llm-configs/" + config["id"],
        job["status_url"],
        job["events_url"],
    ]:
        r = c.get(path, headers={"X-Expected-Actor": str(uuid4())})
        assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_SESSION_INVALID"


def test_lc18_sse_account_limit_releases_and_old_cursor_expires(llm, db):
    from contextlib import ExitStack

    c, h, worker, _, _ = llm
    config = create(c, h).json()["data"]
    job = start(c, h, config).json()["data"]
    worker.run_once()
    token = c.cookies.get("rpb_session")
    with ExitStack() as stack:
        for _ in range(6):
            stack.enter_context(worker.store.event_lease(token))
        response = c.get(job["events_url"])
        assert response.status_code == 429 and response.headers["Retry-After"] == "5"
    assert c.get(job["events_url"]).status_code == 200
    with db[0].begin() as conn:
        row = (
            conn.execute(sa.select(tasks).where(tasks.c.id == UUID(job["task_id"])))
            .mappings()
            .one()
        )
        events = row["events"]
        events[0]["occurred_at"] = (
            (datetime.now(UTC) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        )
        conn.execute(tasks.update().where(tasks.c.id == row["id"]).values(events=events))
    response = c.get(job["events_url"], params={"after_event_id": events[0]["cursor"]})
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "STATE_EVENT_REPLAY_UNAVAILABLE"
    )
    assert c.get(job["status_url"]).status_code == 200


def test_lc20_populated_migration_refuses_and_preserves_secrets(llm, db):
    from test_account_storage import migrate

    c, h, _, _, key = llm
    config = create(c, h).json()["data"]
    with db[0].connect() as conn:
        ciphertext = conn.scalar(sa.select(configs.c.secret_ciphertext))
    with pytest.raises(RuntimeError, match="LLM downgrade refused"):
        migrate(db[0], db[1], "downgrade", "0006_account_profile")
    assert c.get("/api/v1/me/llm-configs/" + config["id"]).json()["data"] == config
    with db[0].connect() as conn:
        after = conn.scalar(sa.select(configs.c.secret_ciphertext))
        assert after == ciphertext and Fernet(key).decrypt(after) == b"SENSITIVE-KEY-123"
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0018_knowledge_build_views"
        )


def test_lc21_concurrent_duplicate_create_has_one_audit(llm, db):
    from rpb.adapters.llm_tables import audit, commands

    c, h, _, provider, _ = llm
    headers = {**h, "Idempotency-Key": str(uuid4())}
    body = {
        "name": "once",
        "provider": "custom",
        "base_url": "https://example.invalid",
        "secret": {"operation": "set", "value": "PRIVATE"},
    }
    import time

    from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK

    with ThreadPoolExecutor(max_workers=2) as pool:
        with db[0].begin() as holder:
            holder.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            futures = [
                pool.submit(c.post, "/api/v1/me/llm-configs", headers=headers, json=body)
                for _ in range(2)
            ]
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
                assert time.monotonic() < deadline, "Both requests must contend before release"
                time.sleep(0.01)
        results = [future.result(timeout=10) for future in futures]
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json()["data"] == results[1].json()["data"]
    with db[0].connect() as conn:
        for table in [configs, audit, commands]:
            assert conn.scalar(sa.select(sa.func.count()).select_from(table)) == 1
    assert not provider.calls


def test_lc22_audit_failure_rolls_back_configuration_and_command(llm, db):
    from rpb.adapters.llm_tables import audit, commands

    c, h, _, provider, _ = llm

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO llm_audit" in statement:
            raise RuntimeError("isolated injected audit failure")

    sa.event.listen(db[0], "before_cursor_execute", fail)
    try:
        response = create(c, h)
        assert response.status_code == 500
    finally:
        sa.event.remove(db[0], "before_cursor_execute", fail)
    with db[0].connect() as conn:
        for table in [configs, audit, commands]:
            assert conn.scalar(sa.select(sa.func.count()).select_from(table)) == 0
    assert provider.calls == [] and "SENSITIVE" not in response.text


def test_lc23_model_context_capacity_defaults_persistence_and_revision(llm):
    c, h, worker, provider, _ = llm
    initial = create(c, h).json()["data"]
    assert initial["model_context_windows"] == {}
    assert start(c, h, initial).status_code == 202
    assert worker.run_once()
    current = c.get("/api/v1/me/llm-configs/" + initial["id"]).json()["data"]
    assert current["models"][0]["context_window_tokens"] == 262144
    changed = patch(c, h, current, model_context_windows={"model-a": 524288}).json()["data"]
    assert changed["model_context_windows"] == {"model-a": 524288}
    assert changed["revision"] != current["revision"]
    assert len(provider.calls) == 1
    assert patch(c, h, current, model_context_windows={}).status_code == 412
    assert start(c, h, changed).status_code == 202
    assert worker.run_once()
    loaded = c.get("/api/v1/me/llm-configs/" + initial["id"]).json()["data"]
    assert loaded["models"][0]["context_window_tokens"] == 524288
    renamed = patch(c, h, loaded, name="same-capacity").json()["data"]
    assert renamed["model_context_windows"] == {"model-a": 524288}
    reset = patch(c, h, renamed, model_context_windows={}).json()["data"]
    assert reset["model_context_windows"] == {}
    assert len(provider.calls) == 2


def test_lc24_invalid_capacity_never_changes_config(llm):
    c, h, _, provider, _ = llm
    original = create(c, h).json()["data"]
    for bad in (None, {"model": True}, {"model": 0}, {"model": "262144"}, {"": 262144}):
        assert patch(c, h, original, model_context_windows=bad).status_code == 422
        assert c.get("/api/v1/me/llm-configs/" + original["id"]).json()["data"] == original
    assert provider.calls == []
