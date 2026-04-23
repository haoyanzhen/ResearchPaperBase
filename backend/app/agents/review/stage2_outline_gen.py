"""
综述模式阶段 2 — 综述架构生成（FR-020）

职责：
  1. 若 modifications 中包含 outline，直接使用（用户在重试时可预填）
  2. 否则调用 LLM 根据课题扩写描述生成架构
  3. 将架构 JSON 写入 review_outlines.outline
  4. 暂停（等待用户审查并确认架构）
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event, get_llm_client, parse_json_response
from app.agents.review.pipeline import (
    get_latest_draft_outline,
    get_project,
    load_review_prompts,
    mark_stage_paused,
)
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 2 执行逻辑。
    完成后暂停，等待用户通过 PATCH /outlines/{id} 修改后调用 confirm。
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    outline = await get_latest_draft_outline(db, project_id)
    if outline is None:
        raise ValueError(f"未找到项目 {project_id} 的综述架构记录")
    if not outline.topic_expansion:
        raise ValueError("topic_expansion 为空，阶段 1 可能未正常完成")

    # ── 路径 A：modifications 提供了 outline ────────────────────────────────
    if modifications.get("outline"):
        outline_data = modifications["outline"]
        logger.info("Stage2: using user-provided outline with %d sections",
                    len(outline_data.get("sections", [])))
    else:
        # ── 路径 B：调用 LLM 生成架构 ────────────────────────────────────────
        emit_sse_event(project_id, "stage_progress", {
            "stage": 2, "progress": 30, "detail": "调用 LLM 生成综述架构..."
        })

        prompts = load_review_prompts()
        cfg = prompts["stage2_outline_generation"]
        system_prompt = cfg["system"]
        user_msg = cfg["user_template"].format_map({
            "name": project.name,
            "topic_expansion": outline.topic_expansion,
        })

        llm = await get_llm_client(db, user_id, "review_2")
        raw = await llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=cfg.get("llm_params", {}).get("temperature"),
            max_tokens=cfg.get("llm_params", {}).get("max_tokens"),
        )
        outline_data = parse_json_response(raw)

    # ── 写入 outline ────────────────────────────────────────────────────────
    outline.outline = outline_data
    await db.commit()

    section_count = len(outline_data.get("sections", []))
    emit_sse_event(project_id, "stage_pause", {
        "stage": 2,
        "status": "paused",
        "result": {
            "outline_id": outline.id,
            "title": outline_data.get("title", ""),
            "section_count": section_count,
        },
    })

    await mark_stage_paused(db, record.id, {
        "outline_id": outline.id,
        "section_count": section_count,
    })
