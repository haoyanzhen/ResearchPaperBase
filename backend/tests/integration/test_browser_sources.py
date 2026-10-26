"""SU: actual browser, HTTP, persistence and fake provider dispatch."""

import pytest
from cryptography.fernet import Fernet
from playwright.sync_api import expect
from test_browser_business import browser_app, login_ui, register_ui  # noqa: F401
from test_source_configuration import FakeSource

from rpb.adapters.auth import AccountStore
from rpb.adapters.source_worker import SourceWorker
from rpb.adapters.sources import SourceStore
from rpb.bootstrap import business


@pytest.fixture
def source_browser(db, monkeypatch, request):
    key = Fernet.generate_key()
    compose = business.create_business_app
    monkeypatch.setattr(
        business,
        "create_business_app",
        lambda engine, origin, encryption_key=None: compose(engine, origin, key),
    )
    provider = FakeSource()
    worker = SourceWorker(SourceStore(AccountStore(db[0]), key), provider)
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_role("button", name="数据源设置", exact=True).click()
    yield page, worker, provider
    context.close()


def save(page, name="My source"):
    page.get_by_label("数据源名称", exact=True).fill(name)
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用外部服务。", exact=True)).to_be_visible()


def test_su01_save_test_reload_edit_invalidates_and_delete(source_browser):
    page, w, p = source_browser
    save(page)
    assert p.calls == []
    expect(page.get_by_role("heading", name="个人数据源配置 / My source")).to_be_visible()
    page.get_by_label("我了解测试会向", exact=False).check()
    page.get_by_role("button", name="测试数据源连接", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert w.run_once()
    page.get_by_role("button", name="刷新数据源测试状态", exact=True).click()
    expect(page.get_by_label("数据源测试详情", exact=True)).to_contain_text("成功")
    page.get_by_label("每分钟请求数", exact=True).fill("1")
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用外部服务。", exact=True)).to_be_visible()
    expect(page.get_by_label("数据源测试详情", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="刷新数据源测试状态", exact=True)).to_have_count(0)
    page.reload()
    page.get_by_role("button", name="数据源设置", exact=True).click()
    page.get_by_role("button", name="My source · 启用", exact=True).click()
    expect(page.get_by_label("每分钟请求数", exact=True)).to_have_value("1")
    page.get_by_label("启用数据源", exact=True).uncheck()
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(page.get_by_role("button", name="My source · 禁用", exact=True)).to_be_visible()
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="删除数据源配置", exact=True).click()
    expect(page.get_by_role("button", name="My source · 禁用", exact=True)).to_have_count(0)
    assert len(p.calls) == 1


def test_su02_unsaved_switch_and_missing_key_repair(source_browser):
    page, w, p = source_browser
    page.get_by_label("数据源名称", exact=True).fill("Draft")
    page.get_by_role("button", name="新增数据源配置", exact=True).click()
    expect(page.get_by_role("group", name="未保存修改")).to_be_visible()
    page.get_by_role("button", name="留在当前配置", exact=True).click()
    expect(page.get_by_label("数据源名称", exact=True)).to_have_value("Draft")
    page.get_by_label("数据源类型", exact=True).select_option("ads")
    save(page, "ADS")
    page.get_by_label("我了解测试会向", exact=False).check()
    page.get_by_role("button", name="测试数据源连接", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert w.run_once()
    page.get_by_role("button", name="刷新数据源测试状态", exact=True).click()
    expect(page.get_by_label("数据源测试详情", exact=True)).to_contain_text(
        "CONFIG_SECRET_UNAVAILABLE"
    )
    assert p.calls == []
    page.get_by_label("数据源API密钥（留空保持已存值）", exact=True).fill("BROWSER-KEY")
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(page.get_by_label("数据源API密钥（留空保持已存值）", exact=True)).to_have_value("")
    expect(page.get_by_label("数据源测试详情", exact=True)).to_have_count(0)


def test_su03_lost_create_response_reuses_command(source_browser):
    page, w, p = source_browser
    lost = [False]

    def route(r):
        if r.request.method == "POST" and not lost[0]:
            lost[0] = True
            r.fetch()
            r.abort("failed")
        else:
            r.continue_()

    page.route("**/api/v1/me/data-source-configs", route)
    page.get_by_label("数据源名称", exact=True).fill("Recovered")
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    page.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(page.get_by_role("button", name="Recovered · 启用", exact=True)).to_have_count(1)
    expect(page.get_by_label("数据源名称", exact=True)).to_have_value("Recovered")
    assert not p.calls


def test_su04_two_tabs_conflict_keeps_draft(source_browser):
    page, w, p = source_browser
    save(page)
    other = page.context.new_page()
    other.goto(page.url)
    other.get_by_role("button", name="数据源设置", exact=True).click()
    other.get_by_role("button", name="My source · 启用", exact=True).click()
    page.get_by_label("数据源名称", exact=True).fill("Changed")
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(page.get_by_role("button", name="Changed · 启用", exact=True)).to_be_visible()
    other.get_by_label("数据源名称", exact=True).fill("Stale draft")
    other.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(
        other.get_by_text("配置已被其他操作修改。草稿保留，请核查当前内容。", exact=True)
    ).to_be_visible()
    expect(other.get_by_label("数据源名称", exact=True)).to_have_value("Stale draft")
    other.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(other.get_by_label("数据源名称", exact=True)).to_have_value("Changed")
    other.close()


def test_su05_lost_test_response_reuses_job(source_browser):
    page, w, p = source_browser
    save(page)
    lost = [False]

    def route(r):
        if not lost[0]:
            lost[0] = True
            r.fetch()
            r.abort("failed")
        else:
            r.continue_()

    page.route("**/api/v1/me/data-source-configs/*/test", route)
    page.get_by_label("我了解测试会向", exact=False).check()
    page.get_by_role("button", name="测试数据源连接", exact=True).click()
    page.get_by_role("button", name="核查同一请求", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert w.run_once() and not w.run_once() and len(p.calls) == 1


def test_su06_lost_patch_and_delete_recover(source_browser):
    page, w, p = source_browser
    save(page)
    lost = set()

    def route(r):
        method = r.request.method
        if method in {"PATCH", "DELETE"} and method not in lost:
            lost.add(method)
            r.fetch()
            r.abort("failed")
        else:
            r.continue_()

    page.route("**/api/v1/me/data-source-configs/*", route)
    page.get_by_label("数据源名称", exact=True).fill("Edited")
    page.get_by_role("button", name="保存数据源配置", exact=True).click()
    page.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(page.get_by_label("数据源名称", exact=True)).to_have_value("Edited")
    page.on("dialog", lambda d: d.accept())
    page.get_by_role("button", name="删除数据源配置", exact=True).click()
    page.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(page.get_by_role("button", name="Edited · 启用", exact=True)).to_have_count(0)
    assert not p.calls


def test_su07_poll_old_task_after_other_tab_edit_preserves_old_draft(source_browser):
    page, w, p = source_browser
    save(page)
    page.get_by_label("我了解测试会向", exact=False).check()
    page.get_by_role("button", name="测试数据源连接", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert w.run_once()
    other = page.context.new_page()
    other.goto(page.url)
    other.get_by_role("button", name="数据源设置", exact=True).click()
    other.get_by_role("button", name="My source · 启用", exact=True).click()
    save(other, "New revision")
    page.get_by_role("button", name="刷新数据源测试状态", exact=True).click()
    expect(
        page.get_by_text("配置已被其他操作修改。草稿保留，请核查当前内容。", exact=True)
    ).to_be_visible()
    expect(page.get_by_label("数据源名称", exact=True)).to_have_value("My source")
    expect(page.get_by_label("数据源测试详情", exact=True)).to_have_count(0)
    other.close()


def test_su08_stale_initial_list_cannot_clear_new_login(source_browser):
    page, w, p = source_browser
    held = []

    def delay(r):
        if not held:
            held.append(r)
        else:
            r.continue_()

    page.route("**/api/v1/me/data-source-configs?*", delay)
    page.reload()
    page.get_by_role("button", name="数据源设置", exact=True).click()
    expect(page.get_by_role("button", name="退出登录", exact=True)).to_be_visible()
    page.get_by_role("button", name="退出登录", exact=True).click()
    login_ui(page)
    expect(page.get_by_role("button", name="退出登录", exact=True)).to_be_visible()
    assert held
    held[0].fulfill(
        status=401,
        content_type="application/json",
        body='{"error":{"code":"AUTH_SESSION_INVALID"}}',
    )
    page.get_by_role("button", name="数据源设置", exact=True).click()
    save(page, "Still signed in")
    expect(page.get_by_role("button", name="Still signed in · 启用", exact=True)).to_be_visible()
