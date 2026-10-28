"""SB: browser system configuration, user selection, recovery and draft isolation."""

from pathlib import Path

from playwright.sync_api import expect
from test_browser_business import browser_app, login_ui, register_ui  # noqa: F401
from test_browser_llm import llm_browser as inherited_llm_browser

from rpb.adapters.llm import LLMStore
from rpb.adapters.llm_worker import LLMWorker

llm_browser = inherited_llm_browser


def system_page(llm_browser):
    page, private_worker, provider = llm_browser
    store = LLMStore(private_worker.store.account, system=True)
    store.cipher = private_worker.store.cipher
    page.get_by_role("button", name="系统LLM", exact=True).click()
    return page, LLMWorker(store, provider), provider


def save_config(page):
    page.get_by_label("配置名称", exact=True).fill("Shared model")
    page.get_by_label("API密钥（留空保持已存值）", exact=True).fill("BROWSER-SYSTEM-SECRET")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()


def test_sb01_admin_test_user_select_restore_and_invalidate(llm_browser):
    page, worker, provider = system_page(llm_browser)
    save_config(page)
    assert provider.calls == []
    page.get_by_label("模型ID（可手工填写）", exact=True).fill("model-a")
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_role("button", name="model-a：测试通过", exact=True)).to_be_visible()
    context = page.context.browser.new_context(viewport={"width": 390, "height": 844})
    user = context.new_page()
    try:
        base = page.url.split("/workspace")[0]
        register_ui(user, base, "Reader", "reader@example.invalid")
        login_ui(user, "Reader")
        expect(user.get_by_role("button", name="系统LLM", exact=True)).to_have_count(0)
        picker = user.get_by_label("当前模型", exact=True)
        expect(picker).to_have_value("")
        picker.select_option(label="系统 / Shared model / model-a")
        expect(picker).not_to_have_value("")
        selected = picker.input_value()
        user.reload()
        expect(user.get_by_label("当前模型", exact=True)).to_have_value(selected)
        page.get_by_label("temperature", exact=True).fill("0.2")
        page.get_by_role("button", name="保存LLM配置", exact=True).click()
        expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
        expect(page.get_by_label("测试详情", exact=True)).to_have_count(0)
        expect(page.get_by_role("status")).to_have_count(0)
        user.get_by_role("button", name="刷新模型选择", exact=True).click()
        expect(user.get_by_label("当前模型", exact=True)).to_contain_text("原模型已失效")
        expect(user.get_by_label("当前模型", exact=True)).to_have_value(selected)
        out = (
            Path(__file__).resolve().parents[3]
            / "docs/workorders/evidence/task031_system_llm_2026-10-26"
        )
        page.screenshot(path=str(out / "system-admin.png"), full_page=True)
        user.screenshot(path=str(out / "user-invalid-mobile.png"), full_page=True)
        assert len(provider.calls) == 1
    finally:
        context.close()


def test_sb02_lost_create_and_separate_drafts(llm_browser):
    page, worker, provider = system_page(llm_browser)

    def drop(route):
        route.fetch()
        route.abort("failed")

    page.route("**/api/v1/admin/llm-configs", drop, times=1)
    page.get_by_label("配置名称", exact=True).fill("Shared model")
    page.get_by_label("API密钥（留空保持已存值）", exact=True).fill("BROWSER-SYSTEM-SECRET")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_role("button", name="核查当前配置（加载将放弃草稿）")).to_be_visible()
    page.get_by_role("button", name="个人资料", exact=True).click()
    page.get_by_role("button", name="系统LLM", exact=True).click()
    expect(page.get_by_role("button", name="核查当前配置（加载将放弃草稿）")).to_be_visible()
    page.get_by_role("button", name="核查当前配置（加载将放弃草稿）").click()
    expect(page.get_by_role("button", name="Shared model", exact=True)).to_have_count(1)
    expect(page.get_by_label("API密钥（留空保持已存值）", exact=True)).to_have_value("")
    page.get_by_label("配置名称", exact=True).fill("System draft")
    page.get_by_role("button", name="LLM设置", exact=True).click()
    page.get_by_label("配置名称", exact=True).fill("Personal draft")
    page.get_by_role("button", name="系统LLM", exact=True).click()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("System draft")
    page.get_by_role("button", name="LLM设置", exact=True).click()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("Personal draft")
    assert not provider.calls


def test_sb03_unknown_patch_keeps_draft_and_reads_committed_result(llm_browser):
    page, worker, provider = system_page(llm_browser)
    save_config(page)
    writes = []

    def drop_patch(route):
        if route.request.method == "PATCH":
            writes.append(route.request.post_data_json)
            response = route.fetch()
            assert response.status == 200
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/admin/llm-configs/*", drop_patch)
    page.get_by_label("配置名称", exact=True).fill("Committed rename")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_role("button", name="核查当前配置（加载将放弃草稿）")).to_be_visible()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("Committed rename")
    expect(page.get_by_role("button", name="保存LLM配置", exact=True)).to_be_disabled()
    page.get_by_role("button", name="管理员用户", exact=True).click()
    page.get_by_role("button", name="系统LLM", exact=True).click()
    expect(page.get_by_role("button", name="核查当前配置（加载将放弃草稿）")).to_be_visible()
    page.get_by_role("button", name="核查当前配置（加载将放弃草稿）").click()
    expect(page.get_by_role("button", name="Committed rename", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="保存LLM配置", exact=True)).to_be_enabled()
    assert len(writes) == 1 and not provider.calls
