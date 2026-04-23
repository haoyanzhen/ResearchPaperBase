"""
HTTP 路由 — 综述模式（FR-020~024）

端点：
  POST   /projects/{project_id}/review/start                                     启动综述流程
  GET    /projects/{project_id}/review/status                                     综述状态查询
  GET    /projects/{project_id}/review/outlines                                   获取综述架构版本列表
  GET    /projects/{project_id}/review/outlines/{outline_id}                      获取综述架构详情
  PATCH  /projects/{project_id}/review/outlines/{outline_id}                      修改综述架构
  POST   /projects/{project_id}/review/outlines/{outline_id}/confirm              确认架构，进入章节撰写
  GET    /projects/{project_id}/review/outlines/{outline_id}/chapters             获取所有章节状态
  GET    /projects/{project_id}/review/outlines/{outline_id}/chapters/{id}        获取章节完整内容
  PATCH  /projects/{project_id}/review/outlines/{outline_id}/chapters/{id}        修改章节内容
  POST   /projects/{project_id}/review/outlines/{outline_id}/chapters/{id}/review 触发章节自动审查
  POST   /projects/{project_id}/review/outlines/{outline_id}/compile              汇总综述文章
  GET    /projects/{project_id}/review/outlines/{outline_id}/export               导出综述文章
  GET    /projects/{project_id}/review/stream                                     综述进度 SSE 流
"""

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event, get_sse_queue
from app.agents.review import run_stage
from app.agents.review.stage4_auto_review import review_chapter_once
from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import get_current_user
from app.core.security import decode_access_token
from app.models.review import ReviewChapter
from app.models.user import User
from app.schemas.common import ok
from app.schemas.review import (
    ChapterDetail,
    ChapterSummary,
    CompileResponse,
    ConfirmOutlineResponse,
    OutlineDetail,
    OutlineSummary,
    ReviewStatusResponse,
    StartReviewRequest,
    StartReviewResponse,
    TriggerChapterReviewResponse,
    UpdateChapterRequest,
    UpdateOutlineRequest,
)
from app.services import review_service

logger = logging.getLogger(__name__)


async def _run_chapter_review(
    user_id: str,
    project_id: str,
    chapter_id: str,
    review_title: str,
    iteration: int,
) -> None:
    """
    BackgroundTask 包装：自行创建 AsyncSession，执行单章节审查，
    完成后推送 SSE chapter_complete 事件。
    """
    async with AsyncSessionLocal() as db:
        chapter = await db.get(ReviewChapter, chapter_id)
        if chapter is None:
            logger.warning("_run_chapter_review: chapter %s not found", chapter_id)
            return
        try:
            await review_chapter_once(db, user_id, project_id, chapter, review_title, iteration)
            emit_sse_event(project_id, "chapter_complete", {
                "chapter_index": chapter.chapter_index,
                "iteration_count": chapter.iteration_count,
            })
        except Exception as exc:
            logger.exception("chapter review failed for %s: %s", chapter_id, exc)
            emit_sse_event(project_id, "stage_error", {
                "stage": 4,
                "error": str(exc),
                "retryable": True,
            })

router = APIRouter(
    prefix="/projects/{project_id}/review",
    tags=["综述模式"],
)


# =============================================================================
# 启动综述流程（FR-020）
# =============================================================================

@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_review(
    project_id: str,
    body: StartReviewRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新版本综述架构，触发阶段 1（课题扩写）Agent。"""
    outline, record = await review_service.start_review(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        topic_hint=body.topic_hint,
    )
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    background_tasks.add_task(
        run_stage,
        project_id,
        current_user.id,
        1,
        record.id,
    )

    return ok(StartReviewResponse(
        task_id=record.id,
        outline_id=outline.id,
        stage=record.stage,
        status=record.status,
    ))


# =============================================================================
# 综述状态查询（FR-020）
# =============================================================================

@router.get("/status")
async def get_review_status(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await review_service.get_review_status(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    return ok(ReviewStatusResponse(**data))


# =============================================================================
# 综述架构版本列表（FR-020 / FR-024）
# =============================================================================

@router.get("/outlines")
async def list_outlines(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outlines = await review_service.list_outlines(db, project_id, current_user.id)
    if outlines is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    return ok([
        OutlineSummary(
            outline_id=o.id,
            version=o.version,
            status=o.status,
            confirmed_at=o.confirmed_at,
            created_at=o.created_at,
        )
        for o in outlines
    ])


# =============================================================================
# 综述架构详情
# =============================================================================

@router.get("/outlines/{outline_id}")
async def get_outline(
    project_id: str,
    outline_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    return ok(OutlineDetail(
        outline_id=outline.id,
        version=outline.version,
        status=outline.status,
        confirmed_at=outline.confirmed_at,
        created_at=outline.created_at,
        topic_expansion=outline.topic_expansion,
        outline=outline.outline,
    ))


# =============================================================================
# 修改综述架构（阶段 2 用户交互）
# =============================================================================

@router.patch("/outlines/{outline_id}")
async def update_outline(
    project_id: str,
    outline_id: str,
    body: UpdateOutlineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    outline = await review_service.update_outline(
        db=db,
        outline=outline,
        topic_expansion=body.topic_expansion,
        outline_data=body.outline,
    )

    return ok(OutlineDetail(
        outline_id=outline.id,
        version=outline.version,
        status=outline.status,
        confirmed_at=outline.confirmed_at,
        created_at=outline.created_at,
        topic_expansion=outline.topic_expansion,
        outline=outline.outline,
    ))


# =============================================================================
# 确认综述架构，进入章节撰写（FR-021）
# =============================================================================

@router.post("/outlines/{outline_id}/confirm")
async def confirm_outline(
    project_id: str,
    outline_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")
    if outline.status == "confirmed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="综述架构已确认")

    outline, record = await review_service.confirm_outline(db, project_id, outline)

    background_tasks.add_task(
        run_stage,
        project_id,
        current_user.id,
        3,
        record.id,
    )

    return ok(ConfirmOutlineResponse(
        outline_id=outline.id,
        status=outline.status,
        confirmed_at=outline.confirmed_at,
        message="架构已确认，开始撰写章节内容...",
    ))


# =============================================================================
# 章节列表（FR-021）
# =============================================================================

@router.get("/outlines/{outline_id}/chapters")
async def list_chapters(
    project_id: str,
    outline_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 验证 outline 归属
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    chapters = await review_service.list_chapters(db, outline_id)

    return ok([
        ChapterSummary(
            chapter_id=c.id,
            chapter_index=c.chapter_index,
            title=c.title,
            status=c.status,
            iteration_count=c.iteration_count,
            completed_at=c.completed_at,
        )
        for c in chapters
    ])


# =============================================================================
# 章节详情（FR-021）
# =============================================================================

@router.get("/outlines/{outline_id}/chapters/{chapter_id}")
async def get_chapter(
    project_id: str,
    outline_id: str,
    chapter_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    chapter = await review_service.get_chapter(db, outline_id, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

    return ok(ChapterDetail(
        chapter_id=chapter.id,
        chapter_index=chapter.chapter_index,
        title=chapter.title,
        status=chapter.status,
        iteration_count=chapter.iteration_count,
        completed_at=chapter.completed_at,
        content=chapter.content,
        citations=chapter.citations,
        review_history=chapter.review_history,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    ))


# =============================================================================
# 修改章节内容（FR-022）
# =============================================================================

@router.patch("/outlines/{outline_id}/chapters/{chapter_id}")
async def update_chapter(
    project_id: str,
    outline_id: str,
    chapter_id: str,
    body: UpdateChapterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    chapter = await review_service.get_chapter(db, outline_id, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

    chapter = await review_service.update_chapter(
        db=db,
        chapter=chapter,
        content=body.content,
        citations=body.citations,
    )

    return ok(ChapterDetail(
        chapter_id=chapter.id,
        chapter_index=chapter.chapter_index,
        title=chapter.title,
        status=chapter.status,
        iteration_count=chapter.iteration_count,
        completed_at=chapter.completed_at,
        content=chapter.content,
        citations=chapter.citations,
        review_history=chapter.review_history,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    ))


# =============================================================================
# 触发章节自动审查（FR-022）
# =============================================================================

@router.post("/outlines/{outline_id}/chapters/{chapter_id}/review", status_code=status.HTTP_202_ACCEPTED)
async def trigger_chapter_review(
    project_id: str,
    outline_id: str,
    chapter_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动触发单章节审查，审查完成后通过 SSE 推送结果。"""
    outline = await review_service.get_outline(db, project_id, outline_id, current_user.id)
    if outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    chapter = await review_service.get_chapter(db, outline_id, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

    chapter = await review_service.trigger_chapter_review(db, project_id, current_user.id, chapter)

    outline_data = outline.outline or {}
    review_title = outline_data.get("title", project_id)

    # 注意：BackgroundTask 必须使用独立 AsyncSession（不能传 HTTP 请求的 db）
    # _run_chapter_review 内部自行创建 AsyncSession
    background_tasks.add_task(
        _run_chapter_review,
        current_user.id,
        project_id,
        chapter.id,
        review_title,
        (chapter.iteration_count or 0) + 1,
    )

    return ok(TriggerChapterReviewResponse(
        chapter_id=chapter.id,
        status=chapter.status,
        message="自动审查已启动",
    ))


# =============================================================================
# 汇总综述文章（FR-023）
# =============================================================================

@router.post("/outlines/{outline_id}/compile", status_code=status.HTTP_202_ACCEPTED)
async def compile_outline(
    project_id: str,
    outline_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await review_service.compile_outline(
        db=db,
        project_id=project_id,
        outline_id=outline_id,
        user_id=current_user.id,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="综述架构不存在或尚未确认",
        )

    background_tasks.add_task(
        run_stage,
        project_id,
        current_user.id,
        5,
        record.id,
    )

    return ok(CompileResponse(
        task_id=record.id,
        message="正在汇总综述文章...",
    ))


# =============================================================================
# 导出综述文章（FR-023~024）
# =============================================================================

@router.get("/outlines/{outline_id}/export")
async def export_outline(
    project_id: str,
    outline_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|pdf|docx)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # PDF / DOCX 尚未实现，先行返回 501
    if format in ("pdf", "docx"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"{format.upper()} 导出尚未实现，请使用 markdown 格式",
        )

    result = await review_service.export_outline(
        db=db,
        project_id=project_id,
        outline_id=outline_id,
        user_id=current_user.id,
        fmt=format,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="综述架构不存在")

    content_bytes, media_type = result
    filename = f"review_{outline_id}.md"

    return StreamingResponse(
        iter([content_bytes]),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# =============================================================================
# 综述进度 SSE 流（FR-020~024）
# =============================================================================

@router.get("/stream")
async def review_stream(
    project_id: str,
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    综述流程进度 SSE 流。

    客户端通过 URL 参数 ?token=<JWT> 认证（EventSource 不支持自定义请求头）。
    Agent 向 get_sse_queue(project_id) 写入事件，此端点消费并推送给客户端。

    SSE 事件类型（见 api.md §7）：
      stage_start / stage_progress / stage_pause / stage_error / pipeline_complete
      chapter_writing / chapter_reviewing / chapter_complete / review_text_delta
    """
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的 token",
        )

    async def event_generator():
        queue = get_sse_queue(project_id)
        yield f"event: connected\ndata: {json.dumps({'project_id': project_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
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
            "X-Accel-Buffering": "no",
        },
    )
