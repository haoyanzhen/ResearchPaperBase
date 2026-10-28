# ruff: noqa: F811
"""Real browser, durable HTTP and isolated PG with controlled external providers."""

from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from playwright.sync_api import expect
from test_browser_business import browser_app  # noqa: F401
from test_browser_terms import enter
from test_construction_runs import Papers, setup

from rpb.adapters.run_worker import RunWorker
from rpb.bootstrap import business


def configured_browser(monkeypatch, request):
    key = Fernet.generate_key()
    compose = business.create_business_app
    apps = []

    def configured(engine, origin, encryption_key=None):
        app = compose(engine, origin, key)
        apps.append(app)
        return app

    monkeypatch.setattr(business, "create_business_app", configured)
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    page, _ = enter(browser, base)
    client = TestClient(apps[0], base_url=base)
    for cookie in page.context.cookies():
        client.cookies.set(cookie["name"], cookie["value"])
    headers = {
        "Origin": base,
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"],
    }
    root = "/api/v1/projects/" + page.url.split("project=")[1]
    body, _ = setup((client, headers, root, apps[0], engine, key))
    assert (
        client.put(
            "/api/v1/me/model-selection",
            headers=headers,
            json={
                "selection": body["model_selection"],
                "expected_revision": client.get("/api/v1/me/model-selection").json()["data"][
                    "revision"
                ],
            },
        ).status_code
        == 200
    )
    page.reload()
    region = page.get_by_role("region", name="构建运行", exact=True)
    expect(region.get_by_label("graph", exact=True)).to_be_enabled()
    return page, region, apps[0], client, headers, root


def test_crb01_start_wait_refresh_cancel_mobile_and_logout(monkeypatch, request):
    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    from test_search_terms import post

    source = post(
        client,
        headers,
        "/api/v1/me/data-source-configs",
        {
            "name": "disabled",
            "provider": "openalex",
            "base_url": "https://api.openalex.org",
            "access_mode": "anonymous",
            "enabled": False,
        },
        "browser-disabled-source1",
    ).json()["data"]
    term = post(
        client,
        headers,
        root + "/construction-workspace/search-terms",
        {
            "query": "blocked term",
            "source_policy": {
                "mode": "selected",
                "source_refs": [{"source": "user", "config_id": source["id"]}],
            },
        },
        "browser-blocked-term001",
    ).json()["data"]
    assert (
        post(
            client,
            headers,
            root + "/construction-workspace/search-terms/" + term["id"] + "/confirm",
            {
                "expected_revision": term["revision"],
                "confirmation_token": term["confirmations"][0]["confirmation_token"],
                "acknowledged_risk_ids": [],
            },
            "browser-blocked-confirm1",
        ).status_code
        == 200
    )
    page.reload()
    region.get_by_label("blocked term", exact=True).check()
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, Papers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(region.get_by_role("heading", name="检索结果待确认", exact=True)).to_be_visible()
    expect(region.get_by_text("Research result", exact=True)).to_be_visible()
    expect(region.get_by_text("CONFIG_SOURCE_DISABLED", exact=False)).to_have_count(2)
    expect(region.get_by_text("的部分来源不可用", exact=False)).to_be_visible()
    region.get_by_text("本轮输入与模型", exact=True).click()
    expect(region.get_by_text("本轮模型：user / fake-model", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    out = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task040_construction_runtime_2026-10-28/browser"
    )
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / "run-mobile.png"), full_page=True)
    # Another tab cancels; refresh must not leave the cleaned body on screen.
    run = client.get(root + "/construction-runs").json()["data"]["items"][0]
    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    response = client.post(
        root + "/construction-runs/" + run["id"] + "/cancel",
        headers=headers | {"Idempotency-Key": "browser-other-tab-cancel"},
        json={"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
    )
    assert response.status_code == 200, response.text
    region.get_by_role("button", name="刷新运行与配置", exact=True).click()
    expect(region.get_by_role("heading", name="已取消", exact=True)).to_be_visible()
    expect(region.get_by_text("Research result", exact=True)).to_have_count(0)
    page.reload()
    expect(region.get_by_role("button", name="启动检索", exact=True)).to_be_visible()
    page.get_by_role("button", name="退出登录", exact=True).click()
    expect(region).to_have_count(0)
    page.close()


def test_crb02_accepted_http_500_replays_original_command(monkeypatch, request):
    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    keys = []

    def fail_response(route):
        if route.request.method == "POST":
            keys.append(route.request.headers["idempotency-key"])
            response = route.fetch()
            assert response.status == 202
            if len(keys) == 1:
                route.fulfill(
                    status=500,
                    content_type="application/json",
                    body='{"error":{"code":"INTERNAL_ERROR","message":"unknown"}}',
                )
            else:
                route.fulfill(response=response)
        else:
            route.continue_()

    page.route("**/construction-runs", fail_response)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("button", name="用原请求核查重试", exact=True)).to_be_enabled()
    expect(region.get_by_role("button", name="启动检索", exact=True)).to_be_disabled()
    region.get_by_role("button", name="用原请求核查重试", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    assert len(client.get(root + "/construction-runs").json()["data"]["items"]) == 1
    region.get_by_role("button", name="取消本次构建", exact=True).click()
    expect(region.get_by_role("heading", name="已取消", exact=True)).to_be_visible()
    page.close()
