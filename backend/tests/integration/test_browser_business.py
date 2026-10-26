"""UI01–06: real browser -> loopback HTTP -> disposable PostgreSQL, no API mocks."""

import importlib.util
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import sqlalchemy as sa
import uvicorn
from playwright.sync_api import expect, sync_playwright

from rpb.adapters.account import accounts
from rpb.adapters.project import projects
from rpb.adapters.project_commands import commands

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "Browser-passphrase-123"


@pytest.fixture
def browser_app(db, request):
    engine, _ = db
    target = Path(request.config.getoption("--storage-target"))
    spec = importlib.util.spec_from_file_location(
        "business_demo", ROOT / "scripts/run_business_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    app, owned_engine = module.create_demo(target, port)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                yield (
                    browser,
                    f"http://127.0.0.1:{port}",
                    engine,
                    json.loads(target.read_text())["run_id"],
                )
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        owned_engine.dispose()
        assert not thread.is_alive(), "API must stop before disposable database cleanup"


def register_ui(page, base, username="BrowserUser", email="browser@example.invalid"):
    page.goto(base + "/workspace")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="注册", exact=True).click()
    page.get_by_label("用户名", exact=True).fill(username)
    page.get_by_label("邮箱", exact=True).fill(email)
    page.get_by_label("密码", exact=True).fill(PASSWORD)
    page.get_by_label("确认密码", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="创建账号", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("注册成功，请登录。")
    expect(page.get_by_label("密码", exact=True)).to_have_value("")
    expect(page.get_by_role("button", name="退出登录")).to_have_count(0)


def login_ui(page, identifier="BrowserUser"):
    page.get_by_label("用户名或邮箱", exact=True).fill(identifier)
    page.get_by_label("密码", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="登录账号", exact=True).click()
    expect(page.get_by_role("button", name="退出登录")).to_be_visible()


def test_ui01_ui02_ui04_register_login_create_reload_logout(browser_app):
    browser, base, engine, run_id = browser_app
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    register_ui(page, base)
    login_ui(page, " BROWSER@EXAMPLE.INVALID ")
    page.get_by_label("项目名称", exact=True).fill("可信研究的第一步")
    page.get_by_label("描述", exact=True).fill("梳理可复现研究中的证据与方法。")
    page.get_by_label("研究范围", exact=True).fill("面向公开研究资料，建立清晰的问题边界。")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="可信研究的第一步")).to_be_visible()
    expect(page.get_by_text("尚未构建知识版本", exact=True)).to_be_visible()
    saved_url = page.url
    assert "?project=" in saved_url
    page.reload()
    expect(page.get_by_role("heading", name="可信研究的第一步")).to_be_visible()
    page.wait_for_load_state("networkidle")
    out = ROOT / "docs/workorders/evidence/task019_browser_2026-10-25"
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / f"project-{run_id}.png"), full_page=True)
    page.get_by_role("button", name="退出登录").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    expect(page.get_by_text("可信研究的第一步", exact=True)).to_have_count(0)
    assert "?" not in page.url
    login_ui(page, "browseruser")
    page.goto(saved_url)
    expect(page.get_by_role("heading", name="可信研究的第一步")).to_be_visible()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 1
    assert not errors
    context.close()


def test_ui03_lost_response_retries_same_command(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Once only")
    keys = []

    def lose_response(route):
        keys.append(route.request.headers["idempotency-key"])
        if len(keys) == 1:
            result = route.fetch()
            assert result.status == 201
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/projects", lose_response)
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    expect(page.get_by_label("项目名称", exact=True)).to_be_disabled()
    page.reload()
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    expect(page.get_by_label("项目名称", exact=True)).to_have_value("Once only")
    page.get_by_role("button", name="用原请求重试").click()
    expect(page.get_by_role("heading", name="Once only")).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 1
    page.close()


def test_ui04_cross_account_and_disabled_safe_empty(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("PRIVATE ALPHA")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="PRIVATE ALPHA")).to_be_visible()
    url = page.url
    page.get_by_role("button", name="退出登录").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    register_ui(page, base, "OtherUser", "other@example.invalid")
    login_ui(page, "OtherUser")
    page.goto(url)
    expect(page.get_by_role("alert")).to_have_text("资源不可用。")
    expect(page.get_by_text("PRIVATE ALPHA", exact=True)).to_have_count(0)
    with engine.begin() as conn:
        conn.execute(
            accounts.update().where(accounts.c.username_key == "otheruser").values(enabled=False)
        )
    page.reload()
    expect(page.get_by_role("alert")).to_have_text("账号已禁用，请联系管理员。")
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    expect(page.get_by_text("PRIVATE ALPHA", exact=True)).to_have_count(0)
    page.close()


def test_ui05_confirmation_visibility_and_mobile_layout(browser_app):
    browser, base, engine, run_id = browser_app
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base + "/workspace")
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="注册", exact=True).click()
    page.get_by_label("用户名", exact=True).fill("MobileUser")
    page.get_by_label("邮箱", exact=True).fill("mobile@example.invalid")
    page.get_by_label("密码", exact=True).fill(PASSWORD)
    page.get_by_label("确认密码", exact=True).fill("different-password")
    page.get_by_role("button", name="创建账号", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text("两次密码不一致。")
    page.get_by_label("显示当前输入的密码").check()
    expect(page.get_by_label("密码", exact=True)).to_have_attribute("type", "text")
    page.get_by_label("显示当前输入的密码").uncheck()
    expect(page.get_by_label("密码", exact=True)).to_have_attribute("type", "password")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 0
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(page.get_by_text("忘记密码", exact=True)).to_have_count(0)
    expect(page.get_by_role("navigation")).to_have_count(0)
    page.screenshot(
        path=str(ROOT / f"docs/workorders/evidence/task019_browser_2026-10-25/mobile-{run_id}.png"),
        full_page=True,
    )
    page.close()


def seed_other(context, base):
    token = context.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
    r = context.request.post(
        base + "/api/v1/auth/register",
        headers={"Origin": base, "X-CSRF-Token": token},
        data={"username": "OtherUser", "email": "other@example.invalid", "password": PASSWORD},
    )
    assert r.status == 201


def switch_other(context, base):
    token = context.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
    r = context.request.post(
        base + "/api/v1/auth/login",
        headers={"Origin": base, "X-CSRF-Token": token},
        data={"identifier": "OtherUser", "password": PASSWORD},
    )
    assert r.status == 200


@pytest.mark.parametrize("moment", ["before_csrf", "between_csrf_and_me", "after_me"])
def test_ui04_actor_bound_submission_across_cookie_change(browser_app, moment):
    browser, base, engine, _ = browser_app
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    seed_other(context, base)
    page.get_by_label("项目名称", exact=True).fill("A PRIVATE DRAFT")
    if moment == "before_csrf":
        # Real second tab changes the shared cookie while the first still holds a draft.
        other = context.new_page()
        other.goto(base + "/workspace")
        expect(other.get_by_role("button", name="退出登录")).to_be_visible()
        other.get_by_role("button", name="退出登录").click()
        expect(other.get_by_role("heading", name="欢迎回来")).to_be_visible()
        login_ui(other, "OtherUser")
    else:

        def swap(route):
            if moment == "between_csrf_and_me":
                switch_other(context, base)
                route.continue_()
            else:
                old_identity = route.fetch()
                assert old_identity.status == 200
                switch_other(context, base)
                route.fulfill(response=old_identity)
            page.unroute("**/api/v1/me", swap)

        page.route("**/api/v1/me", swap)
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    expect(page.get_by_label("项目名称", exact=True)).to_have_count(0)
    assert "A PRIVATE DRAFT" not in page.locator("body").inner_text()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 0
    context.close()


def test_ui03_unknown_result_survives_expiry_and_same_user_login(browser_app):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters.auth import sessions

    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Unknown but committed")
    keys = []

    def lose_once(route):
        keys.append(route.request.headers["idempotency-key"])
        if len(keys) == 1:
            assert route.fetch().status == 201
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/projects", lose_once)
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    with engine.begin() as conn:
        conn.execute(
            sessions.update().values(
                created_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
    page.get_by_role("button", name="用原请求重试").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    assert (
        page.evaluate("Object.keys(sessionStorage).filter(k => k.startsWith('rpb:create:')).length")
        == 1
    )
    login_ui(page)
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    expect(page.get_by_label("项目名称", exact=True)).to_have_value("Unknown but committed")
    page.get_by_role("button", name="用原请求重试").click()
    expect(page.get_by_role("heading", name="Unknown but committed")).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    assert PASSWORD not in page.evaluate(
        "JSON.stringify({local: {...localStorage}, session: {...sessionStorage}})"
    )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 1
    page.close()


def test_ui04_private_boot_read_loses_session_clears_visible_context(browser_app):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters.auth import sessions

    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Private saved project")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="Private saved project")).to_be_visible()

    def expire(route):
        with engine.begin() as conn:
            conn.execute(
                sessions.update().values(
                    created_at=datetime.now(UTC) - timedelta(days=2),
                    expires_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
        route.continue_()

    page.route("**/api/v1/projects/*", expire)
    page.reload()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    expect(page.get_by_role("button", name="退出登录")).to_have_count(0)
    expect(page.get_by_text("Private saved project", exact=True)).to_have_count(0)
    page.close()


def test_ui04_stale_logout_does_not_revoke_other_user(browser_app):
    browser, base, engine, _ = browser_app
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    seed_other(context, base)
    switch_other(context, base)
    page.get_by_role("button", name="退出登录").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    response = context.request.get(base + "/api/v1/me")
    assert response.status == 200 and response.json()["data"]["username"] == "OtherUser"
    context.close()


def test_ui03_unknown_retry_csrf_rejection_preserves_original(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Preserved through rejection")
    keys = []

    def intercept(route):
        keys.append(route.request.headers["idempotency-key"])
        if len(keys) == 1:
            assert route.fetch().status == 201
            route.abort("failed")
        elif len(keys) == 2:
            # Corrupt only the outbound CSRF token; rejection is from the real API.
            headers = {**route.request.headers, "x-csrf-token": "invalid-token"}
            response = route.fetch(headers=headers)
            assert response.status == 403
            route.fulfill(response=response)
        else:
            route.continue_()

    page.route("**/api/v1/projects", intercept)
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    page.get_by_role("button", name="用原请求重试").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    login_ui(page)
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    page.get_by_role("button", name="用原请求重试").click()
    expect(page.get_by_role("heading", name="Preserved through rejection")).to_be_visible()
    assert len(keys) == 3 and len(set(keys)) == 1
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 1
    page.close()


def test_sim01_auth_rejections_then_correction(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    for identifier in ["BrowserUser", "Nobody"]:
        page.get_by_label("用户名或邮箱", exact=True).fill(identifier)
        page.get_by_label("密码", exact=True).fill("incorrect-password")
        page.get_by_role("button", name="登录账号", exact=True).click()
        expect(page.get_by_role("alert")).to_have_text("用户名、邮箱或密码不正确。")
        expect(page.get_by_role("button", name="退出登录")).to_have_count(0)
    page.get_by_role("button", name="注册", exact=True).click()
    page.get_by_label("用户名", exact=True).fill("BROWSERUSER")
    page.get_by_label("邮箱", exact=True).fill("second@example.invalid")
    page.get_by_label("密码", exact=True).fill(PASSWORD)
    page.get_by_label("确认密码", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="创建账号", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text("用户名或邮箱已被使用。")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1
    page.get_by_label("用户名", exact=True).fill("SecondUser")
    page.get_by_role("button", name="创建账号", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("注册成功，请登录。")
    login_ui(page, " SECOND@EXAMPLE.INVALID ")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 2
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 0
    page.close()


@pytest.mark.parametrize("failure", ["before_post", "after_post_read"])
def test_sim02_network_failure_recovery(browser_app, failure):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    keys = []
    page.on(
        "request",
        lambda req: (
            keys.append(req.headers["idempotency-key"])
            if req.method == "POST" and req.url == base + "/api/v1/projects"
            else None
        ),
    )
    pattern = "**/api/v1/projects" if failure == "before_post" else "**/api/v1/projects/*"
    page.route(pattern, lambda route: route.abort("failed"))
    page.get_by_label("项目名称", exact=True).fill("Network recovery")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    with engine.connect() as conn:
        expected = 0 if failure == "before_post" else 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == expected
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == expected
    page.unroute(pattern)
    page.reload()
    expect(page.get_by_role("button", name="用原请求重试")).to_be_enabled()
    page.get_by_role("button", name="用原请求重试").click()
    expect(page.get_by_role("heading", name="Network recovery")).to_be_visible()
    assert len(keys) == 2 and len(set(keys)) == 1
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 1
    page.close()


def test_sim03_storage_unavailable_has_no_write(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    writes = []
    page.on(
        "request",
        lambda req: (
            writes.append(req.url)
            if req.method == "POST" and req.url == base + "/api/v1/projects"
            else None
        ),
    )
    page.evaluate("""() => { window.originalSetItem = Storage.prototype.setItem;
        Storage.prototype.setItem = function() { throw new DOMException('blocked'); }; }""")
    page.get_by_label("项目名称", exact=True).fill("Storage recovered")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text(
        "浏览器无法保留待确认请求，请允许本站会话存储后重试。"
    )
    expect(page.get_by_label("项目名称", exact=True)).to_be_enabled()
    assert not writes
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 0
    page.evaluate("() => { Storage.prototype.setItem = window.originalSetItem; }")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="Storage recovered")).to_be_visible()
    assert len(writes) == 1
    page.close()


def test_sim04_project_validation_multiple_links_and_literal_text(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("   ")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page.get_by_label("项目名称", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="用原请求重试")).to_have_count(0)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 0
    names = ["第一项研究", "第二项研究"]
    urls = []
    literal = '<img src=x onerror="window.untrustedExecuted=true">'
    for name in names:
        page.get_by_label("项目名称", exact=True).fill(name)
        page.get_by_label("描述", exact=True).fill(literal)
        page.get_by_role("button", name="创建 Project", exact=True).click()
        expect(page.get_by_role("heading", name=name)).to_be_visible()
        expect(page.get_by_text(literal, exact=True)).to_be_visible()
        assert page.evaluate("window.untrustedExecuted === undefined")
        urls.append(page.url)
        page.get_by_role("link", name="新建项目", exact=True).click()
        expect(page.get_by_label("项目名称", exact=True)).to_have_value("")
    for url, name in zip(urls, names, strict=True):
        page.goto(url)
        expect(page.get_by_role("heading", name=name)).to_be_visible()
    page.goto(base + "/workspace?project=00000000-0000-0000-0000-000000000001")
    expect(page.get_by_role("alert")).to_have_text("资源不可用。")
    expect(page.get_by_label("项目名称", exact=True)).to_be_enabled()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 2
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 2
    assert not errors
    page.close()


def test_sim07_inflight_form_blocks_duplicate_submission(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    posts = []

    def held_request(route):
        posts.append(route.request.url)
        expect(page.get_by_role("button", name="处理中…", exact=True)).to_be_disabled()
        for label in ["项目名称", "描述", "研究范围"]:
            expect(page.get_by_label(label, exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="退出登录")).to_be_disabled()
        route.continue_()

    page.route("**/api/v1/projects", held_request)
    page.get_by_label("项目名称", exact=True).fill("Only one in flight")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="Only one in flight")).to_be_visible()
    assert len(posts) == 1
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == 1
    page.close()
