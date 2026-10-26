"""Independent user journeys, specified from FR001/03-01/04 and AP01–05."""

import sqlalchemy as sa
from playwright.sync_api import expect
from test_browser_business import browser_app as browser_app
from test_browser_business import login_ui, register_ui

from rpb.adapters.account import accounts
from rpb.adapters.project import projects


def start(page, base):
    register_ui(page, base)
    login_ui(page)


def profile(page):
    page.get_by_role("button", name="个人资料", exact=True).click()


def save_profile(page):
    page.get_by_role("button", name="保存个人资料", exact=True).click()


def patch_profile(page, base, **changes):
    user = page.request.get(base + "/api/v1/me").json()["data"]
    token = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
    result = page.request.patch(
        base + "/api/v1/me",
        headers={"Origin": base, "X-CSRF-Token": token},
        data={"expected_revision": user["revision"], **changes},
    )
    assert result.status == 200
    return result.json()["data"]


def test_journey_project_draft_survives_successful_profile_save(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    start(page, base)
    page.get_by_label("项目名称", exact=True).fill("Original project")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Edited project")
    page.get_by_role("textbox", name="描述", exact=True).fill("Human project draft")
    profile(page)
    page.get_by_label("显示名", exact=True).fill("Researcher")
    save_profile(page)
    expect(page.get_by_role("status").filter(has_text="个人资料已保存。")).to_be_visible()
    page.get_by_role("button", name="返回项目", exact=True).click()
    expect(page.get_by_label("项目名称", exact=True)).to_have_value("Edited project")
    expect(page.get_by_role("textbox", name="描述", exact=True)).to_have_value(
        "Human project draft"
    )
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("heading", name="Edited project", exact=True)).to_be_visible()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(accounts.c.display_name)) == "Researcher"
        row = conn.execute(sa.select(projects)).mappings().one()
        assert row["description"] == "Human project draft"
    page.close()


def test_journey_new_email_login_preserves_project_and_old_session(browser_app):
    browser, base, _, _ = browser_app
    first = browser.new_context()
    page = first.new_page()
    start(page, base)
    page.get_by_label("项目名称", exact=True).fill("Email identity project")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="Email identity project", exact=True)).to_be_visible()
    second = browser.new_context()
    other = second.new_page()
    other.goto(base + "/workspace")
    login_ui(other, "browser@example.invalid")
    profile(page)
    page.get_by_label("个人邮箱", exact=True).fill("replacement@example.invalid")
    save_profile(page)
    expect(page.get_by_role("status").filter(has_text="个人资料已保存。")).to_be_visible()
    # Existing authenticated session remains account-bound; no implicit sign-out policy.
    other.reload()
    expect(
        other.get_by_role("region", name="我的项目").get_by_role(
            "link", name="Email identity project"
        )
    ).to_be_visible()
    other.get_by_role("button", name="退出登录", exact=True).click()
    other.get_by_label("用户名或邮箱", exact=True).fill("browser@example.invalid")
    other.get_by_label("密码", exact=True).fill("Browser-passphrase-123")
    other.get_by_role("button", name="登录账号", exact=True).click()
    expect(other.get_by_role("alert")).to_have_text("用户名、邮箱或密码不正确。")
    login_ui(other, "REPLACEMENT@EXAMPLE.INVALID")
    expect(
        other.get_by_role("region", name="我的项目").get_by_role(
            "link", name="Email identity project"
        )
    ).to_be_visible()
    first.close()
    second.close()


def test_journey_occupied_email_is_correctable_without_losing_name(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    start(page, base)
    other = browser.new_page()
    register_ui(other, base, "Other", "taken@example.invalid")
    profile(page)
    page.get_by_label("个人邮箱", exact=True).fill("taken@example.invalid")
    page.get_by_label("显示名", exact=True).fill("Keep my draft")
    save_profile(page)
    expect(page.get_by_role("status")).to_have_text("邮箱已被使用，请换一个邮箱。")
    expect(page.get_by_label("显示名", exact=True)).to_have_value("Keep my draft")
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_enabled()
    page.get_by_label("个人邮箱", exact=True).fill("free@example.invalid")
    save_profile(page)
    expect(page.get_by_role("status")).to_have_text("个人资料已保存。")
    current = page.request.get(base + "/api/v1/me").json()["data"]
    assert current["email"] == "free@example.invalid" and current["display_name"] == "Keep my draft"
    page.close()
    other.close()


def test_journey_lost_write_then_failed_read_does_not_enable_resubmit(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    start(page, base)
    profile(page)
    page.get_by_label("显示名", exact=True).fill("Committed despite lost response")
    writes = []
    page.on(
        "request",
        lambda request: (
            writes.append(request.post_data)
            if request.method == "PATCH" and request.url == base + "/api/v1/me"
            else None
        ),
    )

    def lose_write(route):
        if route.request.method == "PATCH":
            assert route.fetch().status == 200
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/me", lose_write)
    save_profile(page)
    expect(page.get_by_role("status")).to_contain_text("草稿已保留")
    committed = page.request.get(base + "/api/v1/me").json()["data"]
    page.unroute_all()
    page.route("**/api/v1/me", lambda route: route.abort("failed"))
    page.get_by_role("button", name="核查并加载当前资料（放弃草稿）", exact=True).click()
    expect(page.get_by_label("显示名", exact=True)).to_have_value("Committed despite lost response")
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_disabled()
    expect(
        page.get_by_role("button", name="核查并加载当前资料（放弃草稿）", exact=True)
    ).to_be_enabled()
    page.unroute_all()
    page.get_by_role("button", name="核查并加载当前资料（放弃草稿）", exact=True).click()
    expect(page.get_by_role("status")).to_have_text("已加载当前资料。")
    assert len(writes) == 1
    assert page.request.get(base + "/api/v1/me").json()["data"] == committed
    expect(page.get_by_role("button", name="保存个人资料", exact=True)).to_be_enabled()
    page.close()


def test_journey_display_name_edit_preserves_saved_email_original(browser_app):
    """Identity display original is preserved; editing a different field cannot normalize it."""
    browser, base, _, _ = browser_app
    page = browser.new_page()
    start(page, base)
    original = "  CasePreserved@Example.invalid  "
    patch_profile(page, base, email=original)
    page.reload()
    profile(page)
    page.get_by_label("显示名", exact=True).fill("Only name changed")
    save_profile(page)
    expect(page.get_by_role("status")).to_have_text("个人资料已保存。")
    current = page.request.get(base + "/api/v1/me").json()["data"]
    assert current["email"] == original
    assert current["display_name"] == "Only name changed"
    page.close()


def test_journey_two_tabs_conflict_reload_then_deliberate_new_edit(browser_app):
    browser, base, _, _ = browser_app
    context = browser.new_context()
    first = context.new_page()
    start(first, base)
    profile(first)
    second = context.new_page()
    second.goto(base + "/workspace")
    profile(second)
    first.get_by_label("显示名", exact=True).fill("Tab one")
    second.get_by_label("显示名", exact=True).fill("Old tab two draft")
    save_profile(first)
    expect(first.get_by_role("status")).to_have_text("个人资料已保存。")
    save_profile(second)
    expect(second.get_by_role("status")).to_contain_text("草稿已保留")
    expect(second.get_by_label("显示名", exact=True)).to_have_value("Old tab two draft")
    second.get_by_role("button", name="核查并加载当前资料（放弃草稿）", exact=True).click()
    expect(second.get_by_label("显示名", exact=True)).to_have_value("Tab one")
    second.get_by_label("显示名", exact=True).fill("Deliberate new edit")
    save_profile(second)
    expect(second.get_by_role("status")).to_have_text("个人资料已保存。")
    assert (
        second.request.get(base + "/api/v1/me").json()["data"]["display_name"]
        == "Deliberate new edit"
    )
    context.close()
