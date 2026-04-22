"""
HTTP 路由 — 构建模式（FR-012~019）

端点：
  POST   /projects/{project_id}/construction/start                   启动构建流程
  GET    /projects/{project_id}/construction/status                  获取构建当前状态
  GET    /projects/{project_id}/construction/keywords                获取检索词列表
  PATCH  /projects/{project_id}/construction/keywords                更新检索词（阶段1交互）
  POST   /projects/{project_id}/construction/stages/{stage}/action   阶段用户操作（阶段1-6）
  GET    /projects/{project_id}/construction/stream                  构建进度 SSE 流

设计要点：
  - start_construction 创建 stage 1 记录后，立即通过 BackgroundTasks 触发 Agent 执行
  - stage_action confirm/skip 推进到 next_stage 后，触发对应 Agent（stage 2-6）
  - stage 6 confirm/skip 触发 stage 7 邮件发送（execute_stage7，独立会话）
  - SSE 流读取 agents.base.get_sse_queue() 的 asyncio.Queue，Agent 写入，客户端读取
"""

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import get_sse_queue
from app.agents.construction import run_stage
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import decode_access_token
from app.models.stage import StageRecord
from app.models.user import User
from app.schemas.common import ok
from app.schemas.construction import (
    ConstructionStatusResponse,
    KeywordItemResponse,
    StartConstructionRequest,
    StartConstructionResponse,
    StageActionRequest,
    StageActionResponse,
    UpdateKeywordsRequest,
)
from app.services import construction_service

router = APIRouter(
    prefix="/projects/{project_id}/construction",
    tags=["构建模式"],
)


# =============================================================================
# 启动构建 (POST /construction/start)
# =============================================================================

@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_construction(
    project_id: str,
    body: StartConstructionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    启动构建流程，创建 stage 1 记录并触发 Agent 执行检索词生成。
    """
    record, err = await construction_service.start_construction(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        databases=body.databases,
        score_threshold=body.score_threshold,
    )
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    # 触发 stage 1 Agent（关键词生成）
    background_tasks.add_task(
        run_stage,
        project_id,
        current_user.id,
        1,
        record.id,
    )

    return ok(StartConstructionResponse(
        task_id=record.id,
        project_id=project_id,
        stage=record.stage,
        status=record.status,
        message="检索词生成中...",
    ))


# =============================================================================
# 构建状态查询 (GET /construction/status)
# =============================================================================

@router.get("/status")
async def get_construction_status(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await construction_service.get_construction_status(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    return ok(ConstructionStatusResponse(**data))


# =============================================================================
# 获取检索词列表 (GET /construction/keywords)
# =============================================================================

@router.get("/keywords")
async def get_keywords(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    keywords = await construction_service.list_keywords(db, project_id, current_user.id)
    if keywords is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    return ok([
        KeywordItemResponse(
            keyword_id=kw.id,
            search_word=kw.search_word,
            boolean_expressions=kw.boolean_expressions,
            is_selected=kw.is_selected,
            is_searched=kw.is_searched,
            searched_papers_total=kw.searched_papers_total,
        )
        for kw in keywords
    ])


# =============================================================================
# 更新检索词 (PATCH /construction/keywords)
# =============================================================================

@router.patch("/keywords")
async def update_keywords(
    project_id: str,
    body: UpdateKeywordsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    keywords = await construction_service.upsert_keywords(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        items=[kw.model_dump() for kw in body.keywords],
    )
    if keywords is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    return ok([
        KeywordItemResponse(
            keyword_id=kw.id,
            search_word=kw.search_word,
            boolean_expressions=kw.boolean_expressions,
            is_selected=kw.is_selected,
            is_searched=kw.is_searched,
            searched_papers_total=kw.searched_papers_total,
        )
        for kw in keywords
    ])


# =============================================================================
# 阶段用户操作 (POST /construction/stages/{stage}/action)
# =============================================================================

@router.post("/stages/{stage}/action")
async def stage_action(
    project_id: str,
    stage: int,
    body: StageActionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    处理阶段 1-6 的用户操作（confirm / retry / skip）。

    成功后：
    - retry：重新触发当前 stage 的 Agent
    - confirm/skip（stage 1-5）：触发 next_stage Agent
    - confirm/skip（stage 6）：触发 execute_stage7（邮件发送，全自动）
    """
    if stage < 1 or stage > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stage 取值范围 1-6（第 7 阶段全自动）",
        )

    result, err = await construction_service.apply_stage_action(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        stage=stage,
        action=body.action,
        modifications=body.modifications,
    )
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    next_stage: int | None = result.get("next_stage")

    if next_stage is not None:
        if next_stage == 7:
            # stage 7：邮件发送全自动（独立 DB 会话）
            sr_res = await db.execute(
                select(StageRecord).where(
                    StageRecord.project_id == project_id,
                    StageRecord.mode == "construction",
                    StageRecord.stage == 7,
                    StageRecord.status == "running",
                ).order_by(StageRecord.started_at.desc()).limit(1)
            )
            stage7_record = sr_res.scalar_one_or_none()
            if stage7_record:
                background_tasks.add_task(
                    construction_service.execute_stage7,
                    project_id,
                    current_user.id,
                    stage7_record.id,
                )
        elif 1 <= next_stage <= 6:
            # stage 2-6：触发对应 Agent（独立 DB 会话，由 run_stage 创建）
            sr_res = await db.execute(
                select(StageRecord).where(
                    StageRecord.project_id == project_id,
                    StageRecord.mode == "construction",
                    StageRecord.stage == next_stage,
                    StageRecord.status == "running",
                ).order_by(StageRecord.started_at.desc()).limit(1)
            )
            new_record = sr_res.scalar_one_or_none()
            if new_record:
                background_tasks.add_task(
                    run_stage,
                    project_id,
                    current_user.id,
                    next_stage,
                    new_record.id,
                )
    else:
        # retry：重新触发当前 stage
        sr_res = await db.execute(
            select(StageRecord).where(
                StageRecord.project_id == project_id,
                StageRecord.mode == "construction",
                StageRecord.stage == stage,
                StageRecord.status == "running",
            ).order_by(StageRecord.started_at.desc()).limit(1)
        )
        retry_record = sr_res.scalar_one_or_none()
        if retry_record:
            background_tasks.add_task(
                run_stage,
                project_id,
                current_user.id,
                stage,
                retry_record.id,
            )

    return ok(StageActionResponse(**result))


# =============================================================================
# 构建进度 SSE 流 (GET /construction/stream)
# =============================================================================

@router.get("/stream")
async def construction_stream(
    project_id: str,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    构建进度 SSE 流。

    客户端通过 URL 参数 ?token=<JWT> 认证（EventSource 不支持自定义请求头）。
    Agent 向 get_sse_queue(project_id) 写入事件，此端点消费并推送给客户端。

    SSE 事件类型（见 api.md §4）：
      stage_start / stage_progress / stage_pause / stage_error / pipeline_complete
    """
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的 token",
        )

    async def event_generator():
        queue = get_sse_queue(project_id)
        # 连接确认
        yield f"event: connected\ndata: {json.dumps({'project_id': project_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                # 等待队列中的事件，超时时发送 heartbeat
                event_str = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event_str
            except asyncio.TimeoutError:
                yield f"event: heartbeat\ndata: {json.dumps({'project_id': project_id})}\n\n"
            except Exception:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Nginx 透传 SSE
        },
    )
