"""
综述模式 Agent 管道公共基础设施

提供：
  - 阶段记录状态更新（paused / failed / completed）
  - 项目状态同步
  - 当前综述 outline 获取
"""

import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.review import ReviewChapter, ReviewOutline
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"

# 综述模式阶段名称映射
REVIEW_STAGE_NAMES: dict[int, str] = {
    1: "课题扩写",
    2: "综述架构生成",
    3: "章节内容撰写",
    4: "自动审查迭代",
    5: "综述文章汇总",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def load_review_prompts() -> dict:
    """加载并缓存综述模式提示词配置（config/review_prompts.yaml）。"""
    with open(_CONFIG_DIR / "review_prompts.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# =============================================================================
# 阶段记录状态更新
# =============================================================================

async def mark_stage_paused(
    db: AsyncSession,
    record_id: str,
    result: dict | None = None,
) -> None:
    """将阶段记录标为 paused；同步 project.status = paused。"""
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    record = res.scalar_one_or_none()
    if record is None:
        logger.warning("mark_stage_paused: record %s not found", record_id)
        return
    record.status = "paused"
    record.paused_at = _utcnow()
    if result is not None:
        record.result = result

    proj_res = await db.execute(select(Project).where(Project.id == record.project_id))
    project = proj_res.scalar_one_or_none()
    if project:
        project.status = "paused"
    await db.commit()


async def mark_stage_failed(
    db: AsyncSession,
    record_id: str,
    error: str,
) -> None:
    """将阶段记录标为 failed；同步 project.status = error。"""
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    record = res.scalar_one_or_none()
    if record is None:
        logger.warning("mark_stage_failed: record %s not found", record_id)
        return
    record.status = "failed"
    record.failed_at = _utcnow()
    record.error = error

    proj_res = await db.execute(select(Project).where(Project.id == record.project_id))
    project = proj_res.scalar_one_or_none()
    if project:
        project.status = "error"
    await db.commit()


async def mark_stage_completed(
    db: AsyncSession,
    record_id: str,
    result: dict | None = None,
) -> None:
    """将阶段记录标为 completed（全自动阶段或中间链接阶段）。"""
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    record = res.scalar_one_or_none()
    if record is None:
        return
    record.status = "completed"
    record.completed_at = _utcnow()
    if result is not None:
        record.result = result
    await db.commit()


# =============================================================================
# 辅助查询
# =============================================================================

async def get_record(db: AsyncSession, record_id: str) -> StageRecord | None:
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    return res.scalar_one_or_none()


async def get_project(db: AsyncSession, project_id: str) -> Project | None:
    res = await db.execute(select(Project).where(Project.id == project_id))
    return res.scalar_one_or_none()


async def get_latest_draft_outline(db: AsyncSession, project_id: str) -> ReviewOutline | None:
    """返回该课题最新的 draft/confirmed 综述架构。"""
    res = await db.execute(
        select(ReviewOutline)
        .where(
            ReviewOutline.project_id == project_id,
            ReviewOutline.status.in_(["draft", "confirmed"]),
        )
        .order_by(ReviewOutline.version.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def get_outline_chapters(db: AsyncSession, outline_id: str) -> list[ReviewChapter]:
    """返回该 outline 下所有章节，按 chapter_index 升序。"""
    res = await db.execute(
        select(ReviewChapter)
        .where(ReviewChapter.outline_id == outline_id)
        .order_by(ReviewChapter.chapter_index)
    )
    return list(res.scalars().all())
