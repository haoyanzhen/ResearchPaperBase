# ruff: noqa: F811
"""ST07 real browser and isolated PG; loss and conflict use committed HTTP writes."""

from pathlib import Path

from playwright.sync_api import expect
from test_browser_business import browser_app, login_ui, register_ui  # noqa: F401


def enter(browser, base):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("pageerror", lambda error: print("TERM PAGE ERROR:", error))
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Term research")
    page.get_by_label("描述", exact=True).fill("Research description")
    page.get_by_label("研究范围", exact=True).fill("Research scope")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    region = page.get_by_role("region", name="构建检索词", exact=True)
    expect(region.get_by_role("button", name="添加检索词", exact=True)).to_be_enabled()
    return page, region


def test_stb01_manual_confirm_edit_reload_mobile_and_logout(browser_app):
    browser, base, engine, run_id = browser_app
    page, region = enter(browser, base)
    region.get_by_label("查询表达式", exact=True).fill("graph AND evidence")
    region.get_by_label("自然语言关键词（每行一项）", exact=True).fill("graph\nevidence")
    region.get_by_role("button", name="添加检索词", exact=True).click()
    card = region.get_by_role("article", name="检索词 graph AND evidence", exact=True)
    expect(card).to_be_visible()
    card.get_by_role("button", name="确认此词", exact=True).click()
    expect(card.get_by_text("长期检索词 · 已确认 · 人工修改", exact=True)).to_be_visible()
    card.get_by_role("button", name="编辑此词", exact=True).click()
    region.get_by_label("查询表达式", exact=True).fill("human edited")
    region.get_by_role("button", name="保存词修改", exact=True).click()
    expect(region.get_by_role("article", name="检索词 human edited", exact=True)).to_be_visible()
    page.reload()
    expect(region.get_by_role("article", name="检索词 human edited", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    out = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task037_search_terms_2026-10-28/browser"
    )
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / "terms-mobile.png"), full_page=True)
    page.get_by_role("button", name="退出登录", exact=True).click()
    expect(region).to_have_count(0)
    register_ui(page, base, "Other", "other@example.invalid")
    login_ui(page, "Other")
    expect(page.get_by_text("human edited", exact=True)).to_have_count(0)
    page.close()


def test_stb02_unknown_post_replays_one_write(browser_app):
    browser, base, engine, run_id = browser_app
    page, region = enter(browser, base)
    commands = []

    def lose(route):
        if route.request.method == "POST":
            commands.append(route.request.headers["idempotency-key"])
            response = route.fetch()
            assert response.status == 201
            if len(commands) == 1:
                route.abort("failed")
            else:
                route.fulfill(response=response)
        else:
            route.continue_()

    page.route("**/construction-workspace/search-terms", lose)
    region.get_by_label("查询表达式", exact=True).fill("lost response")
    region.get_by_role("button", name="添加检索词", exact=True).click()
    region.get_by_role("button", name="用原请求核查结果", exact=True).click()
    expect(region.get_by_role("article", name="检索词 lost response", exact=True)).to_have_count(1)
    assert len(commands) == 2 and commands[0] == commands[1]
    page.close()


def test_stb03_conflict_preserves_draft_and_requires_explicit_reload(browser_app):
    browser, base, engine, run_id = browser_app
    page, region = enter(browser, base)
    region.get_by_label("查询表达式", exact=True).fill("original")
    region.get_by_role("button", name="添加检索词", exact=True).click()
    region.get_by_role("button", name="编辑此词", exact=True).click()
    region.get_by_label("查询表达式", exact=True).fill("my draft")

    def conflict(route):
        if route.request.method == "PATCH":
            body = route.request.post_data_json
            response = route.fetch(post_data={**body, "query": "other writer"})
            assert response.status == 200
            route.continue_()
            page.unroute("**/construction-workspace/search-terms/*", conflict)
        else:
            route.continue_()

    page.route("**/construction-workspace/search-terms/*", conflict)
    region.get_by_role("button", name="保存词修改", exact=True).click()
    region.get_by_role("button", name="加载最新内容并保留草稿", exact=True).click()
    expect(region.get_by_label("查询表达式", exact=True)).to_have_value("my draft")
    expect(region.get_by_role("article", name="检索词 other writer", exact=True)).to_be_visible()
    region.get_by_role("button", name="保存词修改", exact=True).click()
    expect(region.get_by_role("article", name="检索词 my draft", exact=True)).to_be_visible()
    page.close()


def test_stb04_generate_review_batch_pagination_and_private_policy(db, monkeypatch, request):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient
    from test_search_terms import FakeTerms, ready

    from rpb.adapters.search_term_worker import TermWorker
    from rpb.bootstrap import business

    key = Fernet.generate_key()
    compose = business.create_business_app
    apps = []

    def configured(engine, origin, encryption_key=None):
        app = compose(engine, origin, key)
        apps.append(app)
        return app

    monkeypatch.setattr(business, "create_business_app", configured)
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    page, region = enter(browser, base)
    # Configure a fake tested model through the same application; no real provider is invoked.
    client = TestClient(apps[0], base_url=base)
    for cookie in page.context.cookies():
        client.cookies.set(cookie["name"], cookie["value"])
    headers = {
        "Origin": base,
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"],
    }
    project_id = page.url.split("project=")[1]
    root = "/api/v1/projects/" + project_id
    subject = client, headers, root, apps[0], engine, key
    selection = ready(subject, materials=False)
    assert (
        client.put(
            "/api/v1/me/model-selection",
            headers=headers,
            json={
                "selection": selection,
                "expected_revision": client.get("/api/v1/me/model-selection").json()["data"][
                    "revision"
                ],
            },
        ).status_code
        == 200
    )
    page.reload()
    region.get_by_text("主题资料分类与Agent使用范围", exact=True).click()
    region.get_by_label("分类依据", exact=True).fill("Owner confirmed research topic")
    region.get_by_role("button", name="确认主题资料分类", exact=True).click()
    expect(
        region.get_by_text("主题分类：已确认私人；Agent范围：仅公开资料", exact=True)
    ).to_be_visible()
    expect(region.get_by_role("button", name="允许本Project私人资料", exact=True)).to_be_disabled()
    region.get_by_label("我理解所选模型服务可能收到本Project私人内容", exact=True).check()
    region.get_by_role("button", name="允许本Project私人资料", exact=True).click()
    expect(
        region.get_by_text("主题分类：已确认私人；Agent范围：允许私人资料", exact=True)
    ).to_be_visible()
    region.get_by_label("本次补充要求", exact=True).fill("Only this command")

    class Many(FakeTerms):
        def __init__(self, prefix):
            super().__init__()
            self.prefix = prefix

        def generate(self, config, model, secret, inputs, authorize):
            super().generate(config, model, secret, inputs, authorize)
            return [{"query": f"{self.prefix}-{i:02d}"} for i in range(15)]

    for prefix in ["first", "second"]:
        region.get_by_role("button", name="生成检索词建议", exact=True).click()
        expect(region.get_by_text("生成任务：排队中", exact=False)).to_be_visible()
        assert TermWorker(apps[0].state.term_store, Many(prefix)).run_once()
        region.get_by_role("button", name="刷新检索词", exact=True).click()
        expect(region.get_by_role("button", name="生成检索词建议", exact=True)).to_be_enabled()
    region.get_by_role("button", name="加载更多检索词", exact=True).click()
    region.get_by_label("选择候选 second-14", exact=True).check()
    # A queued third generation triggers polling while the selected item is on page two.
    region.get_by_role("button", name="生成检索词建议", exact=True).click()
    expect(region.get_by_text("生成任务：排队中", exact=False)).to_be_visible()
    page.wait_for_timeout(1800)
    expect(region.get_by_label("选择候选 second-14", exact=True)).to_be_checked()
    region.get_by_label("选择候选 second-13", exact=True).check()
    confirmations = []

    def second_conflict(route):
        confirmations.append(route.request.url)
        if len(confirmations) == 2:
            body = route.request.post_data_json
            response = route.fetch(
                method="PATCH",
                url=route.request.url.removesuffix("/confirm"),
                post_data={
                    "expected_revision": body["expected_revision"],
                    "rationale": "concurrent edit",
                },
            )
            assert response.status == 200
        route.continue_()

    page.route("**/search-terms/*/confirm", second_conflict)
    region.get_by_role("button", name="接受并确认所选候选", exact=True).click()
    region.get_by_role("button", name="加载最新内容并保留草稿", exact=True).click()
    expect(
        region.get_by_role("article", name="检索词 second-13", exact=True).get_by_text(
            "长期检索词 · 已确认 · 人工确认", exact=True
        )
    ).to_be_visible()
    expect(region.get_by_label("选择候选 second-14", exact=True)).to_be_checked()
    page.unroute("**/search-terms/*/confirm", second_conflict)
    region.get_by_role("button", name="接受并确认所选候选", exact=True).click()
    accepted = region.get_by_role("article", name="检索词 second-14", exact=True)
    expect(accepted.get_by_text("长期检索词 · 已确认 · 人工修改", exact=True)).to_be_visible()
    region.get_by_label("选择候选 first-00", exact=True).check()
    region.get_by_role("button", name="弃用所选候选", exact=True).click()
    expect(region.get_by_role("article", name="检索词 first-00", exact=True)).to_have_count(0)
    region.get_by_role("button", name="关闭私人资料使用", exact=True).click()
    expect(
        region.get_by_text("主题分类：已确认私人；Agent范围：仅公开资料", exact=True)
    ).to_be_visible()
    assert TermWorker(apps[0].state.term_store, Many("third")).run_once() is False
    region.get_by_role("button", name="刷新检索词", exact=True).click()
    expect(region.get_by_text("生成任务：失败，原词保留", exact=False)).to_be_visible()
    expect(accepted).to_be_visible()
    region.get_by_label("查询表达式", exact=True).fill("manual after failure")
    region.get_by_role("button", name="添加检索词", exact=True).click()
    # First-page refresh keeps current pagination, so the appended manual term is visible.
    expect(
        region.get_by_role("article", name="检索词 manual after failure", exact=True)
    ).to_be_visible()
    page.reload()
    expect(region.get_by_text("生成任务：失败，原词保留", exact=False)).to_be_visible()
    page.close()


def test_stb05_concurrent_delete_preserves_draft_as_explicit_new_term(browser_app):
    browser, base, engine, run_id = browser_app
    page, region = enter(browser, base)
    region.get_by_label("查询表达式", exact=True).fill("original")
    region.get_by_role("button", name="添加检索词", exact=True).click()
    region.get_by_role("button", name="编辑此词", exact=True).click()
    region.get_by_label("查询表达式", exact=True).fill("draft survives deletion")

    def remove(route):
        if route.request.method == "PATCH":
            revision = route.request.post_data_json["expected_revision"]
            result = page.request.delete(
                route.request.url + "?expected_revision=" + revision,
                headers={
                    k: v for k, v in route.request.headers.items() if k not in {"content-length"}
                },
            )
            assert result.status == 204, result.text()
        route.continue_()

    page.route("**/construction-workspace/search-terms/*", remove)
    region.get_by_role("button", name="保存词修改", exact=True).click()
    expect(
        region.get_by_text("此检索词已被移除，草稿保留；核对后可另存为新词。", exact=True)
    ).to_be_visible()
    expect(region.get_by_label("查询表达式", exact=True)).to_have_value("draft survives deletion")
    page.unroute("**/construction-workspace/search-terms/*", remove)
    region.get_by_role("button", name="添加检索词", exact=True).click()
    expect(
        region.get_by_role("article", name="检索词 draft survives deletion", exact=True)
    ).to_be_visible()
    page.close()


def test_stb06_explicit_source_identity_stays_visible_after_removal_and_archive(browser_app):
    from uuid import uuid4

    browser, base, engine, run_id = browser_app
    page, region = enter(browser, base)
    headers = {
        "Origin": base,
        "X-CSRF-Token": page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"],
        "Idempotency-Key": str(uuid4()),
    }
    response = page.request.post(
        base + "/api/v1/me/data-source-configs",
        headers=headers,
        data={
            "name": "Arxiv",
            "provider": "arxiv",
            "base_url": "https://export.arxiv.org/api",
            "access_mode": "anonymous",
        },
    )
    assert response.status == 201, response.text()
    source = response.json()["data"]
    region.get_by_role("button", name="刷新检索词", exact=True).click()
    region.get_by_label("查询表达式", exact=True).fill("source scoped")
    region.get_by_label("适用数据源", exact=True).select_option("selected")
    region.get_by_role("checkbox", name="arxiv", exact=False).check()
    region.get_by_role("button", name="添加检索词", exact=True).click()
    card = region.get_by_role("article", name="检索词 source scoped", exact=True)
    expect(card.get_by_text(source["id"], exact=False)).to_be_visible()
    headers["X-CSRF-Token"] = page.request.get(base + "/api/v1/auth/csrf").json()["data"][
        "csrf_token"
    ]
    assert (
        page.request.delete(
            base + "/api/v1/me/data-source-configs/" + source["id"],
            headers=headers | {"Content-Type": "application/json"},
            params={"expected_revision": source["revision"]},
        ).status
        == 204
    )
    region.get_by_role("button", name="刷新检索词", exact=True).click()
    expect(card.get_by_text("（当前不可用）", exact=False)).to_be_visible()
    page.get_by_role("button", name="归档项目", exact=True).click()
    group = page.get_by_role("group", name="操作确认")
    group.get_by_role("checkbox").check()
    group.get_by_role("button", name="确认执行").click()
    expect(page.get_by_text("已归档 · 只读", exact=True)).to_be_visible()
    expect(card.get_by_text(source["id"], exact=False)).to_be_visible()
    expect(card.get_by_role("button", name="编辑此词", exact=True)).to_be_disabled()
    page.close()
