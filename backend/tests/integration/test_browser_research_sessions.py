"""Research session UI with real API/storage; synthetic published consumer fixture."""

from pathlib import Path

import sqlalchemy as sa
from playwright.sync_api import expect
from test_browser_business import browser_app as browser_app
from test_browser_business import login_ui, register_ui
from test_research_sessions import seed_version

from rpb.adapters.project import projects
from rpb.adapters.research_tables import sessions


def test_research_browser_create_restore_version_notice_and_revocation(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Research UI")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    region = page.get_by_role("region", name="研究会话", exact=True)
    expect(region.get_by_text("发布知识版本后可创建研究会话。")).to_be_visible()
    with engine.connect() as conn:
        project_id = conn.scalar(sa.select(projects.c.id).where(projects.c.name == "Research UI"))
    v1 = seed_version(engine, project_id)
    expect(region.get_by_role("button", name="创建研究会话", exact=True)).to_be_visible(
        timeout=10000
    )
    region.get_by_label("研究会话标题").fill("可恢复研究")
    region.get_by_role("button", name="创建研究会话", exact=True).click()
    current = region.get_by_role("article", name="当前研究会话")
    expect(current.get_by_text(v1, exact=True)).to_be_visible()
    expect(
        current.get_by_text("当前版本没有项目证据。后续问答需要显式选择无证据继续。")
    ).to_be_visible()
    page.reload()
    expect(current.get_by_role("heading", name="可恢复研究")).to_be_visible()
    title = region.get_by_label("研究会话标题")
    title.fill("保留中的下一会话草稿")
    title.focus()
    # Hold the first poll's V1 response across multiple timer ticks. A second
    # in-flight request would allow stale success/failure to overwrite V2.
    held = []

    def hold_poll(route):
        held.append((route, route.fetch()))

    page.route("**/research-sessions/*", hold_poll)
    page.wait_for_timeout(3500)
    assert len(held) == 1
    v2 = seed_version(engine, project_id, empty=False)
    page.wait_for_timeout(6500)
    assert len(held) == 1
    held[0][0].fulfill(response=held[0][1])
    page.unroute("**/research-sessions/*", hold_poll)
    expect(current.get_by_text("检测到知识库版本更新")).to_be_visible(timeout=10000)
    expect(current.get_by_text(v2, exact=True)).to_be_visible()
    expect(title).to_have_value("保留中的下一会话草稿")
    expect(title).to_be_focused()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 1
    evidence = (
        Path(__file__).resolve().parents[3] / "docs/workorders/evidence/task051_research/browser"
    )
    evidence.mkdir(exist_ok=True)
    page.screenshot(path=str(evidence / "session-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(evidence / "session-mobile.png"), full_page=True)
    with engine.begin() as conn:
        conn.execute(projects.update().where(projects.c.id == project_id).values(status="deleted"))
    expect(current).to_have_count(0, timeout=10000)
    page.close()


def test_research_browser_lost_creation_response_reuses_command(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Research retry")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    region = page.get_by_role("region", name="研究会话", exact=True)
    expect(region.get_by_text("发布知识版本后可创建研究会话。")).to_be_visible()
    with engine.connect() as conn:
        project_id = conn.scalar(
            sa.select(projects.c.id).where(projects.c.name == "Research retry")
        )
    seed_version(engine, project_id)
    expect(region.get_by_role("button", name="创建研究会话", exact=True)).to_be_visible(
        timeout=10000
    )

    def lose_response(route):
        if route.request.method == "POST":
            assert route.fetch().status == 201
            route.abort()
        else:
            route.continue_()

    page.route("**/research-sessions", lose_response)
    region.get_by_label("研究会话标题").fill("网络中断研究")
    region.get_by_role("button", name="创建研究会话", exact=True).click()
    expect(region.get_by_role("button", name="重试创建会话")).to_be_visible()
    page.unroute("**/research-sessions", lose_response)
    region.get_by_role("button", name="重试创建会话").click()
    expect(
        region.get_by_role("article", name="当前研究会话").get_by_role(
            "heading", name="网络中断研究"
        )
    ).to_be_visible()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(sessions)) == 1
    page.close()


def test_research_browser_rejection_invalidates_late_restore(browser_app):
    browser, base, engine, _ = browser_app
    page = browser.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_label("项目名称", exact=True).fill("Research late")
    page.get_by_role("button", name="创建 Project", exact=True).click()
    region = page.get_by_role("region", name="研究会话", exact=True)
    expect(region.get_by_text("发布知识版本后可创建研究会话。")).to_be_visible()
    with engine.connect() as conn:
        project_id = conn.scalar(sa.select(projects.c.id).where(projects.c.name == "Research late"))
    seed_version(engine, project_id)
    expect(region.get_by_role("button", name="创建研究会话", exact=True)).to_be_visible(
        timeout=10000
    )
    region.get_by_label("研究会话标题").fill("拒绝后不可回填")
    region.get_by_role("button", name="创建研究会话", exact=True).click()
    current = region.get_by_role("article", name="当前研究会话")
    expect(current).to_be_visible()
    held = []

    def interleave(route):
        if "?" in route.request.url:
            route.fulfill(status=404, json={"error": {"code": "PERMISSION_RESOURCE_UNAVAILABLE"}})
        else:
            held.append((route, route.fetch()))

    page.route("**/research-sessions**", interleave)
    page.reload()
    expect(region.get_by_role("alert")).to_have_text("研究会话或知识版本不可用。")
    expect(current).to_have_count(0)
    page.wait_for_timeout(200)
    assert len(held) == 1
    held[0][0].fulfill(response=held[0][1])
    page.unroute("**/research-sessions**", interleave)
    page.wait_for_timeout(300)
    expect(current).to_have_count(0)
    expect(region.get_by_role("alert")).to_have_text("研究会话或知识版本不可用。")
    assert (
        page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('rpb-research:')).length")
        == 0
    )
    page.close()
