"""
构建模式阶段 1 — 检索词生成（FR-012 前置）

职责：
  1. 若 modifications 中包含用户已编辑的检索词，直接使用并存入 DB
  2. 否则调用 LLM 根据课题名称和描述生成检索词列表
  3. 将生成/更新的检索词写入 keywords 表
  4. 将阶段标记为 paused，推送 SSE 通知

注意：Agent 在此阶段只生成检索词，实际检索在 stage2 执行。
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    emit_sse_event,
    get_llm_client,
    load_construction_prompts,
    parse_json_response,
)
from app.agents.construction.pipeline import (
    get_pipeline_params,
    get_project,
    mark_stage_paused,
)
from app.models.project import Keyword
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

    modifications 可包含：
      {"keywords": [{"search_word": "...", "boolean_expressions": {...}, "is_selected": true}, ...]}
      若提供，直接覆盖为初始检索词（用户在重试时可以提前编辑）。
    """
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError(f"项目 {project_id} 不存在")

    pipeline_params = await get_pipeline_params(db, project_id)
    databases = pipeline_params["databases"]

    emit_sse_event(project_id, "stage_progress", {
        "stage": 1, "progress": 10, "detail": "开始生成检索词..."
    })

    # ── 路径 A：用户已通过 modifications 提供检索词 ──────────────────────────
    if modifications.get("keywords"):
        keyword_dicts = modifications["keywords"]
        logger.info("Stage1: using %d user-provided keywords", len(keyword_dicts))
    else:
        # ── 路径 B：调用 LLM 生成检索词 ─────────────────────────────────────
        emit_sse_event(project_id, "stage_progress", {
            "stage": 1, "progress": 30, "detail": "调用 LLM 生成检索词..."
        })

        prompts = load_construction_prompts()
        cfg = prompts["stage1_keyword_generation"]
        system_prompt = cfg["system"]
        user_msg = cfg["user_template"].format_map({
            "name": project.name,
            "description": project.description or project.name,
            "databases": ", ".join(databases),
        })

        llm = await get_llm_client(db, user_id, "construction_1")
        raw = await llm.complete([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ])

        try:
            keyword_dicts = parse_json_response(raw)
            if not isinstance(keyword_dicts, list):
                raise ValueError("LLM 未返回数组")
        except Exception as exc:
            raise RuntimeError(f"LLM 返回的检索词格式无效: {exc}\n原始响应: {raw[:500]}") from exc

        logger.info("Stage1: LLM generated %d keywords", len(keyword_dicts))

    emit_sse_event(project_id, "stage_progress", {
        "stage": 1, "progress": 70, "detail": f"生成 {len(keyword_dicts)} 个检索词，正在保存..."
    })

    # ── 将生成的检索词写入 DB（仅新增，不删除用户已有的） ─────────────────────
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # 获取当前已有检索词（search_word 去重）
    existing_res = await db.execute(
        select(Keyword).where(Keyword.project_id == project_id)
    )
    existing_words = {kw.search_word.lower() for kw in existing_res.scalars().all()}

    added = 0
    for kw_data in keyword_dicts:
        word = kw_data.get("search_word", "").strip()
        if not word:
            continue
        if word.lower() in existing_words:
            continue  # 跳过已存在的检索词

        kw = Keyword(
            id=new_id("kw"),
            project_id=project_id,
            search_word=word,
            boolean_expressions=kw_data.get("boolean_expressions"),
            is_selected=kw_data.get("is_selected", True),
            is_searched=False,
            searched_papers_total=0,
            searched_papers_arxiv=0,
            searched_papers_openalex=0,
            searched_papers_semanticscholar=0,
            searched_papers_ads=0,
            created_at=now,
            last_search_at=now,
        )
        db.add(kw)
        existing_words.add(word.lower())
        added += 1

    await db.commit()

    emit_sse_event(project_id, "stage_progress", {
        "stage": 1, "progress": 95,
        "detail": f"检索词生成完成，新增 {added} 个，共 {len(existing_words)} 个"
    })

    # ── 查询最终检索词列表作为阶段产出 ──────────────────────────────────────
    final_res = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id)
        .order_by(Keyword.created_at)
    )
    all_keywords = final_res.scalars().all()

    stage_result = {
        "total_keywords": len(all_keywords),
        "new_keywords": added,
        "keywords": [
            {
                "keyword_id": kw.id,
                "search_word": kw.search_word,
                "boolean_expressions": kw.boolean_expressions,
                "is_selected": kw.is_selected,
            }
            for kw in all_keywords
        ],
    }

    # ── 标记阶段为 paused，等待用户确认 ─────────────────────────────────────
    await mark_stage_paused(db, record.id, stage_result)

    emit_sse_event(project_id, "stage_pause", {
        "stage": 1,
        "status": "paused",
        "result": {
            "total_keywords": stage_result["total_keywords"],
            "new_keywords": added,
        },
    })
    logger.info("Stage1 paused for project %s: %d keywords", project_id, len(all_keywords))
