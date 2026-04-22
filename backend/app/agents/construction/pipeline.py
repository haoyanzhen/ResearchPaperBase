"""
构建模式 Agent 管道公共基础设施

提供：
  - 阶段记录状态更新（paused / failed / completed）
  - 项目状态同步（running / paused / error / idle）
  - 阶段启动参数读取（数据库列表 / score_threshold）
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# 阶段记录状态更新
# =============================================================================

async def mark_stage_paused(
    db: AsyncSession,
    record_id: str,
    result: dict,
) -> None:
    """
    将阶段记录标为 paused，并写入阶段产出 result。
    同时将关联 project.status 更新为 paused。
    """
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    record = res.scalar_one_or_none()
    if record is None:
        logger.warning("mark_stage_paused: record %s not found", record_id)
        return

    record.status = "paused"
    record.paused_at = _utcnow()
    record.result = result

    # 同步 project 状态
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
    """
    将阶段记录标为 failed，并写入错误信息。
    同时将关联 project.status 更新为 error。
    """
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
    result: dict,
) -> None:
    """将阶段记录标为 completed（用于全自动阶段，如 stage 7）。"""
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    record = res.scalar_one_or_none()
    if record is None:
        return
    record.status = "completed"
    record.completed_at = _utcnow()
    record.result = result
    await db.commit()


# =============================================================================
# 阶段启动参数
# =============================================================================

async def get_pipeline_params(db: AsyncSession, project_id: str) -> dict:
    """
    从阶段1的 result 中读取本次管道启动参数（databases / score_threshold）。
    若找不到则返回默认值。
    """
    res = await db.execute(
        select(StageRecord)
        .where(
            StageRecord.project_id == project_id,
            StageRecord.mode == "construction",
            StageRecord.stage == 1,
        )
        .order_by(StageRecord.started_at.desc())
        .limit(1)
    )
    record = res.scalar_one_or_none()
    if record and record.result:
        return {
            "databases": record.result.get("databases", ["arxiv", "openalex", "semantic_scholar"]),
            "score_threshold": record.result.get("score_threshold", 7),
        }
    return {"databases": ["arxiv", "openalex", "semantic_scholar"], "score_threshold": 7}


async def get_project(db: AsyncSession, project_id: str) -> Project | None:
    """返回 Project 对象（无权限校验，Agent 内部使用）。"""
    res = await db.execute(select(Project).where(Project.id == project_id))
    return res.scalar_one_or_none()


async def get_record(db: AsyncSession, record_id: str) -> StageRecord | None:
    """通过 ID 获取 StageRecord。"""
    res = await db.execute(select(StageRecord).where(StageRecord.id == record_id))
    return res.scalar_one_or_none()
