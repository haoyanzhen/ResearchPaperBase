"""PA06: real browser/HTTP/PostgreSQL, controlled model and file providers."""

import re
from pathlib import Path

from playwright.sync_api import expect
from test_browser_business import browser_app  # noqa: F401
from test_browser_runs import configured_browser
from test_paper_analysis import Generated
from test_paper_deduplication import RepeatedPapers, candidates
from test_paper_processing import Prepared
from test_paper_screening import classify

from rpb.adapters.paper_analysis_worker import AnalysisWorker
from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.run_worker import RunWorker


def test_pab01_generate_edit_reject_overwrite_confirm_refresh(monkeypatch, request):
    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    region.get_by_label("graph", exact=True).check()
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    assert RunWorker(app.state.run_store, RepeatedPapers()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    form = region.get_by_role("form", name=re.compile("^调整评分 ")).first
    form.get_by_label("有效性", exact=True).select_option("true")
    form.get_by_label("判断理由", exact=True).fill("Human included paper")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    region.get_by_role("button", name="确认筛选并下载解析", exact=True).click()
    expect(region.get_by_role("status")).to_contain_text("正在获取并解析")
    assert ProcessingWorker(app.state.run_store, Prepared()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="确认处理结果", exact=True).click()
    expect(region.get_by_role("heading", name="论文AI分析", exact=True)).to_be_visible()
    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    run = client.get(root + "/construction-runs").json()["data"]["items"][0]
    url = root + "/construction-runs/" + run["id"]
    ws = client.get(root + "/construction-workspace").json()["data"]
    classify(client, headers, root, ws["topic_source"]["source_id"])
    for item in candidates(client, url):
        classify(client, headers, root, item["id"])
    section = region.get_by_role("region", name=re.compile("^论文分析 ")).first
    section.get_by_role("button", name="生成或重新生成分析").click()
    region.get_by_role("button", name="确认生成分析", exact=True).click()
    expect(region.get_by_text("分析任务：queued", exact=True)).to_be_visible()
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(section.get_by_label("一句话总结", exact=True)).to_have_value("研究结论")
    section.get_by_label("一句话总结", exact=True).fill("用户保留的分析结论")
    section.get_by_label("亮点解析 1", exact=True).fill("第一行亮点\n同一要点的第二行")
    section.get_by_role("button", name="添加创新点", exact=True).click()
    section.get_by_label("创新点 1", exact=True).fill("有依据的创新点")
    section.get_by_role("button", name="添加创新点", exact=True).click()
    section.get_by_label("创新点 2", exact=True).fill("移除这个草稿")
    section.get_by_role("button", name="移除创新点 2", exact=True).click()
    section.get_by_role("button", name="保存人工分析", exact=True).click()
    expect(section.get_by_text("人工修改", exact=True)).to_be_visible()
    section.get_by_role("button", name="生成或重新生成分析").click()
    expect(region.get_by_text("将替换当前已保存或已确认的论文分析", exact=True)).to_be_visible()
    region.get_by_role("button", name="取消分析确认", exact=True).click()
    expect(section.get_by_label("一句话总结", exact=True)).to_have_value("用户保留的分析结论")
    region.get_by_role("button", name="确认有效分析（失败项不纳入）", exact=True).click()
    expect(
        region.get_by_role("heading", name="分析已确认，等待入库能力", exact=True)
    ).to_be_visible()
    page.reload()
    region.get_by_role("list").first.get_by_role("button").first.click()
    expect(section.get_by_label("一句话总结", exact=True)).to_have_value("用户保留的分析结论")
    expect(section.get_by_label("亮点解析 1", exact=True)).to_have_value(
        "第一行亮点\n同一要点的第二行"
    )
    expect(section.get_by_label("创新点 1", exact=True)).to_have_value("有依据的创新点")
    expect(section.get_by_label("创新点 2", exact=True)).to_have_count(0)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    folder = Path(__file__).parents[3] / "docs/workorders/evidence/task048_next_stage_2026-10-30"
    page.screenshot(path=str(folder / "analysis-mobile.png"), full_page=True)
    page.close()
