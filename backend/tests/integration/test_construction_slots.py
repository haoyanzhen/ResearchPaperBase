# ruff: noqa: F811
"""Project writer ownership persists and old epochs cannot write after cancellation."""

import copy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import sqlalchemy as sa
from test_construction_runs import Papers, setup
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.construction_slots import is_current
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.run_worker import RunWorker
from rpb.adapters.runs import persist, transition
from rpb.modules.account_config.application.ports import AccountError


def test_slot_acquisition_cancellation_and_stale_writer(subject):
    client, headers, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    run = post(client, headers, path, body, "slot-start-command-0001").json()["data"]["run"]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(slots)) == 0
    assert RunWorker(app.state.run_store, Papers()).run_once()
    current = client.get(path + "/" + run["id"]).json()["data"]
    with engine.connect() as conn:
        saved = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(run["id"])))
        slot = conn.execute(sa.select(slots)).mappings().one()
        assert slot["occupant_run_id"] == UUID(run["id"])
        assert slot["epoch"] == saved["slot_epoch"] and is_current(conn, saved)
    response = post(
        client,
        headers,
        path + "/" + run["id"] + "/cancel",
        {"expected_revision": current["revision"], "attempt_id": current["task"]["attempt_id"]},
        "slot-cancel-command-0001",
    )
    assert response.status_code == 200
    with engine.begin() as conn:
        slot = conn.execute(sa.select(slots)).mappings().one()
        assert slot["occupant_run_id"] is None and slot["epoch"] > saved["slot_epoch"]
        assert not is_current(conn, saved)
        with pytest.raises(AccountError):
            persist(conn, copy.deepcopy(saved))
        stale = copy.deepcopy(saved)
        transition(stale, "failed", "PROVIDER_RESULT_UNKNOWN")
        with pytest.raises(AccountError):
            persist(conn, stale)
        assert (
            conn.scalar(sa.select(runs.c.status).where(runs.c.id == UUID(run["id"]))) == "cancelled"
        )


def test_revoking_queued_run_does_not_release_another_run_slot(subject):
    client, headers, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    ids = [
        post(client, headers, path, body, f"slot-queue-command-{i:04d}").json()["data"]["run"]["id"]
        for i in range(3)
    ]
    with engine.begin() as conn:
        conn.execute(
            runs.update()
            .where(runs.c.id == UUID(ids[1]))
            .values(created_at=datetime.now(UTC) - timedelta(hours=1))
        )
    assert RunWorker(app.state.run_store, Papers()).run_once()
    with engine.begin() as conn:
        stale = copy.deepcopy(
            conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(ids[0])))
        )
        stale["authority_epoch"] -= 1
        conn.execute(
            runs.update()
            .where(runs.c.id == UUID(ids[0]))
            .values(payload=stale, created_at=datetime.now(UTC) - timedelta(hours=2))
        )
    RunWorker(app.state.run_store, Papers()).run_once()
    with engine.connect() as conn:
        states = dict(conn.execute(sa.select(runs.c.id, runs.c.status)).all())
    assert states[UUID(ids[0])] == "cancelled"
    assert states[UUID(ids[1])] == "waiting_user"
    assert states[UUID(ids[2])] == "queued"


def test_persisted_candidate_lock_cannot_be_reopened_by_old_snapshot(subject):
    client, headers, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    identity = post(client, headers, path, body, "slot-lock-command-0001").json()["data"]["run"][
        "id"
    ]
    assert RunWorker(app.state.run_store, Papers()).run_once()
    with engine.begin() as conn:
        old = copy.deepcopy(
            conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(identity)))
        )
        locked = copy.deepcopy(old)
        locked["candidate_version"]["content_locked"] = True
        persist(conn, locked)
    with engine.begin() as conn:
        with pytest.raises(AccountError):
            persist(conn, old)
    with engine.connect() as conn:
        saved = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(identity)))
        assert saved["candidate_version"]["content_locked"] is True
