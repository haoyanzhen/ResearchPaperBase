"""
综述模式阶段 4 — 自动审查迭代（FR-022）

职责：
  1. 遍历 confirmed outline 下所有 completed 章节
  2. 对每章调用 LLM 审查（stage4_chapter_review prompt）
  3. 若存在问题（needs_revision=true）且迭代次数 < max_iterations，调用 LLM 修改
  4. 更新章节 content / review_history / iteration_count
  5. 通过 SSE 推送每章审查进度
  6. 所有章节完成后，暂停（等待用户调用 compile）

也可通过 review_service.review_single_chapter() 在不走 stage 系统的情况下
对单章节独立执行一次审查+修改。
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event, get_llm_client, parse_json_response
from app.agents.review.pipeline import (
    get_outline_chapters,
    get_project,
    load_review_prompts,
    mark_stage_paused,
)
from app.models.review import ReviewOutline
from app.models.stage import StageRecord
from sqlalchemy import select

logger = logging.getLogger(__name__)

# 每章最多自动迭代次数
_MAX_ITERATIONS = 2


async def _get_confirmed_outline(db: AsyncSession, project_id: str) -> ReviewOutline | None:
    res = await db.execute(
        select(ReviewOutline)
        .where(
            ReviewOutline.project_id == project_id,
            ReviewOutline.status == "confirmed",
        )
        .order_by(ReviewOutline.version.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def review_chapter_once(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    chapter,          # ReviewChapter ORM instance
    review_title: str,
    iteration: int,
) -> bool:
    """
    对单章节执行一次审查+修改循环。
    返回 True 表示进行了修改，False 表示无需修改。
    """
    prompts = load_review_prompts()

    # ── 审查 ────────────────────────────────────────────────────────────────
    review_cfg = prompts["stage4_chapter_review"]
    citation_count = len(chapter.citations or [])
    user_msg = review_cfg["user_template"].format_map({
        "review_title": review_title,
        "chapter_title": chapter.title,
        "chapter_content": (chapter.content or "")[:6000],
        "citation_count": citation_count,
        "iteration": iteration,
    })
    llm = await get_llm_client(db, user_id, "review_4")
    raw = await llm.complete(
        [
            {"role": "system", "content": review_cfg["system"]},
            {"role": "user", "content": user_msg},
        ],
        temperature=review_cfg.get("llm_params", {}).get("temperature"),
        max_tokens=review_cfg.get("llm_params", {}).get("max_tokens"),
    )
    review_result = parse_json_response(raw)
    issues = review_result.get("issues", [])
    suggestions = review_result.get("suggestions", [])
    needs_revision = review_result.get("needs_revision", False) and bool(issues)

    now = datetime.now(timezone.utc)
    history_entry = {
        "iteration": iteration,
        "reviewed_at": now.isoformat(),
        "issues": issues,
        "suggestions": suggestions,
        "accepted": needs_revision,
        "revised_at": None,
    }

    if needs_revision:
        # ── 修改 ──────────────────────────────────────────────────────────
        revision_cfg = prompts["stage4_chapter_revision"]
        issues_text = "\n".join(
            f"问题{i+1}：{iss}\n建议{i+1}：{sug}"
            for i, (iss, sug) in enumerate(zip(issues, suggestions))
        )
        rev_msg = revision_cfg["user_template"].format_map({
            "review_title": review_title,
            "chapter_title": chapter.title,
            "issues_and_suggestions": issues_text,
            "chapter_content": chapter.content or "",
        })
        llm2 = await get_llm_client(db, user_id, "review_4")
        new_content = await llm2.complete(
            [
                {"role": "system", "content": revision_cfg["system"]},
                {"role": "user", "content": rev_msg},
            ],
            temperature=revision_cfg.get("llm_params", {}).get("temperature"),
            max_tokens=revision_cfg.get("llm_params", {}).get("max_tokens"),
        )
        chapter.content = new_content.strip()
        history_entry["revised_at"] = datetime.now(timezone.utc).isoformat()

    chapter.review_history = (chapter.review_history or []) + [history_entry]
    chapter.iteration_count = (chapter.iteration_count or 0) + 1
    await db.commit()

    return needs_revision


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 4 执行逻辑：遍历所有章节执行审查迭代，然后暂停。
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    outline = await _get_confirmed_outline(db, project_id)
    if outline is None:
        raise ValueError(f"未找到项目 {project_id} 的已确认综述架构")

    chapters = await get_outline_chapters(db, outline.id)
    completed_chapters = [c for c in chapters if c.content is not None]

    outline_data = outline.outline or {}
    review_title = outline_data.get("title", project.name)

    for chapter in completed_chapters:
        emit_sse_event(project_id, "chapter_reviewing", {
            "chapter_index": chapter.chapter_index,
            "iteration": (chapter.iteration_count or 0) + 1,
            "issues": [],
        })

        for iter_num in range(_MAX_ITERATIONS):
            revised = await review_chapter_once(
                db, user_id, project_id, chapter,
                review_title, iter_num + 1,
            )
            emit_sse_event(project_id, "chapter_reviewing", {
                "chapter_index": chapter.chapter_index,
                "iteration": iter_num + 1,
                "revised": revised,
            })
            if not revised:
                break

        emit_sse_event(project_id, "chapter_complete", {
            "chapter_index": chapter.chapter_index,
            "iteration_count": chapter.iteration_count,
        })

    emit_sse_event(project_id, "stage_pause", {
        "stage": 4,
        "status": "paused",
        "result": {
            "outline_id": outline.id,
            "chapters_reviewed": len(completed_chapters),
        },
    })

    await mark_stage_paused(db, record.id, {
        "outline_id": outline.id,
        "chapters_reviewed": len(completed_chapters),
    })
