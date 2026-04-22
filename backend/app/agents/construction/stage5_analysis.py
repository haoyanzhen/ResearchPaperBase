"""
构建模式阶段 5 — AI 分析生成（FR-016）

职责：
  1. 取课题有效论文（is_valid=True）中 ai_analysis_status='not_analyzed' 的记录
  2. 优先使用论文全文（text_path），次选摘要（abstract）
  3. 调用 LLM 生成 JSON 格式分析：summary / highlights / relevance_points / technical_methods
  4. 将结果写入 papers.ai_analysis（JSONB），更新 ai_analysis_status='success'
  5. 处理 analysis_overrides（用户手动覆盖 AI 分析内容）
  6. 将阶段标记为 paused
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    emit_sse_event,
    get_llm_client,
    get_stage_llm_params,
    load_construction_prompts,
    parse_json_response,
)
from app.agents.construction.pipeline import get_project, mark_stage_paused
from app.models.paper import Paper, ProjectPaperRelation
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


def _load_paper_text(text_path: str | None, max_chars: int) -> str | None:
    """从 text_path 加载论文全文，截断至 max_chars。失败时返回 None。"""
    if not text_path:
        return None
    try:
        with open(text_path, "r", encoding="utf-8") as f:
            return f.read(max_chars)
    except OSError:
        return None


async def _analyze_paper(
    llm,
    project_name: str,
    project_desc: str,
    paper: Paper,
    max_text_chars: int,
) -> dict | None:
    """
    对单篇论文调用 LLM 生成分析，返回 dict 或 None（失败时）。
    """
    # 优先全文，次选摘要
    text = _load_paper_text(paper.text_path, max_text_chars)
    if not text:
        text = paper.abstract or "（无全文或摘要）"

    prompts = load_construction_prompts()
    cfg = prompts["stage5_paper_analysis"]
    system_msg = cfg["system"]
    user_msg = cfg["user_template"].format_map({
        "topic": project_name,
        "description": project_desc or project_name,
        "title": paper.title,
        "text": text,
    })

    try:
        raw = await llm.complete([
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ])
        result = parse_json_response(raw)
        if not isinstance(result, dict):
            return None

        # 标准化字段
        return {
            "summary": str(result.get("summary", ""))[:200],
            "highlights": [str(h) for h in (result.get("highlights") or [])],
            "relevance_points": [str(r) for r in (result.get("relevance_points") or [])],
            "technical_methods": [str(m) for m in (result.get("technical_methods") or [])],
        }
    except Exception as exc:
        logger.warning("Analysis failed for paper '%s': %s", paper.title[:60], exc)
        return None


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 5 执行逻辑。

    modifications 可包含：
      {"analysis_overrides": [{"paper_id": "...", "summary": "...", "highlights": [...], ...}]}
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    stage_params = get_stage_llm_params("construction_5")
    batch_size: int = stage_params.get("batch_size", 5)
    batch_delay: float = stage_params.get("batch_delay_seconds", 0.5)
    max_text_chars: int = stage_params.get("max_text_chars", 8000)

    # ── 取待分析的有效论文 ────────────────────────────────────────────────
    pending_res = await db.execute(
        select(Paper)
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
            Paper.ai_analysis_status == "not_analyzed",
        )
    )
    pending_papers = pending_res.scalars().all()

    emit_sse_event(project_id, "stage_progress", {
        "stage": 5, "progress": 5,
        "detail": f"共 {len(pending_papers)} 篇论文待 AI 分析..."
    })

    if not pending_papers:
        logger.info("Stage5: no papers to analyze")
        success_count = 0
        failed_count = 0
    else:
        llm = await get_llm_client(db, user_id, "construction_5")
        total = len(pending_papers)
        success_count = 0
        failed_count = 0

        for batch_start in range(0, total, batch_size):
            batch = pending_papers[batch_start: batch_start + batch_size]

            # 批次内并发分析
            tasks = [
                _analyze_paper(llm, project.name, project.description or "", paper, max_text_chars)
                for paper in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for paper, result in zip(batch, batch_results):
                if isinstance(result, Exception) or result is None:
                    paper.ai_analysis_status = "failed"
                    failed_count += 1
                else:
                    paper.ai_analysis = result
                    paper.ai_analysis_status = "success"
                    success_count += 1

            await db.commit()

            progress = int(5 + 80 * (batch_start + len(batch)) / max(total, 1))
            emit_sse_event(project_id, "stage_progress", {
                "stage": 5, "progress": progress,
                "detail": f"已分析 {batch_start + len(batch)}/{total} 篇"
                          f"（成功 {success_count}，失败 {failed_count}）",
            })

            if batch_start + batch_size < total:
                await asyncio.sleep(batch_delay)

    # ── 应用 analysis_overrides ──────────────────────────────────────────
    overrides: list[dict] = modifications.get("analysis_overrides") or []
    for ov in overrides:
        paper_id = ov.get("paper_id")
        if not paper_id:
            continue
        paper_res = await db.execute(select(Paper).where(Paper.id == paper_id))
        paper = paper_res.scalar_one_or_none()
        if paper is None:
            continue
        existing = paper.ai_analysis or {}
        # 合并覆盖（只覆盖明确提供的字段）
        for field in ("summary", "highlights", "relevance_points", "technical_methods"):
            if field in ov:
                existing[field] = ov[field]
        paper.ai_analysis = existing
        paper.ai_analysis_status = "success"

    await db.commit()

    stage_result = {
        "total_analyzed": success_count,
        "failed": failed_count,
        "overrides_applied": len(overrides),
    }

    await mark_stage_paused(db, record.id, stage_result)

    emit_sse_event(project_id, "stage_pause", {
        "stage": 5,
        "status": "paused",
        "result": stage_result,
    })
    logger.info(
        "Stage5 paused: %d analyzed, %d failed, %d overrides",
        success_count, failed_count, len(overrides)
    )
