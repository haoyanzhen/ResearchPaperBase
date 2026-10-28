"""SC: platform policy behavior, independent of SMTP network availability."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_admin_accounts import admin as inherited_admin

from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.security import (
    DEFAULTS,
    audit,
    configs,
    diagnostics,
    read_policy,
    record_diagnostic,
)

admin = inherited_admin
BASE = "/api/v1/admin/security-config"


def save(client, headers, row, **changes):
    return client.put(
        BASE,
        headers=headers,
        json={**row["effective"], **changes, "expected_revision": row["revision"]},
    )


def test_sc01_defaults_authorization_revision_and_persistence(admin, db):
    a, ah, b, bh, root, user = admin
    row = a.get(BASE).json()["data"]
    assert row["configured"] is False and row["effective"] == DEFAULTS
    assert a.get(BASE).json()["data"] == row
    with db[0].connect() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count()).select_from(configs).where(configs.c.data.is_(None))
            )
            == 1
        )
    assert b.get(BASE).status_code == 404
    assert save(b, bh, row).status_code == 404
    assert save(a, {"Origin": "https://wrong.invalid"}, row).status_code == 403
    assert a.get(BASE, headers={"X-Expected-Actor": user["id"]}).status_code == 401
    response = save(
        a,
        ah,
        row,
        connection_timeout_seconds=7,
        connection_retry_count=2,
        config_snapshot_retention_days=4,
        diagnostic_scope="standard",
    )
    assert response.status_code == 200, response.text
    updated = response.json()["data"]
    assert updated["configured"] and updated["revision"] != row["revision"]
    assert a.get(BASE).json()["data"] == updated
    assert save(a, ah, row).status_code == 412
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1
        assert read_policy(conn)["connection_timeout_seconds"] == 7
        assert read_policy(conn)["_revision"] == updated["revision"]


@pytest.mark.parametrize(
    "change",
    [
        {"connection_timeout_seconds": 0},
        {"connection_timeout_seconds": True},
        {"connection_retry_count": 6},
        {"connection_retry_count": -1},
        {"config_snapshot_retention_days": 0},
        {"diagnostic_scope": "raw"},
        {"platform_concurrency": 4},
    ],
)
def test_sc02_invalid_input_never_changes_policy(admin, db, change):
    a, ah, *_ = admin
    row = a.get(BASE).json()["data"]
    assert save(a, ah, row, **change).status_code == 422
    assert a.get(BASE).json()["data"] == row
    assert a.put(BASE, headers=ah, json=DEFAULTS).status_code == 428
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 0


def test_sc03_audit_failure_rolls_back_policy(admin, db):
    a, ah, *_ = admin
    row = a.get(BASE).json()["data"]
    with db[0].begin() as conn:
        conn.execute(
            sa.text(
                "CREATE FUNCTION reject_security_audit() RETURNS trigger LANGUAGE "
                "plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected'; END; $$"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TRIGGER fail_security_audit BEFORE INSERT ON security_audit "
                "FOR EACH ROW EXECUTE FUNCTION reject_security_audit()"
            )
        )
    try:
        assert save(a, ah, row, connection_timeout_seconds=3).status_code == 500
        assert a.get(BASE).json()["data"] == row
    finally:
        with db[0].begin() as conn:
            conn.execute(sa.text("DROP TRIGGER fail_security_audit ON security_audit"))
            conn.execute(sa.text("DROP FUNCTION reject_security_audit()"))


def test_sc04_parallel_revision_has_one_winner(admin, db):
    a, ah, *_ = admin
    row = a.get(BASE).json()["data"]
    # Both live requests wait on the actual governance lock before either commits.
    with ThreadPoolExecutor(max_workers=2) as pool:
        with db[0].begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            first = pool.submit(save, a, ah, row, connection_timeout_seconds=8)
            second = pool.submit(save, a, ah, row, connection_timeout_seconds=9)
            deadline = monotonic() + 5
            while True:
                with db[0].connect() as observer:
                    count = observer.scalar(
                        sa.text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() "
                            "AND wait_event='advisory'"
                        )
                    )
                if count >= 2:
                    break
                assert monotonic() < deadline
                sleep(0.01)
        results = [first.result(10), second.result(10)]
    assert sorted(x.status_code for x in results) == [200, 412]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1


def test_sc05_diagnostics_whitelist_and_expiry_do_not_delete_task_data(admin, db):
    a, ah, *_ = admin
    now = datetime.now(UTC)
    with db[0].begin() as conn:
        old, recent = uuid4(), uuid4()
        conn.execute(
            diagnostics.insert(),
            [
                {
                    "id": old,
                    "task_id": uuid4(),
                    "occurred_at": now - timedelta(days=31),
                    "data": {"status": "failed"},
                },
                {
                    "id": recent,
                    "task_id": uuid4(),
                    "occurred_at": now,
                    "data": {"status": "succeeded"},
                },
            ],
        )
        record_diagnostic(
            conn,
            uuid4(),
            DEFAULTS,
            stage="secret-in-stage",
            status="failed",
            error="raw secret exception",
            elapsed_ms=1,
            attempts=1,
            protocol="secret-in-protocol",
        )
        data = conn.execute(sa.select(diagnostics)).mappings().all()
        assert old not in [x["id"] for x in data] and recent in [x["id"] for x in data]
        value = next(x["data"] for x in data if x["id"] != recent)
        assert set(value) == {"task_id", "stage", "status", "error"}
        assert value["error"] is None and value["stage"] == "test"
        record_diagnostic(
            conn,
            uuid4(),
            {**DEFAULTS, "diagnostic_scope": "standard"},
            stage="test",
            status="succeeded",
            error=None,
            elapsed_ms=42,
            attempts=2,
            protocol="http",
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(diagnostics)) == 3
        # Retention has no access to platform configuration/audit facts.
        assert conn.scalar(sa.select(sa.func.count()).select_from(configs)) == 0
    row = a.get(BASE).json()["data"]
    save(a, ah, row, config_snapshot_retention_days=1)
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == 1


@pytest.mark.parametrize(
    "kind,system,operation",
    [
        ("llm", False, "test"),
        ("llm", True, "test"),
        ("llm", False, "refresh"),
        ("llm", True, "refresh"),
        ("source", False, "test"),
        ("source", True, "test"),
    ],
)
def test_sc06_policy_applies_to_each_test_and_is_frozen_at_start(
    admin, db, kind, system, operation
):
    from threading import Event
    from uuid import UUID

    from test_llm_configuration import FakeProvider
    from test_source_configuration import FakeSource

    from rpb.adapters.auth import AccountStore
    from rpb.adapters.llm import LLMStore
    from rpb.adapters.llm_worker import LLMWorker
    from rpb.adapters.source_worker import SourceWorker
    from rpb.adapters.sources import SourceStore

    a, ah, *_ = admin
    initial = a.get(BASE).json()["data"]
    policy = save(a, ah, initial, connection_timeout_seconds=7, diagnostic_scope="standard").json()[
        "data"
    ]
    path = "/api/v1/" + ("admin/" if system else "me/")
    path += "llm-configs" if kind == "llm" else "data-source-configs"
    fields = (
        {
            "name": "Budget",
            "provider": "custom",
            "base_url": "https://example.invalid/v1",
            "timeout_seconds": 120,
            "secret": {"operation": "set", "value": "NEVER-LOG"},
        }
        if kind == "llm"
        else {
            "name": "Budget",
            "provider": "arxiv",
            "base_url": "https://export.arxiv.org/api",
            "access_mode": "anonymous",
        }
    )
    created = a.post(path, headers={**ah, "Idempotency-Key": str(uuid4())}, json=fields)
    assert created.status_code == 201, created.text
    row = created.json()["data"]
    suffix = "/models/refresh" if operation == "refresh" else "/test"
    job = a.post(
        path + "/" + row["id"] + suffix,
        headers={**ah, "Idempotency-Key": str(uuid4())},
        json={"model_id": "m"} if kind == "llm" and operation == "test" else {},
    ).json()["data"]
    account = AccountStore(db[0])
    store = (LLMStore if kind == "llm" else SourceStore)(
        account, a.app.state.test_key, system=system
    )
    provider = FakeProvider() if kind == "llm" else FakeSource()
    provider.entered, provider.release = Event(), Event()
    worker = (LLMWorker if kind == "llm" else SourceWorker)(store, provider)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker.run_once)
        assert provider.entered.wait(5)
        try:
            assert save(a, ah, policy, connection_timeout_seconds=2).status_code == 200
        finally:
            provider.release.set()
        assert future.result(10)
    assert 0 < provider.calls[0][0]["timeout_seconds"] <= 7
    assert provider.calls[0][0]["_test_policy"]["_revision"] == policy["revision"]
    assert a.get(path + "/" + row["id"]).json()["data"]["revision"] == row["revision"]
    with db[0].connect() as conn:
        task = (
            conn.execute(sa.select(store.tasks).where(store.tasks.c.id == UUID(job["task_id"])))
            .mappings()
            .one()
        )
        assert task["input"]["_test_policy"]["connection_timeout_seconds"] == 7
        assert read_policy(conn)["connection_timeout_seconds"] == 2
        diagnostic = (
            conn.execute(
                sa.select(diagnostics).where(diagnostics.c.task_id == UUID(job["task_id"]))
            )
            .mappings()
            .one()["data"]
        )
        assert diagnostic["attempts"] == 1 and diagnostic["protocol"] == "http"
        assert "NEVER-LOG" not in str(diagnostic)
        frozen = dict(task["input"])
    # Only diagnostic retention is disposable; committed task input remains unchanged.
    with db[0].begin() as conn:
        conn.execute(
            diagnostics.update().values(occurred_at=datetime.now(UTC) - timedelta(days=40))
        )
        record_diagnostic(
            conn,
            uuid4(),
            DEFAULTS,
            stage="test",
            status="succeeded",
            error=None,
            elapsed_ms=1,
            attempts=1,
            protocol="http",
        )
        assert (
            conn.execute(
                sa.select(store.tasks.c.input).where(store.tasks.c.id == UUID(job["task_id"]))
            ).scalar_one()
            == frozen
        )


def test_sc07_expired_retry_budget_persists_actual_attempt_count(admin, db, monkeypatch):
    from uuid import UUID

    from test_llm_configuration import create, start

    import rpb.adapters.security as policy_module
    from rpb.adapters.auth import AccountStore
    from rpb.adapters.llm import LLMStore
    from rpb.adapters.llm_provider import ProviderFailure
    from rpb.adapters.llm_worker import LLMWorker

    a, ah, *_ = admin
    policy = a.get(BASE).json()["data"]
    assert (
        save(
            a,
            ah,
            policy,
            connection_timeout_seconds=10,
            connection_retry_count=5,
            diagnostic_scope="standard",
        ).status_code
        == 200
    )
    row = create(a, ah).json()["data"]
    job = start(a, ah, row).json()["data"]

    class UnsubmittedFailures:
        calls = 0

        def execute(self, config, operation, model, secret, authorize):
            self.calls += 1
            raise ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=False)

    provider = UnsubmittedFailures()
    clock = iter([0, 0, 1, 11])
    monkeypatch.setattr(policy_module, "monotonic", lambda: next(clock))
    assert LLMWorker(LLMStore(AccountStore(db[0]), a.app.state.test_key), provider).run_once()
    assert provider.calls == 2
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    with db[0].connect() as conn:
        recorded = conn.scalar(
            sa.select(diagnostics.c.data).where(diagnostics.c.task_id == UUID(job["task_id"]))
        )
        assert recorded["attempts"] == 2 and recorded["error"] == "PROVIDER_TIMEOUT"
