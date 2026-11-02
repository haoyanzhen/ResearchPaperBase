"""PA06: real browser/HTTP/PostgreSQL, controlled model and file providers."""

import re

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


def test_pab01_generate_edit_reject_overwrite_confirm_refresh(monkeypatch, request, tmp_path):
    page, region, app, client, headers, root = configured_browser(monkeypatch, request)
    from test_ingestion_preview import embedding_factory

    from rpb.adapters.first_publication_worker import FirstPublicationWorker

    class EmptyGraph:
        def extract(self, config, model, secret, text, metadata, authorize):
            with authorize():
                return [], []

    worker = FirstPublicationWorker(
        app.state.run_store, tmp_path / "objects", embedding_factory(), EmptyGraph()
    )
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
        region.get_by_role("heading", name="分析已确认，等待入库确认", exact=True)
    ).to_be_visible()
    expect(region.get_by_role("region", name="入库预览")).to_contain_text("拟纳入论文：1")
    expect(region.get_by_role("button", name="确认检索并去重", exact=True)).to_have_count(0)
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
    page.screenshot(path=str(tmp_path / "analysis-mobile.png"), full_page=True)
    region.get_by_role("button", name="接受上述风险并确认入库", exact=True).click()
    expect(region.get_by_role("heading", name="正在构建知识版本", exact=True)).to_be_visible()
    assert worker.run_once()
    published = client.get(url).json()["data"]
    from jsonschema import Draft202012Validator
    from test_account_auth import SPEC

    Draft202012Validator(
        {"$ref": "#/components/schemas/RetrievalRunView", "components": SPEC["components"]}
    ).validate(published)
    assert published["status"] == "succeeded", published["steps"]
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="查看已发布版本", exact=True).click()
    version = region.get_by_role("region", name="已发布版本")
    expect(version).to_contain_text(published["published_knowledge_version_id"])
    expect(version).to_contain_text(candidates(client, url)[0]["metadata"]["title"])
    expect(version).to_contain_text("用户保留的分析结论")
    papers = client.get(root + "/papers").json()["data"]
    Draft202012Validator(
        {"$ref": "#/components/schemas/PublishedPaperView", "components": SPEC["components"]}
    ).validate(papers["items"][0])
    assert papers["knowledge_version_id"] == published["published_knowledge_version_id"]
    assert papers["items"][0]["analysis"]["one_sentence_summary"] == "用户保留的分析结论"
    from test_project_commands import create

    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    other_response = create(
        client, headers, {"name": "Other publication project"}, key="published-scope-isolation1"
    )
    assert other_response.status_code == 201, other_response.text
    other = other_response.json()["data"]["id"]
    foreign = client.get(
        f"/api/v1/projects/{other}/papers",
        params={"knowledge_version_id": papers["knowledge_version_id"]},
    )
    assert foreign.status_code == 404 and "用户保留的分析结论" not in foreign.text
    assert (
        client.post(
            url + "/cancel",
            headers=headers | {"Idempotency-Key": "late-publish-cancel1"},
            json={
                "expected_revision": published["revision"],
                "attempt_id": published["task"]["attempt_id"],
            },
        ).status_code
        == 409
    )
    assert not worker.run_once()
    page.close()
