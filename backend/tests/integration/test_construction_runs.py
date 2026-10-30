# ruff: noqa: F811
"""CR acceptance, actual commits, frozen inputs and terminal-state fencing."""

import sqlalchemy as sa
from jsonschema import Draft202012Validator, FormatChecker
from test_account_auth import SPEC
from test_search_terms import add, post, ready, subject  # noqa: F401

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.run_tables import runs
from rpb.adapters.run_worker import RunWorker


class Papers:
    def __init__(self, failure=False, hook=None):
        self.calls = []
        self.failure, self.hook = failure, hook

    def search(self, config, secret, query, window, limit, authorize):
        if self.hook:
            self.hook()
        with authorize(secret()):
            self.calls.append((query, limit))
        if self.failure:
            raise ProviderFailure("PROVIDER_TIMEOUT")
        return {
            "items": [
                {
                    "title": query,
                    "authors": ["Author"],
                    "year": 2026,
                    "abstract": "Research result",
                    "doi": None,
                    "arxiv_id": "2601.00001",
                    "url": "https://arxiv.org/abs/2601.00001",
                }
            ]
        }


def setup(subject):
    c, h, root, app, engine, key = subject
    selection = ready(subject, materials=False)
    r = post(
        c,
        h,
        "/api/v1/me/data-source-configs",
        {
            "name": "arxiv",
            "provider": "arxiv",
            "base_url": "https://export.arxiv.org/api",
            "access_mode": "anonymous",
            "enabled": True,
        },
        "construction-source-0001",
    )
    assert r.status_code == 201, r.text
    term = add(c, h, root)
    r = post(
        c,
        h,
        root + "/construction-workspace/search-terms/" + term["id"] + "/confirm",
        {
            "expected_revision": term["revision"],
            "confirmation_token": term["confirmations"][0]["confirmation_token"],
            "acknowledged_risk_ids": [],
        },
        "construction-term-confirm",
    )
    assert r.status_code == 200, r.text
    body = {
        "selected_terms": [{"term_id": term["id"], "confirmed_revision": term["revision"]}],
        "retrieval_range": {"published_from": None, "published_until": None},
        "result_limit_per_source": 100,
        "model_selection": selection,
    }
    return body, term


def test_cr01_start_freeze_history_cancel_and_no_publish(subject):
    c, h, root, app, engine, _ = subject
    body, term = setup(subject)
    path = root + "/construction-runs"
    r = post(c, h, path, body, "construction-start-0001")
    assert r.status_code == 202, r.text
    accepted = r.json()["data"]
    assert accepted["run"]["status"] == "queued"
    assert accepted["run"]["input_snapshot"] is None
    assert post(c, h, path, body, "construction-start-0001").json()["data"] == accepted
    assert (
        post(
            c, h, path, body | {"result_limit_per_source": 99}, "construction-start-0001"
        ).status_code
        == 409
    )
    provider = Papers()
    assert RunWorker(app.state.run_store, provider).run_once()
    run_url = path + "/" + accepted["run"]["id"]
    current = c.get(run_url).json()["data"]
    Draft202012Validator(
        {"$ref": "#/components/schemas/RetrievalRunView", "components": SPEC["components"]},
        format_checker=FormatChecker(),
    ).validate(current)
    assert current["status"] == "waiting_user"
    assert current["published_knowledge_version_id"] is None and current["completion"] is None
    assert current["input_snapshot"]["selected_terms"][0]["content"]["query"] == "graph"
    assert "SECRET-TERM-KEY" not in str(current)
    assert len(c.get(run_url + "/candidates").json()["data"]["items"]) == 1
    assert (
        c.get(root + "/construction-workspace").json()["data"]["occupying_run_id"] == current["id"]
    )
    assert post(c, h, path, body, "construction-start-0002").status_code == 409
    edited = c.patch(
        root + "/construction-workspace/search-terms/" + term["id"],
        headers=h,
        json={"expected_revision": term["revision"], "query": "new"},
    )
    assert edited.status_code == 200
    assert c.get(run_url).json()["data"]["input_snapshot"] == current["input_snapshot"]
    cancelled = post(
        c,
        h,
        run_url + "/cancel",
        {"expected_revision": current["revision"], "attempt_id": current["task"]["attempt_id"]},
        "construction-cancel-0001",
    )
    assert cancelled.status_code == 200, cancelled.text
    end = cancelled.json()["data"]["run"]
    assert end["status"] == "cancelled" and end["candidate_version"]["state"] == "discarded"
    assert c.get(run_url + "/candidates").json()["data"]["items"] == []
    assert c.get(root + "/construction-workspace").json()["data"]["occupying_run_id"] is None
    assert c.get(accepted["task"]["status_url"]).json()["data"]["execution_status"] == "cancelled"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(runs)) == 1


def test_cr02_no_sources_or_unconfirmed_no_orphan(subject):
    c, h, root, app, engine, _ = subject
    body, term = setup(subject)
    sources = c.get("/api/v1/me/data-source-configs").json()["data"]["items"]
    src = sources[0]
    assert (
        c.patch(
            "/api/v1/me/data-source-configs/" + src["id"],
            headers=h,
            json={"expected_revision": src["revision"], "enabled": False},
        ).status_code
        == 200
    )
    r = post(c, h, root + "/construction-runs", body, "construction-start-0001")
    assert r.status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(runs)) == 0


def test_cr03_all_failed_no_waiting_or_success(subject):
    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    started = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    assert RunWorker(app.state.run_store, Papers(failure=True)).run_once()
    run = c.get(root + "/construction-runs/" + started["run"]["id"]).json()["data"]
    assert run["status"] == "failed" and run["completion"] is None
    assert run["steps"][0]["result_summary"]["sources"][0]["error"] == "PROVIDER_TIMEOUT"


def test_cr04_late_provider_after_cancel_cannot_commit(subject):
    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    accepted = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    path = root + "/construction-runs/" + accepted["run"]["id"]

    def cancel():
        run = c.get(path).json()["data"]
        assert (
            post(
                c,
                h,
                path + "/cancel",
                {"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
                "construction-cancel-0001",
            ).status_code
            == 200
        )

    provider = Papers(hook=cancel)
    assert RunWorker(app.state.run_store, provider).run_once()
    assert provider.calls == []
    assert c.get(path).json()["data"]["status"] == "cancelled"
    assert c.get(path + "/candidates").json()["data"]["items"] == []


def archive(c, h, root):
    project = c.get(root).json()["data"]
    preview = post(
        c,
        h,
        root + "/action-preview",
        {"action": "archive", "expected_revision": project["revision"]},
        "construction-archive-preview",
    ).json()["data"]
    return post(
        c,
        h,
        root + "/archive",
        {
            "expected_revision": project["revision"],
            "confirmation_token": preview["confirmation_token"],
            "acknowledged_risk_ids": [risk["id"] for risk in preview["risks"]],
        },
        "construction-archive-0001",
    )


def test_cr05_archive_waiting_revokes_without_worker(subject):
    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    accepted = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    RunWorker(app.state.run_store, Papers()).run_once()
    assert archive(c, h, root).status_code == 200
    with app.state.run_store.account.engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.status)) == "cancelled"
    assert (
        c.get(root + "/construction-runs/" + accepted["run"]["id"]).json()["data"]["status"]
        == "cancelled"
    )
    assert (
        post(c, h, root + "/construction-runs", body, "construction-start-0002").status_code == 409
    )


def test_cr06_source_disabled_after_acceptance_prevents_dispatch(subject):
    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    accepted = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    src = c.get("/api/v1/me/data-source-configs").json()["data"]["items"][0]
    assert (
        c.patch(
            "/api/v1/me/data-source-configs/" + src["id"],
            headers=h,
            json={"expected_revision": src["revision"], "enabled": False},
        ).status_code
        == 200
    )
    provider = Papers()
    assert not RunWorker(app.state.run_store, provider).run_once()
    assert provider.calls == []
    current = c.get(root + "/construction-runs/" + accepted["run"]["id"]).json()["data"]
    assert current["status"] == "failed" and current["input_snapshot"] is None


def test_cr07_two_queued_workers_one_claim_and_cancel_progress(subject):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    first = post(c, h, path, body, "construction-start-0001").json()["data"]["run"]
    second = post(c, h, path, body, "construction-start-0002").json()["data"]["run"]
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    provider = Papers(hook=pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(RunWorker(app.state.run_store, provider).run_once)
        assert entered.wait(10)
        assert not RunWorker(app.state.run_store, Papers()).run_once()
        release.set()
        assert future.result(10)
    assert len(provider.calls) == 1
    current = c.get(path + "/" + first["id"]).json()["data"]
    assert current["status"] == "waiting_user"
    assert c.get(path + "/" + second["id"]).json()["data"]["status"] == "queued"
    assert (
        post(
            c,
            h,
            path + "/" + first["id"] + "/cancel",
            {"expected_revision": current["revision"], "attempt_id": current["task"]["attempt_id"]},
            "construction-cancel-0001",
        ).status_code
        == 200
    )
    # Simulate elapsed provider pacing, without external calls or test sleeps.
    from rpb.adapters.source_tables import dispatch_limits

    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(app.state.run_store, Papers()).run_once()
    assert c.get(path + "/" + second["id"]).json()["data"]["status"] == "waiting_user"


def test_cr08_expired_attempt_not_resent(subject):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters.runs import persist

    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    post(c, h, root + "/construction-runs", body, "construction-start-0001")
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run.update(
            status="running", lease_until=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        )
        persist(conn, run)
    provider = Papers()
    assert not RunWorker(app.state.run_store, provider).run_once()
    assert provider.calls == []
    with engine.connect() as conn:
        value = conn.scalar(sa.select(runs.c.payload))
        assert value["status"] == "failed" and value["error"] == "PROVIDER_RESULT_UNKNOWN"


def test_cr09_invalid_wire_never_creates_run(subject):
    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    for patch in (
        {"supplement_ids": None},
        {"supplement_ids": False},
        {"supplement_ids": ""},
        {"graph_mode": []},
        {"graph_mode": {}},
        {"result_limit_per_source": False},
        {"selected_terms": []},
    ):
        r = post(c, h, root + "/construction-runs", body | patch, "construction-invalid-0001")
        assert r.status_code == 422, r.text
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(runs)) == 0


def test_cr10_cross_project_and_actor_reads_rejected(subject):
    from test_project_commands import create

    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    accepted = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    other = create(c, h, key="construction-other-project").json()["data"]
    assert (
        c.get(
            "/api/v1/projects/" + other["id"] + "/construction-runs/" + accepted["run"]["id"]
        ).status_code
        == 404
    )
    assert (
        c.get(
            root + "/construction-runs",
            headers={"X-Expected-Actor": "00000000-0000-4000-8000-000000000001"},
        ).status_code
        == 401
    )
    assert c.post(root + "/construction-runs", json=body).status_code == 403


def test_cr11_partial_source_failure_keeps_healthy_result(subject):
    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    response = post(
        c,
        h,
        "/api/v1/me/data-source-configs",
        {
            "name": "ADS",
            "provider": "ads",
            "base_url": "https://api.adsabs.harvard.edu/v1",
            "access_mode": "api_key",
            "secret": {"operation": "set", "value": "ADS-private-key"},
        },
        "construction-ads-source",
    )
    assert response.status_code == 201, response.text

    class Partial(Papers):
        def search(self, config, secret, query, window, limit, authorize):
            if config["provider"] == "ads":
                from rpb.adapters.paper_retrieval import PaperRetrieval

                class Malformed:
                    def request(self, *args, **kwargs):
                        with args[7]():
                            return {
                                "response": {
                                    "numFound": 1,
                                    "docs": [{"title": [], "bibcode": "id"}],
                                }
                            }

                return PaperRetrieval(Malformed()).search(
                    config, secret, query, window, limit, authorize
                )
            return super().search(config, secret, query, window, limit, authorize)

    accepted = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    assert RunWorker(app.state.run_store, Partial()).run_once()
    run = c.get(root + "/construction-runs/" + accepted["run"]["id"]).json()["data"]
    assert run["status"] == "waiting_user"
    result = run["steps"][0]["result_summary"]
    assert result["candidate_count"] == 1
    assert sorted(x["status"] for x in result["sources"]) == ["failed", "succeeded"]
    assert (
        next(x for x in result["sources"] if x["status"] == "failed")["error"]
        == "PROVIDER_RESPONSE_INVALID"
    )


def test_cr12_selected_failure_is_per_term_and_freezes_diagnostics(subject):
    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    sources = c.get("/api/v1/me/data-source-configs").json()["data"]["items"]
    disabled = post(
        c,
        h,
        "/api/v1/me/data-source-configs",
        {
            "name": "OA",
            "provider": "openalex",
            "base_url": "https://api.openalex.org",
            "access_mode": "anonymous",
            "enabled": False,
        },
        "construction-disabled-source",
    ).json()["data"]
    term = post(
        c,
        h,
        root + "/construction-workspace/search-terms",
        {
            "query": "should not dispatch",
            "source_policy": {
                "mode": "selected",
                "source_refs": [
                    {"source": "user", "config_id": x["id"]} for x in [sources[0], disabled]
                ],
            },
        },
        "construction-selected-term",
    ).json()["data"]
    assert (
        post(
            c,
            h,
            root + "/construction-workspace/search-terms/" + term["id"] + "/confirm",
            {
                "expected_revision": term["revision"],
                "confirmation_token": term["confirmations"][0]["confirmation_token"],
                "acknowledged_risk_ids": [],
            },
            "construction-selected-confirm",
        ).status_code
        == 200
    )
    body["selected_terms"].append({"term_id": term["id"], "confirmed_revision": term["revision"]})
    accepted = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]
    provider = Papers()
    assert RunWorker(app.state.run_store, provider).run_once()
    assert provider.calls == [("graph", 100)]
    run = c.get(root + "/construction-runs/" + accepted["run"]["id"]).json()["data"]
    resolution = run["steps"][0]["result_summary"]["resolution"]
    assert resolution["failed"][0]["term_id"] == term["id"]
    assert (
        resolution["failed"][0]["resolution"]["rejected"][0]["reason_code"]
        == "CONFIG_SOURCE_DISABLED"
    )
    assert len(run["input_snapshot"]["selected_terms"]) == 2
    Draft202012Validator(
        {"$ref": "#/components/schemas/RetrievalRunView", "components": SPEC["components"]},
        format_checker=FormatChecker(),
    ).validate(run)


def test_cr13_receipt_failure_rolls_back_run(subject):
    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    injected = []

    def fail_receipt(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO construction_run_commands"):
            injected.append(True)
            raise RuntimeError("injected receipt failure")

    sa.event.listen(engine, "before_cursor_execute", fail_receipt)
    try:
        response = post(c, h, root + "/construction-runs", body, "construction-start-0001")
        assert response.status_code == 500
        assert injected == [True]
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_receipt)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(runs)) == 0


def test_cr14_db_unique_writer_and_nonempty_downgrade_protection(subject, db):
    import copy
    from uuid import uuid4

    import pytest
    from alembic import command
    from sqlalchemy.exc import IntegrityError

    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    post(c, h, root + "/construction-runs", body, "construction-start-0001")
    assert RunWorker(app.state.run_store, Papers()).run_once()
    with engine.connect() as conn:
        record = dict(conn.execute(sa.select(runs)).mappings().one())
    record["id"] = uuid4()
    record["payload"] = copy.deepcopy(record["payload"])
    record["payload"]["id"] = str(record["id"])
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(runs.insert().values(**record))
    _, cfg = db
    with pytest.raises(RuntimeError, match="Refusing to discard durable Run facts"):
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "0013_search_terms")
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0015_processing_objects"
        )


def test_cr15_project_preview_binds_new_and_changed_run(subject):
    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    project = c.get(root).json()["data"]

    def preview():
        return post(
            c,
            h,
            root + "/action-preview",
            {"action": "archive", "expected_revision": project["revision"]},
        ).json()["data"]

    def execute(p, key):
        return post(
            c,
            h,
            root + "/archive",
            {
                "expected_revision": project["revision"],
                "confirmation_token": p["confirmation_token"],
                "acknowledged_risk_ids": [r["id"] for r in p["risks"]],
            },
            key,
        )

    empty = preview()
    run = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()["data"][
        "run"
    ]
    assert (
        execute(empty, "construction-archive-stale1").json()["error"]["code"]
        == "STATE_CONFIRMATION_STALE"
    )
    queued = preview()
    assert queued["impact_revision"] != empty["impact_revision"]
    assert queued["affected_items"][0]["kind"] == "execution_revocation"
    assert queued["affected_items"][0]["object"]["id"] == run["id"]
    assert RunWorker(app.state.run_store, Papers()).run_once()
    assert execute(queued, "construction-archive-stale2").status_code == 409
    assert preview()["impact_revision"] != queued["impact_revision"]
    assert execute(preview(), "construction-archive-fresh1").status_code == 200
    assert c.get(root + "/construction-runs/" + run["id"]).json()["data"]["status"] == "cancelled"


def test_cr16_admin_preview_binds_private_run_without_disclosure(subject):
    from fastapi.testclient import TestClient
    from test_account_auth import ORIGIN, csrf, login, register
    from test_admin_accounts import BASE, prepare
    from test_project_commands import create

    a, ah, _, app, engine, key = subject
    b = TestClient(app, base_url=ORIGIN)
    bh = csrf(b)
    user = register(b, bh, "Bob", "bob@example.invalid").json()["data"]
    login(b, bh, "Bob")
    bh = csrf(b)
    root = "/api/v1/projects/" + create(b, bh).json()["data"]["id"]
    body, _ = setup((b, bh, root, app, engine, key))
    empty = prepare(a, ah, user, "disable")
    accepted = post(b, bh, root + "/construction-runs", body, "construction-start-0001").json()[
        "data"
    ]["run"]
    url = BASE + "/" + user["id"]
    assert (
        a.patch(url, headers=ah, json={"action": "disable", **empty}).json()["error"]["code"]
        == "STATE_CONFIRMATION_STALE"
    )
    queued = prepare(a, ah, user, "disable")
    assert RunWorker(app.state.run_store, Papers()).run_once()
    assert a.patch(url, headers=ah, json={"action": "disable", **queued}).status_code == 409
    fresh = prepare(a, ah, user, "disable")
    assert accepted["id"] not in str(fresh)
    assert a.patch(url, headers=ah, json={"action": "disable", **fresh}).status_code == 200
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.status)) == "cancelled"


def test_cr17_pagination_scopes_and_cancel_replays(subject):
    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    first = post(c, h, path, body, "construction-start-0001").json()["data"]["run"]
    second = post(c, h, path, body, "construction-start-0002").json()["data"]["run"]
    page1 = c.get(path, params={"page_size": 1}).json()
    cursor = page1["meta"]["next_cursor"]
    page2 = c.get(path, params={"page_size": 1, "cursor": cursor}).json()
    assert {page1["data"]["items"][0]["id"], page2["data"]["items"][0]["id"]} == {
        first["id"],
        second["id"],
    }
    assert page2["meta"]["next_cursor"] is None
    url = path + "/" + first["id"]
    assert (
        c.get(url + "/candidates", params={"cursor": cursor}).json()["error"]["code"]
        == "VALIDATION_CURSOR_MISMATCH"
    )
    assert c.get(url + "/input-revisions").json()["meta"]["has_more"] is False
    body = {"expected_revision": first["revision"], "attempt_id": first["task"]["attempt_id"]}
    cancelled = post(c, h, url + "/cancel", body, "construction-cancel-0001").json()["data"]
    assert post(c, h, url + "/cancel", body, "construction-cancel-0001").json()["data"] == cancelled
    assert post(c, h, url + "/cancel", body, "construction-cancel-0002").status_code == 412
    body["expected_revision"] = cancelled["run"]["revision"]
    assert post(c, h, url + "/cancel", body, "construction-cancel-0003").json()["data"] == cancelled


def test_cr18_cumulative_source_budget_and_candidate_cursor_invalidation(subject):
    c, h, root, app, *_ = subject
    body, _ = setup(subject)
    term = add(c, h, root, "second", "construction-second-term")
    assert (
        post(
            c,
            h,
            root + "/construction-workspace/search-terms/" + term["id"] + "/confirm",
            {
                "expected_revision": term["revision"],
                "confirmation_token": term["confirmations"][0]["confirmation_token"],
                "acknowledged_risk_ids": [],
            },
            "construction-second-confirm",
        ).status_code
        == 200
    )
    body["selected_terms"].append({"term_id": term["id"], "confirmed_revision": term["revision"]})
    body["result_limit_per_source"] = 2

    class Two(Papers):
        def search(self, *args):
            output = super().search(*args)
            output["items"].append(output["items"][0] | {"title": "second paper"})
            return output

    provider = Two()
    run = post(c, h, root + "/construction-runs", body, "construction-start-0001").json()["data"][
        "run"
    ]
    assert RunWorker(app.state.run_store, provider).run_once()
    assert provider.calls == [("graph", 2)]
    url = root + "/construction-runs/" + run["id"]
    run = c.get(url).json()["data"]
    assert [r["status"] for r in run["steps"][0]["result_summary"]["sources"]] == [
        "succeeded",
        "skipped",
    ]
    first = c.get(url + "/candidates", params={"page_size": 1}).json()
    cursor = first["meta"]["next_cursor"]
    second = c.get(url + "/candidates", params={"page_size": 1, "cursor": cursor}).json()
    assert first["data"]["items"][0]["id"] != second["data"]["items"][0]["id"]
    assert second["meta"]["has_more"] is False
    assert (
        post(
            c,
            h,
            url + "/cancel",
            {"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
            "construction-cancel-0001",
        ).status_code
        == 200
    )
    assert (
        c.get(url + "/candidates", params={"cursor": cursor}).json()["error"]["code"]
        == "VALIDATION_CURSOR_MISMATCH"
    )
