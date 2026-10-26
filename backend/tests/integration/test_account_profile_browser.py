"""AP05 real browser profile maintenance, recovery and identity isolation."""

import pytest
from playwright.sync_api import expect
from test_browser_business import browser_app as browser_app
from test_browser_business import login_ui, register_ui


def open_profile(page, base):
    register_ui(page, base)
    login_ui(page)
    page.get_by_role("button", name="个人资料", exact=True).click()


@pytest.mark.parametrize("width", [1280, 390])
def test_ap05_edit_cancel_save_reload(browser_app, width):
    browser, base, _, _ = browser_app
    page = browser.new_page(viewport={"width": width, "height": 900})
    open_profile(page, base)
    page.get_by_label("显示名", exact=True).fill("Discard")
    page.get_by_role("button", name="取消资料编辑", exact=True).click()
    expect(page.get_by_label("显示名", exact=True)).to_have_value("")
    page.get_by_label("个人邮箱", exact=True).fill("updated@example.invalid")
    page.get_by_label("显示名", exact=True).fill("研究者")
    page.get_by_role("button", name="保存个人资料", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("个人资料已保存。")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.reload()
    page.get_by_role("button", name="个人资料", exact=True).click()
    expect(page.get_by_label("显示名", exact=True)).to_have_value("研究者")
    expect(page.get_by_label("个人邮箱", exact=True)).to_have_value("updated@example.invalid")
    page.close()


@pytest.mark.parametrize("lost", [False, True])
def test_ap05_conflict_or_lost_response_preserves_draft(browser_app, lost):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    open_profile(page, base)
    page.get_by_label("显示名", exact=True).fill("Draft")
    if lost:

        def intercept(route):
            if route.request.method == "PATCH":
                response = route.fetch()
                assert response.status == 200
                route.abort("failed")
            else:
                route.continue_()

        page.route("**/api/v1/me", intercept)
    else:
        user = page.request.get(base + "/api/v1/me").json()["data"]
        token = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
        assert (
            page.request.patch(
                base + "/api/v1/me",
                headers={"Origin": base, "X-CSRF-Token": token},
                data={"expected_revision": user["revision"], "display_name": "Other"},
            ).status
            == 200
        )
    page.get_by_role("button", name="保存个人资料", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("草稿已保留")
    expect(page.get_by_label("显示名", exact=True)).to_have_value("Draft")
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_disabled()
    page.get_by_role("button", name="返回项目", exact=True).click()
    page.get_by_role("button", name="个人资料", exact=True).click()
    expect(page.get_by_label("显示名", exact=True)).to_have_value("Draft")
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_disabled()
    page.unroute_all()
    page.get_by_role("button", name="核查并加载当前资料（放弃草稿）", exact=True).click()
    expect(page.get_by_label("显示名", exact=True)).to_have_value("Draft" if lost else "Other")
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_enabled()
    page.close()


def test_ap05_changed_cookie_rejects_old_profile(browser_app):
    browser, base, _, _ = browser_app
    context = browser.new_context()
    page = context.new_page()
    open_profile(page, base)
    page.get_by_label("显示名", exact=True).fill("Private A")
    other = context.new_page()
    other.goto(base + "/workspace")
    other.get_by_role("button", name="退出登录", exact=True).click()
    expect(other.get_by_role("status")).to_have_text("已退出当前会话。")
    register_ui(other, base, "Other", "other@example.invalid")
    login_ui(other, "Other")
    page.get_by_role("button", name="保存个人资料", exact=True).click()
    expect(page.get_by_role("region", name="个人资料", exact=True)).to_have_count(0)
    current = other.request.get(base + "/api/v1/me").json()["data"]
    assert current["username"] == "Other" and current["display_name"] is None
    context.close()


def test_ap05_validation_can_be_corrected(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    open_profile(page, base)
    field = page.get_by_label("显示名", exact=True)
    field.evaluate("element => element.removeAttribute('maxlength')")
    field.fill("x" * 201)
    page.get_by_role("button", name="保存个人资料", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("输入未通过校验，请修正后保存。")
    expect(field).to_have_value("x" * 201)
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_enabled()
    field.fill("Corrected")
    page.get_by_role("button", name="保存个人资料", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("个人资料已保存。")
    page.close()


def test_ap05_navigation_preserves_profile_and_project_drafts(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    open_profile(page, base)
    page.get_by_label("显示名", exact=True).fill("Keep profile draft")
    page.get_by_role("button", name="返回项目", exact=True).click()
    page.get_by_role("button", name="个人资料", exact=True).click()
    expect(page.get_by_label("显示名", exact=True)).to_have_value("Keep profile draft")
    page.get_by_role("button", name="返回项目", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Project")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Keep project draft")
    page.get_by_role("button", name="个人资料", exact=True).click()
    page.get_by_role("button", name="返回项目", exact=True).click()
    expect(page.get_by_label("项目名称", exact=True)).to_have_value("Keep project draft")
    page.close()
