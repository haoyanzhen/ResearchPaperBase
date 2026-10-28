"""SSB: system maintenance and four independent personal providers in real browser."""

from pathlib import Path

from playwright.sync_api import expect
from test_browser_business import browser_app, login_ui, register_ui  # noqa: F401
from test_browser_sources import source_browser as inherited_source_browser

from rpb.adapters.source_worker import SourceWorker
from rpb.adapters.sources import SourceStore

source_browser = inherited_source_browser


def system_page(source_browser):
    page, private, provider = source_browser
    store = SourceStore(private.store.account, system=True)
    store.cipher = private.store.cipher
    page.get_by_role("button", name="系统数据源", exact=True).click()
    return (
        page,
        page.get_by_role("region", name="系统数据源设置", exact=True),
        SourceWorker(store, provider),
        provider,
    )


def save(region, name):
    region.get_by_label("数据源名称", exact=True).fill(name)
    region.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(region.get_by_text("配置已保存；保存不会调用外部服务。", exact=True)).to_be_visible()


def test_ssb01_platform_test_refresh_disable_and_regular_user(source_browser):
    page, region, worker, provider = system_page(source_browser)
    save(region, "System arXiv")
    region.get_by_label("我了解测试会向", exact=False).check()
    region.get_by_role("button", name="测试数据源连接", exact=True).click()
    expect(region.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    region.get_by_role("button", name="刷新数据源测试状态", exact=True).click()
    expect(region.get_by_label("数据源测试详情", exact=True)).to_contain_text("成功")
    region.get_by_label("启用数据源", exact=True).uncheck()
    region.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(region.get_by_role("button", name="System arXiv · 禁用", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("button", name="系统数据源", exact=True).click()
    region.get_by_role("button", name="System arXiv · 禁用", exact=True).click()
    expect(region.get_by_label("启用数据源", exact=True)).not_to_be_checked()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    out = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task033_system_sources_2026-10-26"
    )
    page.screenshot(path=str(out / "system-source-mobile.png"), full_page=True)
    context = page.context.browser.new_context()
    try:
        user = context.new_page()
        register_ui(user, page.url.split("/workspace")[0], "Reader", "reader@example.invalid")
        login_ui(user, "Reader")
        expect(user.get_by_role("button", name="系统数据源", exact=True)).to_have_count(0)
        user.get_by_role("button", name="数据源设置", exact=True).click()
        expect(user.get_by_role("button", name="System arXiv · 禁用", exact=True)).to_have_count(0)
    finally:
        context.close()
    assert len(provider.calls) == 1


def test_ssb02_unknown_create_and_separate_drafts(source_browser):
    page, region, worker, provider = system_page(source_browser)

    def drop(route):
        route.fetch()
        route.abort("failed")

    page.route("**/api/v1/admin/data-source-configs", drop, times=1)
    region.get_by_label("数据源名称", exact=True).fill("Lost source")
    region.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(
        region.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="个人资料", exact=True).click()
    page.get_by_role("button", name="系统数据源", exact=True).click()
    region.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(region.get_by_role("button", name="Lost source · 启用", exact=True)).to_have_count(1)
    region.get_by_label("数据源名称", exact=True).fill("System draft")
    page.get_by_role("button", name="数据源设置", exact=True).click()
    personal = page.get_by_role("region", name="数据源设置", exact=True)
    personal.get_by_label("数据源名称", exact=True).fill("Personal draft")
    page.get_by_role("button", name="系统数据源", exact=True).click()
    expect(region.get_by_label("数据源名称", exact=True)).to_have_value("System draft")
    page.get_by_role("button", name="数据源设置", exact=True).click()
    expect(personal.get_by_label("数据源名称", exact=True)).to_have_value("Personal draft")
    assert not provider.calls


def test_ssb03_four_personal_api_configs_persist_separately(source_browser):
    page, worker, provider = source_browser
    region = page.get_by_role("region", name="数据源设置", exact=True)
    for index, name in enumerate(["arxiv", "openalex", "semantic_scholar", "ads"]):
        if index:
            region.get_by_role("button", name="新增数据源配置", exact=True).click()
        region.get_by_label("数据源类型", exact=True).select_option(name)
        region.get_by_label("检索服务/API入口", exact=True).fill(
            "https://" + name.replace("_", "-") + ".example.invalid/api"
        )
        if name != "arxiv":
            region.get_by_label("访问模式", exact=True).select_option("api_key")
            region.get_by_label("数据源API密钥（留空保持已存值）", exact=True).fill(
                "PRIVATE-" + name
            )
        save(region, name)
    page.reload()
    page.get_by_role("button", name="数据源设置", exact=True).click()
    for name in ["arxiv", "openalex", "semantic_scholar", "ads"]:
        region.get_by_role("button", name=name + " · 启用", exact=True).click()
        expect(region.get_by_label("数据源类型", exact=True)).to_have_value(name)
        expect(region.get_by_label("检索服务/API入口", exact=True)).to_have_value(
            "https://" + name.replace("_", "-") + ".example.invalid/api"
        )
        expect(region.get_by_label("数据源API密钥（留空保持已存值）", exact=True)).to_have_value("")
        if name != "arxiv":
            expect(region.get_by_text("已保存凭据，无法读取明文。", exact=False)).to_be_visible()
    assert not provider.calls


def test_ssb04_unknown_patch_reads_committed_config_without_resubmission(source_browser):
    page, region, worker, provider = system_page(source_browser)
    save(region, "Original")
    writes = []

    def drop(route):
        if route.request.method == "PATCH":
            writes.append(route.request.post_data_json)
            response = route.fetch()
            assert response.status == 200
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/admin/data-source-configs/*", drop)
    region.get_by_label("数据源名称", exact=True).fill("Committed rename")
    region.get_by_role("button", name="保存数据源配置", exact=True).click()
    expect(
        region.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="个人资料", exact=True).click()
    page.get_by_role("button", name="系统数据源", exact=True).click()
    expect(region.get_by_label("数据源名称", exact=True)).to_have_value("Committed rename")
    region.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(region.get_by_role("button", name="Committed rename · 启用", exact=True)).to_have_count(
        1
    )
    assert len(writes) == 1 and not provider.calls
