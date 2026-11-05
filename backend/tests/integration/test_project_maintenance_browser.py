"""PM07: real browser workflows and deterministic response-loss recovery."""

from pathlib import Path

import sqlalchemy as sa
from playwright.sync_api import expect
from test_browser_business import browser_app as browser_app
from test_browser_business import login_ui, register_ui

from rpb.adapters.project import projects
from rpb.adapters.project_commands import lifecycle


def open_project(page, base, name="Maintenance"):
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill(name)
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name=name, exact=True)).to_be_visible()


def test_pm07_edit_cancel_archive_readonly_and_delete(browser_app):
    browser, base, engine, run_id = browser_app
    page = browser.new_page(viewport={"width": 390, "height": 844})
    open_project(page, base)
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Discarded")
    page.get_by_role("button", name="取消编辑", exact=True).click()
    expect(page.get_by_role("heading", name="Maintenance", exact=True)).to_be_visible()
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Edited")
    page.get_by_label("描述", exact=True).fill("Preserved human description")
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("heading", name="Edited", exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_role("heading", name="Edited", exact=True)).to_be_visible()
    page.get_by_role("button", name="归档项目", exact=True).click()
    group = page.get_by_role("group", name="操作确认")
    expect(group.get_by_role("button", name="确认执行")).to_be_disabled()
    group.get_by_role("button", name="取消操作").click()
    expect(group).to_have_count(0)
    page.get_by_role("button", name="归档项目", exact=True).click()
    group.get_by_role("checkbox").check()
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    out = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task022_project_maintenance_2026-10-25"
    )
    page.screenshot(path=str(out / f"confirmation-mobile-{run_id}.png"), full_page=True)
    group.get_by_role("button", name="确认执行").click()
    expect(page.get_by_text("已归档 · 只读", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="编辑信息", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="删除项目", exact=True)).to_have_count(0)
    page.get_by_role("link", name="新建项目", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Delete me")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    expect(page.get_by_role("heading", name="Delete me", exact=True)).to_be_visible()
    deleted_url = page.url
    page.get_by_role("button", name="删除项目", exact=True).click()
    group.get_by_role("checkbox").check()
    group.get_by_role("button", name="确认执行").click()
    expect(page.get_by_role("status")).to_have_text("Project 已软删除。")
    expect(
        page.get_by_role("region", name="我的项目").get_by_role("link", name="Delete me")
    ).to_have_count(0)
    page.goto(deleted_url)
    expect(page.get_by_role("alert")).to_have_text("资源不可用。")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 2
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 2
    page.close()


def test_head_poll_clears_unavailable_project_and_form(browser_app):
    browser, base, _, _ = browser_app
    context = browser.new_context()
    page = context.new_page()
    open_project(page, base, "Private project name")
    other = context.new_page()
    other.goto(page.url)
    other.get_by_role("button", name="删除项目", exact=True).click()
    group = other.get_by_role("group", name="操作确认")
    group.get_by_role("checkbox").check()
    group.get_by_role("button", name="确认执行").click()
    expect(other.get_by_role("status")).to_have_text("Project 已软删除。")
    other.close()
    page.bring_to_front()
    expect(page.get_by_role("alert")).to_have_text("资源不可用。", timeout=12000)
    expect(page.get_by_label("项目名称", exact=True)).to_have_value("")
    assert page.url == base + "/workspace"
    context.close()


def test_pm07_conflict_retains_draft_and_requires_explicit_reload(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    open_project(page, base)
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("My unsaved draft")
    csrf = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
    with engine.connect() as conn:
        p = conn.execute(sa.select(projects)).mappings().one()
    r = page.request.patch(
        base + "/api/v1/projects/" + str(p["id"]),
        headers={"Origin": base, "X-CSRF-Token": csrf},
        data={"expected_revision": str(p["revision"]), "name": "Other window"},
    )
    assert r.status == 200
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("草稿已保留")
    expect(page.get_by_label("项目名称", exact=True)).to_have_value("My unsaved draft")
    expect(page.get_by_role("button", name="保存修改", exact=True)).to_be_disabled()
    page.get_by_role("button", name="核查并加载当前内容（放弃草稿）", exact=True).click()
    expect(page.get_by_role("heading", name="Other window", exact=True)).to_be_visible()
    page.close()


def test_pm07_lost_patch_and_archive_responses(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    open_project(page, base)
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Committed edit")

    def lose_patch(route):
        if route.request.method == "PATCH":
            assert route.fetch().status == 200
            route.abort()
        else:
            route.continue_()

    page.route("**/api/v1/projects/*", lose_patch)
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("提交结果尚未确认")
    page.unroute("**/api/v1/projects/*")
    page.get_by_role("button", name="核查并加载当前内容（放弃草稿）", exact=True).click()
    expect(page.get_by_role("heading", name="Committed edit", exact=True)).to_be_visible()
    page.get_by_role("button", name="归档项目", exact=True).click()
    page.get_by_role("group", name="操作确认").get_by_role("checkbox").check()
    keys = []

    def lose_archive(route):
        keys.append(route.request.headers["idempotency-key"])
        if len(keys) == 1:
            assert route.fetch().status == 200
            route.abort()
        else:
            route.continue_()

    page.route("**/archive", lose_archive)
    page.get_by_role("button", name="确认执行", exact=True).click()
    expect(page.get_by_role("button", name="核查原归档请求", exact=True)).to_be_enabled()
    page.get_by_role("button", name="核查原归档请求", exact=True).click()
    expect(page.get_by_text("已归档 · 只读", exact=True)).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 1
        assert conn.scalar(sa.select(projects.c.authority_epoch)) == 1
    page.close()


def test_pm07_shared_cookie_change_cannot_submit_old_draft(browser_app):
    browser, base, engine, _ = browser_app
    context = browser.new_context()
    page = context.new_page()
    open_project(page, base)
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("Wrong actor draft")
    other = context.new_page()
    other.goto(base + "/workspace")
    other.get_by_role("button", name="退出登录", exact=True).click()
    expect(other.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
    register_ui(other, base, "Other", "other@example.invalid")
    login_ui(other, "Other")
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
    expect(page.get_by_text("Wrong actor draft", exact=True)).to_have_count(0)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.name)) == "Maintenance"
    context.close()


def test_pm07_invalid_edit_can_be_corrected_without_losing_draft(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    open_project(page, base)
    page.get_by_role("button", name="编辑信息", exact=True).click()
    page.get_by_label("项目名称", exact=True).fill("   ")
    page.get_by_label("描述", exact=True).fill("Keep my description draft")
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text("输入未通过校验，请修正后再保存。")
    expect(page.get_by_role("button", name="保存修改", exact=True)).to_be_enabled()
    expect(page.get_by_role("textbox", name="描述", exact=True)).to_have_value(
        "Keep my description draft"
    )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.name)) == "Maintenance"
    page.get_by_label("项目名称", exact=True).fill("Corrected name")
    page.get_by_role("button", name="保存修改", exact=True).click()
    expect(page.get_by_role("heading", name="Corrected name", exact=True)).to_be_visible()
    expect(page.get_by_text("Keep my description draft", exact=True)).to_be_visible()
    page.close()


def test_pm07_lost_delete_then_404_clears_unavailable_project(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    open_project(page, base)
    page.get_by_role("button", name="删除项目", exact=True).click()
    page.get_by_role("group", name="操作确认").get_by_role("checkbox").check()

    def lose_delete(route):
        if route.request.method == "DELETE":
            assert route.fetch().status == 204
            route.abort()
        else:
            route.continue_()

    page.route("**/api/v1/projects/*", lose_delete)
    page.get_by_role("button", name="确认执行", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("提交结果尚未确认")
    page.get_by_role("button", name="核查并加载当前内容（放弃草稿）", exact=True).click()
    expect(page.get_by_role("alert")).to_have_text("资源不可用。")
    expect(page.get_by_role("region", name="当前项目")).to_have_count(0)
    expect(page.get_by_role("group", name="操作确认")).to_have_count(0)
    expect(page.get_by_role("heading", name="Maintenance", exact=True)).to_have_count(0)
    expect(page.get_by_text("Project 已软删除。", exact=True)).to_have_count(0)
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(0)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.status)) == "deleted"
        assert conn.scalar(sa.select(sa.func.count()).select_from(lifecycle)) == 1
    page.close()
