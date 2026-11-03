"""MI: cross-module policy, wire and irreversible governance boundaries."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event, current_thread
from time import monotonic, sleep
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from jsonschema import Draft202012Validator
from sqlalchemy.engine import Connection
from test_admin_accounts import admin as inherited_admin
from test_admin_accounts import prepare, remove, update
from test_smtp_configuration import BASE, oauth_start, save, start
from test_smtp_configuration import mail as inherited_mail

from rpb.adapters import smtp_tables as tables
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK

admin, mail = inherited_admin, inherited_mail


def validate(name, data):
    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )
    schema = {"$ref": "#/components/schemas/" + name, "components": spec["components"]}
    Draft202012Validator(schema).validate(data)


def test_mi01_live_wire_and_no_secret_snapshot(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    validate("SMTPConfigView", a.get(BASE).json()["data"])
    response = save(a, ah, secret={"operation": "set", "value": "WIRE-PRIVATE-SECRET"})
    assert response.status_code == 200, response.text
    validate("SMTPConfigView", response.json()["data"])
    job = start(a, ah).json()["data"]
    validate("SMTPTaskView", job)
    assert worker.run_once()
    validate("SMTPTaskView", a.get(job["status_url"]).json()["data"])
    with db[0].connect() as conn:
        frozen = conn.scalar(sa.select(tables.tasks.c.input))
        assert "WIRE-PRIVATE-SECRET" not in json.dumps(frozen)
    security = a.get("/api/v1/admin/security-config").json()["data"]
    validate("SecurityView", security)


@pytest.mark.parametrize("phase", ["queued", "claim_done", "dispatch_done"])
def test_mi02_revocation_regrant_never_revives_tasks(mail, db, monkeypatch, phase):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    user = update(a, ah, user, "grant_admin").json()["data"]
    assert save(b, bh, secret={"operation": "set", "value": "SMTP-SECRET"}).status_code == 200
    job = start(b, bh).json()["data"]
    original = db[0].begin
    reached, release = Event(), Event()
    count = 0

    @contextmanager
    def bounded():
        nonlocal count
        is_worker = current_thread().name.startswith("smtp-governance")
        with original() as conn:
            yield conn
        if is_worker:
            count += 1
            if count == (1 if phase == "claim_done" else 2):
                reached.set()
                assert release.wait(10)

    monkeypatch.setattr(db[0], "begin", bounded)
    with ThreadPoolExecutor(1, thread_name_prefix="smtp-governance") as pool:
        future = pool.submit(worker.run_once) if phase != "queued" else None
        if future:
            assert reached.wait(10)
        try:
            user = update(a, ah, user, "revoke_admin").json()["data"]
            update(a, ah, user, "grant_admin")
        finally:
            release.set()
        if future:
            assert future.result(10)
    if phase == "queued":
        assert not worker.run_once()
    view = a.get(job["status_url"]).json()["data"]
    assert view["execution_status"] == "failed"
    assert view["error"]["code"] == "PERMISSION_RESOURCE_UNAVAILABLE"
    assert a.get(BASE).json()["data"]["config"]["connection_status"] == "untested"
    assert len(smtp.calls) == (1 if phase == "dispatch_done" else 0)


def test_mi03_preview_binds_new_oauth_and_regrant_cannot_replay(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    user = update(a, ah, user, "grant_admin").json()["data"]
    assert (
        save(
            b,
            bh,
            provider="gmail",
            server="smtp.gmail.com",
            auth_type="token",
            oauth={
                "client_id": "client",
                "tenant": None,
                "client_secret": {"operation": "set", "value": "CLIENT"},
            },
        ).status_code
        == 200
    )
    preview = prepare(a, ah, user, "revoke_admin")
    reply = oauth_start(b, bh)
    assert reply.status_code == 200
    validate("SMTPOAuthLink", reply.json()["data"])
    query = parse_qs(urlsplit(reply.json()["data"]["authorization_url"]).query)
    stale = a.patch(
        "/api/v1/admin/users/" + user["id"], headers=ah, json={"action": "revoke_admin", **preview}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STATE_CONFIRMATION_STALE"
    user = update(a, ah, user, "revoke_admin").json()["data"]
    user = update(a, ah, user, "grant_admin").json()["data"]
    response = b.get(
        BASE + "/oauth/callback",
        params={"state": query["state"][0], "code": "CODE"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/workspace?smtp_oauth=failed"
    assert not oauth.calls
    user = update(a, ah, user, "revoke_admin").json()["data"]
    assert remove(a, ah, user, prepare(a, ah, user, "delete")).status_code == 200
    assert a.get(BASE).json()["data"]["configured"]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(tables.audit)) >= 2


def test_mi04_smtp_audit_failure_and_downgrade_preserve_committed_config(mail, db, monkeypatch):
    a, ah, *rest = mail
    row = save(a, ah, secret={"operation": "set", "value": "ORIGINAL"}).json()["data"]
    original = Connection.execute

    def execute(conn, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and statement.table.name == "smtp_audit":
            raise RuntimeError("injected audit failure")
        return original(conn, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", execute)
        failed = save(
            a,
            ah,
            sender_email="new@example.invalid",
            secret={"operation": "set", "value": "CHANGED"},
        )
        assert failed.status_code == 500
    assert a.get(BASE).json()["data"] == row
    with pytest.raises(RuntimeError), db[0].begin() as conn:
        db[1].attributes["connection"] = conn
        command.downgrade(db[1], "0011_system_sources")
    with db[0].connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0019_run_temporary_cleanup"
        )
    assert a.get(BASE).json()["data"] == row


def test_mi05_two_admins_concurrent_revision_and_duplicate_test(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    update(a, ah, user, "grant_admin")
    row = save(a, ah, secret={"operation": "set", "value": "CONCURRENT"}).json()["data"]
    body = {
        k: v
        for k, v in row["config"].items()
        if k not in {"secret", "oauth_status", "connection_status", "last_test_at"}
    }
    entered = [Event(), Event()]

    def write(client, headers, suffix, index):
        entered[index].set()
        return client.put(
            BASE,
            headers=headers,
            json={
                **body,
                "expected_revision": row["revision"],
                "sender_email": suffix + "@example.invalid",
            },
        )

    with db[0].begin() as blocker:
        blocker.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )
        pool = ThreadPoolExecutor(2)
        futures = [pool.submit(write, a, ah, "first", 0), pool.submit(write, b, bh, "second", 1)]
        assert all(e.wait(5) for e in entered)
        deadline = monotonic() + 5
        while True:
            with db[0].connect() as observer:
                count_waiting = observer.scalar(
                    sa.text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND wait_event='advisory'"
                    )
                )
            if count_waiting >= 2:
                break
            assert monotonic() < deadline
            sleep(0.01)
        # Both commands are blocked at the actual database authorization lock.
    try:
        responses = [f.result(10) for f in futures]
    finally:
        pool.shutdown()
    assert sorted(r.status_code for r in responses) == [200, 412]
    key = str(uuid4())
    with ThreadPoolExecutor(2) as pool:
        with db[0].begin() as blocker:
            blocker.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            futures = [pool.submit(start, a, ah, key) for _ in range(2)]
            deadline = monotonic() + 5
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
                assert monotonic() < deadline
                sleep(0.01)
        results = [future.result(10) for future in futures]
    assert all(r.status_code == 202 for r in results)
    assert results[0].json()["data"]["task_id"] == results[1].json()["data"]["task_id"]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(tables.tasks)) == 1
