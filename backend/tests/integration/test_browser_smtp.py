"""SMB: real browser/HTTP/PG SMTP editor; no external mail delivery."""

from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from playwright.sync_api import expect
from test_browser_business import PASSWORD, browser_app, login_ui, register_ui  # noqa: F401

from rpb.adapters.smtp_tables import handshakes
from rpb.adapters.smtp_worker import SMTPWorker
from rpb.bootstrap import business


@pytest.fixture
def smtp_browser(db, monkeypatch, request):
    key = Fernet.generate_key()
    compose = business.create_business_app
    apps = []

    def configured_app(engine, origin, encryption_key=None):
        app = compose(engine, origin, key)
        apps.append(app)
        return app

    monkeypatch.setattr(business, "create_business_app", configured_app)
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    context = browser.new_context()
    page = context.new_page()
    register_ui(page, base)
    login_ui(page)
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    region = page.get_by_role("region", name="系统SMTP设置", exact=True)
    expect(region.get_by_role("button", name="保存SMTP配置", exact=True)).to_be_enabled()
    yield page, region, base, key, engine, apps[0]
    context.close()


def fill_password(region):
    region.get_by_label("发件邮箱", exact=True).fill("sender@qq.com")
    region.get_by_label("SMTP账号", exact=True).fill("sender@qq.com")
    region.get_by_label("SMTP授权码或应用密码", exact=True).fill("BROWSER-APP-PASSWORD")


def save(region):
    region.get_by_role("button", name="保存SMTP配置", exact=True).click()
    expect(region.get_by_text("SMTP配置已保存；保存不会连接外部服务。", exact=True)).to_be_visible()


def test_smb01_save_refresh_secret_and_mobile(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    fill_password(region)
    save(region)
    expect(region.get_by_label("SMTP授权码或应用密码", exact=True)).to_have_value("")
    expect(region.get_by_text("已保存凭据，留空保持；无法读取明文。", exact=False)).to_be_visible()
    value = page.request.get(base + "/api/v1/admin/smtp-config").json()["data"]
    assert value["configured"] and value["config"]["secret"]["configured"]
    assert "BROWSER-APP-PASSWORD" not in str(value)
    assert value["config"]["connection_status"] == "untested"
    page.reload()
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    expect(region.get_by_label("发件邮箱", exact=True)).to_have_value("sender@qq.com")
    expect(region.get_by_label("SMTP授权码或应用密码", exact=True)).to_have_value("")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    output = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task035_smtp_security_2026-10-26/browser"
    )
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / "smtp-mobile.png"), full_page=True)
    assert region.get_by_role("button", name="删除SMTP配置", exact=True).count() == 0


def test_smb02_unknown_put_is_read_back_without_resubmission(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    writes = []

    def drop(route):
        if route.request.method == "PUT":
            writes.append(route.request.post_data_json)
            assert route.fetch().status == 200
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/admin/smtp-config", drop)
    fill_password(region)
    region.get_by_role("button", name="保存SMTP配置", exact=True).click()
    recover = region.get_by_role("button", name="核查SMTP配置（加载将放弃草稿）", exact=True)
    expect(recover).to_be_visible()
    page.get_by_role("button", name="基础安全", exact=True).click()
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    expect(region.get_by_label("SMTP账号", exact=True)).to_have_value("sender@qq.com")
    recover.click()
    expect(region.get_by_text("已加载当前SMTP配置。", exact=True)).to_be_visible()
    expect(region.get_by_label("SMTP授权码或应用密码", exact=True)).to_have_value("")
    assert len(writes) == 1
    assert page.request.get(base + "/api/v1/admin/smtp-config").json()["data"]["configured"]


def test_smb03_service_auth_fields_and_navigation_drafts(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    fill_password(region)
    save(region)
    region.get_by_label("邮件服务", exact=True).select_option("sendgrid")
    expect(region.get_by_label("SMTP认证方式", exact=True)).to_have_value("api_key")
    expect(region.get_by_label("SMTP账号", exact=True)).to_have_count(0)
    region.get_by_label("发件邮箱", exact=True).fill("sender@example.org")
    region.get_by_label("SMTP API Key", exact=True).fill("SENDGRID-BROWSER-KEY")
    save(region)
    assert (
        page.request.get(base + "/api/v1/admin/smtp-config").json()["data"]["config"]["provider"]
        == "sendgrid"
    )
    region.get_by_label("邮件服务", exact=True).select_option("gmail")
    region.get_by_label("SMTP账号", exact=True).fill("sender@gmail.com")
    region.get_by_label("OAuth Client ID", exact=True).fill("browser-client")
    region.get_by_label("OAuth Client Secret", exact=True).fill("BROWSER-OAUTH-SECRET")
    page.get_by_role("button", name="基础安全", exact=True).click()
    security = page.get_by_role("region", name="基础安全设置", exact=True)
    expect(security.get_by_role("button", name="保存安全配置", exact=True)).to_be_enabled()
    security.get_by_label("连接测试超时（秒）", exact=True).fill("21")
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    expect(region.get_by_label("OAuth Client ID", exact=True)).to_have_value("browser-client")
    expect(region.get_by_label("OAuth Client Secret", exact=True)).to_have_value(
        "BROWSER-OAUTH-SECRET"
    )
    save(region)
    expect(region.get_by_label("OAuth Client Secret", exact=True)).to_have_value("")
    expect(region.get_by_role("button", name="连接发件账号", exact=True)).to_be_visible()
    assert region.get_by_label("Access Token", exact=True).count() == 0
    page.get_by_role("button", name="基础安全", exact=True).click()
    expect(security.get_by_label("连接测试超时（秒）", exact=True)).to_have_value("21")


def test_smb04_regular_user_and_stale_admin_form_do_not_write(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    fill_password(region)
    save(region)
    context = page.context.browser.new_context()
    try:
        reader = context.new_page()
        register_ui(reader, base, "SMTPReader", "smtp-reader@example.invalid")
        login_ui(reader, "SMTPReader")
        expect(reader.get_by_role("button", name="系统SMTP", exact=True)).to_have_count(0)
        assert reader.request.get(base + "/api/v1/admin/smtp-config").status == 404
        csrf = page.request.get(base + "/api/v1/auth/csrf").json()["data"]["csrf_token"]
        response = page.request.post(
            base + "/api/v1/auth/login",
            headers={"Origin": base, "X-CSRF-Token": csrf},
            data={"identifier": "SMTPReader", "password": PASSWORD},
        )
        assert response.status == 200
        writes = []
        page.on(
            "request",
            lambda request: writes.append(request.url) if request.method == "PUT" else None,
        )
        region.get_by_label("发件邮箱", exact=True).fill("must-not-save@example.org")
        region.get_by_role("button", name="保存SMTP配置", exact=True).click()
        expect(page.get_by_role("heading", name="欢迎回来", exact=True)).to_be_visible()
        assert not writes
        expect(page.get_by_label("SMTP授权码或应用密码", exact=True)).to_have_count(0)
    finally:
        context.close()


class FakeSMTP:
    def __init__(self):
        self.calls = []

    def execute(self, config, secret, timeout):
        self.calls.append((config, secret, timeout))
        return {"authenticated": True}


class FakeOAuth:
    def __init__(self):
        self.calls = []

    def exchange(self, config, client_secret, fields, timeout=30):
        self.calls.append((config, client_secret, fields, timeout))
        return {
            "access_token": "BROWSER-ACCESS",
            "refresh_token": "BROWSER-REFRESH",
            "token_type": "Bearer",
            "expires_in": 3600,
        }


def test_smb05_oauth_callback_and_explicit_test_with_no_external_access(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    oauth, provider = FakeOAuth(), FakeSMTP()
    app.state.smtp_store.oauth = oauth
    worker = SMTPWorker(app.state.smtp_store, provider)
    region.get_by_label("邮件服务", exact=True).select_option("gmail")
    region.get_by_label("发件邮箱", exact=True).fill("sender@gmail.com")
    region.get_by_label("SMTP账号", exact=True).fill("sender@gmail.com")
    region.get_by_label("OAuth Client ID", exact=True).fill("browser-client")
    region.get_by_label("OAuth Client Secret", exact=True).fill("BROWSER-OAUTH-SECRET")
    save(region)
    assert not oauth.calls and not provider.calls
    auth_urls = []

    def authorize(route):
        auth_urls.append(route.request.url)
        query = parse_qs(urlsplit(route.request.url).query)
        assert query["client_id"] == ["browser-client"]
        assert query["code_challenge_method"] == ["S256"]
        callback = (
            base
            + "/api/v1/admin/smtp-config/oauth/callback?"
            + urlencode({"state": query["state"][0], "code": "browser-code"})
        )
        route.fulfill(status=302, headers={"Location": callback}, body="")

    page.route("https://accounts.google.com/**", authorize)
    region.get_by_role("button", name="连接发件账号", exact=True).click()
    expect(region.get_by_text("OAuth状态：已授权，可按需刷新", exact=True)).to_be_visible()
    assert len(auth_urls) == len(oauth.calls) == 1
    assert "smtp_oauth" not in page.url and "code=" not in page.url
    assert not provider.calls
    value = page.request.get(base + "/api/v1/admin/smtp-config").json()["data"]
    assert value["config"]["connection_status"] == "untested"
    assert "BROWSER-ACCESS" not in str(value) and "BROWSER-REFRESH" not in str(value)
    region.get_by_role("button", name="测试SMTP连接", exact=True).click()
    expect(region.get_by_text("SMTP任务状态：queued", exact=False)).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新SMTP测试状态", exact=True).click()
    expect(region.get_by_label("SMTP测试详情", exact=True)).to_contain_text("成功")
    assert len(provider.calls) == 1 and provider.calls[0][1] == "BROWSER-ACCESS"
    page.reload()
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    expect(region.get_by_text("OAuth状态：已授权，可按需刷新", exact=True)).to_be_visible()


def test_smb06_unknown_test_reuses_key_and_single_task(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    provider = FakeSMTP()
    worker = SMTPWorker(app.state.smtp_store, provider)
    fill_password(region)
    save(region)
    keys, ids = [], []

    def lose_first(route):
        keys.append(route.request.headers["idempotency-key"])
        response = route.fetch()
        assert response.status == 202
        ids.append(response.json()["data"]["task_id"])
        if len(keys) == 1:
            route.abort("failed")
        else:
            route.fulfill(response=response)

    page.route("**/api/v1/admin/smtp-config/test", lose_first)
    region.get_by_role("button", name="测试SMTP连接", exact=True).click()
    expect(region.get_by_role("button", name="核查同一SMTP请求", exact=True)).to_be_visible()
    page.get_by_role("button", name="个人资料", exact=True).click()
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    region.get_by_role("button", name="核查同一SMTP请求", exact=True).click()
    expect(region.get_by_text("SMTP任务状态：queued", exact=False)).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1] and ids[0] == ids[1]
    assert worker.run_once() and not worker.run_once()
    assert len(provider.calls) == 1


def test_smb07_unknown_oauth_start_reuses_handshake_then_real_callback(smtp_browser):
    page, region, base, key, engine, app = smtp_browser
    oauth = FakeOAuth()
    app.state.smtp_store.oauth = oauth
    region.get_by_label("邮件服务", exact=True).select_option("gmail")
    region.get_by_label("发件邮箱", exact=True).fill("sender@gmail.com")
    region.get_by_label("SMTP账号", exact=True).fill("sender@gmail.com")
    region.get_by_label("OAuth Client ID", exact=True).fill("recover-browser-client")
    region.get_by_label("OAuth Client Secret", exact=True).fill("RECOVER-OAUTH-SECRET")
    save(region)
    keys, started_urls, navigations = [], [], []

    def lose_first_start(route):
        keys.append(route.request.headers["idempotency-key"])
        response = route.fetch()
        assert response.status == 200
        started_urls.append(response.json()["data"]["authorization_url"])
        if len(keys) == 1:
            route.abort("failed")
        else:
            route.fulfill(response=response)

    def authorize(route):
        navigations.append(route.request.url)
        query = parse_qs(urlsplit(route.request.url).query)
        assert query["client_id"] == ["recover-browser-client"]
        assert query["code_challenge_method"] == ["S256"]
        callback = (
            base
            + "/api/v1/admin/smtp-config/oauth/callback?"
            + urlencode({"state": query["state"][0], "code": "recovered-browser-code"})
        )
        route.fulfill(status=302, headers={"Location": callback}, body="")

    page.route("**/api/v1/admin/smtp-config/oauth/start", lose_first_start)
    page.route("https://accounts.google.com/**", authorize)
    region.get_by_role("button", name="连接发件账号", exact=True).click()
    expect(region.get_by_role("button", name="核查同一SMTP请求", exact=True)).to_be_visible()
    # Pending is rendered before the CSRF/read preflight; wait until the dropped
    # response has actually completed and recovery is actionable.
    expect(region.get_by_role("button", name="核查同一SMTP请求", exact=True)).to_be_enabled()
    assert len(keys) == 1 and not oauth.calls and not navigations
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(handshakes)) == 1
        assert not conn.scalar(sa.select(handshakes.c.used))
    page.get_by_role("button", name="基础安全", exact=True).click()
    page.get_by_role("button", name="系统SMTP", exact=True).click()
    region.get_by_role("button", name="核查同一SMTP请求", exact=True).click()
    expect(region.get_by_text("OAuth状态：已授权，可按需刷新", exact=True)).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    assert started_urls[0] == started_urls[1]
    assert navigations == [started_urls[0]] and len(oauth.calls) == 1
    assert "smtp_oauth" not in page.url and "code=" not in page.url
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(handshakes)) == 1
        assert conn.scalar(sa.select(handshakes.c.used))
    current = page.request.get(base + "/api/v1/admin/smtp-config").json()["data"]
    assert current["config"]["oauth_status"] == "connected"
    assert current["config"]["connection_status"] == "untested"
