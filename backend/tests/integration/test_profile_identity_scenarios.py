"""IS01–06: independently derived real-user identity workflows, not implementation mirrors."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
import sqlalchemy as sa
from test_account_auth import client, csrf, login, register
from test_account_profile import edit
from test_project_commands import create, signed_in

from rpb.adapters.account import accounts
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK


def me(c):
    response = c.get("/api/v1/me")
    assert response.status_code == 200
    return response.json()["data"]


def test_identity_scenario_is01_swap_requires_vacancy_and_preserves_ownership(db):
    engine, _ = db
    a, ah = signed_in(engine, "Alice")
    b, bh = signed_in(engine, "Bob")
    av, bv = me(a), me(b)
    project = create(a, ah).json()["data"]
    assert edit(a, ah, av, email=bv["email"]).status_code == 409
    assert edit(b, bh, bv, email=av["email"]).status_code == 409
    assert me(a) == av and me(b) == bv
    temporary = edit(a, ah, av, email="temporary@example.invalid").json()["data"]
    moved_b = edit(b, bh, bv, email=av["email"]).json()["data"]
    moved_a = edit(a, ah, temporary, email=bv["email"]).json()["data"]
    assert moved_a["id"] == av["id"] and moved_b["id"] == bv["id"]
    for email, expected in [(av["email"], bv["id"]), (bv["email"], av["id"])]:
        fresh = client(engine)
        response = login(fresh, csrf(fresh), email)
        assert response.status_code == 200 and response.json()["data"]["user"]["id"] == expected
    assert a.get("/api/v1/projects/" + project["id"]).status_code == 200
    assert b.get("/api/v1/projects/" + project["id"]).status_code == 404
    assert me(a)["username"] == "Alice" and me(b)["username"] == "Bob"


def test_identity_scenario_is02_unicode_cross_field_collision_rejected(db):
    engine, _ = db
    a, ah = signed_in(engine, "Alice")
    b = client(engine)
    bh = csrf(b)
    assert register(b, bh, "straße@example.invalid", "second@example.invalid").status_code == 201
    assert login(b, bh, "STRASSE@example.invalid").status_code == 200
    av, bv = me(a), me(b)
    response = edit(a, ah, av, email="  STRASSE@EXAMPLE.INVALID  ")
    assert response.status_code == 409
    assert bv["id"] not in response.text and bv["email"] not in response.text
    assert me(a) == av and me(b) == bv
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 2


def test_identity_scenario_is03_two_sessions_stale_noop_requires_refresh(db):
    engine, _ = db
    a, ah = signed_in(engine)
    b = client(engine)
    assert login(b, csrf(b), "Alice").status_code == 200
    bh = csrf(b)
    av, bv = me(a), me(b)
    first = edit(a, ah, av, display_name="First session").json()["data"]
    assert edit(b, bh, bv).status_code == 412
    assert me(a) == first and me(b) == first
    refreshed = me(b)
    second = edit(b, bh, refreshed, email="second-session@example.invalid").json()["data"]
    assert second["display_name"] == "First session" and second["id"] == av["id"]
    assert me(a) == second
    # Logging out the second independent session does not revoke the first one.
    assert b.post("/api/v1/auth/logout", headers=bh, json={}).status_code == 200
    assert me(a) == second and b.get("/api/v1/me").status_code == 401


def test_identity_scenario_is04_reenable_does_not_resurrect_rejected_session(db):
    engine, _ = db
    c, h = signed_in(engine)
    original = me(c)
    with engine.begin() as conn:
        conn.execute(
            accounts.update().where(accounts.c.id == UUID(original["id"])).values(enabled=False)
        )
    assert edit(c, h, original, display_name="Forbidden").status_code == 401
    with engine.begin() as conn:
        conn.execute(
            accounts.update().where(accounts.c.id == UUID(original["id"])).values(enabled=True)
        )
    assert c.get("/api/v1/me").status_code == 401
    assert edit(c, h, original, display_name="Still forbidden").status_code == 401
    with engine.connect() as conn:
        assert conn.scalar(sa.select(accounts.c.display_name)) is None
    fresh = client(engine)
    assert login(fresh, csrf(fresh), "Alice").status_code == 200
    new_headers = csrf(fresh)
    assert edit(fresh, new_headers, me(fresh), display_name="Fresh login").status_code == 200


def test_identity_scenario_is05_simultaneous_occupied_swap_is_not_implicit_exchange(db):
    engine, _ = db
    a, ah = signed_in(engine, "Alice")
    b, bh = signed_in(engine, "Bob")
    av, bv = me(a), me(b)
    with engine.begin() as blocker:
        blocker.execute(sa.text("SELECT pg_advisory_xact_lock(:k)"), {"k": ACCOUNT_GOVERNANCE_LOCK})
        pid = blocker.scalar(sa.text("SELECT pg_backend_pid()"))
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(edit, a, ah, av, email=bv["email"])
            second = pool.submit(edit, b, bh, bv, email=av["email"])
            try:
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        observer.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
                        waiting = observer.scalar(
                            sa.text(
                                "SELECT count(DISTINCT pid) FROM pg_locks "
                                "WHERE locktype = 'advisory' AND NOT granted "
                                "AND classid = 0 AND objid = :key "
                                "AND :blocker = ANY(pg_blocking_pids(pid))"
                            ),
                            {"key": ACCOUNT_GOVERNANCE_LOCK, "blocker": pid},
                        )
                        if waiting == 2:
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("Both profile requests must wait on the held governance lock")
            finally:
                blocker.commit()
            assert first.result().status_code == second.result().status_code == 409
    assert me(a) == av and me(b) == bv


def test_identity_scenario_is06_foreign_revision_is_not_object_authority(db):
    engine, _ = db
    a, ah = signed_in(engine, "Alice")
    b, _ = signed_in(engine, "Bob")
    av, bv = me(a), me(b)
    response = edit(a, ah, bv, display_name="Pretend to edit Bob")
    assert response.status_code == 412
    assert bv["id"] not in response.text and bv["email"] not in response.text
    assert me(a) == av and me(b) == bv
