"""AB: real browser administrator journeys and response-loss recovery."""

import pytest
from playwright.sync_api import expect
from test_browser_business import browser_app, login_ui, register_ui  # noqa: F401


@pytest.fixture
def admin_browser(request):
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    ac, bc = browser.new_context(), browser.new_context()
    a, b = ac.new_page(), bc.new_page()
    register_ui(a, base)
    login_ui(a)
    register_ui(b, base, "Bob", "bob@example.invalid")
    login_ui(b, "Bob")
    expect(b.get_by_role("button", name="管理员用户", exact=True)).to_have_count(0)
    a.get_by_role("button", name="管理员用户", exact=True).click()
    yield a, b, engine
    ac.close()
    bc.close()


def choose(page):
    page.get_by_role("button", name="Bob · 普通用户 · 启用", exact=True).click()


def confirm(page):
    page.get_by_role("button", name="预览账号操作", exact=True).click()
    page.get_by_label("我已核对目标账号及上述影响", exact=True).check()
    page.get_by_role("button", name="确认执行账号操作", exact=True).click()


def test_ab01_email_disable_enable_delete(admin_browser):
    a, b, engine = admin_browser
    choose(a)
    a.get_by_label("新的邮箱", exact=True).fill("changed@example.invalid")
    confirm(a)
    expect(a.get_by_text("changed@example.invalid", exact=True)).to_be_visible()
    choose(a)
    a.get_by_label("账号操作", exact=True).select_option("disable")
    confirm(a)
    expect(a.get_by_role("button", name="Bob · 普通用户 · 禁用", exact=True)).to_be_visible()
    b.reload()
    expect(b.get_by_label("用户名或邮箱", exact=True)).to_be_visible()
    a.get_by_role("button", name="Bob · 普通用户 · 禁用", exact=True).click()
    a.get_by_label("账号操作", exact=True).select_option("enable")
    confirm(a)
    choose(a)
    a.get_by_label("账号操作", exact=True).select_option("delete")
    confirm(a)
    expect(a.get_by_role("button", name="Bob · 普通用户 · 启用", exact=True)).to_have_count(0)


def test_ab02_reset_response_loss_does_not_redisclose(admin_browser):
    a, b, engine = admin_browser
    choose(a)
    a.get_by_label("账号操作", exact=True).select_option("reset_password")
    count = []

    def lost(route):
        response = route.fetch()
        count.append(response.json()["data"])
        route.abort()

    a.route("**/api/v1/admin/users/*/reset-password", lost, times=1)
    confirm(a)
    expect(a.get_by_role("alert")).to_be_visible()
    a.get_by_role("button", name="核查原请求", exact=True).click()
    expect(
        a.get_by_text(
            "密码已重置；新密码不会再次披露。如首次响应丢失，请重新预览发起新的重置。", exact=True
        )
    ).to_be_visible()
    expect(a.get_by_label("生成的新密码", exact=True)).to_have_count(0)
    assert len(count) == 1 and count[0]["password_disclosed"]


def test_ab03_patch_response_loss_reads_current(admin_browser):
    a, b, engine = admin_browser
    choose(a)
    a.get_by_label("新的邮箱", exact=True).fill("recovered@example.invalid")
    sent = []

    def lost(route):
        if route.request.method == "PATCH":
            sent.append(route.request.post_data)
            route.fetch()
            route.abort()
        else:
            route.continue_()

    a.route("**/api/v1/admin/users/*", lost)
    confirm(a)
    expect(a.get_by_role("alert")).to_be_visible()
    a.get_by_role("button", name="核查原请求", exact=True).click()
    expect(
        a.get_by_text("已读取当前账号状态，请核对列表。若仍需修改，请重新预览。", exact=True)
    ).to_be_visible()
    expect(a.get_by_label("新的邮箱", exact=True)).to_have_value("recovered@example.invalid")
    assert len(sent) == 1


def test_ab04_self_reset_preserves_one_time_password(admin_browser):
    a, b, engine = admin_browser
    a.get_by_role("button", name="BrowserUser · 管理员 · 启用", exact=True).click()
    a.get_by_label("账号操作", exact=True).select_option("reset_password")
    confirm(a)
    password = a.get_by_label("生成的新密码", exact=True)
    expect(password).to_be_visible()
    value = password.inner_text()
    assert len(value) >= 12
    # The server rejects the now revoked session; the page must not automatically
    # consume that 401 and erase the only password response before the user copies it.
    expect(password).to_have_text(value)
    a.reload()
    expect(a.get_by_label("用户名或邮箱", exact=True)).to_be_visible()
    expect(a.get_by_label("生成的新密码", exact=True)).to_have_count(0)
    a.get_by_label("用户名或邮箱", exact=True).fill("BrowserUser")
    a.get_by_label("密码", exact=True).fill(value)
    a.get_by_role("button", name="登录账号", exact=True).click()
    expect(a.get_by_role("button", name="管理员用户", exact=True)).to_be_visible()
