"""SCB: administrator settings, persistence, conflict and unknown-save recovery."""

from pathlib import Path

import pytest
from playwright.sync_api import expect
from test_browser_business import PASSWORD, login_ui, register_ui
from test_browser_business import browser_app as inherited_browser_app

browser_app = inherited_browser_app


@pytest.fixture
def security_browser(browser_app):
    browser, base, engine, run_id = browser_app
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_role("button", name="基础安全", exact=True).click()
    region = page.get_by_role("region", name="基础安全设置", exact=True)
    expect(region.get_by_text("当前使用系统默认值。", exact=True)).to_be_visible()
    yield page, region, base
    context.close()


def test_scb01_defaults_save_refresh_mobile_and_regular_user(security_browser):
    page, region, base = security_browser
    expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("30")
    expect(region.get_by_label("连接建立重试次数", exact=True)).to_have_value("0")
    region.get_by_label("连接测试超时（秒）", exact=True).fill("17")
    region.get_by_label("连接建立重试次数", exact=True).fill("2")
    region.get_by_label("诊断快照保留天数", exact=True).fill("11")
    region.get_by_label("诊断信息范围", exact=True).select_option("standard")
    region.get_by_role("button", name="保存安全配置", exact=True).click()
    expect(region.get_by_text("安全配置已保存。", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("button", name="基础安全", exact=True).click()
    expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("17")
    expect(region.get_by_label("连接建立重试次数", exact=True)).to_have_value("2")
    expect(region.get_by_label("诊断快照保留天数", exact=True)).to_have_value("11")
    expect(region.get_by_label("诊断信息范围", exact=True)).to_have_value("standard")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    output = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task035_smtp_security_2026-10-26/browser"
    )
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / "security-mobile.png"), full_page=True)
    context = page.context.browser.new_context()
    try:
        reader = context.new_page()
        register_ui(reader, base, "SecurityReader", "security-reader@example.invalid")
        login_ui(reader, "SecurityReader")
        expect(reader.get_by_role("button", name="基础安全", exact=True)).to_have_count(0)
        assert reader.request.get(base + "/api/v1/admin/security-config").status == 404
    finally:
        context.close()


def test_scb02_unknown_save_survives_navigation_without_resubmission(security_browser):
    page, region, base = security_browser
    writes = []

    def drop(route):
        if route.request.method == "PUT":
            writes.append(route.request.post_data_json)
            assert route.fetch().status == 200
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/admin/security-config", drop)
    region.get_by_label("连接测试超时（秒）", exact=True).fill("19")
    region.get_by_role("button", name="保存安全配置", exact=True).click()
    recover = region.get_by_role("button", name="核查安全配置（加载将放弃草稿）", exact=True)
    expect(recover).to_be_visible()
    page.get_by_role("button", name="个人资料", exact=True).click()
    page.get_by_role("button", name="基础安全", exact=True).click()
    expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("19")
    recover.click()
    expect(region.get_by_text("已加载当前安全配置。", exact=True)).to_be_visible()
    expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("19")
    assert len(writes) == 1


def test_scb03_conflict_preserves_draft_then_loads_current(security_browser):
    page, region, base = security_browser
    saved = page.request.get(base + "/api/v1/admin/security-config").json()["data"]
    csrf = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
    response = page.request.put(
        base + "/api/v1/admin/security-config",
        headers={"Origin": base, "X-CSRF-Token": csrf},
        data={
            **saved["effective"],
            "connection_timeout_seconds": 23,
            "expected_revision": saved["revision"],
        },
    )
    assert response.status == 200
    region.get_by_label("连接测试超时（秒）", exact=True).fill("18")
    region.get_by_role("button", name="保存安全配置", exact=True).click()
    expect(
        region.get_by_text("安全配置已被其他管理员修改。草稿保留，请核查当前配置。", exact=True)
    ).to_be_visible()
    expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("18")
    region.get_by_role("button", name="核查安全配置（加载将放弃草稿）", exact=True).click()
    expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("23")


def test_scb04_stale_admin_switch_rejects_write_and_discards_draft(security_browser):
    page, region, base = security_browser
    before = page.request.get(base + "/api/v1/admin/security-config").json()["data"]
    region.get_by_label("连接测试超时（秒）", exact=True).fill("18")
    region.get_by_label("诊断信息范围", exact=True).select_option("standard")
    context = page.context.browser.new_context()
    try:
        reader = context.new_page()
        register_ui(reader, base, "SecuritySwitch", "security-switch@example.invalid")
        login_ui(reader, "SecuritySwitch")
        csrf = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
        response = page.request.post(
            base + "/api/v1/auth/login",
            headers={"Origin": base, "X-CSRF-Token": csrf},
            data={"identifier": "SecuritySwitch", "password": PASSWORD},
        )
        assert response.status == 200
        writes = []
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "PUT" else None,
        )
        region.get_by_role("button", name="保存安全配置", exact=True).click()
        expect(page.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
        expect(page.get_by_role("region", name="基础安全设置", exact=True)).to_have_count(0)
        assert not writes
        assert page.request.get(base + "/api/v1/admin/security-config").status == 404
        login_ui(page)
        page.get_by_role("button", name="基础安全", exact=True).click()
        expect(region.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("30")
        expect(region.get_by_label("诊断信息范围", exact=True)).to_have_value("minimal")
        after = page.request.get(base + "/api/v1/admin/security-config").json()["data"]
        assert after == before
        assert not writes
    finally:
        context.close()
