"""LU: browser -> real HTTP -> isolated PostgreSQL -> deterministic LLM worker."""

import json

import pytest
from cryptography.fernet import Fernet
from playwright.sync_api import expect
from test_browser_business import browser_app, login_ui, register_ui  # noqa: F401
from test_llm_configuration import FakeProvider

from rpb.adapters.auth import AccountStore
from rpb.adapters.llm import LLMStore
from rpb.adapters.llm_worker import LLMWorker
from rpb.bootstrap import business


@pytest.fixture
def llm_browser(db, monkeypatch, request):
    key = Fernet.generate_key()
    compose = business.create_business_app
    monkeypatch.setattr(
        business,
        "create_business_app",
        lambda engine, origin, encryption_key=None: compose(engine, origin, key),
    )
    provider = FakeProvider()
    worker = LLMWorker(LLMStore(AccountStore(db[0]), key), provider)
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_role("button", name="LLM设置", exact=True).click()
    yield page, worker, provider
    context.close()


def fill_config(page):
    page.get_by_label("配置名称", exact=True).fill("My model")
    page.get_by_label("API密钥（留空保持已存值）", exact=True).fill("SECRET-BROWSER-KEY")
    page.get_by_label("temperature", exact=True).fill("0")


def test_lu01_save_discover_test_select_reload_and_invalidate(llm_browser):
    page, worker, provider = llm_browser
    fill_config(page)
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    assert provider.calls == []
    expect(page.get_by_label("API密钥（留空保持已存值）", exact=True)).to_have_value("")
    page.get_by_role("button", name="刷新可发现模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_role("button", name="model-a：待测试或失败", exact=True)).to_be_visible()
    expect(page.get_by_label("当前模型", exact=True).locator("option")).to_have_count(1)
    page.get_by_role("button", name="model-a：待测试或失败", exact=True).click()
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_role("button", name="model-a：测试通过", exact=True)).to_be_visible()
    picker = page.get_by_label("当前模型", exact=True)
    expect(picker.locator("option")).to_have_count(2)
    picker.select_option(label="My model / model-a")
    expect(picker).not_to_have_value("")
    selected = picker.input_value()
    page.reload()
    expect(page.get_by_label("当前模型", exact=True)).to_have_value(selected)
    page.get_by_role("button", name="LLM设置", exact=True).click()
    page.get_by_role("button", name="My model", exact=True).click()
    expect(page.get_by_label("temperature", exact=True)).to_have_value("0")
    page.get_by_label("temperature", exact=True).fill("0.5")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_label("当前模型", exact=True)).to_contain_text("原模型已失效")
    assert len(provider.calls) == 2


def test_lu02_duplicate_json_and_unsaved_switch(llm_browser):
    page, _, provider = llm_browser
    fill_config(page)
    page.get_by_label("高级参数 JSON", exact=True).fill('{"seed":0,"seed":1}')
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("参数JSON无效或有重复字段，请修正后保存。", exact=True)).to_be_visible()
    page.get_by_role("button", name="新增LLM配置", exact=True).click()
    expect(page.get_by_role("group", name="未保存修改")).to_be_visible()
    page.get_by_role("button", name="留在当前配置", exact=True).click()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("My model")
    page.get_by_label("高级参数 JSON", exact=True).fill('{"seed":0}')
    page.get_by_role("button", name="新增LLM配置", exact=True).click()
    page.get_by_role("button", name="保存并切换", exact=True).click()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("")
    page.get_by_role("button", name="My model", exact=True).click()
    expect(page.get_by_label("高级参数 JSON", exact=True)).to_have_value(
        json.dumps({"seed": 0}, indent=2)
    )
    assert provider.calls == []


def test_lu03_lost_create_and_test_reply_reuses_command(llm_browser):
    page, worker, provider = llm_browser
    fill_config(page)
    keys = []

    def lose(route):
        keys.append(route.request.headers["idempotency-key"])
        route.fetch()
        route.abort("failed")

    page.route("**/api/v1/me/llm-configs", lose)
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(
        page.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True)
    ).to_be_visible()
    page.unroute("**/api/v1/me/llm-configs", lose)

    def capture(route):
        keys.append(route.request.headers["idempotency-key"])
        route.continue_()

    page.route("**/api/v1/me/llm-configs", capture)
    page.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True).click()
    expect(page.get_by_text("已保存凭据，无法读取明文。", exact=True)).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    page.unroute("**/api/v1/me/llm-configs", capture)
    keys.clear()
    page.get_by_label("模型ID（可手工填写）", exact=True).fill("manual-model")
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.route("**/test", lose)
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("button", name="核查同一测试请求", exact=True)).to_be_enabled()
    assert worker.run_once()
    page.unroute("**/test", lose)
    page.route("**/test", capture)
    page.get_by_role("button", name="核查同一测试请求", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("succeeded")
    assert keys[0] == keys[1] and len(provider.calls) == 1
    assert not worker.run_once()


def test_lu04_poll_does_not_upgrade_edit_revision(llm_browser):
    page, worker, _ = llm_browser
    fill_config(page)
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    page.get_by_label("模型ID（可手工填写）", exact=True).fill("manual")
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    other = page.context.new_page()
    other.goto(page.url)
    other.get_by_role("button", name="LLM设置", exact=True).click()
    other.get_by_role("button", name="My model", exact=True).click()
    other.get_by_label("配置名称", exact=True).fill("Edited elsewhere")
    other.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(other.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("succeeded")
    page.get_by_label("temperature", exact=True).fill("0.5")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(
        page.get_by_text("配置已被其他操作修改。草稿保留，请核查当前内容。", exact=True)
    ).to_be_visible()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("My model")
    other.reload()
    other.get_by_role("button", name="LLM设置", exact=True).click()
    other.get_by_role("button", name="Edited elsewhere", exact=True).click()
    expect(other.get_by_label("temperature", exact=True)).to_have_value("0")
    other.close()


def test_lu05_consent_failure_details_and_extension_values(llm_browser):
    page, worker, provider = llm_browser
    fill_config(page)
    page.get_by_label("扩展参数名", exact=True).select_option("reasoning_effort")
    page.get_by_label("扩展参数值（JSON类型）", exact=True).fill('"low"')
    page.get_by_role("button", name="添加或更新扩展参数", exact=True).click()
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    page.get_by_label("模型ID（可手工填写）", exact=True).fill("manual")
    expect(page.get_by_role("button", name="测试所选模型", exact=True)).to_be_disabled()
    assert not worker.run_once() and provider.calls == []
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    provider.error = "PROVIDER_RATE_LIMITED"
    assert worker.run_once()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_label("测试详情", exact=True)).to_contain_text("PROVIDER_RATE_LIMITED")
    expect(page.get_by_label("当前模型", exact=True).locator("option")).to_have_count(1)


def test_lu06_lost_patch_and_delete_are_reconciled(llm_browser):
    page, _, provider = llm_browser
    fill_config(page)
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()

    def lose(route):
        if route.request.method in {"PATCH", "DELETE"}:
            route.fetch()
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/me/llm-configs/*", lose)
    page.get_by_label("配置名称", exact=True).fill("Updated once")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    recovery = page.get_by_role("button", name="核查当前配置（加载将放弃草稿）", exact=True)
    expect(recovery).to_be_enabled()
    page.unroute("**/api/v1/me/llm-configs/*", lose)
    recovery.click()
    expect(page.get_by_role("button", name="Updated once", exact=True)).to_be_visible()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("Updated once")
    page.route("**/api/v1/me/llm-configs/*", lose)
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="删除LLM配置", exact=True).click()
    expect(recovery).to_be_enabled()
    page.unroute("**/api/v1/me/llm-configs/*", lose)
    recovery.click()
    expect(page.get_by_label("配置名称", exact=True)).to_have_value("")
    expect(page.get_by_role("button", name="Updated once", exact=True)).to_have_count(0)
    assert provider.calls == []


def test_lu07_other_tab_account_change_clears_private_draft(llm_browser):
    page, _, _ = llm_browser
    fill_config(page)
    other = page.context.new_page()
    other.goto(page.url)
    other.get_by_role("button", name="退出登录", exact=True).click()
    expect(other.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
    register_ui(other, page.url.rsplit("/workspace", 1)[0], "SecondUser", "second@example.invalid")
    login_ui(other, "SecondUser")
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
    expect(page.get_by_label("API密钥（留空保持已存值）", exact=True)).to_have_count(0)
    other.close()


def test_lu08_rejected_test_can_repair_credentials(llm_browser):
    page, worker, provider = llm_browser
    page.get_by_label("配置名称", exact=True).fill("No credential yet")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    page.get_by_label("模型ID（可手工填写）", exact=True).fill("manual")
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(
        page.get_by_text("凭据不可用，请配置密钥或检查服务端密钥保管设置。", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("button", name="保存LLM配置", exact=True)).to_be_enabled()
    assert not worker.run_once()
    page.get_by_label("API密钥（留空保持已存值）", exact=True).fill("REPAIRED")
    page.get_by_label("temperature", exact=True).fill("0")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_label("测试详情", exact=True)).to_contain_text('"temperature": 0')
    assert len(provider.calls) == 1


def test_lu09_actual_anthropic_test_override_is_visible(llm_browser):
    from rpb.adapters.llm_provider import HTTPProvider

    page, worker, _ = llm_browser
    sent = []

    class LocalProtocolStub(HTTPProvider):
        def request(self, *args):
            with args[-1]():
                sent.append(args[5])
            return {"content": [{"type": "text", "text": "OK"}]}

    worker.provider = LocalProtocolStub()
    page.get_by_label("配置名称", exact=True).fill("Anthropic protocol")
    page.get_by_label("Provider", exact=True).select_option("anthropic")
    page.get_by_label("Base URL", exact=True).fill("https://example.invalid/v1")
    page.get_by_label("API密钥（留空保持已存值）", exact=True).fill("LOCAL-STUB-KEY")
    page.get_by_role("button", name="保存LLM配置", exact=True).click()
    expect(page.get_by_text("配置已保存；保存不会调用模型。", exact=True)).to_be_visible()
    page.get_by_label("模型ID（可手工填写）", exact=True).fill("model")
    page.get_by_label("我了解测试会调用", exact=False).check()
    page.get_by_role("button", name="测试所选模型", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("queued")
    assert worker.run_once()
    page.get_by_role("button", name="刷新测试状态", exact=True).click()
    expect(page.get_by_label("测试详情", exact=True)).to_contain_text('"max_tokens": 32')
    assert sent[0]["max_tokens"] == 32 and len(sent) == 1
