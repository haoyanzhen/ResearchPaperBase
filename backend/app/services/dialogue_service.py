"""
业务逻辑 — 深度研究模式（FR-025~028）

职责：
  - 对话会话 CRUD（list_dialogues / create_dialogue / get_dialogue /
                   update_dialogue / delete_dialogue）
  - 对话轮次查询（list_turns）
  - 项目权限校验（_get_project）
  - sub_mode 派生（从最近一轮 sub_mode 或默认 "technical"）
  - AgentSummary JSON 的序列化/反序列化
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dialogue import DialogueTurn, ResearchDialogue
from app.models.project import Project
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

_DEFAULT_SUB_MODE = "technical"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# 辅助：项目权限校验
# =============================================================================

async def _get_project(db: AsyncSession, project_id: str, user_id: str) -> Project | None:
    res = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def _derive_sub_mode(db: AsyncSession, dialogue_id: str) -> str:
    """从最近一轮 sub_mode 派生对话当前子模式；若无轮次则返回默认值。"""
    res = await db.execute(
        select(DialogueTurn.sub_mode)
        .where(DialogueTurn.dialogue_id == dialogue_id)
        .order_by(DialogueTurn.turn_index.desc())
        .limit(1)
    )
    sub_mode = res.scalar_one_or_none()
    return sub_mode or _DEFAULT_SUB_MODE


def _parse_summary(raw: str | None) -> dict | None:
    """将 DB TEXT 字段中的 JSON 字符串解析为 dict；失败时返回 None。"""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _summary_preview(raw: str | None) -> str | None:
    """返回摘要纯文本预览（取 progress 字段或截断原文）。"""
    if not raw:
        return None
    parsed = _parse_summary(raw)
    if parsed and isinstance(parsed, dict):
        return parsed.get("progress") or str(raw)[:200]
    return raw[:200] if raw else None


# =============================================================================
# 对话会话 CRUD
# =============================================================================

async def list_dialogues(
    db: AsyncSession,
    project_id: str,
    user_id: str,
) -> list[dict] | None:
    """
    返回课题所有对话会话（按 last_active_at 降序），附带派生的 sub_mode。
    项目不存在/无权限返回 None。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    res = await db.execute(
        select(ResearchDialogue)
        .where(ResearchDialogue.project_id == project_id)
        .order_by(ResearchDialogue.last_active_at.desc())
    )
    dialogues = list(res.scalars().all())

    results = []
    for d in dialogues:
        sub_mode = await _derive_sub_mode(db, d.id)
        results.append({
            "dialogue": d,
            "sub_mode": sub_mode,
            "summary_preview": _summary_preview(d.summary),
        })
    return results


async def create_dialogue(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    title: str | None,
    init_sub_mode: str | None,
) -> ResearchDialogue | None:
    """
    创建新对话会话。
    init_sub_mode 不存储于 DB，仅用于前端 UI 首轮默认值提示。
    项目不存在/无权限返回 None。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    now = _utcnow()
    dialogue = ResearchDialogue(
        id=new_id("dlg"),
        project_id=project_id,
        title=title,
        status="active",
        turn_count=0,
        last_active_at=now,
    )
    db.add(dialogue)
    await db.commit()
    await db.refresh(dialogue)
    return dialogue


async def get_dialogue(
    db: AsyncSession,
    project_id: str,
    dialogue_id: str,
    user_id: str,
) -> ResearchDialogue | None:
    """返回指定对话会话；归属校验失败返回 None。"""
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None
    res = await db.execute(
        select(ResearchDialogue).where(
            ResearchDialogue.id == dialogue_id,
            ResearchDialogue.project_id == project_id,
        )
    )
    return res.scalar_one_or_none()


async def update_dialogue(
    db: AsyncSession,
    dialogue: ResearchDialogue,
    title: str | None,
    tags: list[str] | None,
    new_status: str | None,
) -> ResearchDialogue:
    """更新对话会话元数据（标题/标签/状态）。"""
    if title is not None:
        dialogue.title = title
    if tags is not None:
        dialogue.tags = tags
    if new_status is not None and new_status in ("active", "archived"):
        dialogue.status = new_status
    await db.commit()
    await db.refresh(dialogue)
    return dialogue


async def delete_dialogue(
    db: AsyncSession,
    dialogue: ResearchDialogue,
) -> None:
    """删除对话会话（级联删除所有轮次）。"""
    await db.delete(dialogue)
    await db.commit()


# =============================================================================
# 对话轮次查询（FR-027）
# =============================================================================

async def list_turns(
    db: AsyncSession,
    dialogue_id: str,
    offset: int = 0,
    limit: int | None = None,
) -> list[DialogueTurn]:
    """
    返回对话轮次（按 turn_index 升序），支持 offset/limit 分页。
    """
    stmt = (
        select(DialogueTurn)
        .where(DialogueTurn.dialogue_id == dialogue_id)
        .order_by(DialogueTurn.turn_index)
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())
