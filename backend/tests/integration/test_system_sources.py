"""SS: approved Provider precedence, private multi-source APIs and platform governance."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
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
from test_source_configuration import FakeSource
from test_source_configuration import create as private_create
from test_source_configuration import patch as private_patch

from rpb.adapters.auth import AccountStore
from rpb.adapters.source_resolution import SourceResolver
from rpb.adapters.source_worker import SourceWorker
from rpb.adapters.sources import SourceStore
from rpb.adapters.system_source_tables import audit, configs, tasks
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.domain.sources import PROVIDERS

admin = inherited_admin
BASE = "/api/v1/admin/data-source-configs"


def create(c, h, key=None, **values):
    return c.post(
        BASE,
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={
            "name": "Shared",
            "provider": "arxiv",
            "base_url": PROVIDERS["arxiv"]["url"],
            "access_mode": "anonymous",
            **values,
        },
    )


def patch(c, h, row, **values):
    return c.patch(
        BASE + "/" + row["id"], headers=h, json={"expected_revision": row["revision"], **values}
    )


def start(c, h, row, key=None):
    return c.post(
        BASE + "/" + row["id"] + "/test",
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={},
    )


@pytest.fixture
def system(admin, db):
    a, ah, b, bh, root, user = admin
    provider = FakeSource()
    worker = SourceWorker(
        SourceStore(AccountStore(db[0]), a.app.state.test_key, system=True), provider
    )
    resolver = SourceResolver(SourceStore(AccountStore(db[0]), a.app.state.test_key))
    return a, ah, b, bh, root, user, worker, provider, resolver


def resolve(resolver, client, policy=None):
    return resolver.resolve(client.cookies.get("rpb_session"), policy)


def test_ss01_scope_secret_contract_and_audit(system, db):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    private = private_create(a, ah).json()["data"]
    response = create(
        a,
        ah,
        provider="ads",
        base_url=PROVIDERS["ads"]["url"],
        access_mode="api_key",
        secret={"operation": "set", "value": "SYS-KEY"},
    )
    assert response.status_code == 201, response.text
    row = response.json()["data"]
    assert response.headers["Location"] == BASE + "/" + row["id"]
    assert "SYS-KEY" not in response.text and not provider.calls
    assert create(b, bh).status_code == 404 and b.get(BASE).status_code == 404
    assert a.get(BASE + "/" + private["id"]).status_code == 404
    assert b.get("/api/v1/me/data-source-configs/" + row["id"]).status_code == 404
    assert a.get(BASE, headers={"X-Expected-Actor": user["id"]}).status_code == 401
    assert create(a, {"Origin": "https://wrong.invalid"}).status_code == 403
    with db[0].connect() as conn:
        stored = conn.execute(sa.select(configs)).mappings().one()
        assert Fernet(a.app.state.test_key).decrypt(stored["secret_ciphertext"]) == b"SYS-KEY"
        fact = conn.execute(sa.select(audit)).mappings().one()
        assert (
            fact["owner_id"] == UUID(root["id"])
            and fact["config_type"] == "system_source"
            and fact["result"] == "succeeded"
        )
    job = start(a, ah, row).json()["data"]
    assert b.get(job["status_url"]).status_code == 404
    schemas = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )["components"]["schemas"]
    Draft202012Validator(
        {"$ref": "#/components/schemas/SystemSourceTaskView", "components": {"schemas": schemas}}
    ).validate(job)
    assert worker.run_once() and provider.calls[0][1] == "SYS-KEY"
    assert "SYS-KEY" not in a.get(job["events_url"]).text
    assert "SYS-KEY" not in json.dumps(resolve(resolver, b))


def test_ss02_crud_revision_keys_pagination_and_duplicates(system):
    a, ah, *rest = system
    key = str(uuid4())
    row = create(a, ah, key=key).json()["data"]
    assert create(a, ah, key=key).json()["data"] == row
    assert create(a, ah, key=key, name="other").status_code == 409
    assert create(a, ah, provider="unknown").status_code == 422
    assert create(a, ah, rate_limit_per_minute=True).status_code == 422
    assert (
        a.post(
            BASE,
            headers={**ah, "Idempotency-Key": str(uuid4()), "Content-Type": "application/json"},
            content='{"name":"a","name":"b"}',
        ).status_code
        == 422
    )
    assert a.patch(BASE + "/" + row["id"], headers=ah, json={"name": "new"}).status_code == 428
    saved = patch(a, ah, row, enabled=False, secret={"operation": "set", "value": "KEY"}).json()[
        "data"
    ]
    assert not saved["enabled"] and saved["secret"]["configured"]
    assert patch(a, ah, row, name="stale").status_code == 412
    saved = patch(a, ah, saved, secret={"operation": "clear"}).json()["data"]
    assert not saved["secret"]["configured"]
    another = create(a, ah).json()["data"]
    page = a.get(BASE, params={"page_size": 1}).json()
    assert page["data"]["items"][0]["id"] == another["id"] and page["meta"]["has_more"]
    assert (
        a.get(BASE, params={"cursor": page["meta"]["next_cursor"]}).json()["data"]["items"][0]["id"]
        == row["id"]
    )
    assert (
        a.delete(
            BASE + "/" + row["id"],
            headers={**ah, "Content-Type": "application/json"},
            params={"expected_revision": saved["revision"]},
        ).status_code
        == 204
    )
    assert a.get(BASE + "/" + row["id"]).status_code == 404


def test_ss03_precedence_multiple_instances_disabled_deleted_and_selected(system):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    arxiv = create(a, ah).json()["data"]
    alex = create(a, ah, provider="openalex", base_url=PROVIDERS["openalex"]["url"]).json()["data"]
    initial = resolve(resolver, b)
    assert {x["config_id"] for x in initial["sources"]} == {arxiv["id"], alex["id"]}
    selected = {"mode": "selected", "source_refs": [{"source": "system", "config_id": arxiv["id"]}]}
    frozen = copy.deepcopy(resolve(resolver, b, selected))
    personal = private_create(b, bh).json()["data"]
    second = private_create(b, bh, name="Second endpoint").json()["data"]
    current = resolve(resolver, b)
    assert {x["config_id"] for x in current["sources"]} == {
        personal["id"],
        second["id"],
        alex["id"],
    }
    with pytest.raises(AccountError) as error:
        resolve(resolver, b, selected)
    assert error.value.code == "CONFIG_CONNECTION_FAILED"
    personal = private_patch(b, bh, personal, enabled=False).json()["data"]
    current = resolve(resolver, b)
    assert {x["config_id"] for x in current["sources"]} == {second["id"], alex["id"]}
    assert current["rejected"][0]["reason_code"] == "CONFIG_SOURCE_DISABLED"
    selection = {
        "mode": "selected",
        "source_refs": [{"source": "user", "config_id": personal["id"]}],
    }
    assert not resolve(resolver, b, selection)["valid"]
    mixed = resolve(
        resolver,
        b,
        {
            "mode": "selected",
            "source_refs": [
                {"source": "user", "config_id": second["id"]},
                {"source": "system", "config_id": alex["id"]},
            ],
        },
    )
    assert mixed["valid"] and {x["config_id"] for x in mixed["sources"]} == {
        second["id"],
        alex["id"],
    }
    second = private_patch(b, bh, second, enabled=False).json()["data"]
    disabled = resolve(resolver, b)
    assert {x["config_id"] for x in disabled["sources"]} == {alex["id"]}
    assert {x["config_id"] for x in disabled["rejected"]} == {personal["id"], second["id"]}
    for row in (personal, second):
        assert (
            b.delete(
                "/api/v1/me/data-source-configs/" + row["id"],
                headers={**bh, "Content-Type": "application/json"},
                params={"expected_revision": row["revision"]},
            ).status_code
            == 204
        )
    assert {x["config_id"] for x in resolve(resolver, b)["sources"]} == {arxiv["id"], alex["id"]}
    patch(a, ah, arxiv, enabled=False)
    assert frozen["sources"][0]["enabled"] is True
    assert not resolve(resolver, b, selected)["valid"]
    assert not provider.calls


@pytest.mark.parametrize("provider_name", list(PROVIDERS))
def test_ss04_personal_provider_api_configuration_independent(system, provider_name):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    mode = "anonymous" if provider_name == "arxiv" else "api_key"
    row = private_create(
        b,
        bh,
        name=provider_name,
        provider=provider_name,
        base_url=PROVIDERS[provider_name]["url"],
        access_mode=mode,
        secret={"operation": "set", "value": "PERSONAL-" + provider_name},
    ).json()["data"]
    assert row["provider"] == provider_name and row["secret"]["configured"]
    assert (
        b.get("/api/v1/me/data-source-configs/" + row["id"]).json()["data"]["base_url"]
        == PROVIDERS[provider_name]["url"]
    )
    assert a.get("/api/v1/me/data-source-configs/" + row["id"]).status_code == 404
    got = resolve(resolver, b)
    assert got["valid"] and got["sources"][0]["source"] == "user"
    assert "PERSONAL-" not in json.dumps(got) and not provider.calls


@pytest.mark.parametrize(
    "error_code", ["PROVIDER_RATE_LIMITED", "CONFIG_CONNECTION_FAILED", "CONFIG_SECRET_UNAVAILABLE"]
)
def test_ss05_failed_personal_source_never_falls_back(system, error_code):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    create(a, ah)
    row = private_create(b, bh).json()["data"]
    from test_source_configuration import start as private_start

    job = private_start(b, bh, row).json()["data"]
    private_worker = SourceWorker(resolver.store, provider)
    provider.error = error_code
    assert private_worker.run_once()
    assert b.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    result = resolve(resolver, b)
    assert not result["valid"] and not result["sources"]
    assert (
        result["rejected"][0]["source"] == "user"
        and result["rejected"][0]["reason_code"] == error_code
    )


def test_ss06_disabled_test_missing_key_and_revision_invalidation(system):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    row = create(a, ah, enabled=False).json()["data"]
    job = start(a, ah, row).json()["data"]
    assert worker.run_once()
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    assert not resolve(resolver, b)["valid"]
    row = patch(
        a,
        ah,
        row,
        provider="ads",
        base_url=PROVIDERS["ads"]["url"],
        access_mode="api_key",
        enabled=True,
    ).json()["data"]
    assert row["connection_status"] == "untested"
    assert resolve(resolver, b)["rejected"][0]["reason_code"] == "CONFIG_SECRET_UNAVAILABLE"
    job = start(a, ah, row).json()["data"]
    assert worker.run_once()
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("phase", ["queued", "running", "outbound"])
def test_ss07_revocation_regrant_and_late_results(system, phase):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    user = update(a, ah, user, "grant_admin").json()["data"]
    row = create(b, bh).json()["data"]
    job = start(b, bh, row).json()["data"]
    if phase == "running":
        provider.entered, provider.release = Event(), Event()
    if phase == "outbound":
        entered, release = Event(), Event()
        execute = provider.execute

        def blocked(*args):
            entered.set()
            assert release.wait(10)
            return execute(*args)

        provider.execute = blocked
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run_once) if phase != "queued" else None
        if phase == "running":
            assert provider.entered.wait(10)
        if phase == "outbound":
            assert entered.wait(10)
        user = update(a, ah, user, "revoke_admin").json()["data"]
        user = update(a, ah, user, "grant_admin").json()["data"]
        if phase == "running":
            provider.release.set()
        if phase == "outbound":
            release.set()
        if future:
            assert future.result(10)
    if phase == "queued":
        assert not worker.run_once()
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    assert a.get(BASE + "/" + row["id"]).json()["data"]["connection_status"] == "untested"
    assert resolve(resolver, a)["valid"]
    assert len(provider.calls) == (1 if phase == "running" else 0)


def test_ss08_creator_delete_retains_platform_and_preview_binds_jobs(system, db):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    user = update(a, ah, user, "grant_admin").json()["data"]
    row = create(b, bh).json()["data"]
    preview = prepare(a, ah, user, "revoke_admin")
    job = start(b, bh, row).json()["data"]
    stale = a.patch(
        "/api/v1/admin/users/" + user["id"], headers=ah, json={"action": "revoke_admin", **preview}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STATE_CONFIRMATION_STALE"
    assert worker.run_once()
    user = update(a, ah, user, "revoke_admin").json()["data"]
    assert remove(a, ah, user, prepare(a, ah, user, "delete")).status_code == 200
    assert a.get(BASE + "/" + row["id"]).json()["data"]["connection_status"] == "available"
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1


def test_ss09_audit_rollback_and_downgrade_refusal(system, db, monkeypatch):
    from sqlalchemy.engine import Connection

    a, ah, *_ = system
    original = Connection.execute

    def fail(conn, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and getattr(statement, "table", None) is audit:
            raise RuntimeError("injected")
        return original(conn, statement, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Connection, "execute", fail)
        assert create(a, ah).status_code == 500
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 0
    create(a, ah)
    with pytest.raises(RuntimeError, match="downgrade refused"):
        with db[0].begin() as conn:
            db[1].attributes["connection"] = conn
            command.downgrade(db[1], "0010_system_llm")
    with db[0].connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0014_construction_runs"
        )
        assert sa.inspect(conn).has_table("system_source_audit")


def test_ss10_expired_task_and_late_config_result(system, db):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    row = create(a, ah).json()["data"]
    job = start(a, ah, row).json()["data"]
    provider.entered, provider.release = Event(), Event()
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run_once)
        assert provider.entered.wait(10)
        changed = patch(a, ah, row, name="Changed").json()["data"]
        provider.release.set()
        assert future.result(10)
    assert a.get(BASE + "/" + row["id"]).json()["data"]["connection_status"] == "untested"
    job = start(a, ah, changed).json()["data"]
    with db[0].begin() as conn:
        conn.execute(
            tasks.update()
            .where(tasks.c.id == UUID(job["task_id"]))
            .values(state="running", lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert worker.run_once() and len(provider.calls) == 1
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"


def test_ss11_two_admins_parallel_revision_and_duplicate_create(system, db):
    import time

    from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK

    a, ah, b, bh, root, user, worker, provider, resolver = system
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


@pytest.mark.parametrize(
    "policy",
    [
        {"mode": []},
        {"mode": "selected", "source_refs": [{"source": [], "config_id": "x"}]},
        {"mode": "selected", "source_refs": []},
        {"mode": "all_resolvable", "source_refs": []},
    ],
)
def test_ss12_invalid_policy_returns_validation_error(system, policy):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    with pytest.raises(AccountError) as error:
        resolve(resolver, b, policy)
    assert error.value.code == "VALIDATION_FIELD_INVALID" and error.value.status == 422
    assert not provider.calls


def test_ss13_foreign_selection_and_actor_mismatch_are_rejected(system):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    row = private_create(a, ah).json()["data"]
    with pytest.raises(AccountError) as error:
        resolve(
            resolver,
            b,
            {"mode": "selected", "source_refs": [{"source": "user", "config_id": row["id"]}]},
        )
    assert error.value.code == "CONFIG_CONNECTION_FAILED"
    with pytest.raises(AccountError) as error:
        resolver.resolve(b.cookies.get("rpb_session"), expected_actor=root["id"])
    assert error.value.status == 401


def test_ss14_shared_system_rate_cannot_be_bypassed_by_other_admin(system):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    update(a, ah, user, "grant_admin")
    row = create(
        a, ah, provider="openalex", base_url=PROVIDERS["openalex"]["url"], rate_limit_per_minute=1
    ).json()["data"]
    first = start(a, ah, row).json()["data"]
    assert worker.run_once()
    second = start(b, bh, row).json()["data"]
    assert worker.run_once()
    assert a.get(first["status_url"]).json()["data"]["execution_status"] == "succeeded"
    assert (
        b.get(second["status_url"] + "/result").json()["data"]["payload"]["reason_code"]
        == "PROVIDER_RATE_LIMITED"
    )
    assert len(provider.calls) == 1


def test_ss15_missing_source_has_explicit_diagnostic(system):
    a, ah, b, bh, root, user, worker, provider, resolver = system
    result = resolve(resolver, b)
    assert not result["valid"] and result["reason_code"] == "CONFIG_MISSING"
    assert result["sources"] == [] and result["rejected"] == []
    assert not provider.calls
