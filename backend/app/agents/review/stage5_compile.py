"""
综述模式阶段 5 — 综述文章汇总（FR-023）

职责：
  1. 取 confirmed outline 下所有章节（按 chapter_index 排序）
  2. 调用 LLM 生成摘要（abstract）和关键词（keywords）
  3. 将完整综述文章（Markdown 格式）写入 outline.outline["compiled_content"]
  4. 将 project.status 置为 idle，标记阶段 5 completed
  5. 推送 SSE pipeline_complete 事件

汇总后的内容结构（Markdown）：
  # {title}

  **摘要**：{abstract}

  **关键词**：{keywords}

  ---

  ## 1. {chapter_1_title}
  {chapter_1_content}

  ## 2. {chapter_2_title}
  ...

  ## 参考文献
  {reference_list}
"""

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
)
from app.models.project import Project
from app.models.review import ReviewOutline
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


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


def _build_reference_list(chapters: list) -> str:
    """从所有章节引用中合并去重，生成参考文献列表。"""
    seen: set[str] = set()
    refs: list[str] = []
    ref_num = 1
    for chapter in chapters:
        for cit in (chapter.citations or []):
            pid = cit.get("paper_id", "")
            if pid not in seen:
                seen.add(pid)
                refs.append(f"[{ref_num}] {cit.get('format_apa', pid)}")
                ref_num += 1
    return "\n".join(refs) if refs else "（暂无引用文献）"


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """阶段 5 执行逻辑：生成摘要+关键词，汇总成完整 Markdown 综述文章。"""
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    outline = await _get_confirmed_outline(db, project_id)
    if outline is None:
        raise ValueError(f"未找到项目 {project_id} 的已确认综述架构")

    chapters = await get_outline_chapters(db, outline.id)
    outline_data = outline.outline or {}
    review_title = outline_data.get("title", project.name)

    emit_sse_event(project_id, "stage_progress", {
        "stage": 5, "progress": 20, "detail": "正在生成摘要和关键词..."
    })

    # ── 生成摘要和关键词 ─────────────────────────────────────────────────────
    prompts = load_review_prompts()
    cfg = prompts["stage5_compile_abstract"]

    chapter_summaries = "\n".join(
        f"第 {c.chapter_index} 章 《{c.title}》：\n{(c.content or '')[:300]}..."
        for c in chapters if c.content
    )

    user_msg = cfg["user_template"].format_map({
        "review_title": review_title,
        "topic_expansion": outline.topic_expansion or project.description or project.name,
        "chapter_summaries": chapter_summaries,
    })

    llm = await get_llm_client(db, user_id, "review_5")
    raw = await llm.complete(
        [
            {"role": "system", "content": cfg["system"]},
            {"role": "user", "content": user_msg},
        ],
        temperature=cfg.get("llm_params", {}).get("temperature"),
        max_tokens=cfg.get("llm_params", {}).get("max_tokens"),
    )
    abstract_data = parse_json_response(raw)
    abstract = abstract_data.get("abstract", "")
    keywords = abstract_data.get("keywords", [])

    emit_sse_event(project_id, "stage_progress", {
        "stage": 5, "progress": 60, "detail": "正在汇总章节内容..."
    })

    # ── 汇总成完整 Markdown ──────────────────────────────────────────────────
    md_parts: list[str] = [
        f"# {review_title}\n",
        f"**摘要**：{abstract}\n",
        f"**关键词**：{'，'.join(keywords)}\n",
        "---\n",
    ]
    for chapter in chapters:
        md_parts.append(f"## {chapter.chapter_index}. {chapter.title}\n")
        md_parts.append((chapter.content or "（章节内容尚未生成）") + "\n")

    md_parts.append("## 参考文献\n")
    md_parts.append(_build_reference_list(chapters))

    compiled_content = "\n".join(md_parts)

    # ── 写回 outline ─────────────────────────────────────────────────────────
    updated_outline = dict(outline_data)
    updated_outline["abstract"] = abstract
    updated_outline["keywords"] = keywords
    updated_outline["compiled_content"] = compiled_content
    outline.outline = updated_outline

    # 将项目状态重置为 idle（综述流程结束）
    proj_res = await db.execute(select(Project).where(Project.id == project_id))
    proj = proj_res.scalar_one_or_none()
    if proj:
        proj.status = "idle"

    await db.commit()

    emit_sse_event(project_id, "pipeline_complete", {
        "outline_id": outline.id,
        "total_chapters": len(chapters),
        "compiled": True,
    })

    await mark_stage_completed(db, record.id, {
        "outline_id": outline.id,
        "total_chapters": len(chapters),
        "abstract_length": len(abstract),
        "keywords_count": len(keywords),
    })
