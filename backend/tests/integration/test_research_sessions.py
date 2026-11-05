# ruff: noqa: F811
"""R1-R4: committed isolated PG; synthetic versions test consumer behavior only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from test_project_commands import create
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.project import projects
from rpb.adapters.research_tables import commands, sessions
from rpb.adapters.run_tables import runs


def seed_version(engine, project_id, *, empty=True, sealed=True):
    """Synthetic sealed consumer fixture, never evidence of real publication."""
    project_id = UUID(str(project_id))
    version_id, run_id = uuid4(), uuid4()
    with engine.begin() as conn:
        project = (
            conn.execute(sa.select(projects).where(projects.c.id == project_id).with_for_update())
            .mappings()
            .one()
        )
        conn.execute(
            runs.insert().values(
                id=run_id,
                project_id=project_id,
                owner_id=project["owner_id"],
                status="succeeded",
                revision=uuid4(),
                payload={},
                created_at=datetime.now(UTC),
            )
        )
        conn.execute(
            versions.insert().values(
                id=version_id,
                project_id=project_id,
                source_run_id=run_id,
                manifest={"papers": [] if empty else [{"id": "fixture-paper"}]},
                manifest_digest="consumer-fixture",
                ready_proof={},
                sealed=sealed,
                published_at=datetime.now(UTC),
            )
        )
        conn.execute(heads.delete().where(heads.c.project_id == project_id))
        if sealed:
            conn.execute(heads.insert().values(project_id=project_id, version_id=version_id))
    return str(version_id)


def test_research_create_restore_latest_and_replay(subject):
    c, h, root, _, engine, _ = subject
    path = root + "/research-sessions"
    assert post(c, h, path, {}).status_code == 404
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 0
    v1 = seed_version(engine, root.split("/")[-1])
    response = post(c, h, path, {"title": "证据研究"})
    assert response.status_code == 201, response.text
    first = response.json()["data"]
    assert first["no_project_evidence"] and first["latest_knowledge_version_id"] == v1
    assert first["last_execution_knowledge_version_id"] is None
    assert first["current_attempt_id"] is None
    url = response.headers["location"]
    v2 = seed_version(engine, root.split("/")[-1], empty=False)
    current = c.get(url).json()["data"]
    assert current["id"] == first["id"] and current["revision"] == first["revision"]
    assert current["latest_knowledge_version_id"] == v2 and not current["no_project_evidence"]
    replay = post(c, h, path, {"title": "证据研究"})
    assert replay.json()["data"] == first  # receipt preserves original response
    assert replay.json()["meta"]["original_request_id"] == response.json()["meta"]["request_id"]
    assert post(c, h, path, {"title": "changed"}).status_code == 409
    listed = c.get(path).json()["data"]["items"]
    assert len(listed) == 1 and listed[0] == current
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.select(sa.func.count()).select_from(runs)) == 2
        )  # reads create no task/run


def test_research_validation_permissions_paging_and_archived(subject):
    c, h, root, _, engine, _ = subject
    path = root + "/research-sessions"
    seed_version(engine, root.split("/")[-1])
    for body in (
        {"title": " "},
        {"title": "x" * 201},
        {"knowledge_version_id": str(uuid4())},
        {"title": None},
    ):
        assert post(c, h, path, body).status_code == 422
    assert c.post(path, json={}, headers=h).status_code == 400
    assert (
        c.post(path, json={}, headers={"Idempotency-Key": "research-no-csrf1"}).status_code == 403
    )
    assert c.get(path, headers={"X-Expected-Actor": str(uuid4())}).status_code == 401
    first = post(c, h, path, {"title": "one"}, "research-create-01").json()["data"]
    second = post(c, h, path, {"title": "two"}, "research-create-02").json()["data"]
    page = c.get(path + "?page_size=1").json()
    assert page["data"]["items"][0]["id"] == second["id"]
    next_page = c.get(path, params={"page_size": 1, "cursor": page["meta"]["next_cursor"]}).json()
    assert next_page["data"]["items"][0]["id"] == first["id"]
    assert not next_page["meta"]["has_more"]
    assert c.get(path + "?cursor=broken").status_code == 400
    assert c.get(path + "?unknown=1").status_code == 400
    other = create(c, h, key="research-other-project").json()["data"]["id"]
    seed_version(engine, other)
    assert c.get(f"/api/v1/projects/{other}/research-sessions/{first['id']}").status_code == 404
    assert (
        c.get(
            f"/api/v1/projects/{other}/research-sessions",
            params={"cursor": page["meta"]["next_cursor"]},
        ).status_code
        == 400
    )
    with engine.begin() as conn:
        conn.execute(
            projects.update()
            .where(projects.c.id == UUID(root.split("/")[-1]))
            .values(status="archived")
        )
    assert post(c, h, path, {}, "research-archived-01").status_code == 409
    assert c.get(path + "/" + first["id"]).status_code == 200
    with engine.begin() as conn:
        conn.execute(
            projects.update()
            .where(projects.c.id == UUID(root.split("/")[-1]))
            .values(status="deleted")
        )
    assert c.get(path).status_code == 404
    assert post(c, h, path, {"title": "one"}, "research-create-01").status_code == 404


def test_research_rollback_duplicate_and_expiry(subject):
    c, h, root, _, engine, _ = subject
    path = root + "/research-sessions"
    seed_version(engine, root.split("/")[-1])

    def fail_receipt(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO research_create_commands"):
            raise RuntimeError("injected receipt failure")

    sa.event.listen(engine, "before_cursor_execute", fail_receipt)
    try:
        assert post(c, h, path, {}).status_code == 500
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_receipt)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(c, h, path, {}).json()["data"], range(2)))
    assert results[0]["id"] == results[1]["id"]
    with engine.begin() as conn:
        conn.execute(commands.update().values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert post(c, h, path, {}).json()["data"]["id"] != results[0]["id"]


def test_research_candidate_not_readable(subject):
    c, h, root, _, engine, _ = subject
    with pytest.raises(DBAPIError, match="must be sealed"):
        seed_version(engine, root.split("/")[-1], sealed=False)
    assert post(c, h, root + "/research-sessions", {}).status_code == 404


def test_research_actual_owner_revocation_and_read_no_writes(subject):
    from fastapi.testclient import TestClient
    from test_account_auth import ORIGIN, csrf, login, register

    c, h, root, app, engine, _ = subject
    path = root + "/research-sessions"
    version = seed_version(engine, root.split("/")[-1])
    response = post(c, h, path, {"title": "private"})
    session = response.json()["data"]

    def facts():
        with engine.connect() as conn:
            return tuple(
                tuple(conn.execute(sa.select(table)).all())
                for table in (sessions, commands, runs, heads, versions)
            )

    before = facts()
    assert c.get(path).status_code == 200
    assert c.get(path + "/" + session["id"]).status_code == 200
    assert facts() == before
    other = TestClient(app, base_url=ORIGIN)
    oh = csrf(other)
    assert register(other, oh, "Bob", "bob@example.invalid").status_code == 201
    login(other, oh, "Bob")
    oh = csrf(other)
    assert other.get(path).status_code == 404
    assert other.get(path + "/" + session["id"]).status_code == 404
    assert post(other, oh, path, {}).status_code == 404
    from rpb.adapters.account import accounts

    owner_id = c.get("/api/v1/me").json()["data"]["id"]
    assert session["latest_knowledge_version_id"] == version
    with engine.begin() as conn:
        conn.execute(accounts.update().where(accounts.c.id == UUID(owner_id)).values(enabled=False))
    assert c.get(path + "/" + session["id"]).status_code == 401
    assert post(c, h, path, {"title": "private"}).status_code == 401
    assert other.get(path + "/" + session["id"]).status_code == 404


def test_research_migration_preserves_populated_data(subject, db):
    from alembic import command

    c, h, root, _, engine, _ = subject
    _, cfg = db
    seed_version(engine, root.split("/")[-1])
    row = post(c, h, root + "/research-sessions", {}).json()["data"]
    with pytest.raises(RuntimeError, match="contains data"):
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "0019_run_temporary_cleanup")
    assert c.get(root + "/research-sessions/" + row["id"]).status_code == 200
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0020_research_sessions"
        )


def test_research_empty_downgrade_and_failed_upgrade_atomic(db):
    from alembic import command

    engine, cfg = db
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0019_run_temporary_cleanup")

    def fail_create(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE research_sessions" in statement:
            raise RuntimeError("injected migration failure")

    sa.event.listen(engine, "before_cursor_execute", fail_create)
    try:
        with pytest.raises(RuntimeError, match="injected migration"):
            with engine.begin() as conn:
                cfg.attributes["connection"] = conn
                command.upgrade(cfg, "head")
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_create)
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0019_run_temporary_cleanup"
        )
        assert conn.scalar(sa.text("SELECT to_regclass('research_catalogs')")) is None
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
