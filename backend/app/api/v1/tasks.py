"""
FR-008 任务管理 — 全局 /tasks 端点

当前 tasks 以 stage_records 表中的活跃记录为权威来源：
  task_id  == stage_record.id
  task_type == stage_record.mode （construction / review）

暂停 / 恢复 / 取消 均通过修改 stage_record.status 和上层 project.status 实现，
实际 Agent 进程的控制信号由 Agent 层订阅并响应（超出 API 层职责）。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.project import Project
from app.models.stage import StageRecord
from app.models.user import User
from app.schemas.common import ok
from app.schemas.project import TaskItem, TaskStatusResponse

router = APIRouter(prefix="/tasks", tags=["任务管理"])


async def _get_task_and_project(
    db: AsyncSession,
    task_id: str,
    user_id: str,
) -> tuple[StageRecord, Project]:
    """获取 task(stage_record) 并验证归属用户。"""
    rec_result = await db.execute(select(StageRecord).where(StageRecord.id == task_id))
    record = rec_result.scalar_one_or_none()
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    proj_result = await db.execute(
        select(Project).where(
            Project.id == record.project_id,
            Project.user_id == user_id,
        )
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权操作此任务")

    return record, project


@router.get("")
async def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    project_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户所有课题的任务列表（FR-008）"""
    # 只查本用户的课题
    proj_query = select(Project.id).where(Project.user_id == current_user.id)
    if project_id:
        proj_query = proj_query.where(Project.id == project_id)
    proj_result = await db.execute(proj_query)
    user_project_ids = [row[0] for row in proj_result.all()]

    if not user_project_ids:
        return ok([])

    query = (
        select(StageRecord)
        .where(StageRecord.project_id.in_(user_project_ids))
        .order_by(StageRecord.started_at.desc())
        .limit(100)
    )
    if status_filter:
        query = query.where(StageRecord.status == status_filter)

    result = await db.execute(query)
    records = result.scalars().all()

    return ok([
        TaskItem(
            task_id=r.id,
            project_id=r.project_id,
            task_type=r.mode,
            status=r.status,
            stage=r.stage,
            created_at=r.started_at,
        )
        for r in records
    ])


@router.post("/{task_id}/pause")
async def pause_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record, project = await _get_task_and_project(db, task_id, current_user.id)
    if record.status != "running":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "只有运行中的任务可以暂停")

    record.status = "paused"
    project.status = "paused"
    await db.commit()
    return ok(TaskStatusResponse(task_id=task_id, status="paused"))


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record, project = await _get_task_and_project(db, task_id, current_user.id)
    if record.status != "paused":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "只有暂停中的任务可以恢复")

    record.status = "running"
    project.status = "running"
    await db.commit()
    return ok(TaskStatusResponse(task_id=task_id, status="running"))


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record, project = await _get_task_and_project(db, task_id, current_user.id)
    if record.status not in ("running", "paused"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该任务已结束，无法取消")

    record.status = "failed"
    record.error = "用户取消"
    project.status = "idle"
    await db.commit()
    return ok(TaskStatusResponse(task_id=task_id, status="cancelled"))
