# ruff: noqa: F811
"""Real browser, durable HTTP and isolated PG with controlled external providers."""

import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from playwright.sync_api import expect
from test_browser_business import browser_app  # noqa: F401
from test_browser_terms import enter
from test_construction_runs import Papers, setup

from rpb.adapters.run_worker import RunWorker
from rpb.bootstrap import business


def configured_browser(monkeypatch, request):
    key = Fernet.generate_key()
    compose = business.create_business_app
    apps = []

    def configured(engine, origin, encryption_key=None):
        app = compose(engine, origin, key)
        apps.append(app)
        return app

    monkeypatch.setattr(business, "create_business_app", configured)
    browser, base, engine, run_id = request.getfixturevalue("browser_app")
    page, _ = enter(browser, base)
    client = TestClient(apps[0], base_url=base)
    for cookie in page.context.cookies():
        client.cookies.set(cookie["name"], cookie["value"])
    headers = {
        "Origin": base,
        "X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"],
    }
    root = "/api/v1/projects/" + page.url.split("project=")[1]
    body, _ = setup((client, headers, root, apps[0], engine, key))
    assert (
        client.put(
            "/api/v1/me/model-selection",
            headers=headers,
            json={
                "selection": body["model_selection"],
                "expected_revision": client.get("/api/v1/me/model-selection").json()["data"][
                    "revision"
                ],
            },
        ).status_code
        == 200
    )
    page.reload()
    region = page.get_by_role("region", name="构建运行", exact=True)
    expect(region.get_by_label("graph", exact=True)).to_be_enabled()
    return page, region, apps[0], client, headers, root


def test_crb01_start_wait_refresh_cancel_mobile_and_logout(monkeypatch, request):
    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    from test_search_terms import post

    source = post(
        client,
        headers,
        "/api/v1/me/data-source-configs",
        {
            "name": "disabled",
            "provider": "openalex",
            "base_url": "https://api.openalex.org",
            "access_mode": "anonymous",
            "enabled": False,
        },
        "browser-disabled-source1",
    ).json()["data"]
    term = post(
        client,
        headers,
        root + "/construction-workspace/search-terms",
        {
            "query": "blocked term",
            "source_policy": {
                "mode": "selected",
                "source_refs": [{"source": "user", "config_id": source["id"]}],
            },
        },
        "browser-blocked-term001",
    ).json()["data"]
    assert (
        post(
            client,
            headers,
            root + "/construction-workspace/search-terms/" + term["id"] + "/confirm",
            {
                "expected_revision": term["revision"],
                "confirmation_token": term["confirmations"][0]["confirmation_token"],
                "acknowledged_risk_ids": [],
            },
            "browser-blocked-confirm1",
        ).status_code
        == 200
    )
    page.reload()
    region.get_by_label("blocked term", exact=True).check()
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, Papers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(region.get_by_role("heading", name="检索结果待确认", exact=True)).to_be_visible()
    expect(region.get_by_text("Research result", exact=True)).to_be_visible()
    expect(region.get_by_text("CONFIG_SOURCE_DISABLED", exact=False)).to_have_count(2)
    expect(region.get_by_text("的部分来源不可用", exact=False)).to_be_visible()
    region.get_by_text("本轮输入与模型", exact=True).click()
    expect(region.get_by_text("本轮模型：user / fake-model", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    out = (
        Path(__file__).resolve().parents[3]
        / "docs/workorders/evidence/task040_construction_runtime_2026-10-28/browser"
    )
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / "run-mobile.png"), full_page=True)
    # Another tab cancels; refresh must not leave the cleaned body on screen.
    run = client.get(root + "/construction-runs").json()["data"]["items"][0]
    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    response = client.post(
        root + "/construction-runs/" + run["id"] + "/cancel",
        headers=headers | {"Idempotency-Key": "browser-other-tab-cancel"},
        json={"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
    )
    assert response.status_code == 200, response.text
    region.get_by_role("button", name="刷新运行与配置", exact=True).click()
    expect(region.get_by_role("heading", name="已取消", exact=True)).to_be_visible()
    expect(region.get_by_text("Research result", exact=True)).to_have_count(0)
    page.reload()
    expect(region.get_by_role("button", name="启动检索", exact=True)).to_be_visible()
    page.get_by_role("button", name="退出登录", exact=True).click()
    expect(region).to_have_count(0)
    page.close()


def test_crb02_accepted_http_500_replays_original_command(monkeypatch, request):
    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    keys = []

    def fail_response(route):
        if route.request.method == "POST":
            keys.append(route.request.headers["idempotency-key"])
            response = route.fetch()
            assert response.status == 202
            if len(keys) == 1:
                route.fulfill(
                    status=500,
                    content_type="application/json",
                    body='{"error":{"code":"INTERNAL_ERROR","message":"unknown"}}',
                )
            else:
                route.fulfill(response=response)
        else:
            route.continue_()

    page.route("**/construction-runs", fail_response)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("button", name="用原请求核查重试", exact=True)).to_be_enabled()
    expect(region.get_by_role("button", name="启动检索", exact=True)).to_be_disabled()
    region.get_by_role("button", name="用原请求核查重试", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    assert len(client.get(root + "/construction-runs").json()["data"]["items"]) == 1
    region.get_by_role("button", name="取消本次构建", exact=True).click()
    expect(region.get_by_role("heading", name="已取消", exact=True)).to_be_visible()
    page.close()


def test_pdb01_confirm_correct_refresh_unknown_submit_and_cancel(monkeypatch, request):
    from test_paper_deduplication import RepeatedPapers

    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, RepeatedPapers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    expect(region.get_by_text("不同论文：2 · 重复来源：1 · 身份待补充：1")).to_be_visible()
    forms = region.get_by_role("form", name=re.compile("^纠正去重 "))
    expect(forms).to_have_count(4)
    keys = []

    def unknown(route):
        keys.append(route.request.headers["idempotency-key"])
        response = route.fetch()
        assert response.status == 200
        if len(keys) == 1:
            route.fulfill(
                status=500,
                content_type="application/json",
                body='{"error":{"code":"INTERNAL_ERROR","message":"unknown"}}',
            )
        else:
            route.fulfill(response=response)

    page.route("**/deduplication-decision", unknown)
    forms.nth(1).get_by_label("纠正理由").fill("Keep this version separate")
    forms.nth(1).get_by_role("button", name="保存去重决定").click()
    expect(region.get_by_role("button", name="用原请求核查重试")).to_be_enabled()
    region.get_by_role("button", name="用原请求核查重试").click()
    expect(region.get_by_text("不同论文：3 · 重复来源：0 · 身份待补充：1")).to_be_visible()
    assert len(keys) == 2 and keys[0] == keys[1]
    page.unroute("**/deduplication-decision", unknown)
    forms.nth(1).get_by_label("处理方式").select_option(index=1)
    forms.nth(1).get_by_label("纠正理由").fill("Same paper after checking")
    forms.nth(1).get_by_role("button", name="保存去重决定").click()
    expect(region.get_by_text("不同论文：2 · 重复来源：1 · 身份待补充：1")).to_be_visible()
    region.get_by_role("button", name="刷新本次结果").click()
    expect(region.get_by_text("人工决定", exact=False)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    output = Path(__file__).parents[3] / "docs/workorders/evidence/task042_title_rule_2026-10-28"
    page.screenshot(path=str(output / "dedup-mobile.png"), full_page=True)
    region.get_by_role("button", name="取消本次构建", exact=True).click()
    expect(region.get_by_role("heading", name="已取消", exact=True)).to_be_visible()
    expect(region.get_by_text("Keep this version separate", exact=False)).to_be_visible()
    expect(region.get_by_role("button", name="保存去重决定")).to_have_count(0)
    page.close()


def test_psb01_classification_scoring_human_edit_preview_and_refresh(monkeypatch, request):
    from test_paper_deduplication import RepeatedPapers
    from test_paper_screening import Scores

    from rpb.adapters.paper_scoring_worker import ScoreWorker

    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, RepeatedPapers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    forms = region.get_by_role("form", name=re.compile("^来源分类 "))
    expect(forms).to_have_count(4)
    page.get_by_text("主题资料分类与Agent使用范围", exact=True).click()
    page.get_by_label("主题分类", exact=True).select_option("public")
    page.get_by_label("分类依据", exact=True).fill("Public project topic checked")
    page.get_by_role("button", name="确认主题资料分类", exact=True).click()
    expect(page.get_by_text("主题分类：已确认公开", exact=False)).to_be_visible()
    for index in range(2):
        forms.nth(index).get_by_label("实际内容依据").fill("Checked public metadata")
        forms.nth(index).get_by_role("button", name="确认来源分类").click()
        expect(forms.nth(index).get_by_text("已确认：public", exact=True)).to_be_visible()
    score = region.get_by_role("region", name=re.compile("^论文评分 ")).first
    score.get_by_role("button", name="评分或重新评分", exact=True).click()
    preview = region.get_by_role("region", name="评分确认", exact=True)
    expect(preview).to_be_visible()
    preview.get_by_role("button", name="确认评分", exact=True).click()
    expect(region.get_by_text("评分任务：queued", exact=True)).to_be_visible()
    assert ScoreWorker(app.state.run_store, Scores([7])).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(score.get_by_text("评分：7 / 10", exact=False)).to_be_visible()
    form = score.get_by_role("form", name=re.compile("^调整评分 "))
    form.get_by_label("评分", exact=True).fill("3")
    form.get_by_label("有效性", exact=True).select_option("false")
    form.get_by_label("判断理由", exact=True).fill("Human relevance judgment")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    expect(score.get_by_text("评分：3 / 10 · 无效 · 人工修改", exact=True)).to_be_visible()
    score.get_by_role("button", name="评分或重新评分", exact=True).click()
    expect(preview.get_by_text("将替换所选论文组的人工评分/有效性", exact=True)).to_be_visible()
    preview.get_by_role("button", name="取消评分确认", exact=True).click()
    expect(score.get_by_text("Human relevance judgment", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    output = (
        Path(__file__).parents[3] / "docs/workorders/evidence/task044_screening_gate_2026-10-29"
    )
    page.screenshot(path=str(output / "screening-mobile.png"), full_page=True)
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(score.get_by_text("Human relevance judgment", exact=True)).to_be_visible()
    page.close()


def test_psb02_validity_only_and_both_merged_human_judgments(monkeypatch, request):
    from test_paper_deduplication import RepeatedPapers

    page, region, app, _, _, _ = configured_browser(monkeypatch, request)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, RepeatedPapers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    scores = region.get_by_role("region", name=re.compile("^论文评分 "))
    first = scores.nth(0)
    form = first.get_by_role("form", name=re.compile("^调整评分 "))
    form.get_by_label("有效性", exact=True).select_option("false")
    form.get_by_label("判断理由", exact=True).fill("Human invalid without invented score")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    expect(first.get_by_text("评分：未判定 / 10 · 无效 · 人工修改", exact=True)).to_be_visible()
    form.get_by_label("评分", exact=True).fill("8")
    form.get_by_label("判断理由", exact=True).fill("Human eight")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    expect(first.get_by_text("评分：8 / 10 · 有效 · 人工修改", exact=True)).to_be_visible()
    expect(first.get_by_text("默认评分阈值：7 / 10（系统默认）", exact=True)).to_be_visible()
    second = scores.nth(2)
    form2 = second.get_by_role("form", name=re.compile("^调整评分 "))
    form2.get_by_label("评分", exact=True).fill("3")
    form2.get_by_label("判断理由", exact=True).fill("Human three")
    form2.get_by_role("button", name="保存人工评分", exact=True).click()
    expect(second.get_by_text("评分：3 / 10 · 无效 · 人工修改", exact=True)).to_be_visible()
    first_id = first.get_attribute("aria-label").removeprefix("论文评分 ")
    correction = region.get_by_role("form", name=re.compile("^纠正去重 ")).nth(2)
    correction.get_by_label("处理方式").select_option(first_id)
    correction.get_by_label("纠正理由").fill("Same paper after human review")
    correction.get_by_role("button", name="保存去重决定").click()
    expect(
        first.get_by_text("评分：8 / 10 · 依据已变化，待复核 · 人工修改", exact=True)
    ).to_be_visible()
    expect(
        second.get_by_text("评分：3 / 10 · 依据已变化，待复核 · 人工修改", exact=True)
    ).to_be_visible()
    expect(second.get_by_text("最后人工修改：", exact=False)).to_be_visible()
    second.get_by_text("保留的判断记录", exact=True).click()
    expect(second.get_by_role("listitem").filter(has_text="Human three")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    output = (
        Path(__file__).parents[3] / "docs/workorders/evidence/task044_screening_gate_2026-10-29"
    )
    page.screenshot(path=str(output / "screening-merged-mobile.png"), full_page=True)
    page.close()


@pytest.mark.parametrize("cancel_phase", ["processing", "analysis"])
def test_ppb01_manual_screening_to_processing_confirmation_and_edit(
    monkeypatch, request, cancel_phase
):
    from test_paper_deduplication import RepeatedPapers
    from test_paper_processing import Prepared

    from rpb.adapters.paper_processing import ProcessingWorker

    page, region, app, _, _, _ = configured_browser(monkeypatch, request)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, RepeatedPapers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    form = region.get_by_role("form", name=re.compile("^调整评分 ")).first
    form.get_by_label("有效性", exact=True).select_option("true")
    form.get_by_label("判断理由", exact=True).fill("Human inclusion decision")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    region.get_by_role("button", name="确认筛选并下载解析", exact=True).click()
    expect(region.get_by_role("status")).to_contain_text("正在获取并解析")
    assert ProcessingWorker(app.state.run_store, Prepared()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    result = region.get_by_role("region", name=re.compile("^论文处理 ")).first
    expect(result.get_by_role("heading", name="摘要降级（不是全文）", exact=True)).to_be_visible()
    expect(result.get_by_text("本轮所用来源：", exact=False)).to_be_visible()
    result.get_by_text("查看所用文本节选", exact=False).click()
    expect(result.get_by_text("Version 0", exact=True)).to_be_visible()
    region.get_by_role("button", name="确认处理结果", exact=True).click()
    expect(region.get_by_role("heading", name="论文AI分析", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    output = (
        Path(__file__).parents[3] / "docs/workorders/evidence/task046_processing_gate_2026-10-29"
    )
    page.screenshot(path=str(output / "processing-mobile.png"), full_page=True)
    form.get_by_label("有效性", exact=True).select_option("false")
    form.get_by_label("判断理由", exact=True).fill("Exclude after checking text")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    expect(region.get_by_role("heading", name="去重结果待核对", exact=True)).to_be_visible()
    expect(result.get_by_text("处理结果未确认", exact=False)).to_be_visible()
    form.get_by_label("有效性", exact=True).select_option("true")
    form.get_by_label("判断理由", exact=True).fill("Include again")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    region.get_by_role("button", name="确认筛选并下载解析", exact=True).click()
    expect(region.get_by_role("status")).to_contain_text("正在获取并解析")
    if cancel_phase == "analysis":
        assert ProcessingWorker(app.state.run_store, Prepared()).run_once()
        region.get_by_role("button", name="刷新本次结果", exact=True).click()
        region.get_by_role("button", name="确认处理结果", exact=True).click()
    region.get_by_role("button", name="取消本次构建", exact=True).click()
    expect(region.get_by_role("heading", name="已取消", exact=True)).to_be_visible()
    expect(region.get_by_role("button", name="确认处理结果", exact=True)).to_have_count(0)
    page.close()


def test_plb01_real_pdf_classification_auto_continue_compare_and_confirm(monkeypatch, request):
    import io

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    from test_paper_deduplication import RepeatedPapers
    from test_paper_processing import pdf
    from test_pdf_cleanup import Model

    from rpb.adapters.pdf_cleanup_worker import CleanupWorker
    from rpb.adapters.pdf_processing import PDFProvider

    page, region, app, _, _, _ = configured_browser(monkeypatch, request)
    region.get_by_label("PDF提取引擎", exact=True).select_option("llm_text_cleanup")
    expect(region.get_by_text("本引擎默认4096 tokens", exact=False)).to_be_visible()
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()

    class PapersWithFile(RepeatedPapers):
        def search(self, *args):
            result = super().search(*args)
            for item in result["items"]:
                item["url"] = "https://example.org/full.pdf"
            return result

    assert RunWorker(app.state.run_store, PapersWithFile()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    form = region.get_by_role("form", name=re.compile("^调整评分 ")).first
    form.get_by_label("有效性", exact=True).select_option("true")
    form.get_by_label("判断理由", exact=True).fill("Read this paper")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    region.get_by_role("button", name="确认筛选并下载解析", exact=True).click()

    expect(region.get_by_role("status")).to_contain_text("正在获取并解析")

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf())))
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 720 Td (first) Tj 0 -14 Td (second) Tj ET")
    writer.pages[0][NameObject("/Contents")] = writer._add_object(content)
    stream = io.BytesIO()
    writer.write(stream)

    class Files(PDFProvider):
        def download(self, link, authorize):
            with authorize():
                return stream.getvalue()

    model = Model()
    worker = CleanupWorker(app.state.run_store, Files(), model)
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(region.get_by_role("button", name="确认处理结果", exact=True)).to_have_count(0)
    assert model.calls == []
    evidence = (
        Path(__file__).parents[3] / "docs/workorders/evidence/task047_llm_pdf_design_2026-10-30"
    )
    region.get_by_role("region", name=re.compile("^全文分类等待 ")).first.screenshot(
        path=str(evidence / "cleanup-classification.png")
    )
    classification = region.get_by_role("form", name=re.compile("^全文分类 ")).first
    classification.get_by_label("全文分类", exact=True).select_option("public")
    classification.get_by_label("全文分类依据", exact=True).fill("Actual public PDF checked")
    classification.get_by_role("button", name="保存全文分类并继续", exact=True).click()
    expect(
        region.get_by_text("全文分类已保存，原作业将自动重验权限和预算后继续。", exact=True)
    ).to_be_visible()
    assert worker.run_once() and len(model.calls) == 1
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="核对原始与整理全文", exact=True).click()
    expect(region.get_by_role("heading", name="原始提取全文", exact=True)).to_be_visible()
    assert region.locator("pre").nth(0).text_content() == "first\nsecond\n"
    assert region.locator("pre").nth(1).text_content() == "first second\n"
    region.get_by_role("region", name=re.compile("^论文处理 ")).first.screenshot(
        path=str(evidence / "cleanup-comparison.png")
    )
    region.get_by_role("button", name="确认处理结果", exact=True).click()
    expect(region.get_by_role("heading", name="论文AI分析", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    output = (
        Path(__file__).parents[3] / "docs/workorders/evidence/task047_llm_pdf_design_2026-10-30"
    )
    page.screenshot(path=str(output / "cleanup-mobile.png"), full_page=True)
    page.close()


def test_failed_run_can_start_a_separate_run(monkeypatch, request):
    page, region, app, client, _, root = configured_browser(monkeypatch, request)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, Papers(failure=True)).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(region.get_by_role("heading", name="失败", exact=True)).to_be_visible()
    old = client.get(root + "/construction-runs").json()["data"]["items"][0]
    region.get_by_role("button", name="重新运行", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    expect(region.get_by_text("来源构建：" + old["id"], exact=False)).to_be_visible()
    assert client.get(root + "/construction-runs/" + old["id"]).json()["data"] == old
    page.close()
