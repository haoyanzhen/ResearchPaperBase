"""
构建模式阶段 3 — 智能评分与筛选（FR-013）

职责：
  1. 取课题关联的未评分论文（reference_score IS NULL）
  2. 批量调用 LLM 对每篇论文打分（reference_score 0-5 + technical_score 0-5 + reason）
  3. 将评分写入 project_paper_relations，并按 score_threshold 设置 is_valid
  4. 应用用户 score_overrides（手动覆盖评分结果）
  5. 更新 project.total_papers / project.valid_papers
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
from app.agents.construction.pipeline import (
    get_pipeline_params,
    get_project,
    mark_stage_paused,
)
from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Project
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


async def _score_paper(
    llm,
    project_name: str,
    project_desc: str,
    paper: Paper,
) -> dict | None:
    """
    对单篇论文调用 LLM 评分，返回 {"reference_score": int, "technical_score": int, "reason": str}。
    解析失败时返回 None（由调用方决定处理策略）。
    """
    prompts = load_construction_prompts()
    cfg = prompts["stage3_paper_scoring"]
    system_msg = cfg["system"]
    user_msg = cfg["user_template"].format_map({
        "topic": project_name,
        "description": project_desc or project_name,
        "title": paper.title,
        "abstract": paper.abstract or "（无摘要）",
        "venue": paper.venue or "未知",
        "authors": ", ".join(paper.authors or []) or "未知",
    })

    try:
        raw = await llm.complete([
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ])
        scored = parse_json_response(raw)
        if not isinstance(scored, dict):
            return None
        ref = int(scored.get("reference_score", 0))
        tech = int(scored.get("technical_score", 0))
        reason = str(scored.get("reason", ""))
        # 边界检查
        ref = max(0, min(5, ref))
        tech = max(0, min(5, tech))
        return {"reference_score": ref, "technical_score": tech, "reason": reason}
    except Exception as exc:
        logger.warning("Scoring failed for paper '%s': %s", paper.title[:60], exc)
        return None


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 3 执行逻辑。

    modifications 可包含：
      {"score_overrides": [{"paper_id": "...", "reference_score": 4, "technical_score": 4,
                            "is_valid": true, "reason": "手动覆盖"}]}
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    pipeline_params = await get_pipeline_params(db, project_id)
    score_threshold: int = pipeline_params["score_threshold"]

    # ── 取未评分的关联论文 ─────────────────────────────────────────────────
    unscored_res = await db.execute(
        select(ProjectPaperRelation, Paper)
        .join(Paper, ProjectPaperRelation.paper_id == Paper.id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.reference_score == None,
        )
    )
    unscored_rows = unscored_res.all()

    emit_sse_event(project_id, "stage_progress", {
        "stage": 3, "progress": 5,
        "detail": f"共 {len(unscored_rows)} 篇论文待评分（阈值 {score_threshold} 分）..."
    })

    if not unscored_rows:
        logger.info("Stage3: no unscored papers, skipping LLM calls")
    else:
        # ── 批量 LLM 评分 ──────────────────────────────────────────────────
        llm = await get_llm_client(db, user_id, "construction_3")
        stage_params = get_stage_llm_params("construction_3")
        batch_size: int = stage_params.get("batch_size", 10)
        batch_delay: float = stage_params.get("batch_delay_seconds", 0.3)

        total = len(unscored_rows)
        scored_count = 0
        failed_count = 0

        for batch_start in range(0, total, batch_size):
            batch = unscored_rows[batch_start: batch_start + batch_size]

            # 并发评分（同批次内并发，批次间串行 + 延迟）
            score_tasks = [
                _score_paper(llm, project.name, project.description or "", paper)
                for rel, paper in batch
            ]
            batch_results = await asyncio.gather(*score_tasks, return_exceptions=True)

            for (rel, paper), result in zip(batch, batch_results):
                if isinstance(result, Exception) or result is None:
                    failed_count += 1
                    # 评分失败：给默认分 0/0，不标记为 valid
                    rel.reference_score = 0
                    rel.technical_score = 0
                    rel.total_score = 0
                    rel.scoring_reason = f"评分失败: {result}"
                    rel.is_valid = False
                else:
                    rel.reference_score = result["reference_score"]
                    rel.technical_score = result["technical_score"]
                    rel.total_score = result["reference_score"] + result["technical_score"]
                    rel.scoring_reason = result["reason"]
                    rel.is_valid = rel.total_score >= score_threshold
                    scored_count += 1

            await db.commit()

            progress = int(5 + 80 * (batch_start + len(batch)) / max(total, 1))
            emit_sse_event(project_id, "stage_progress", {
                "stage": 3, "progress": progress,
                "detail": f"已评分 {batch_start + len(batch)}/{total} 篇"
                          f"（成功 {scored_count}，失败 {failed_count}）"
            })

            if batch_start + batch_size < total:
                await asyncio.sleep(batch_delay)

    # ── 应用用户手动覆盖 score_overrides ────────────────────────────────────
    overrides: list[dict] = modifications.get("score_overrides") or []
    for ov in overrides:
        paper_id = ov.get("paper_id")
        if not paper_id:
            continue
        rel_res = await db.execute(
            select(ProjectPaperRelation).where(
                ProjectPaperRelation.project_id == project_id,
                ProjectPaperRelation.paper_id == paper_id,
            )
        )
        rel = rel_res.scalar_one_or_none()
        if rel is None:
            continue
        if "reference_score" in ov:
            rel.reference_score = max(0, min(5, int(ov["reference_score"])))
        if "technical_score" in ov:
            rel.technical_score = max(0, min(5, int(ov["technical_score"])))
        if rel.reference_score is not None and rel.technical_score is not None:
            rel.total_score = rel.reference_score + rel.technical_score
        if "is_valid" in ov:
            rel.is_valid = bool(ov["is_valid"])
        elif rel.total_score is not None:
            rel.is_valid = rel.total_score >= score_threshold
        if "reason" in ov:
            rel.scoring_reason = str(ov["reason"])

    await db.commit()

    # ── 汇总统计，更新 project 计数 ───────────────────────────────────────
    all_rels_res = await db.execute(
        select(ProjectPaperRelation).where(
            ProjectPaperRelation.project_id == project_id
        )
    )
    all_rels = all_rels_res.scalars().all()
    total_papers = len(all_rels)
    valid_papers = sum(1 for r in all_rels if r.is_valid)

    project.total_papers = total_papers
    project.valid_papers = valid_papers
    await db.commit()

    stage_result = {
        "total_papers": total_papers,
        "valid_papers": valid_papers,
        "invalid_papers": total_papers - valid_papers,
        "threshold": score_threshold,
        "score_failed": failed_count if unscored_rows else 0,
    }

    await mark_stage_paused(db, record.id, stage_result)

    emit_sse_event(project_id, "stage_pause", {
        "stage": 3,
        "status": "paused",
        "result": stage_result,
    })
    logger.info(
        "Stage3 paused: %d total, %d valid (threshold=%d)",
        total_papers, valid_papers, score_threshold
    )
