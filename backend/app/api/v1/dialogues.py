"""
HTTP 路由 — 深度研究模式（FR-025~028）

端点：
  GET    /projects/{project_id}/dialogues                            获取对话列表
  POST   /projects/{project_id}/dialogues                            新建对话会话
  GET    /projects/{project_id}/dialogues/{dialogue_id}              获取会话详情
  PATCH  /projects/{project_id}/dialogues/{dialogue_id}              更新会话元数据
  DELETE /projects/{project_id}/dialogues/{dialogue_id}              删除对话会话
  GET    /projects/{project_id}/dialogues/{dialogue_id}/turns        获取对话历史（分页）
  POST   /projects/{project_id}/dialogues/{dialogue_id}/turns        发送消息（SSE 流）
  POST   /projects/{project_id}/dialogues/{dialogue_id}/summarize    生成摘要（FR-028）
  GET    /projects/{project_id}/graph                                获取知识图谱（FR-025）
  POST   /projects/{project_id}/graph/rebuild                        重建知识图谱（FR-025）
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deep_research import (
    build_graph_data,
    generate_summary,
    get_graphml,
    rebuild_graph_stub,
    run_dialogue_turn,
)
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import ok
from app.schemas.dialogue import (
    CreateDialogueRequest,
    DeleteDialogueResponse,
    DialogueDetail,
    DialogueSummaryItem,
    DialogueTurnItem,
    GraphDataResponse,
    GraphEdge,
    GraphNode,
    GraphStats,
    RebuildGraphResponse,
    SendMessageRequest,
    SummarizeResponse,
    UpdateDialogueRequest,
)
from app.services import dialogue_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}",
    tags=["深度研究模式"],
)


# =============================================================================
# 辅助：派生 sub_mode（不存在于 dialogue 本身，需从 turns 计算）
# =============================================================================

async def _get_sub_mode(db: AsyncSession, dialogue_id: str) -> str:
    return await dialogue_service._derive_sub_mode(db, dialogue_id)


# =============================================================================
# 对话会话 CRUD
# =============================================================================

@router.get("/dialogues")
async def list_dialogues(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await dialogue_service.list_dialogues(db, project_id, current_user.id)
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    return ok([
        DialogueSummaryItem(
            dialogue_id=it["dialogue"].id,
            title=it["dialogue"].title,
            sub_mode=it["sub_mode"],
            status=it["dialogue"].status,
            turn_count=it["dialogue"].turn_count,
            summary=it["summary_preview"],
            tags=it["dialogue"].tags,
            created_at=it["dialogue"].created_at,
            last_active_at=it["dialogue"].last_active_at,
        )
        for it in items
    ])


@router.post("/dialogues", status_code=status.HTTP_201_CREATED)
async def create_dialogue(
    project_id: str,
    body: CreateDialogueRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dialogue = await dialogue_service.create_dialogue(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        title=body.title,
        init_sub_mode=body.sub_mode,
    )
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    sub_mode = await _get_sub_mode(db, dialogue.id)
    return ok(DialogueDetail(
        dialogue_id=dialogue.id,
        title=dialogue.title,
        sub_mode=sub_mode,
        status=dialogue.status,
        turn_count=dialogue.turn_count,
        summary=None,
        tags=dialogue.tags,
        created_at=dialogue.created_at,
        last_active_at=dialogue.last_active_at,
        updated_at=dialogue.updated_at,
    ))


@router.get("/dialogues/{dialogue_id}")
async def get_dialogue(
    project_id: str,
    dialogue_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dialogue = await dialogue_service.get_dialogue(db, project_id, dialogue_id, current_user.id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")

    sub_mode = await _get_sub_mode(db, dialogue_id)
    summary_dict = dialogue_service._parse_summary(dialogue.summary)

    return ok(DialogueDetail(
        dialogue_id=dialogue.id,
        title=dialogue.title,
        sub_mode=sub_mode,
        status=dialogue.status,
        turn_count=dialogue.turn_count,
        summary=summary_dict,
        tags=dialogue.tags,
        created_at=dialogue.created_at,
        last_active_at=dialogue.last_active_at,
        updated_at=dialogue.updated_at,
    ))


@router.patch("/dialogues/{dialogue_id}")
async def update_dialogue(
    project_id: str,
    dialogue_id: str,
    body: UpdateDialogueRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dialogue = await dialogue_service.get_dialogue(db, project_id, dialogue_id, current_user.id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")

    dialogue = await dialogue_service.update_dialogue(
        db=db,
        dialogue=dialogue,
        title=body.title,
        tags=body.tags,
        new_status=body.status,
    )

    sub_mode = await _get_sub_mode(db, dialogue_id)
    summary_dict = dialogue_service._parse_summary(dialogue.summary)

    return ok(DialogueDetail(
        dialogue_id=dialogue.id,
        title=dialogue.title,
        sub_mode=sub_mode,
        status=dialogue.status,
        turn_count=dialogue.turn_count,
        summary=summary_dict,
        tags=dialogue.tags,
        created_at=dialogue.created_at,
        last_active_at=dialogue.last_active_at,
        updated_at=dialogue.updated_at,
    ))


@router.delete("/dialogues/{dialogue_id}")
async def delete_dialogue(
    project_id: str,
    dialogue_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dialogue = await dialogue_service.get_dialogue(db, project_id, dialogue_id, current_user.id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")

    await dialogue_service.delete_dialogue(db, dialogue)
    return ok(DeleteDialogueResponse(message="deleted"))


# =============================================================================
# 对话轮次：获取历史（FR-027）
# =============================================================================

@router.get("/dialogues/{dialogue_id}/turns")
async def get_turns(
    project_id: str,
    dialogue_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取完整对话历史，支持 offset/limit 分页（FR-027）。"""
    dialogue = await dialogue_service.get_dialogue(db, project_id, dialogue_id, current_user.id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")

    turns = await dialogue_service.list_turns(db, dialogue_id, offset=offset, limit=limit)

    return ok([
        DialogueTurnItem(
            turn_id=t.id,
            turn_index=t.turn_index,
            user_content=t.user_content,
            assistant_content=t.assistant_content,
            sub_mode_before=t.sub_mode,
            sub_mode_after=t.sub_mode,
            referenced_papers=t.referenced_papers,
            input_tokens=t.input_tokens,
            output_tokens=t.output_tokens,
            created_at=t.created_at,
        )
        for t in turns
    ])


# =============================================================================
# 发送消息（SSE 流）（FR-026）
# =============================================================================

@router.post("/dialogues/{dialogue_id}/turns")
async def send_message(
    project_id: str,
    dialogue_id: str,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    发送消息并获取 SSE 流式回复（FR-026）。

    返回 text/event-stream，事件类型：
      turn_start / text_delta / turn_complete / error
    """
    dialogue = await dialogue_service.get_dialogue(db, project_id, dialogue_id, current_user.id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")
    if dialogue.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该对话已归档，无法发送消息",
        )

    sub_mode = body.sub_mode if body.sub_mode in ("theory", "technical", "experiment") else "technical"

    # StreamingResponse：generator 在 HTTP 请求期间保持 db session 存活
    async def event_generator():
        async for event_str in run_dialogue_turn(
            db=db,
            user_id=current_user.id,
            project_id=project_id,
            dialogue=dialogue,
            user_content=body.user_content,
            sub_mode=sub_mode,
        ):
            yield event_str

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# 生成摘要（FR-028）
# =============================================================================

@router.post("/dialogues/{dialogue_id}/summarize")
async def summarize_dialogue(
    project_id: str,
    dialogue_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成/更新对话研究进展摘要（FR-028）。"""
    dialogue = await dialogue_service.get_dialogue(db, project_id, dialogue_id, current_user.id)
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话会话不存在")

    summary_data = await generate_summary(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        dialogue=dialogue,
    )

    return ok(SummarizeResponse(
        dialogue_id=dialogue_id,
        summary=summary_data,
    ))


# =============================================================================
# 知识图谱（FR-025）
# =============================================================================

@router.get("/graph")
async def get_graph(
    project_id: str,
    format: str = Query(default="json", pattern="^(json|graphml)$"),
    node_types: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取课题知识图谱数据（FR-025）。

    format=json  → 返回 GraphDataResponse（JSON）
    format=graphml → 返回 GraphML XML 文件流
    node_types=paper,keyword → 只返回指定类型的节点（逗号分隔）
    """
    from app.services.project_service import get_project
    project = await get_project(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    types_filter = [t.strip() for t in node_types.split(",")] if node_types else None

    if format == "graphml":
        graphml_str = await get_graphml(db, project_id)
        return StreamingResponse(
            iter([graphml_str.encode("utf-8")]),
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="graph_{project_id}.graphml"',
            },
        )

    graph_data = await build_graph_data(db, project_id, node_types=types_filter)
    return ok(GraphDataResponse(
        nodes=[GraphNode(**n) for n in graph_data["nodes"]],
        edges=[GraphEdge(**e) for e in graph_data["edges"]],
        stats=GraphStats(**graph_data["stats"]),
    ))


@router.post("/graph/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_graph(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发知识图谱重建任务（FR-025，当前为存根）。"""
    from app.services.project_service import get_project
    project = await get_project(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    result = await rebuild_graph_stub(project_id, db=db)
    return ok(RebuildGraphResponse(**result))
