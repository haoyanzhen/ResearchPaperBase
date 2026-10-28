"""ST01–06: committed isolated PG, HTTP, explicit fake generation and rejection."""

import json
from uuid import UUID

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from test_account_auth import ORIGIN, SPEC, csrf, login, register
from test_project_commands import create, signed_in

from rpb.adapters.llm import LLMStore
from rpb.adapters.llm_worker import LLMWorker
from rpb.adapters.search_term_worker import TermWorker
from rpb.adapters.search_terms import states
from rpb.bootstrap.business import create_business_app


class TermsClient(TestClient):
    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        parts = response.request.url.path.removeprefix("/api/v1").split("/")
        if (
            len(parts) > 3
            and parts[1] == "projects"
            and parts[3] in {"construction-workspace", "material-policy", "material-sources"}
        ):
            parts[2] = "{project_id}"
            if "material-sources" in parts:
                parts[4] = "{source_id}"
            if "search-terms" in parts and len(parts) > 5 and parts[5] != "generate":
                parts[5] = "{term_id}"
            operation = SPEC["paths"].get("/".join(parts), {}).get(response.request.method.lower())
            if operation and response.status_code != 204:
                assert str(response.status_code) in operation["responses"], (
                    parts,
                    response.status_code,
                )
                if response.status_code >= 400:
                    schema = {
                        "$ref": "#/components/schemas/ErrorEnvelope" + str(response.status_code)
                    }
                else:
                    schema = operation["responses"][str(response.status_code)]["content"][
                        "application/json"
                    ]["schema"]
                Draft202012Validator(
                    schema | {"components": SPEC["components"]}, format_checker=FormatChecker()
                ).validate(response.json())
        return response


@pytest.fixture
def subject(db):
    engine, _ = db
    key = Fernet.generate_key()
    app = create_business_app(engine, ORIGIN, key)
    c = TermsClient(app, base_url=ORIGIN)
    h = csrf(c)
    assert register(c, h, "Alice", "alice@example.invalid").status_code == 201
    login(c, h, "Alice")
    h = csrf(c)
    project = create(c, h).json()["data"]
    root = "/api/v1/projects/" + project["id"]
    return c, h, root, app, engine, key


def post(c, h, url, data, key="term-command-00000001"):
    return c.post(url, headers=h | {"Idempotency-Key": key}, json=data)


def add(c, h, root, query="graph", key="term-command-00000001"):
    r = post(c, h, root + "/construction-workspace/search-terms", {"query": query}, key)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_st01_manual_confirm_edit_delete_replay_and_forbidden_side_effects(subject):
    c, h, root, app, engine, key = subject
    path = root + "/construction-workspace/search-terms"
    term = add(c, h, root)
    assert term["auto_update_enabled"] and term["confirmed_revision"] is None
    assert add(c, h, root)["id"] == term["id"]
    assert post(c, h, path, {"query": "different"}).status_code == 409
    assert c.patch(path + "/" + term["id"], headers=h, json={"query": "new"}).status_code == 428
    body = {
        "expected_revision": term["revision"],
        "confirmation_token": term["confirmations"][0]["confirmation_token"],
        "acknowledged_risk_ids": [],
    }
    confirmed = post(c, h, path + "/" + term["id"] + "/confirm", body).json()["data"]
    assert confirmed["confirmed_revision"] == term["revision"]
    edited = c.patch(
        path + "/" + term["id"],
        headers=h,
        json={"expected_revision": term["revision"], "auto_update_enabled": False},
    ).json()["data"]
    assert edited["confirmed_revision"] is None and edited["content_state"] == "manual_edit"
    assert (
        post(c, h, path + "/" + term["id"] + "/confirm", body, "stale-confirm-key-01").status_code
        == 412
    )
    assert (
        c.delete(
            path + "/" + term["id"],
            headers=h | {"Content-Type": "application/json"},
            params={"expected_revision": edited["revision"]},
        ).status_code
        == 204
    )
    assert c.get(path).json()["data"]["items"] == []
    with engine.connect() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        history = state["terms"][term["id"]]["confirmation_history"]
        assert history[0]["content"]["auto_update_enabled"] is True
        assert history[0]["content"]["query"] == "graph"
    assert c.get(root + "/construction-workspace").json()["data"]["scheduler_available"] is False


def test_st02_project_scope_csrf_archive_and_unknown_fields(subject):
    c, h, root, app, engine, key = subject
    add(c, h, root)
    path = root + "/construction-workspace/search-terms"
    assert post(c, {}, path, {"query": "bad"}).status_code == 403
    assert (
        post(c, h, path, {"query": "bad", "enabled": True}, "unknown-fields-key01").status_code
        == 422
    )
    other, oh = signed_in(engine, "Other")
    assert other.get(path).status_code == 404
    assert post(other, oh, path, {"query": "bad"}).status_code == 404
    p = c.get(root).json()["data"]
    preview = post(
        c, h, root + "/action-preview", {"expected_revision": p["revision"], "action": "archive"}
    ).json()["data"]
    r = post(
        c,
        h,
        root + "/archive",
        {
            "expected_revision": p["revision"],
            "confirmation_token": preview["confirmation_token"],
            "acknowledged_risk_ids": [x["id"] for x in preview["risks"]],
        },
    )
    assert r.status_code == 200, r.text
    assert c.get(path).status_code == 200
    assert post(c, h, path, {"query": "new"}, "archived-command001").status_code == 409


class FakeLLM:
    def execute(self, config, operation, model, secret, authorize):
        with authorize():
            pass
        return {"discovered_models": [], "tested_parameters": {}, "test_overrides": {}}


class FakeTerms:
    def __init__(self, before=None, after=None):
        self.calls = 0
        self.before = before
        self.after = after

    def generate(self, config, model, secret, inputs, authorize):
        if self.before:
            self.before()
        with authorize():
            self.calls += 1
        if self.after:
            self.after()
        return [
            {
                "query": "generated query",
                "keywords": ["q"],
                "rationale": "broad",
                "coverage": "topic",
            }
        ]


def ready(subject, materials=True):
    c, h, root, app, engine, key = subject
    cfg = post(
        c,
        h,
        "/api/v1/me/llm-configs",
        {
            "name": "fake",
            "provider": "openai",
            "base_url": "https://example.invalid/v1",
            "secret": {"operation": "set", "value": "SECRET-TERM-KEY"},
        },
        "create-llm-config01",
    ).json()["data"]
    assert (
        post(
            c,
            h,
            "/api/v1/me/llm-configs/" + cfg["id"] + "/test",
            {"model_id": "fake-model"},
            "test-llm-model-001",
        ).status_code
        == 202
    )
    LLMWorker(LLMStore(app.state.term_store.account, key), FakeLLM()).run_once()
    selection = {"source": "user", "config_id": cfg["id"], "model_id": "fake-model"}
    if not materials:
        return selection
    w = c.get(root + "/construction-workspace").json()["data"]
    url = root + "/material-sources/" + w["topic_source"]["source_id"] + "/classification"
    classification = c.get(url).json()["data"]
    assert (
        post(
            c,
            h,
            url + "/confirm",
            {
                "expected_revision": classification["revision"],
                "content_revision": classification["source"]["content_revision"],
                "classification": "private",
                "basis": "Owner research topic",
                "explicit_confirmation": True,
            },
            "classify-topic-001",
        ).status_code
        == 200
    )
    policy = c.get(root + "/material-policy").json()["data"]
    assert (
        c.put(
            root + "/material-policy",
            headers=h,
            json={
                "expected_revision": policy["revision"],
                "mode": "allow_private",
                "risk_acknowledged": True,
            },
        ).status_code
        == 200
    )
    return selection


def start(subject, selection, key="generate-terms-0001"):
    c, h, root, *_ = subject
    w = c.get(root + "/construction-workspace").json()["data"]
    return post(
        c,
        h,
        root + "/construction-workspace/search-terms/generate",
        {
            "expected_revision": w["revision"],
            "model_selection": selection,
            "additional_requirements": "include recent studies",
            "acknowledged_risk_ids": [],
        },
        key,
    )


def test_st04_generate_review_discard_and_no_repeated_suggestions(subject):
    c, h, root, app, engine, key = subject
    manual = add(c, h, root, "manual preserved")
    selection = ready(subject)
    r = start(subject, selection)
    assert r.status_code == 202, r.text
    task = r.json()["data"]
    fake = FakeTerms()
    worker = TermWorker(app.state.term_store, fake)
    assert worker.run_once() and fake.calls == 1
    view = c.get(task["status_url"]).json()["data"]
    assert view["execution_status"] == "succeeded"
    assert view["project_id"] == root.split("/")[-1]
    items = c.get(root + "/construction-workspace/search-terms").json()["data"]["items"]
    candidate = next(x for x in items if x["status"] == "candidate")
    assert next(x for x in items if x["id"] == manual["id"])["query"] == "manual preserved"
    assert candidate["confirmed_revision"] is None
    assert (
        post(
            c,
            h,
            root + "/construction-workspace/search-terms/" + candidate["id"] + "/discard",
            {"expected_revision": candidate["revision"]},
            "discard-candidate01",
        ).status_code
        == 200
    )
    assert start(subject, selection, "generate-second-001").status_code == 202
    worker.run_once()
    assert len(c.get(root + "/construction-workspace/search-terms").json()["data"]["items"]) == 1
    with engine.connect() as conn:
        assert "SECRET-TERM-KEY" not in json.dumps(conn.scalar(sa.select(states.c.payload)))


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_st06_policy_tightening_prevents_dispatch_or_commit(subject, boundary):
    c, h, root, app, engine, key = subject
    selection = ready(subject)
    r = start(subject, selection)
    assert r.status_code == 202, r.text

    def revoke():
        policy = c.get(root + "/material-policy").json()["data"]
        assert (
            c.put(
                root + "/material-policy",
                headers=h,
                json={
                    "expected_revision": policy["revision"],
                    "mode": "public_only",
                    "risk_acknowledged": False,
                },
            ).status_code
            == 200
        )

    fake = FakeTerms(**{boundary: revoke})
    TermWorker(app.state.term_store, fake).run_once()
    task = c.get(r.json()["data"]["status_url"]).json()["data"]
    assert task["execution_status"] == "failed"
    assert fake.calls == (0 if boundary == "before" else 1)
    assert c.get(root + "/construction-workspace/search-terms").json()["data"]["items"] == []


def test_st06_unclassified_topic_never_implicitly_authorized(subject):
    c, h, root, app, engine, key = subject
    response = start(subject, {"source": "user", "config_id": str(UUID(int=1)), "model_id": "fake"})
    assert response.status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(states)) == 0


def test_st02_confirmation_survives_process_restart_and_rejects_malformed(subject):
    c, h, root, app, engine, key = subject
    term = add(c, h, root)
    path = root + "/construction-workspace/search-terms/" + term["id"] + "/confirm"
    other = TestClient(create_business_app(engine, ORIGIN, key), base_url=ORIGIN)
    other.cookies.update(c.cookies)
    body = {"expected_revision": term["revision"], "acknowledged_risk_ids": []}
    for index, token in enumerate([123, [], {}, "invalid", "☃.☃"]):
        response = post(
            other, h, path, body | {"confirmation_token": token}, f"bad-token-value-{index:04d}"
        )
        assert response.status_code == 409, response.text
    response = post(
        other,
        h,
        path,
        body | {"confirmation_token": term["confirmations"][0]["confirmation_token"]},
    )
    assert response.status_code == 200, response.text


def test_st01_pagination_and_revision_race(subject):
    from concurrent.futures import ThreadPoolExecutor

    c, h, root, app, engine, key = subject
    items = [add(c, h, root, f"term-{i}", f"pagination-term-{i:04d}") for i in range(3)]
    path = root + "/construction-workspace/search-terms"
    first = c.get(path, params={"page_size": 2}).json()
    assert len(first["data"]["items"]) == 2 and first["meta"]["has_more"]
    second = c.get(path, params={"cursor": first["meta"]["next_cursor"]}).json()
    assert len(second["data"]["items"]) == 1 and not second["meta"]["has_more"]
    assert c.get(path, params={"cursor": "bad"}).status_code == 400
    assert c.get(path, params={"page_size": 101}).status_code == 422

    def edit(query):
        client = TestClient(app, base_url=ORIGIN)
        client.cookies.update(c.cookies)
        return client.patch(
            path + "/" + items[0]["id"],
            headers=h,
            json={"expected_revision": items[0]["revision"], "query": query},
        ).status_code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(edit, ["winner-a", "winner-b"])) == [200, 412]


def test_st04_multiple_projects_commit_to_claimed_project_only(subject):
    c, h, root, app, engine, key = subject
    selection = ready(subject)
    task = start(subject, selection).json()["data"]
    second = create(c, h, key="second-project-00001").json()["data"]
    second_root = "/api/v1/projects/" + second["id"]
    add(c, h, second_root, "other project manual")
    fake = FakeTerms()
    assert TermWorker(app.state.term_store, fake).run_once()
    assert c.get(task["status_url"]).json()["data"]["execution_status"] == "succeeded"
    assert len(c.get(root + "/construction-workspace/search-terms").json()["data"]["items"]) == 1
    other = c.get(second_root + "/construction-workspace/search-terms").json()["data"]["items"]
    assert len(other) == 1 and other[0]["query"] == "other project manual"


def test_st04_expired_running_attempt_is_not_resent(subject):
    from datetime import UTC, datetime, timedelta

    c, h, root, app, engine, key = subject
    selection = ready(subject)
    task = start(subject, selection).json()["data"]
    with engine.begin() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        state["jobs"][task["task_id"]].update(
            state="running", lease_until=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        )
        conn.execute(states.update().values(payload=state))
    fake = FakeTerms()
    assert not TermWorker(app.state.term_store, fake).run_once()
    result = c.get(task["status_url"]).json()["data"]
    assert result["execution_status"] == "failed"
    assert result["error"]["code"] == "PROVIDER_FAILED" and fake.calls == 0
    with engine.connect() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        assert state["jobs"][task["task_id"]]["error"] == "PROVIDER_RESULT_UNKNOWN"


def test_st06_audit_provenance_and_no_overwrite(subject):
    c, h, root, app, engine, key = subject
    manual = add(c, h, root, "manual")
    selection = ready(subject)
    task = start(subject, selection).json()["data"]

    def edit():
        assert (
            c.patch(
                root + "/construction-workspace/search-terms/" + manual["id"],
                headers=h,
                json={"expected_revision": manual["revision"], "query": "human latest"},
            ).status_code
            == 200
        )

    TermWorker(app.state.term_store, FakeTerms(after=edit)).run_once()
    with engine.connect() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        job = state["jobs"][task["task_id"]]
        assert [x["boundary"] for x in job["material_audit"]] == [
            "accept",
            "read",
            "dispatch",
            "commit",
        ]
        assert all(
            x["permitted"] and x["policy_revision"] and x["classification_revision"]
            for x in job["material_audit"]
        )
        assert state["terms"][manual["id"]]["query"] == "human latest"
        generated = state["terms"][job["term_ids"][0]]
        assert generated["source_dependencies"]["submission_scope_id"] == task["task_id"]
        assert job["input"]["submission_project_id"] == root.split("/")[-1]


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_st06_disabled_then_enabled_account_cannot_revive_task(subject, boundary):
    from test_admin_accounts import update

    c, h, root, app, engine, key = subject
    # Alice is initial administrator; a second admin performs the governance action.
    from rpb.adapters.account import accounts

    admin = TestClient(app, base_url=ORIGIN)
    ah = csrf(admin)
    aid = register(admin, ah, "Governor", "governor@example.invalid").json()["data"]["id"]
    with engine.begin() as conn:
        conn.execute(accounts.update().where(accounts.c.id == UUID(aid)).values(is_admin=True))
    login(admin, ah, "Governor")
    ah = csrf(admin)
    actor = c.get("/api/v1/me").json()["data"]
    revoked = update(admin, ah, actor, "revoke_admin")
    assert revoked.status_code == 200, revoked.text
    actor = revoked.json()["data"]
    selection = ready(subject)
    task = start(subject, selection).json()["data"]

    def revoke_restore():
        disabled = update(admin, ah, actor, "disable")
        assert disabled.status_code == 200, disabled.text
        enabled = update(admin, ah, disabled.json()["data"], "enable")
        assert enabled.status_code == 200, enabled.text

    fake = FakeTerms(**{boundary: revoke_restore})
    TermWorker(app.state.term_store, fake).run_once()
    login(c, csrf(c), "Alice")
    result = c.get(task["status_url"]).json()["data"]
    assert result["execution_status"] == "cancelled"
    assert fake.calls == (0 if boundary == "before" else 1)
    assert c.get(root + "/construction-workspace/search-terms").json()["data"]["items"] == []


def test_st05_accept_generated_preserves_source_history_and_discard_minimal(subject):
    c, h, root, app, engine, key = subject
    selection = ready(subject)
    assert start(subject, selection).status_code == 202
    TermWorker(app.state.term_store, FakeTerms()).run_once()
    path = root + "/construction-workspace/search-terms"
    term = c.get(path).json()["data"]["items"][0]
    result = post(
        c,
        h,
        path + "/" + term["id"] + "/confirm",
        {
            "expected_revision": term["revision"],
            "confirmation_token": term["confirmations"][0]["confirmation_token"],
            "acknowledged_risk_ids": [],
        },
    ).json()["data"]
    assert result["status"] == "accepted" and result["content_state"] == "manual_confirm"
    assert (
        c.patch(
            path + "/" + term["id"],
            headers=h,
            json={"expected_revision": term["revision"], "query": "edited human"},
        ).status_code
        == 200
    )
    with engine.connect() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        history = state["terms"][term["id"]]["confirmation_history"][0]
        assert history["content_state"] == "manual_confirm" and history["modified_by"] is None
        assert history["content"]["query"] == "generated query"
    assert start(subject, selection, "generate-discard-0001").status_code == 202
    TermWorker(app.state.term_store, FakeTerms()).run_once()
    candidate = next(v for v in c.get(path).json()["data"]["items"] if v["status"] == "candidate")
    url = path + "/" + candidate["id"] + "/discard"
    body = {"expected_revision": candidate["revision"]}
    response = post(c, h, url, body)
    assert response.status_code == 200
    assert post(c, h, url, body).json()["data"] == response.json()["data"]
    with engine.connect() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        assert candidate["id"] not in state["terms"]
        assert len(state["discarded"][0]) == 64


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_st04_model_deleted_at_boundary_never_commits(subject, boundary):
    c, h, root, app, engine, key = subject
    selection = ready(subject)
    task = start(subject, selection).json()["data"]

    def remove():
        config = c.get("/api/v1/me/llm-configs/" + selection["config_id"]).json()["data"]
        result = c.delete(
            "/api/v1/me/llm-configs/" + selection["config_id"],
            headers=h | {"Content-Type": "application/json"},
            params={"expected_revision": config["revision"]},
        )
        assert result.status_code == 204, result.text

    fake = FakeTerms(**{boundary: remove})
    TermWorker(app.state.term_store, fake).run_once()
    assert fake.calls == (0 if boundary == "before" else 1)
    assert c.get(task["status_url"]).json()["data"]["execution_status"] == "failed"
    assert c.get(root + "/construction-workspace/search-terms").json()["data"]["items"] == []


def test_st04_concurrent_workers_dispatch_once_and_receipt_replay(subject):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    c, h, root, app, engine, key = subject
    selection = ready(subject)
    response = start(subject, selection)
    task = response.json()["data"]
    # Exact original command, including original revision, must recover the same Task.
    original = json.loads(response.request.content)
    replay = post(
        c,
        h,
        root + "/construction-workspace/search-terms/generate",
        original,
        "generate-terms-0001",
    )
    assert replay.json()["data"]["task_id"] == task["task_id"]
    entered, release = Event(), Event()

    def hold():
        entered.set()
        assert release.wait(10)

    fake = FakeTerms(after=hold)
    worker = TermWorker(app.state.term_store, fake)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(worker.run_once)
        assert entered.wait(10)
        assert not pool.submit(worker.run_once).result(10)
        release.set()
        assert first.result(10)
    assert fake.calls == 1
    assert c.get(task["status_url"]).json()["data"]["execution_status"] == "succeeded"


@pytest.mark.parametrize("bad", [None, [], {"mode": []}, {"mode": "selected", "source_refs": []}])
def test_st03_invalid_source_policy_has_no_write(subject, bad):
    c, h, root, app, engine, key = subject
    path = root + "/construction-workspace/search-terms"
    response = post(c, h, path, {"query": "no write", "source_policy": bad})
    assert response.status_code == 422
    assert c.get(path).json()["data"]["items"] == []


def test_st03_selected_refs_persist_exactly_without_resolution_or_schedule(subject):
    c, h, root, app, engine, key = subject
    policy = {
        "mode": "selected",
        "source_refs": [{"source": "system", "config_id": str(UUID(int=1))}],
    }
    response = post(
        c,
        h,
        root + "/construction-workspace/search-terms",
        {"query": "future source", "source_policy": policy, "auto_update_enabled": False},
    )
    assert response.status_code == 201
    term = response.json()["data"]
    assert term["source_policy"] == policy and term["auto_update_enabled"] is False
    workspace = c.get(root + "/construction-workspace").json()["data"]
    assert workspace["scheduler_available"] is False and workspace["generation_tasks"] == []


def test_st08_nonempty_migration_downgrade_refused_and_project_cleanup_cascades(subject, db):
    from test_account_storage import migrate

    from rpb.adapters.project import construction_workspaces, projects

    c, h, root, app, engine, key = subject
    add(c, h, root)
    with pytest.raises(RuntimeError, match="Refusing"):
        migrate(engine, db[1], "downgrade", "0012_platform_mail")
    with engine.begin() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0013_search_terms"
        )
        conn.execute(
            sa.text("DELETE FROM project_create_commands WHERE project_id=:id"),
            {"id": UUID(root.split("/")[-1])},
        )
        conn.execute(
            construction_workspaces.delete().where(
                construction_workspaces.c.project_id == UUID(root.split("/")[-1])
            )
        )
        conn.execute(projects.delete().where(projects.c.id == UUID(root.split("/")[-1])))
        assert conn.scalar(sa.select(sa.func.count()).select_from(states)) == 0


def test_st01_cursor_survives_application_instance(subject):
    c, h, root, app, engine, key = subject
    for i in range(3):
        add(c, h, root, f"page {i}", f"cursor-instance-{i:04d}")
    path = root + "/construction-workspace/search-terms"
    first = c.get(path, params={"page_size": 1}).json()
    other = TestClient(create_business_app(engine, ORIGIN, key), base_url=ORIGIN)
    other.cookies.update(c.cookies)
    second = other.get(path, params={"cursor": first["meta"]["next_cursor"]})
    assert second.status_code == 200, second.text
    assert len(second.json()["data"]["items"]) == 2
    assert first["data"]["items"][0]["id"] not in [x["id"] for x in second.json()["data"]["items"]]


def test_st07_recent_task_projection_uses_creation_time_after_jsonb_roundtrip(subject):
    from copy import deepcopy
    from uuid import uuid4

    c, h, root, app, engine, key = subject
    selection = ready(subject)
    current = start(subject, selection).json()["data"]
    with engine.begin() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        original = state["jobs"][current["task_id"]]
        for i in range(21):
            job = deepcopy(original)
            job.update(id=str(uuid4()), created_at=f"2026-01-01T00:00:{i:02d}Z", state="failed")
            state["jobs"][job["id"]] = job
        conn.execute(states.update().values(payload=state))
    tasks = c.get(root + "/construction-workspace").json()["data"]["generation_tasks"]
    assert len(tasks) == 20 and tasks[-1]["task_id"] == current["task_id"]
    assert tasks[-1]["execution_status"] == "queued"
    assert [j["created_at"] for j in tasks] == sorted(j["created_at"] for j in tasks)


@pytest.mark.parametrize("boundary", ["queued", "dispatch"])
def test_st06_rejected_read_or_dispatch_has_current_audit(subject, boundary):
    c, h, root, app, engine, key = subject
    selection = ready(subject)
    task = start(subject, selection).json()["data"]

    def revoke():
        policy = c.get(root + "/material-policy").json()["data"]
        result = c.put(
            root + "/material-policy",
            headers=h,
            json={
                "expected_revision": policy["revision"],
                "mode": "public_only",
                "risk_acknowledged": False,
            },
        )
        assert result.status_code == 200

    if boundary == "queued":
        revoke()
    fake = FakeTerms(before=revoke if boundary == "dispatch" else None)
    TermWorker(app.state.term_store, fake).run_once()
    assert fake.calls == 0
    policy = c.get(root + "/material-policy").json()["data"]
    with engine.connect() as conn:
        state = conn.scalar(sa.select(states.c.payload))
        audit = state["jobs"][task["task_id"]]["material_audit"]
        rejected = [a for a in audit if a.get("outcome") == "rejected"]
        assert rejected and rejected[0]["policy_revision"] == policy["revision"]
        assert rejected[0]["boundary"] == ("read" if boundary == "queued" else "dispatch")
        assert not rejected[0]["permitted"]


@pytest.mark.parametrize(
    "content_type,body,status",
    [("text/plain", "x", 415), ("application/json", "x" * (1024 * 1024 + 1), 413)],
)
def test_st08_public_transport_error_is_bound(subject, content_type, body, status):
    c, h, root, app, engine, key = subject
    response = c.post(
        root + "/construction-workspace/search-terms",
        headers=h | {"Content-Type": content_type, "Idempotency-Key": "transport-error001"},
        content=body,
    )
    assert response.status_code == status


def test_st02_confirmation_expiry_target_scope_and_transaction_rollback(subject, monkeypatch):
    import base64
    import hashlib
    import hmac

    import rpb.adapters.search_terms as adapter

    c, h, root, app, engine, key = subject
    terms = [add(c, h, root, f"target {i}", f"confirm-scope-{i:04d}") for i in range(2)]
    path = root + "/construction-workspace/search-terms/"

    def body(term, token=None):
        return {
            "expected_revision": term["revision"],
            "acknowledged_risk_ids": [],
            "confirmation_token": token or term["confirmations"][0]["confirmation_token"],
        }

    assert (
        post(
            c,
            h,
            path + terms[1]["id"] + "/confirm",
            body(terms[1], terms[0]["confirmations"][0]["confirmation_token"]),
            "wrong-target-key01",
        ).status_code
        == 409
    )
    with engine.connect() as conn:
        secret = conn.scalar(sa.select(states.c.payload))["terms"][terms[0]["id"]][
            "confirmation_secret"
        ]
    raw, _ = terms[0]["confirmations"][0]["confirmation_token"].split(".")
    payload = json.loads(base64.urlsafe_b64decode(raw))
    payload[-1] = 1
    expired = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    expired += "." + hmac.new(secret.encode(), expired.encode(), hashlib.sha256).hexdigest()
    assert (
        post(
            c,
            h,
            path + terms[0]["id"] + "/confirm",
            body(terms[0], expired),
            "expired-target-key01",
        ).status_code
        == 409
    )

    def fail(*args):
        raise RuntimeError("database write failure - must not expose this")

    with monkeypatch.context() as patch:
        patch.setattr(adapter, "save", fail)
        result = post(
            c, h, path + terms[0]["id"] + "/confirm", body(terms[0]), "rollback-target-key01"
        )
        assert result.status_code == 500 and "database write" not in result.text
    assert c.get(path + terms[0]["id"]).json()["data"]["confirmed_revision"] is None
    # The same key on distinct target resources is a distinct idempotency scope.
    for term in terms:
        assert (
            post(
                c, h, path + term["id"] + "/confirm", body(term), "shared-target-key01"
            ).status_code
            == 200
        )
