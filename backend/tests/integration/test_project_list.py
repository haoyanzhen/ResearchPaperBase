"""PH01–04: owned, bounded, current-authority project discovery on real PG."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import sqlalchemy as sa
from test_account_auth import client
from test_project_commands import counts, create, service_subject, signed_in

from rpb.adapters.account import accounts
from rpb.adapters.project import projects
from rpb.modules.account_config.application.ports import AccountError


def seed(c, h, count):
    return [
        create(c, h, {"name": f"Project {i:03}"}, f"list-project-{i:08}").json()["data"]
        for i in range(count)
    ]


def test_ph01_empty_owned_status_projection_and_no_writes(db):
    engine, _ = db
    admin, ah = signed_in(engine, "Admin")
    assert admin.get("/api/v1/projects").json()["data"] == {"items": []}
    other, oh = signed_in(engine, "Other")
    owned = seed(other, oh, 3)
    create(admin, ah, {"name": "Private admin"})
    with engine.begin() as conn:
        conn.execute(
            projects.update().where(projects.c.id == UUID(owned[0]["id"])).values(status="archived")
        )
        conn.execute(
            projects.update().where(projects.c.id == UUID(owned[1]["id"])).values(status="deleted")
        )
    before = counts(engine)
    writes = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    sa.event.listen(engine, "before_cursor_execute", observe)
    try:
        r = other.get("/api/v1/projects")
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert {x["id"] for x in items} == {owned[0]["id"], owned[2]["id"]}
        for item in items:
            assert item == other.get("/api/v1/projects/" + item["id"]).json()["data"]
        assert [x["name"] for x in admin.get("/api/v1/projects").json()["data"]["items"]] == [
            "Private admin"
        ]
    finally:
        sa.event.remove(engine, "before_cursor_execute", observe)
    assert not writes and counts(engine) == before
    assert r.json()["meta"]["next_cursor"] is None and not r.json()["meta"]["has_more"]


def test_ph02_default_bounds_ties_insert_and_terminal(db):
    engine, _ = db
    c, h = signed_in(engine)
    rows = seed(c, h, 23)
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as conn:
        conn.execute(projects.update().values(created_at=instant))
    expected = sorted((x["id"] for x in rows), reverse=True)
    first = c.get("/api/v1/projects").json()
    assert [x["id"] for x in first["data"]["items"]] == expected[:20]
    assert first["meta"]["has_more"]
    create(c, h, {"name": "Inserted after first page"}, "inserted-after-page-0001")
    second = c.get("/api/v1/projects", params={"cursor": first["meta"]["next_cursor"]}).json()
    assert [x["id"] for x in second["data"]["items"]] == expected[20:]
    assert second["meta"]["next_cursor"] is None and not second["meta"]["has_more"]
    assert len(c.get("/api/v1/projects?page_size=100").json()["data"]["items"]) == 24
    assert len(c.get("/api/v1/projects?page_size=1").json()["data"]["items"]) == 1


@pytest.mark.parametrize(
    "query",
    ["page_size=0", "page_size=101", "page_size=x", "page_size=1.5", "cursor=" + "x" * 2049],
)
def test_ph02_invalid_page_inputs(db, query):
    c, _ = signed_in(db[0])
    assert c.get("/api/v1/projects?" + query).status_code == 422


@pytest.mark.parametrize(
    "query", ["sort=name", "owner_id=someone", "status=deleted", "cursor=garbage", "cursor="]
)
def test_ph03_unknown_query_and_malformed_cursor(db, query):
    c, _ = signed_in(db[0])
    assert c.get("/api/v1/projects?" + query).status_code == 400


def test_ph03_tamper_actor_and_current_authorization(db):
    engine, _ = db
    a, h = signed_in(engine)
    seed(a, h, 2)
    cursor = a.get("/api/v1/projects?page_size=1").json()["meta"]["next_cursor"]
    actor = a.get("/api/v1/me").json()["data"]["id"]
    b, _ = signed_in(engine, "Bob")
    for c, value in [(a, cursor + "0"), (b, cursor)]:
        r = c.get("/api/v1/projects", params={"cursor": value})
        assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_CURSOR_MISMATCH"
    assert b.get("/api/v1/projects", headers={"X-Expected-Actor": actor}).status_code == 401
    assert a.get("/api/v1/projects", headers={"X-Expected-Actor": actor}).status_code == 200
    assert client(engine).get("/api/v1/projects").status_code == 401
    with engine.begin() as conn:
        conn.execute(accounts.update().where(accounts.c.id == UUID(actor)).values(enabled=False))
    r = a.get("/api/v1/projects", params={"cursor": cursor})
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_ACCOUNT_DISABLED"


def test_ph03_expiry_and_process_restart(db):
    service, token, csrf = service_subject(db[0])
    now = datetime.now(UTC)
    service.clock = lambda: now
    for i in range(2):
        service.create(
            token,
            csrf,
            f"expiry-command-{i:08}",
            {"name": str(i), "description": "", "research_scope": ""},
        )
    _, cursor = service.list_projects(token, 1, None)
    service.clock = lambda: now + timedelta(minutes=30)
    with pytest.raises(AccountError) as exc:
        service.list_projects(token, 1, cursor)
    assert exc.value.code == "VALIDATION_CURSOR_EXPIRED" and exc.value.status == 400
    assert service.list_projects(token, 1, None)[0]
    from rpb.modules.project.application.service import ProjectService

    restarted = ProjectService(service.uow)
    with pytest.raises(AccountError) as exc:
        restarted.list_projects(token, 1, cursor)
    assert exc.value.code == "VALIDATION_CURSOR_MISMATCH"


def test_ph04_failure_safe_retry(db):
    engine, _ = db
    c, h = signed_in(engine)
    seed(c, h, 1)
    before = counts(engine)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if "FROM projects" in statement:
            raise RuntimeError("PRIVATE database exception")

    sa.event.listen(engine, "before_cursor_execute", fail)
    try:
        r = c.get("/api/v1/projects")
        assert r.status_code == 500 and "PRIVATE" not in r.text
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail)
    assert len(c.get("/api/v1/projects").json()["data"]["items"]) == 1
    assert counts(engine) == before
