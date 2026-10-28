"""SM: singleton, encrypted auth, durable tests and one-use OAuth credentials."""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from test_admin_accounts import admin as inherited_admin

from rpb.adapters import smtp_tables as tables
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.smtp import SMTP_ID
from rpb.adapters.smtp_worker import SMTPWorker

admin = inherited_admin
BASE = "/api/v1/admin/smtp-config"


class FakeSMTP:
    def __init__(self):
        self.calls = []
        self.error = None

    def execute(self, config, secret, timeout):
        self.calls.append((config, secret, timeout))
        if self.error:
            raise self.error
        return {"authenticated": config["auth_type"] != "none"}


class FakeOAuth:
    def __init__(self):
        self.calls = []
        self.error = None

    def exchange(self, config, client_secret, fields, timeout=30):
        self.calls.append((config, client_secret, fields))
        if self.error:
            raise self.error
        return {
            "access_token": "ACCESS-SECRET",
            "refresh_token": "REFRESH-SECRET-" + str(len(self.calls)),
            "token_type": "Bearer",
            "expires_in": 3600,
        }


def save(a, h, **changes):
    row = a.get(BASE).json()["data"]
    config = row["config"] or {
        "sender_email": "sender@example.invalid",
        "provider": "custom",
        "server": "smtp.example.invalid",
        "port": 587,
        "encryption": "starttls",
        "auth_type": "password",
        "username": "sender@example.invalid",
    }
    config = {
        k: v
        for k, v in config.items()
        if k not in {"secret", "oauth_status", "connection_status", "last_test_at"}
    }
    if config.get("oauth"):
        config["oauth"] = {k: v for k, v in config["oauth"].items() if k != "client_secret"}
    return a.put(BASE, headers=h, json={**config, "expected_revision": row["revision"], **changes})


def start(a, h, key=None):
    return a.post(BASE + "/test", headers={**h, "Idempotency-Key": key or str(uuid4())}, json={})


def oauth_start(a, h, key=None):
    revision = a.get(BASE).json()["data"]["revision"]
    return a.post(
        BASE + "/oauth/start",
        headers={**h, "Idempotency-Key": key or str(uuid4())},
        json={"expected_revision": revision},
    )


def authorize(a, h):
    reply = oauth_start(a, h)
    assert reply.status_code == 200, reply.text
    query = parse_qs(urlsplit(reply.json()["data"]["authorization_url"]).query)
    response = a.get(
        BASE + "/oauth/callback",
        params={"state": query["state"][0], "code": "AUTH-CODE"},
        follow_redirects=False,
    )
    return query, response


@pytest.fixture
def mail(admin):
    a, ah, b, bh, root, user = admin
    smtp, oauth = FakeSMTP(), FakeOAuth()
    a.app.state.smtp_store.oauth = oauth
    return a, ah, b, bh, root, user, SMTPWorker(a.app.state.smtp_store, smtp), smtp, oauth


def test_sm01_singleton_scope_secret_revision_and_no_implicit_network(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    initial = a.get(BASE).json()["data"]
    assert initial["config"] is None and not initial["configured"]
    assert initial == a.get(BASE).json()["data"]
    assert b.get(BASE).status_code == 404
    response = save(a, ah, secret={"operation": "set", "value": "MAIL-SECRET"})
    assert response.status_code == 200, response.text
    assert "MAIL-SECRET" not in response.text and not smtp.calls and not oauth.calls
    row = response.json()["data"]
    body = {
        k: v
        for k, v in row["config"].items()
        if k not in {"secret", "oauth_status", "connection_status", "last_test_at"}
    }
    body["expected_revision"] = row["revision"]
    assert b.put(BASE, headers=bh, json=body).status_code == 404
    assert (
        a.put(BASE, headers={**ah, "Origin": "https://evil.invalid"}, json=body).status_code == 403
    )
    assert row["config"]["secret"] == {"configured": True, "hint": None}
    stale = a.put(
        BASE,
        headers=ah,
        json={
            **{
                k: v
                for k, v in row["config"].items()
                if k not in {"secret", "oauth_status", "connection_status", "last_test_at"}
            },
            "expected_revision": initial["revision"],
        },
    )
    assert stale.status_code == 412
    assert save(a, ah).json()["data"]["revision"] == row["revision"]
    with db[0].connect() as conn:
        fact = conn.execute(sa.select(tables.configs)).mappings().one()
        assert fact["id"] == SMTP_ID
        assert Fernet(a.app.state.test_key).decrypt(fact["secret_ciphertext"]) == b"MAIL-SECRET"
        assert conn.scalar(sa.select(sa.func.count()).select_from(tables.audit)) == 1


@pytest.mark.parametrize(
    "provider,server,mode,username",
    [
        ("qq", "smtp.qq.com", "password", "s@qq.com"),
        ("163", "smtp.163.com", "password", "s@163.com"),
        ("gmail", "smtp.gmail.com", "password", "s@gmail.com"),
        ("sendgrid", "smtp.sendgrid.net", "api_key", None),
        ("custom", "smtp.example.invalid", "none", None),
    ],
)
def test_sm02_provider_mapping_and_durable_test(mail, db, provider, server, mode, username):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    value = {"provider": provider, "server": server, "auth_type": mode, "username": username}
    if mode != "none":
        value["secret"] = {"operation": "set", "value": "APP-PASSWORD"}
    response = save(a, ah, **value)
    assert response.status_code == 200, response.text
    key = str(uuid4())
    job = start(a, ah, key).json()["data"]
    assert start(a, ah, key).json()["data"]["task_id"] == job["task_id"]
    assert b.get(job["status_url"]).status_code == 404
    assert worker.run_once() and not worker.run_once()
    result = a.get(job["status_url"] + "/result").json()["data"]["payload"]
    assert result["status"] == "succeeded" and result["authenticated"] == (mode != "none")
    assert smtp.calls[0][0]["username"] == ("apikey" if provider == "sendgrid" else username)
    assert a.get(BASE).json()["data"]["config"]["connection_status"] == "available"
    assert "APP-PASSWORD" not in a.get(job["events_url"]).text


@pytest.mark.parametrize(
    "change",
    [
        {"provider": "sendgrid", "server": "smtp.sendgrid.net", "auth_type": "password"},
        {"server": "http://localhost"},
        {"port": 0},
        {"port": True},
        {"secret": None},
        {"provider": "gmail", "server": "evil.invalid"},
        {"username": "bad\r\nAUTH"},
        {
            "provider": "microsoft365",
            "server": "smtp.office365.com",
            "auth_type": "token",
            "oauth": {"client_id": "x", "tenant": "../../evil"},
        },
    ],
)
def test_sm03_invalid_combinations_rejected_without_persistence(mail, db, change):
    a, ah, *rest = mail
    assert save(a, ah, **change).status_code == 422
    assert not a.get(BASE).json()["data"]["configured"]
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(tables.audit)) == 0


@pytest.mark.parametrize(
    "provider,server,tenant",
    [("gmail", "smtp.gmail.com", None), ("microsoft365", "smtp.office365.com", "example-tenant")],
)
def test_sm04_oauth_callback_pkce_refresh_and_no_credentials_in_wire(
    mail, db, provider, server, tenant
):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    response = save(
        a,
        ah,
        provider=provider,
        server=server,
        auth_type="token",
        oauth={
            "client_id": "client",
            "tenant": tenant,
            "client_secret": {"operation": "set", "value": "CLIENT-SECRET"},
        },
    )
    assert response.status_code == 200, response.text
    query, callback = authorize(a, ah)
    assert callback.headers["location"] == "/workspace?smtp_oauth=connected"
    assert query["code_challenge_method"] == ["S256"]
    verifier = oauth.calls[0][2]["code_verifier"]
    assert (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        == query["code_challenge"][0]
    )
    assert oauth.calls[0][1] == "CLIENT-SECRET"
    assert a.get(BASE).json()["data"]["config"]["connection_status"] == "untested"
    replay = a.get(
        BASE + "/oauth/callback",
        params={"state": query["state"][0], "code": "AUTH-CODE"},
        follow_redirects=False,
    )
    assert replay.headers["location"].endswith("failed") and len(oauth.calls) == 1
    with db[0].begin() as conn:
        row = conn.execute(sa.select(tables.configs)).mappings().one()
        grant = a.app.state.smtp_store.decrypt(row["oauth_ciphertext"])
        grant["expires_at"] = datetime.now(UTC).isoformat()
        conn.execute(
            tables.configs.update().values(oauth_ciphertext=a.app.state.smtp_store.encrypt(grant))
        )
    job = start(a, ah).json()["data"]
    assert worker.run_once() and len(oauth.calls) == 2
    assert oauth.calls[1][2]["grant_type"] == "refresh_token"
    assert smtp.calls[0][1] == "ACCESS-SECRET"
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "succeeded"
    for endpoint in [BASE, job["status_url"], job["status_url"] + "/result", job["events_url"]]:
        value = a.get(endpoint).text
        assert all(
            secret not in value
            for secret in ["CLIENT-SECRET", "ACCESS-SECRET", "REFRESH-SECRET", "AUTH-CODE"]
        )
    with db[0].connect() as conn:
        grant = a.app.state.smtp_store.decrypt(
            conn.scalar(sa.select(tables.configs.c.oauth_ciphertext))
        )
        assert grant["refresh_token"] == "REFRESH-SECRET-2"


def test_sm05_callback_wrong_session_stale_configuration_and_denial(mail):
    a, ah, b, bh, *rest = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    reply = oauth_start(a, ah).json()["data"]
    state = parse_qs(urlsplit(reply["authorization_url"]).query)["state"][0]
    assert (
        b.get(
            BASE + "/oauth/callback", params={"state": state, "code": "x"}, follow_redirects=False
        )
        .headers["location"]
        .endswith("failed")
    )
    assert save(a, ah, sender_email="changed@example.invalid").status_code == 200
    assert (
        a.get(
            BASE + "/oauth/callback", params={"state": state, "code": "x"}, follow_redirects=False
        )
        .headers["location"]
        .endswith("failed")
    )
    state = parse_qs(urlsplit(oauth_start(a, ah).json()["data"]["authorization_url"]).query)[
        "state"
    ][0]
    assert (
        a.get(
            BASE + "/oauth/callback",
            params={"state": state, "error": "access_denied"},
            follow_redirects=False,
        )
        .headers["location"]
        .endswith("failed")
    )
    assert not rest[-1].calls


def test_sm06_unknown_refresh_requires_reauthorization_and_never_replays(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    authorize(a, ah)
    with db[0].begin() as conn:
        row = conn.execute(sa.select(tables.configs)).mappings().one()
        grant = a.app.state.smtp_store.decrypt(row["oauth_ciphertext"])
        grant["expires_at"] = datetime.now(UTC).isoformat()
        conn.execute(
            tables.configs.update().values(oauth_ciphertext=a.app.state.smtp_store.encrypt(grant))
        )
    oauth.error = ProviderFailure("PROVIDER_RESULT_UNKNOWN")
    job = start(a, ah).json()["data"]
    assert worker.run_once()
    assert a.get(BASE).json()["data"]["config"]["oauth_status"] == "reauthorization_required"
    start(a, ah)
    assert worker.run_once() and len(oauth.calls) == 2 and not smtp.calls
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"


def test_sm07_stale_task_and_expired_lease_do_not_call_adapter(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(a, ah, secret={"operation": "set", "value": "old"})
    job = start(a, ah).json()["data"]
    save(a, ah, secret={"operation": "set", "value": "new"})
    assert worker.run_once() and not smtp.calls
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    start(a, ah)
    with db[0].begin() as conn:
        conn.execute(
            tables.tasks.update()
            .where(tables.tasks.c.state == "queued")
            .values(state="running", lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert worker.run_once() and not smtp.calls


def test_sm08_late_oauth_flow_cannot_overwrite_new_grant_and_denial_consumed(mail):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    first = parse_qs(urlsplit(oauth_start(a, ah).json()["data"]["authorization_url"]).query)[
        "state"
    ][0]
    second = parse_qs(urlsplit(oauth_start(a, ah).json()["data"]["authorization_url"]).query)[
        "state"
    ][0]
    response = a.get(
        BASE + "/oauth/callback", params={"state": second, "code": "new"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("connected")
    response = a.get(
        BASE + "/oauth/callback", params={"state": first, "code": "old"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("failed") and len(oauth.calls) == 1
    third = parse_qs(urlsplit(oauth_start(a, ah).json()["data"]["authorization_url"]).query)[
        "state"
    ][0]
    a.get(
        BASE + "/oauth/callback",
        params={"state": third, "error": "access_denied"},
        follow_redirects=False,
    )
    response = a.get(
        BASE + "/oauth/callback",
        params={"state": third, "code": "replayed"},
        follow_redirects=False,
    )
    assert response.headers["location"].endswith("failed") and len(oauth.calls) == 1


def test_sm09_rotated_refresh_survives_smtp_failure(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    authorize(a, ah)
    with db[0].begin() as conn:
        grant = a.app.state.smtp_store.decrypt(
            conn.scalar(sa.select(tables.configs.c.oauth_ciphertext))
        )
        grant["expires_at"] = datetime.now(UTC).isoformat()
        conn.execute(
            tables.configs.update().values(oauth_ciphertext=a.app.state.smtp_store.encrypt(grant))
        )
    smtp.error = ProviderFailure("CONFIG_CONNECTION_FAILED")
    job = start(a, ah).json()["data"]
    assert worker.run_once()
    with db[0].connect() as conn:
        row = conn.execute(sa.select(tables.configs)).mappings().one()
        assert (
            a.app.state.smtp_store.decrypt(row["oauth_ciphertext"])["refresh_token"]
            == "REFRESH-SECRET-2"
        )
        assert row["oauth_status"] == "connected"
    assert a.get(job["status_url"]).json()["data"]["execution_status"] == "failed"
    smtp.error = None
    start(a, ah)
    assert worker.run_once() and len(oauth.calls) == 2


def test_sm10_crashed_refresh_intent_requires_reauthorization(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    authorize(a, ah)
    start(a, ah)
    with db[0].begin() as conn:
        task = (
            conn.execute(sa.select(tables.tasks).where(tables.tasks.c.state == "queued"))
            .mappings()
            .one()
        )
        conn.execute(
            tables.configs.update().values(
                oauth_status="refreshing",
                refresh_task_id=task["id"],
                refresh_attempt_id=task["attempt_id"],
            )
        )
        conn.execute(
            tables.tasks.update()
            .where(tables.tasks.c.state == "queued")
            .values(state="running", lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert worker.run_once()
    assert a.get(BASE).json()["data"]["config"]["oauth_status"] == "reauthorization_required"
    start(a, ah)
    assert worker.run_once() and len(oauth.calls) == 1 and not smtp.calls


def test_sm11_expired_oauth_handshake_and_missing_refresh_fail_safely(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    state = parse_qs(urlsplit(oauth_start(a, ah).json()["data"]["authorization_url"]).query)[
        "state"
    ][0]
    with db[0].begin() as conn:
        conn.execute(
            tables.handshakes.update().values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert (
        a.get(
            BASE + "/oauth/callback",
            params={"state": state, "code": "expired"},
            follow_redirects=False,
        )
        .headers["location"]
        .endswith("failed")
    )
    assert not oauth.calls
    oauth.exchange = lambda *args, **kwargs: {
        "access_token": "ACCESS",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    query, response = authorize(a, ah)
    assert response.headers["location"].endswith("failed")
    assert a.get(BASE).json()["data"]["config"]["oauth_status"] == "not_connected"


def test_sm12_competing_job_cannot_clear_another_refresh_intent(mail, db, monkeypatch):
    """A commits refresh intent, B finishes, then A resumes: one refresh succeeds."""
    from contextlib import contextmanager
    from threading import Event, Thread, current_thread

    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    authorize(a, ah)
    with db[0].begin() as conn:
        grant = a.app.state.smtp_store.decrypt(
            conn.scalar(sa.select(tables.configs.c.oauth_ciphertext))
        )
        grant["expires_at"] = datetime.now(UTC).isoformat()
        conn.execute(
            tables.configs.update().values(oauth_ciphertext=a.app.state.smtp_store.encrypt(grant))
        )
    first, second = start(a, ah).json()["data"], start(a, ah).json()["data"]
    claimed, release = Event(), Event()
    original = db[0].begin
    outcomes = []

    @contextmanager
    def gated_begin():
        with original() as conn:
            yield conn
        if current_thread().name == "refresh_owner" and not claimed.is_set():
            claimed.set()
            assert release.wait(10)

    monkeypatch.setattr(db[0], "begin", gated_begin)
    thread = Thread(name="refresh_owner", target=lambda: outcomes.append(worker.run_once()))
    thread.start()
    try:
        assert claimed.wait(10)
        assert SMTPWorker(a.app.state.smtp_store, smtp).run_once()
        with db[0].connect() as conn:
            row = conn.execute(sa.select(tables.configs)).mappings().one()
            assert row["oauth_status"] == "refreshing"
            assert str(row["refresh_task_id"]) == first["task_id"]
        assert len(oauth.calls) == 1 and not smtp.calls
    finally:
        release.set()
        thread.join(10)
    assert outcomes == [True] and not thread.is_alive()
    assert len(oauth.calls) == 2 and len(smtp.calls) == 1
    assert a.get(first["status_url"]).json()["data"]["execution_status"] == "succeeded"
    assert a.get(second["status_url"]).json()["data"]["execution_status"] == "failed"
    assert a.get(BASE).json()["data"]["config"]["oauth_status"] == "connected"


def test_sm13_unreadable_pkce_material_is_consumed_without_external_request(mail, db):
    a, ah, b, bh, root, user, worker, smtp, oauth = mail
    save(
        a,
        ah,
        provider="gmail",
        server="smtp.gmail.com",
        auth_type="token",
        oauth={"client_id": "client", "client_secret": {"operation": "set", "value": "CLIENT"}},
    )
    state = parse_qs(urlsplit(oauth_start(a, ah).json()["data"]["authorization_url"]).query)[
        "state"
    ][0]
    with db[0].begin() as conn:
        conn.execute(
            tables.handshakes.update().values(verifier_ciphertext=b"invalid-encrypted-value")
        )
    response = a.get(
        BASE + "/oauth/callback", params={"state": state, "code": "x"}, follow_redirects=False
    )
    assert response.headers["location"].endswith("failed") and not oauth.calls
    with db[0].connect() as conn:
        assert conn.scalar(sa.select(tables.handshakes.c.used)) is True
