"""SL: system assets, safe options, current authority and committed failure paths."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from cryptography.fernet import Fernet
from jsonschema import Draft202012Validator
from test_admin_accounts import admin as inherited_admin
from test_admin_accounts import prepare, remove, update
from test_llm_configuration import FakeProvider
from test_llm_configuration import create as private_create

from rpb.adapters.auth import AccountStore
from rpb.adapters.llm import LLMStore
from rpb.adapters.llm_worker import LLMWorker
from rpb.adapters.system_llm_tables import audit, commands, configs, tasks

admin = inherited_admin
BASE = "/api/v1/admin/llm-configs"


def create(c, h, key=None, **values):
    return c.post(
        BASE,
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={
            "name": "Shared",
            "provider": "custom",
            "base_url": "https://example.invalid/v1",
            "secret": {"operation": "set", "value": "SYSTEM-SECRET"},
            **values,
        },
    )


def start(c, h, config, operation="test", key=None):
    return c.post(
        BASE + "/" + config["id"] + ("/test" if operation == "test" else "/models/refresh"),
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={"model_id": "model-a"} if operation == "test" else {},
    )


def patch(c, h, config, **values):
    return c.patch(
        BASE + "/" + config["id"],
        headers=h,
        json={"expected_revision": config["revision"], **values},
    )


@pytest.fixture
def system(admin, db):
    a, ah, b, bh, root, user = admin
    provider = FakeProvider()
    worker = LLMWorker(LLMStore(AccountStore(db[0]), a.app.state.test_key, system=True), provider)
    return a, ah, b, bh, root, user, worker, provider


def test_sl01_management_scope_and_no_secret(system, db):
    a, ah, b, bh, root, user, worker, provider = system
    personal = private_create(a, ah).json()["data"]
    response = create(a, ah)
    assert response.status_code == 201, response.text
    config = response.json()["data"]
    assert response.headers["Location"] == BASE + "/" + config["id"]
    assert provider.calls == [] and "SYSTEM-SECRET" not in response.text
    assert b.get(BASE).status_code == 404
    assert create(b, bh).status_code == 404
    assert a.get(BASE + "/" + personal["id"]).status_code == 404
    assert a.get("/api/v1/me/llm-configs/" + config["id"]).status_code == 404
    assert a.get(BASE).json()["data"]["items"] == [config]
    assert a.get(BASE, headers={"X-Expected-Actor": user["id"]}).status_code == 401
    assert create(a, {"Origin": "https://other.invalid"}).status_code == 403
    with db[0].connect() as conn:
        row = conn.execute(sa.select(configs)).mappings().one()
        assert Fernet(a.app.state.test_key).decrypt(row["secret_ciphertext"]) == b"SYSTEM-SECRET"
        record = conn.execute(sa.select(audit)).mappings().one()
        assert record["owner_id"] == UUID(root["id"])
        assert record["result"] == "succeeded" and record["config_type"] == "system_llm"
        assert "SYSTEM-SECRET" not in str(record)


def test_sl02_revision_validation_pagination_and_idempotency(system, db):
    a, ah, *rest = system
    key = str(uuid4())
    config = create(a, ah, key=key).json()["data"]
    assert create(a, ah, key=key).json()["data"] == config
    assert create(a, ah, key=key, name="changed").status_code == 409
    assert create(a, ah, parameters={"temperature": True}).status_code == 422
    assert create(a, ah, enabled=True).status_code == 422
    assert (
        a.post(
            BASE,
            headers={**ah, "Idempotency-Key": str(uuid4()), "Content-Type": "application/json"},
            content='{"name":"a","name":"b"}',
        ).status_code
        == 422
    )
    changed = patch(a, ah, config, name="renamed").json()["data"]
    assert changed["secret"]["configured"]
    assert patch(a, ah, config, name="stale").status_code == 412
    assert (
        a.patch(BASE + "/" + config["id"], headers=ah, json={"name": "no revision"}).status_code
        == 428
    )
    second = create(a, ah).json()["data"]
    page = a.get(BASE, params={"page_size": 1}).json()
    assert page["data"]["items"] == [changed] and page["meta"]["has_more"]
    assert a.get(BASE, params={"cursor": page["meta"]["next_cursor"]}).json()["data"]["items"] == [
        second
    ]
    cleared = patch(a, ah, changed, secret={"operation": "clear"}).json()["data"]
    assert not cleared["secret"]["configured"] and start(a, ah, cleared).status_code == 409
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 2


def test_sl03_discovery_selection_and_failure(system):
    a, ah, b, bh, root, user, worker, provider = system
    config = create(a, ah).json()["data"]
    assert b.get("/api/v1/me/model-selection").json()["data"]["selection"] is None
    job = start(a, ah, config, "refresh").json()["data"]
    assert b.get(job["status_url"]).status_code == 404
    assert b.get(job["events_url"]).status_code == 404
    assert worker.run_once()
    options = b.get("/api/v1/me/model-options").json()["data"]["items"]
    assert len(options) == 2 and all(
        o["source"] == "system" and not o["available"] for o in options
    )
    selection = {k: options[0][k] for k in ("source", "config_id", "model_id")}

    def select():
        revision = b.get("/api/v1/me/model-selection").json()["data"]["revision"]
        return b.put(
            "/api/v1/me/model-selection",
            headers=bh,
            json={"expected_revision": revision, "selection": selection},
        )

    assert select().status_code == 409
    job = start(a, ah, config).json()["data"]
    assert (
        job["operation_id"] == "Admin.TestSystemLLM"
        and job["target"]["type"] == "system_llm_config"
    )
    worker.run_once()
    assert select().json()["data"]["valid"]
    assert b.get("/api/v1/me/model-selection").json()["data"]["selection"] == selection
    assert provider.calls[-1][3] == "SYSTEM-SECRET"
    assert "SYSTEM-SECRET" not in b.get("/api/v1/me/model-options").text
    assert b.get(job["status_url"] + "/result").status_code == 404
    provider.error = "PROVIDER_TIMEOUT"
    start(a, ah, config)
    worker.run_once()
    current = b.get("/api/v1/me/model-selection").json()["data"]
    assert not current["valid"] and current["selection"] == selection


@pytest.mark.parametrize("change", ["parameters", "credential", "delete"])
def test_sl04_late_result_cannot_activate_and_snapshot_fixed(system, change):
    a, ah, b, bh, root, user, worker, provider = system
    config = create(a, ah).json()["data"]
    job = start(a, ah, config).json()["data"]
    provider.entered, provider.release = Event(), Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(worker.run_once)
        assert provider.entered.wait(10)
        try:
            if change == "delete":
                assert (
                    a.delete(
                        BASE + "/" + config["id"],
                        headers={**ah, "Content-Type": "application/json"},
                        params={"expected_revision": config["revision"]},
                    ).status_code
                    == 204
                )
            else:
                values = (
                    {"parameters": {"temperature": 0.2}}
                    if change == "parameters"
                    else {"secret": {"operation": "set", "value": "ROTATED"}}
                )
                assert patch(a, ah, config, **values).status_code == 200
        finally:
            provider.release.set()
        assert future.result(10)
    assert not any(
        x["available"] for x in b.get("/api/v1/me/model-options").json()["data"]["items"]
    )
    assert provider.calls[0][0]["parameters"] == config["parameters"]
    if change != "delete":
        payload = a.get(job["status_url"] + "/result").json()["data"]["payload"]
        assert payload["config_revision"] == config["revision"]


@pytest.mark.parametrize("running", [False, True])
def test_sl05_revoke_regrant_never_revives_old_task(system, db, running):
    a, ah, b, bh, root, user, worker, provider = system
    user = update(a, ah, user, "grant_admin").json()["data"]
    config = create(b, bh).json()["data"]
    job = start(b, bh, config).json()["data"]
    assert a.get(job["status_url"]).status_code == 200
    with ThreadPoolExecutor() as pool:
        if running:
            provider.entered, provider.release = Event(), Event()
            future = pool.submit(worker.run_once)
            assert provider.entered.wait(10)
        try:
            user = update(a, ah, user, "revoke_admin").json()["data"]
            assert b.get(job["status_url"]).status_code == 404
            user = update(a, ah, user, "grant_admin").json()["data"]
        finally:
            if running:
                provider.release.set()
        if running:
            assert future.result(10)
        else:
            assert not worker.run_once()
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    assert not any(
        o["available"] for o in b.get("/api/v1/me/model-options").json()["data"]["items"]
    )
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(tasks.c.state)) == "failed"


def test_sl06_delete_creator_retains_platform_success_and_audit(system, db):
    a, ah, b, bh, root, user, worker, provider = system
    user = update(a, ah, user, "grant_admin").json()["data"]
    config = create(b, bh).json()["data"]
    job = start(b, bh, config).json()["data"]
    worker.run_once()
    user = update(a, ah, user, "revoke_admin").json()["data"]
    body = prepare(a, ah, user, "delete")
    assert remove(a, ah, user, body).status_code == 200
    assert a.get(BASE + "/" + config["id"]).status_code == 200
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    assert a.get("/api/v1/me/model-options").json()["data"]["items"][0]["available"]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 1


def test_sl07_new_task_invalidates_revoke_preview(system):
    a, ah, b, bh, root, user, worker, provider = system
    user = update(a, ah, user, "grant_admin").json()["data"]
    config = create(b, bh).json()["data"]
    preview = prepare(a, ah, user, "revoke_admin")
    start(b, bh, config)
    response = a.patch(
        "/api/v1/admin/users/" + user["id"], headers=ah, json={"action": "revoke_admin", **preview}
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "STATE_CONFIRMATION_STALE"
    )
    assert b.get(BASE).status_code == 200


def test_sl08_wire_system_task_and_safe_fields(system):
    a, ah, b, bh, root, user, worker, provider = system
    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )

    def valid(name, value):
        Draft202012Validator(
            {"$ref": "#/components/schemas/" + name, "components": spec["components"]}
        ).validate(value)

    config = create(a, ah).json()["data"]
    valid("LLMView", config)
    job = start(a, ah, config).json()["data"]
    valid("SystemLLMTaskView", job)
    assert job["target_location"]["read_url"] == BASE + "/" + config["id"]
    worker.run_once()
    valid("SystemLLMTaskView", a.get(job["status_url"]).json()["data"])
    valid("ConnectionResult", a.get(job["status_url"] + "/result").json()["data"])
    for item in b.get("/api/v1/me/model-options").json()["data"]["items"]:
        assert set(item) == {
            "source",
            "config_id",
            "model_id",
            "label",
            "available",
            "unavailable_reason",
        }
        valid("ModelOption", item)
    assert "SYSTEM-SECRET" not in a.get(job["events_url"]).text


def test_sl09_failed_audit_rolls_back_and_downgrade_refused(system, db, monkeypatch):
    from sqlalchemy.engine import Connection

    a, ah, *rest = system
    execute = Connection.execute

    def fail(conn, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and getattr(statement, "table", None) is audit:
            raise RuntimeError("injected audit failure")
        return execute(conn, statement, *args, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(Connection, "execute", fail)
        assert create(a, ah).status_code == 500
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 0
    create(a, ah)
    with pytest.raises(RuntimeError, match="downgrade refused"):
        with db[0].begin() as conn:
            db[1].attributes["connection"] = conn
            command.downgrade(db[1], "0009_account_governance")
    with db[0].connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0013_search_terms"
        )
        assert sa.inspect(conn).has_table("system_source_audit")
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 1


def test_sl10_same_model_sources_and_private_tasks_stay_isolated(system):
    a, ah, b, bh, root, user, worker, provider = system
    from test_llm_configuration import start as private_start

    user = update(a, ah, user, "grant_admin").json()["data"]
    private = private_create(b, bh, name="Shared").json()["data"]
    job = private_start(b, bh, private).json()["data"]
    assert a.get(job["status_url"]).status_code == 404
    private_worker = LLMWorker(LLMStore(worker.store.account, a.app.state.test_key), provider)
    private_worker.run_once()
    system_config = create(a, ah).json()["data"]
    start(a, ah, system_config)
    worker.run_once()
    options = b.get("/api/v1/me/model-options").json()["data"]["items"]
    assert len(options) == 2 and {o["source"] for o in options} == {"user", "system"}
    for option in options:
        assert option["label"].startswith("个人 / " if option["source"] == "user" else "系统 / ")
        current = b.get("/api/v1/me/model-selection").json()["data"]
        choice = {k: option[k] for k in ("source", "config_id", "model_id")}
        selected = b.put(
            "/api/v1/me/model-selection",
            headers=bh,
            json={"expected_revision": current["revision"], "selection": choice},
        )
        assert selected.status_code == 200 and selected.json()["data"]["selection"] == choice
    assert len(a.get("/api/v1/me/model-options").json()["data"]["items"]) == 1


def test_sl11_two_admins_parallel_revision_and_duplicate_create(system, db):
    import time

    from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK

    a, ah, b, bh, root, user, worker, provider = system
    update(a, ah, user, "grant_admin")

    def concurrently(first, second):
        with ThreadPoolExecutor(max_workers=2) as pool:
            with db[0].begin() as holder:
                holder.execute(
                    sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
                )
                futures = [pool.submit(first), pool.submit(second)]
                deadline = time.monotonic() + 5
                while True:
                    with db[0].connect() as observer:
                        count = observer.scalar(
                            sa.text(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE datname=current_database() AND wait_event='advisory'"
                            )
                        )
                    if count >= 2:
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
            return [f.result(10) for f in futures]

    key = str(uuid4())
    results = concurrently(lambda: create(a, ah, key=key), lambda: create(a, ah, key=key))
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json()["data"] == results[1].json()["data"]
    config = results[0].json()["data"]
    changed = concurrently(
        lambda: patch(a, ah, config, name="A"), lambda: patch(b, bh, config, name="B")
    )
    assert sorted(r.status_code for r in changed) == [200, 412]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 2
    assert provider.calls == []


def test_sl12_revoke_between_claim_and_outbound_and_expired_no_resend(system, db):
    from datetime import UTC, datetime, timedelta

    a, ah, b, bh, root, user, worker, provider = system
    user = update(a, ah, user, "grant_admin").json()["data"]
    config = create(b, bh).json()["data"]
    job = start(b, bh, config).json()["data"]
    ready, release = Event(), Event()

    class BeforeDispatch:
        def execute(self, config, operation, model, secret, authorize):
            ready.set()
            assert release.wait(10)
            return provider.execute(config, operation, model, secret, authorize)

    guarded = LLMWorker(worker.store, BeforeDispatch())
    with ThreadPoolExecutor() as pool:
        future = pool.submit(guarded.run_once)
        assert ready.wait(10)
        try:
            user = update(a, ah, user, "revoke_admin").json()["data"]
            user = update(a, ah, user, "grant_admin").json()["data"]
        finally:
            release.set()
        assert future.result(10)
    assert not provider.calls
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    expired = start(b, bh, config).json()["data"]
    with db[0].begin() as conn:
        conn.execute(
            tasks.update()
            .where(tasks.c.id == UUID(expired["task_id"]))
            .values(
                state="running",
                started_at=datetime.now(UTC),
                lease_until=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    assert worker.run_once() and not provider.calls
    assert a.get(expired["status_url"]).json()["data"]["error"]["code"] == "PROVIDER_FAILED"
