"""PH05: discover owned projects using the real browser and API."""

from pathlib import Path

from playwright.sync_api import expect
from test_browser_business import PASSWORD, login_ui, register_ui
from test_browser_business import browser_app as browser_app

from rpb.adapters.account import accounts
from rpb.adapters.project import projects


def seed_browser(page, base, count):
    csrf = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
    headers = {"Origin": base, "X-CSRF-Token": csrf}
    for i in range(count):
        result = page.request.post(
            base + "/api/v1/projects",
            headers=headers | {"Idempotency-Key": f"hub-project-{i:08}"},
            data={"name": f"Hub {i:03}", "description": "<script>literal only</script>"},
        )
        assert result.status == 201


def test_ph05_hub_empty_paging_enter_return_mobile(browser_app):
    browser, base, engine, run_id = browser_app
    page = browser.new_page(viewport={"width": 390, "height": 844})
    register_ui(page, base)
    login_ui(page)
    hub = page.get_by_role("region", name="我的项目")
    expect(hub.get_by_text("还没有可显示的项目，可在下方创建。")).to_be_visible()
    seed_browser(page, base, 21)
    with engine.begin() as conn:
        conn.execute(
            projects.update().where(projects.c.name == "Hub 020").values(status="archived")
        )
    page.get_by_role("button", name="刷新列表").click()
    expect(hub.get_by_role("link")).to_have_count(20)
    expect(hub.get_by_text("已归档 · 只读", exact=True)).to_be_visible()
    page.get_by_role("button", name="下一页").click()
    expect(hub.get_by_role("link")).to_have_count(1)
    expect(hub.get_by_role("link", name="Hub 000", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="下一页")).to_have_count(0)
    page.get_by_role("button", name="返回第一页").click()
    expect(hub.get_by_role("link")).to_have_count(20)
    hub.get_by_role("link", name="Hub 020", exact=True).click()
    expect(page.get_by_role("heading", name="Hub 020", exact=True)).to_be_visible()
    expect(page.get_by_text("已归档 · 只读", exact=True)).to_be_visible()
    page.get_by_role("link", name="我的项目", exact=True).click()
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(20)
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    evidence = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task021_project_hub_2026-10-25"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence / f"hub-mobile-{run_id}.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.screenshot(path=str(evidence / f"hub-desktop-{run_id}.png"), full_page=True)
    page.get_by_role("button", name="退出登录").click()
    expect(page.get_by_role("region", name="我的项目")).to_have_count(0)
    login_ui(page)
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(20)
    page.close()


def test_ph05_hub_network_failure_retry_and_expired_cursor(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    seed_browser(page, base, 21)
    page.route("**/api/v1/projects?*", lambda route: route.abort())
    page.get_by_role("button", name="刷新列表").click()
    expect(page.get_by_role("alert")).to_have_text("项目列表读取失败，请重试。")
    page.unroute("**/api/v1/projects?*")
    page.get_by_role("button", name="重试列表").click()
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(20)

    # Tamper only the request cursor: rejection comes from the real service.
    def invalid_cursor(route):
        route.continue_(url=base + "/api/v1/projects?page_size=20&cursor=invalid")

    page.route("**/api/v1/projects?*cursor=*", invalid_cursor)
    page.get_by_role("button", name="下一页").click()
    expect(page.get_by_role("alert")).to_have_text("列表位置已失效，请返回第一页。")
    page.get_by_role("button", name="返回第一页").click()
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(20)
    page.close()


def test_ph05_hub_actor_switch_before_read_and_disabled(browser_app):
    browser, base, engine, _ = browser_app
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    seed_browser(page, base, 1)
    other = browser.new_page()
    register_ui(other, base, "Other", "other@example.invalid")
    login_ui(other, "Other")
    seed_browser(other, base, 1)
    other.close()

    def switch(route):
        csrf = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
        response = page.request.post(
            base + "/api/v1/auth/login",
            headers={"Origin": base, "X-CSRF-Token": csrf},
            data={"identifier": "Other", "password": PASSWORD},
        )
        assert response.status == 200
        route.continue_()

    page.route("**/api/v1/projects?*", switch)
    page.get_by_role("button", name="刷新列表").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    expect(page.get_by_role("region", name="我的项目")).to_have_count(0)
    page.unroute("**/api/v1/projects?*")
    login_ui(page, "Other")
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(1)
    with engine.begin() as conn:
        conn.execute(
            accounts.update().where(accounts.c.username_key == "other").values(enabled=False)
        )
    page.get_by_role("button", name="刷新列表").click()
    expect(page.get_by_role("alert")).to_have_text("账号已禁用，请联系管理员。")
    expect(page.get_by_role("region", name="我的项目")).to_have_count(0)
    context.close()


def test_ph05_delayed_list_cannot_restore_previous_account(browser_app):
    browser, base, _, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    seed_browser(page, base, 1)
    other = browser.new_page()
    register_ui(other, base, "EmptyOther", "empty-other@example.invalid")
    other.close()
    # Hold delivery of a REAL response after fetch completes. Ignore abort solely
    # in this test to exercise the alive guard against already queued completion.
    page.evaluate("""() => {
      const original = window.fetch;
      window.hubHeld = false;
      let holdNext = true;
      window.fetch = async (url, init) => {
        if (holdNext && String(url).startsWith('/api/v1/projects?')) {
          holdNext = false;
          const response = await original(url, {...init, signal: undefined});
          return new Promise(resolve => {
            window.hubRelease = () => resolve(response);
            window.hubHeld = true;
          });
        }
        return original(url, init);
      };
    }""")
    page.get_by_role("button", name="刷新列表").click()
    page.wait_for_function("window.hubHeld === true")
    expect(page.get_by_text("正在读取项目…", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="刷新列表")).to_be_disabled()
    page.get_by_role("button", name="退出登录").click()
    expect(page.get_by_role("heading", name="欢迎回来")).to_be_visible()
    login_ui(page, "EmptyOther")
    expect(page.get_by_text("还没有可显示的项目，可在下方创建。")).to_be_visible()
    page.evaluate("""async () => {
      window.hubRelease();
      await new Promise(resolve => setTimeout(resolve, 0));
    }""")
    expect(page.get_by_role("region", name="我的项目").get_by_role("link")).to_have_count(0)
    expect(page.get_by_text("Hub 000", exact=True)).to_have_count(0)
    page.close()
