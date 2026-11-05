"""PA06: real browser/HTTP/PostgreSQL, controlled model and file providers."""

import os
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
    expect(page.get_by_text("尚未构建知识版本", exact=True)).to_be_visible()
    page.get_by_role("button", name="编辑信息", exact=True).click()
    draft = page.get_by_label("项目名称", exact=True)
    draft.fill("保留未保存的项目名称")
    assert worker.run_once()
    expect(page.get_by_text("已有知识版本", exact=True)).to_be_visible(timeout=12000)
    expect(draft).to_have_value("保留未保存的项目名称")
    expect(draft).to_be_focused()
    page.get_by_role("button", name="取消编辑").click()
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
    listing = {p["id"]: p for p in client.get("/api/v1/projects").json()["data"]["items"]}
    assert listing[other]["default_knowledge_version_id"] is None
    assert (
        listing[root.rsplit("/", 1)[1]]["default_knowledge_version_id"]
        == papers["knowledge_version_id"]
    )
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
    from uuid import UUID

    import sqlalchemy as sa
    from test_incremental_vector_view import second_preview

    from rpb.adapters.run_tables import runs

    store = app.state.run_store
    engine = store.account.engine
    with engine.connect() as conn:
        first = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(run["id"])))
    inputs = {
        k: first["request"][k]
        for k in ("selected_terms", "retrieval_range", "model_selection", "result_limit_per_source")
    }
    second_url, _ = second_preview(client, headers, root, store, engine, inputs)
    second_run = client.get(second_url).json()["data"]
    page.reload()

    def open_run(item):
        region.get_by_role("list").first.get_by_role(
            "button", name=re.compile(re.escape(item["created_at"]))
        ).click()

    evidence = os.environ.get("PUBLICATION_BROWSER_EVIDENCE_DIR")
    open_run(second_run)
    preview = region.get_by_role("region", name="入库预览")
    expect(preview).to_contain_text("本轮拟新增论文：1")
    expect(preview).to_contain_text(published["published_knowledge_version_id"])
    if evidence:
        preview.screenshot(path=str(Path(evidence) / "preview.png"))
    region.get_by_role("button", name="接受上述风险并确认入库", exact=True).click()
    expect(region.get_by_role("heading", name="正在构建知识版本", exact=True)).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    region.get_by_role("button", name="查看已发布版本", exact=True).click()
    latest = client.get(second_url).json()["data"]["published_knowledge_version_id"]
    assert latest and latest != published["published_knowledge_version_id"]
    expect(version).to_contain_text(latest)
    expect(version).to_contain_text("graph")
    expect(version).to_contain_text("用户保留的分析结论")
    if evidence:
        version.screenshot(path=str(Path(evidence) / "incremental.png"))
    open_run(published)
    region.get_by_role("button", name="查看已发布版本", exact=True).click()
    expect(version).to_contain_text(published["published_knowledge_version_id"])
    expect(version).not_to_contain_text("graph")
    if evidence:
        version.screenshot(path=str(Path(evidence) / "original.png"))
    from uuid import uuid4

    from test_construction_runs import Papers
    from test_search_terms import post

    from rpb.adapters.source_tables import dispatch_limits

    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    third = post(client, headers, root + "/construction-runs", inputs, str(uuid4()))
    assert third.status_code == 202
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(store, Papers()).run_once()
    third_url = root + "/construction-runs/" + third.json()["data"]["run"]["id"]
    page.reload()
    open_run(client.get(third_url).json()["data"])
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    zero = region.get_by_role("region", name="零新增预览")
    expect(zero).to_contain_text("本轮拟新增论文：0")
    expect(zero).to_contain_text(latest)
    expect(region.get_by_role("button", name="确认入库", exact=True)).to_have_count(0)
    if evidence:
        zero.screenshot(path=str(Path(evidence) / "baseline-match.png"))
    region.get_by_label("纠正理由").fill("核对后作为不同论文保留")
    region.get_by_role("button", name="保存去重决定").click()
    expect(zero).to_have_count(0)
    detail = client.get(third_url).json()["data"]
    assert detail["status"] == "waiting_user" and detail["completion"] is None
    assert "baseline_match_preview" not in detail
    match_id = next(
        p["id"]
        for p in client.get(root + "/papers").json()["data"]["items"]
        if p["title"] == "graph"
    )
    region.get_by_label("其他已有论文 ID（可选）").fill(match_id)
    region.get_by_label("纠正理由").fill("再次核对，与既有论文一致")
    region.get_by_role("button", name="保存去重决定").click()
    expect(zero).to_be_visible()
    region.get_by_role("button", name="确认全部匹配，查看核验范围", exact=True).click()
    expect(region.get_by_role("region", name="入库预览")).to_contain_text(latest)
    region.get_by_role("button", name="确认核验既有版本", exact=True).click()
    expect(region.get_by_role("heading", name="正在核验既有版本", exact=True)).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(region.get_by_role("heading", name="检查成功，无知识变化", exact=True)).to_be_visible()
    verified = region.get_by_role("region", name="核验结果")
    expect(verified).to_contain_text("检索词：graph")
    expect(verified).to_contain_text("核验时间")
    expect(verified).to_contain_text(latest)
    expect(region.get_by_role("button", name="查看已发布版本", exact=True)).to_have_count(0)
    if evidence:
        verified.screenshot(path=str(Path(evidence) / "no-change.png"))
    from test_baseline_match_preview import ZeroPapers

    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    empty_run = post(client, headers, root + "/construction-runs", inputs, str(uuid4()))
    assert empty_run.status_code == 202
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(store, ZeroPapers()).run_once()
    page.reload()
    open_run(empty_run.json()["data"]["run"])
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    expect(zero).to_contain_text("共返回 0 条")
    expect(zero).to_contain_text(latest)
    if evidence:
        zero.screenshot(path=str(Path(evidence) / "zero-results.png"))
    region.get_by_role("button", name="确认检索零条，查看核验范围").click()
    region.get_by_role("button", name="确认核验既有版本", exact=True).click()
    expect(region.get_by_role("heading", name="正在核验既有版本")).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(verified).to_contain_text(latest)
    expect(verified).to_contain_text("检索词：graph")

    class NewPaper(Papers):
        def search(self, *args):
            result = super().search(*args)
            result["items"][0]["title"] = "Unrelated paper"
            return result

    headers["X-CSRF-Token"] = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    screened_run = post(client, headers, root + "/construction-runs", inputs, str(uuid4()))
    assert screened_run.status_code == 202
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(store, NewPaper()).run_once()
    page.reload()
    open_run(screened_run.json()["data"]["run"])
    region.get_by_role("button", name="确认检索并去重", exact=True).click()
    form.get_by_label("有效性", exact=True).select_option("false")
    form.get_by_label("判断理由", exact=True).fill("研究对象不在本项目范围")
    form.get_by_role("button", name="保存人工评分", exact=True).click()
    expect(zero).to_contain_text("1 篇论文均已排除")
    region.get_by_role("button", name="确认筛选排除，查看核验范围").click()
    preview = region.get_by_role("region", name="入库预览")
    expect(preview).to_contain_text("筛选排除：研究对象不在本项目范围")
    if evidence:
        preview.screenshot(path=str(Path(evidence) / "excluded.png"))
    region.get_by_role("button", name="确认核验既有版本", exact=True).click()
    expect(region.get_by_role("heading", name="正在核验既有版本")).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果", exact=True).click()
    expect(verified).to_contain_text(latest)
    # A frozen rebuild request follows the same review path even with no additions.
    region.get_by_label("graph", exact=True).check()
    region.get_by_label("知识构建方式").select_option("rebuild")
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(store, ZeroPapers()).run_once()
    region.get_by_role("button", name="刷新本次结果").click()
    region.get_by_role("button", name="确认检索并去重").click()
    region.get_by_role("button", name="确认检索零条，查看核验范围").click()
    expect(preview).to_contain_text("本轮已选择重建")
    if evidence:
        preview.screenshot(path=str(Path(evidence) / "rebuild.png"))
    region.get_by_role("button", name="确认按当前配置核验并构建版本").click()
    building = region.get_by_role("heading", name=re.compile("^正在(构建知识版本|核验既有版本)$"))
    expect(building).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果").click()
    expect(verified).to_contain_text(latest)

    # A failed Run keeps its diagnostics across the explicit cleanup command.
    region.get_by_label("知识构建方式").select_option("incremental")
    region.get_by_role("button", name="启动检索", exact=True).click()
    expect(region.get_by_role("heading", name="排队中", exact=True)).to_be_visible()
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(store, Papers(failure=True)).run_once()
    region.get_by_role("button", name="刷新本次结果").click()
    region.get_by_role("button", name="清理临时资产", exact=True).click()
    region.get_by_role("button", name="确认清理可释放的临时资产").click()
    expect(region.get_by_role("status")).to_contain_text("等待回收")
    from rpb.adapters.run_temporary_cleanup import process_one

    while process_one(engine, tmp_path / "objects"):
        pass
    region.get_by_role("button", name="刷新本次结果").click()
    expect(region.get_by_role("status")).to_contain_text("临时资产清理：已完成")
    if evidence:
        region.get_by_role("status").screenshot(path=str(Path(evidence) / "cleanup.png"))
    expect(region.get_by_role("heading", name="失败", exact=True)).to_be_visible()

    region.get_by_role("button", name="加载当前版本论文").click()
    region.get_by_role("button", name="预览移除全部论文").click()
    removal = region.get_by_role("region", name="移除影响预览")
    expect(removal).to_contain_text("新版本将不含任何知识证据")
    expect(removal).to_contain_text(latest)
    if evidence:
        removal.screenshot(path=str(Path(evidence) / "removal.png"))
    removal.get_by_role("button", name="确认以上范围并启动移除构建").click()
    expect(region.get_by_role("heading", name="等待发布移除结果")).to_be_visible()
    assert worker.run_once()
    region.get_by_role("button", name="刷新本次结果").click()
    region.get_by_role("button", name="查看已发布版本").click()
    expect(version).to_contain_text("此版本没有论文证据")
    if evidence:
        version.screenshot(path=str(Path(evidence) / "empty-version.png"))
    open_run(published)
    region.get_by_role("button", name="查看已发布版本").click()
    expect(version).to_contain_text("用户保留的分析结论")
    page.close()
