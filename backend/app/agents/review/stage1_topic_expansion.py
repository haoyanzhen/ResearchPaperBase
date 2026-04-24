"""
综述模式阶段 1 — 课题扩写（FR-020）

职责：
  1. 若 modifications 中包含 topic_expansion，直接使用
  2. 否则调用 LLM 扩写课题背景描述
  3. 将结果写入 review_outlines.topic_expansion
  4. 标记阶段 1 completed（全自动，不暂停）
  5. 立即创建并启动阶段 2

阶段 1 不暂停等待用户，自动链接到阶段 2。
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_error_event, emit_sse_event, get_llm_client
from app.agents.review.pipeline import (
    get_latest_draft_outline,
    get_project,
    load_review_prompts,
    mark_stage_completed,
    mark_stage_failed,
)
from app.core.errors import AppErrorCode, make_envelope
from app.models.stage import StageRecord
from app.utils.ids import new_id

logger = logging.getLogger(__name__)


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 1 执行逻辑。
    完成后自动创建阶段 2 记录并触发执行（链式调用）。

    modifications 可包含：
      {"topic_expansion": "用户自定义扩写文本"}  — 直接使用，跳过 LLM 调用
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    outline = await get_latest_draft_outline(db, project_id)
    if outline is None:
        raise ValueError(f"未找到项目 {project_id} 的综述架构记录")

    emit_sse_event(project_id, "stage_start", {
        "stage": 1,
        "stage_name": "课题扩写",
    })

    # ── 路径 A：modifications 提供了 topic_expansion ────────────────────────
    if modifications.get("topic_expansion"):
        topic_expansion = modifications["topic_expansion"]
        logger.info("Stage1: using user-provided topic_expansion")
    else:
        # ── 路径 B：调用 LLM 扩写 ──────────────────────────────────────────
        emit_sse_event(project_id, "stage_progress", {
            "stage": 1, "progress": 30, "detail": "调用 LLM 扩写课题描述..."
        })

        prompts = load_review_prompts()
        cfg = prompts["stage1_topic_expansion"]
        system_prompt = cfg["system"]

        topic_hint_section = ""
        if outline.topic_expansion:
            topic_hint_section = f"用户附加说明：{outline.topic_expansion}"

        user_msg = cfg["user_template"].format_map({
            "name": project.name,
            "description": project.description or project.name,
            "topic_hint_section": topic_hint_section,
        })

        llm = await get_llm_client(db, user_id, "review_1")
        topic_expansion = await llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=cfg.get("llm_params", {}).get("temperature"),
            max_tokens=cfg.get("llm_params", {}).get("max_tokens"),
        )
        topic_expansion = topic_expansion.strip()

    # ── 写入 outline.topic_expansion ────────────────────────────────────────
    outline.topic_expansion = topic_expansion
    await db.commit()

    emit_sse_event(project_id, "stage_progress", {
        "stage": 1, "progress": 100, "detail": "课题扩写完成，正在生成综述架构..."
    })

    # ── 标记阶段 1 完成（不暂停，自动链接到阶段 2）──────────────────────────
    await mark_stage_completed(db, record.id, {"topic_expansion_length": len(topic_expansion)})

    # ── 创建阶段 2 记录并直接调用 ────────────────────────────────────────────
    record2 = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode="review",
        stage=2,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(record2)
    await db.commit()
    await db.refresh(record2)

    emit_sse_event(project_id, "stage_start", {
        "stage": 2,
        "stage_name": "综述架构生成",
    })

    # 延迟导入避免循环
    from app.agents.review import stage2_outline_gen
    try:
        await stage2_outline_gen.run(db, project_id, user_id, record2, {})
    except Exception as exc:
        # 阶段 2 失败：用阶段 2 的 record_id 标记失败，阶段 1 本身已正常完成，不再抛出
        logger.exception("Stage2 failed (chained from Stage1) for project %s: %s", project_id, exc)
        from app.core.errors import classify_agent_error
        error_code = classify_agent_error(exc, "review", 2)
        envelope = make_envelope(
            error_code, str(exc), exc=exc,
            detail={"stage": 2, "stage_name": "综述架构生成"},
            project_id=project_id, stage_record_id=record2.id,
        )
        await mark_stage_failed(db, record2.id, envelope.model_dump_json())
        emit_error_event(project_id, envelope)
