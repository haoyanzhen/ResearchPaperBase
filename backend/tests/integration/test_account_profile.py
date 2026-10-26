"""AP01–04: personal profile requirements against committed isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from test_account_auth import client, csrf, login, register
from test_account_storage import migrate
from test_project_commands import counts, create, signed_in
from test_project_maintenance import wait_for_blocker

from rpb.adapters.account import accounts, metadata
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK


def edit(c, h, user, **changes):
    return c.patch("/api/v1/me", headers=h, json={"expected_revision": user["revision"], **changes})


def test_ap01_partial_clear_noop_and_protected_facts(db):
    engine, _ = db
    c, h = signed_in(engine)
    create(c, h)
    before = c.get("/api/v1/me").json()["data"]
    with engine.connect() as conn:
        row = dict(conn.execute(sa.select(accounts)).mappings().one())
    updated = edit(c, h, before, display_name="  A  B  ").json()["data"]
    assert updated["display_name"] == "A  B" and updated["email"] == before["email"]
    assert updated["revision"] != before["revision"]
    assert c.get("/api/v1/me").json()["data"] == updated
    assert edit(c, h, updated).json()["data"] == updated
    assert edit(c, h, updated, display_name="A  B").json()["data"] == updated
    cleared = edit(c, h, updated, display_name=None).json()["data"]
    assert cleared["display_name"] is None
    assert edit(c, h, cleared, display_name="  " + "x" * 200 + "  ").status_code == 200
    with engine.connect() as conn:
        after = dict(conn.execute(sa.select(accounts)).mappings().one())
    for key in set(row) - {"display_name", "revision", "updated_at"}:
        assert row[key] == after[key]
    assert counts(engine) == (1, 1, 1)


def test_ap02_identity_uniqueness_and_login(db):
    engine, _ = db
    c, h = signed_in(engine)
    other = client(engine)
    oh = csrf(other)
    assert (
        register(other, oh, "taken@example.invalid", "taken-mail@example.invalid").status_code
        == 201
    )
    assert login(other, oh, "taken@example.invalid").status_code == 200
    oh = csrf(other)
    other_before = other.get("/api/v1/me").json()["data"]
    user = c.get("/api/v1/me").json()["data"]
    for email in [" TAKEN@EXAMPLE.INVALID ", other_before["email"].upper()]:
        assert edit(c, h, user, email=email).status_code == 409
        assert c.get("/api/v1/me").json()["data"] == user
    updated = edit(c, h, user, email="  New@Example.invalid  ").json()["data"]
    assert updated["email"] == "  New@Example.invalid  "
    fresh = client(engine)
    assert login(fresh, csrf(fresh), "alice@example.invalid").status_code == 401
    assert login(fresh, csrf(fresh), " NEW@EXAMPLE.INVALID ").status_code == 200
    assert other.get("/api/v1/me").json()["data"] == other_before
    # The same account may use its own username as email.
    assert edit(other, oh, other_before, email="taken@example.invalid").status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"email": None},
        {"email": "bad"},
        {"email": "x" * 255 + "@a.b"},
        {"display_name": "x" * 201},
        {"display_name": 3},
        {"enabled": False},
        {"is_admin": True},
        {"username": "new"},
        {"password": "new"},
        {"owner_id": "other"},
        {"expected_revision": None},
        {"expected_revision": ""},
        {"expected_revision": "x" * 129},
    ],
)
def test_ap03_invalid_rejected_without_writes(db, change):
    engine, _ = db
    c, h = signed_in(engine)
    user = c.get("/api/v1/me").json()["data"]
    assert edit(c, h, user, **change).status_code == 422
    assert c.get("/api/v1/me").json()["data"] == user


def test_ap03_revision_and_authorization(db):
    engine, _ = db
    c, h = signed_in(engine)
    user = c.get("/api/v1/me").json()["data"]
    assert c.patch("/api/v1/me", headers=h, json={"display_name": "x"}).status_code == 428
    assert edit(c, h, user, expected_revision="stale").status_code == 412
    assert edit(c, {}, user, display_name="x").status_code == 403
    assert (
        edit(c, h | {"Origin": "https://foreign.invalid"}, user, display_name="x").status_code
        == 403
    )
    assert edit(client(engine), h, user, display_name="x").status_code == 401
    assert c.get("/api/v1/me").json()["data"] == user
    with engine.begin() as conn:
        conn.execute(accounts.update().values(enabled=False))
    assert edit(c, h, user, display_name="x").status_code == 401
    with engine.connect() as conn:
        assert conn.scalar(sa.select(accounts.c.display_name)) is None


def test_ap04_write_failure_rolls_back(db):
    engine, _ = db
    c, h = signed_in(engine)
    user = c.get("/api/v1/me").json()["data"]

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE accounts"):
            raise RuntimeError("PRIVATE profile write failed")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        response = edit(c, h, user, email="new@example.invalid", display_name="New")
        assert response.status_code == 500 and "PRIVATE" not in response.text
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    assert c.get("/api/v1/me").json()["data"] == user
    assert edit(c, h, user, display_name="Retry").status_code == 200


def test_ap02_concurrent_edits_have_one_winner(db):
    engine, _ = db
    c, h = signed_in(engine)
    user = c.get("/api/v1/me").json()["data"]
    other = client(engine)
    other.cookies.update(c.cookies)
    with engine.begin() as blocker:
        blocker.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": ACCOUNT_GOVERNANCE_LOCK})
        pid = blocker.scalar(sa.text("SELECT pg_backend_pid()"))
        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(edit, c, h, user, display_name="one")
            b = pool.submit(edit, other, h, user, display_name="two")
            try:
                wait_for_blocker(engine, pid)
            finally:
                blocker.commit()
            assert sorted([a.result().status_code, b.result().status_code]) == [200, 412]
    assert c.get("/api/v1/me").json()["data"]["display_name"] in {"one", "two"}


def test_ap04_migration_preserves_data_and_guards_downgrade(db):
    engine, cfg = db
    c, h = signed_in(engine)
    before = c.get("/api/v1/me").json()["data"]
    migrate(engine, cfg, "downgrade", "0005_project_lifecycle")
    with engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT email FROM accounts")) == before["email"]
    migrate(engine, cfg, "upgrade", "head")
    assert c.get("/api/v1/me").json()["data"] == before
    edited = edit(c, h, before, display_name="Keep").json()["data"]
    with pytest.raises(RuntimeError, match="display names contain data"):
        migrate(engine, cfg, "downgrade", "0005_project_lifecycle")
    assert c.get("/api/v1/me").json()["data"] == edited
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []


@pytest.mark.parametrize("competitor", ["edit", "register"])
def test_ap02_identity_claim_serializes_with_other_writers(db, competitor):
    engine, _ = db
    c, h = signed_in(engine)
    other, oh = signed_in(engine, "Other")
    user = c.get("/api/v1/me").json()["data"]
    second = other.get("/api/v1/me").json()["data"]

    fresh = client(engine)
    fh = csrf(fresh)
    with engine.begin() as blocker:
        blocker.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": ACCOUNT_GOVERNANCE_LOCK})
        pid = blocker.scalar(sa.text("SELECT pg_backend_pid()"))
        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(edit, c, h, user, email="claim@example.invalid")
            b = (
                pool.submit(edit, other, oh, second, email="CLAIM@example.invalid")
                if competitor == "edit"
                else pool.submit(
                    register, fresh, fh, "CLAIM@example.invalid", "third@example.invalid"
                )
            )
            try:
                wait_for_blocker(engine, pid)
            finally:
                blocker.commit()
            statuses = sorted([a.result().status_code, b.result().status_code])
            assert statuses in ([200, 409], [201, 409])
    with engine.connect() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(accounts)
                .where(
                    sa.or_(
                        accounts.c.email_key == "claim@example.invalid",
                        accounts.c.username_key == "claim@example.invalid",
                    )
                )
            )
            == 1
        )


def test_ap04_committed_profile_prevents_waiting_downgrade(db):
    engine, cfg = db
    c, _ = signed_in(engine)
    user = c.get("/api/v1/me").json()["data"]
    with engine.begin() as writer:
        writer.execute(accounts.update().values(display_name="Committed before downgrade"))
        pid = writer.scalar(sa.text("SELECT pg_backend_pid()"))
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(migrate, engine, cfg, "downgrade", "0005_project_lifecycle")
            try:
                wait_for_blocker(engine, pid)
            finally:
                writer.commit()
            with pytest.raises(RuntimeError, match="display names contain data"):
                future.result()
    current = c.get("/api/v1/me").json()["data"]
    assert current["id"] == user["id"] and current["display_name"] == "Committed before downgrade"


def test_ap04_database_rejects_oversized_display_name(db):
    engine, _ = db
    c, _ = signed_in(engine)
    before = c.get("/api/v1/me").json()["data"]
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(accounts.update().values(display_name="x" * 201))
    assert c.get("/api/v1/me").json()["data"] == before


def test_ap02_old_email_login_waiting_for_email_change_is_rejected(db):
    """R2: login reads old identity, email change commits, login must recheck identity."""
    from threading import Event

    engine, _ = db
    c, h = signed_in(engine)
    user = c.get("/api/v1/me").json()["data"]
    fresh = client(engine)
    fh = csrf(fresh)
    written, release = Event(), Event()
    writer_pid = []

    def hold(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE accounts"):
            writer_pid.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
            written.set()
            assert release.wait(15)

    sa.event.listen(engine, "after_cursor_execute", hold)
    try:
        with ThreadPoolExecutor(2) as pool:
            change = pool.submit(edit, c, h, user, email="changed@example.invalid")
            assert written.wait(10)
            attempt = pool.submit(login, fresh, fh, "alice@example.invalid")
            try:
                wait_for_blocker(engine, writer_pid[0])
            finally:
                release.set()
            assert change.result().status_code == 200
            assert attempt.result().status_code == 401
    finally:
        release.set()
        sa.event.remove(engine, "after_cursor_execute", hold)
    assert login(fresh, csrf(fresh), "changed@example.invalid").status_code == 200
