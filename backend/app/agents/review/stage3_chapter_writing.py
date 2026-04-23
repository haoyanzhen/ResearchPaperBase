"""
综述模式阶段 3 — 章节内容撰写（FR-021）

职责：
  1. 获取 confirmed outline 下的所有章节（pending 状态）
  2. 逐章节调用 LLM 撰写内容
  3. 自动为每章生成引用列表（从项目论文库中匹配）
  4. 写入章节 content + citations，标记 chapter.status = completed
  5. 通过 SSE 推送每章进度
  6. 所有章节完成后，自动执行阶段 4（自动审查）
  7. 阶段 4 完成后，暂停等待用户调用 compile
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event, get_llm_client, parse_json_response
from app.agents.review.pipeline import (
    get_outline_chapters,
    get_project,
    load_review_prompts,
    mark_stage_completed,
    mark_stage_failed,
    mark_stage_paused,
)
from app.models.paper import Paper, ProjectPaperRelation
from app.models.review import ReviewChapter, ReviewOutline
from app.models.stage import StageRecord
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

# 每章最多取多少篇论文作为参考
_MAX_PAPERS_PER_CHAPTER = 15
# 每篇论文摘要截断长度
_ABSTRACT_TRUNCATE = 500


async def _get_confirmed_outline(db: AsyncSession, project_id: str) -> ReviewOutline | None:
    """返回该课题最新 confirmed 的综述架构。"""
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


async def _build_papers_context(db: AsyncSession, project_id: str) -> tuple[list[dict], str]:
    """
    从项目论文库中取有效论文，构建供 LLM 参考的论文摘要上下文。
    返回 (papers_list, context_str)
    """
    res = await db.execute(
        select(Paper, ProjectPaperRelation)
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
        )
        .order_by(ProjectPaperRelation.total_score.desc())
        .limit(_MAX_PAPERS_PER_CHAPTER)
    )
    rows = res.all()

    papers = []
    context_lines = []
    for paper, rel in rows:
        papers.append({
            "paper_id": paper.id,
            "title": paper.title,
            "authors": paper.authors or [],
            "pub_date": str(paper.pub_date) if paper.pub_date else "",
            "venue": paper.venue or "",
            "total_score": rel.total_score,
        })
        abstract_snippet = (paper.abstract or "")[:_ABSTRACT_TRUNCATE]
        context_lines.append(
            f"[{paper.id}] {paper.title}\n"
            f"  作者: {', '.join((paper.authors or [])[:3])}\n"
            f"  来源: {paper.venue or '未知'} ({str(paper.pub_date)[:4] if paper.pub_date else ''})\n"
            f"  摘要: {abstract_snippet}"
        )

    return papers, "\n\n".join(context_lines) if context_lines else "（暂无有效论文，请先完成构建模式）"


def _extract_citations(content: str, papers: list[dict]) -> list[dict]:
    """
    从章节正文中提取 [cite:paper_id] 引用，生成 citations 数组。
    """
    import re
    cited_ids = set(re.findall(r'\[cite:([^\]]+)\]', content))
    papers_map = {p["paper_id"]: p for p in papers}
    citations = []
    for pid in cited_ids:
        if pid in papers_map:
            p = papers_map[pid]
            authors = p.get("authors") or []
            first_author = authors[0].split()[-1] if authors else "Unknown"
            year = str(p.get("pub_date", ""))[:4] or "n.d."
            citations.append({
                "paper_id": pid,
                "citation_key": f"{first_author.lower()}{year}",
                "format_apa": f"{', '.join(authors[:3])} ({year}). {p['title']}. {p['venue']}.",
                "context": "",
            })
    return citations


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 3 执行逻辑：逐章节撰写，自动链接到阶段 4（审查迭代），再暂停。
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    outline = await _get_confirmed_outline(db, project_id)
    if outline is None:
        raise ValueError(f"未找到项目 {project_id} 的已确认综述架构")

    chapters = await get_outline_chapters(db, outline.id)
    if not chapters:
        raise ValueError("综述架构尚无章节，请先确认架构")

    papers, papers_context = await _build_papers_context(db, project_id)

    prompts = load_review_prompts()
    cfg = prompts["stage3_chapter_writing"]
    system_prompt = cfg["system"]
    llm_params = cfg.get("llm_params", {})

    outline_data = outline.outline or {}
    sections_map = {
        s["index"]: s
        for s in outline_data.get("sections", [])
    }

    pending_chapters = [c for c in chapters if c.status == "pending"]
    total = len(pending_chapters)
    logger.info("Stage3: writing %d chapters for project %s", total, project_id)

    for idx, chapter in enumerate(pending_chapters):
        emit_sse_event(project_id, "chapter_writing", {
            "chapter_index": chapter.chapter_index,
            "title": chapter.title,
            "status": "writing",
        })

        # 标记章节为 writing
        chapter.status = "writing"
        await db.commit()

        section = sections_map.get(chapter.chapter_index, {})
        key_points = section.get("key_points", [])
        chapter_type = section.get("type", "methodology")

        key_points_str = "\n".join(f"- {kp}" for kp in key_points) if key_points else "（无具体要点）"

        user_msg = cfg["user_template"].format_map({
            "review_title": outline_data.get("title", project.name),
            "topic_expansion": outline.topic_expansion or project.description or project.name,
            "chapter_index": chapter.chapter_index,
            "chapter_title": chapter.title,
            "chapter_type": chapter_type,
            "key_points": key_points_str,
            "papers_context": papers_context,
        })

        llm = await get_llm_client(db, user_id, "review_3")
        content = await llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=llm_params.get("temperature"),
            max_tokens=llm_params.get("max_tokens"),
        )
        content = content.strip()

        citations = _extract_citations(content, papers)

        chapter.content = content
        chapter.citations = citations
        chapter.status = "completed"
        chapter.completed_at = datetime.now(timezone.utc)
        await db.commit()

        progress = int((idx + 1) / total * 100)
        emit_sse_event(project_id, "chapter_complete", {
            "chapter_index": chapter.chapter_index,
            "iteration_count": 0,
            "progress": progress,
        })

    await mark_stage_completed(db, record.id, {"chapters_written": total})

    # ── 自动链接到阶段 4（审查迭代） ─────────────────────────────────────────
    record4 = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode="review",
        stage=4,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(record4)
    await db.commit()
    await db.refresh(record4)

    emit_sse_event(project_id, "stage_start", {
        "stage": 4,
        "stage_name": "自动审查迭代",
    })

    from app.agents.review import stage4_auto_review
    try:
        await stage4_auto_review.run(db, project_id, user_id, record4, {})
    except Exception as exc:
        # 阶段 4 失败：用阶段 4 的 record_id 标记失败，阶段 3 本身已正常完成，不再抛出
        logger.exception("Stage4 failed (chained from Stage3) for project %s: %s", project_id, exc)
        await mark_stage_failed(db, record4.id, str(exc))
        emit_sse_event(project_id, "stage_error", {
            "stage": 4,
            "error": str(exc),
            "retryable": True,
        })
