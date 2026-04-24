"""
Pydantic 请求/响应 Schema — 深度研究模式（FR-025~028）

对齐：docs/api.md §6
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


# =============================================================================
# 对话会话（research_dialogues）
# =============================================================================

class DialogueSummaryItem(BaseModel):
    """对话会话列表条目（GET /dialogues 响应元素）"""
    dialogue_id: str
    title: str | None
    sub_mode: str                    # 派生自最近一轮 sub_mode，默认 "technical"
    status: str
    turn_count: int
    summary: str | None             # 纯文本摘要（AgentSummary.progress 或原始 TEXT）
    tags: list[str] | None
    created_at: datetime
    last_active_at: datetime


class DialogueDetail(DialogueSummaryItem):
    """对话会话详情（GET /dialogues/{id} 响应）"""
    summary: dict | None            # 完整 AgentSummary JSON（覆盖父类的 str | None）
    updated_at: datetime


class CreateDialogueRequest(BaseModel):
    title: str | None = None
    sub_mode: str | None = None     # 仅作为首轮默认子模式提示，不存储于 dialogue 本身


class UpdateDialogueRequest(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
    status: str | None = None       # active → archived
    sub_mode: str | None = None     # theory / technical / experiment（不存储于 dialogue，仅透传给前端）


class DeleteDialogueResponse(BaseModel):
    message: str


# =============================================================================
# 对话轮次（dialogue_turns）
# =============================================================================

class DialogueTurnItem(BaseModel):
    """单轮对话数据（GET /turns 响应元素，POST /turns SSE turn_complete 数据）"""
    turn_id: str
    turn_index: int
    user_content: str
    assistant_content: str
    sub_mode_before: str
    sub_mode_after: str
    referenced_papers: list[str] | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime


class SendMessageRequest(BaseModel):
    user_content: str
    sub_mode: str = "technical"     # theory / technical / experiment


# =============================================================================
# FR-028 摘要生成
# =============================================================================

class SummarizeResponse(BaseModel):
    dialogue_id: str
    summary: dict                   # AgentSummary JSON


# =============================================================================
# FR-025 知识图谱
# =============================================================================

class GraphNode(BaseModel):
    id: str
    type: str                       # paper / author / keyword / venue
    label: str
    score: float | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str                       # authored_by / has_keyword / in_venue / ...
    weight: float = 1.0


class GraphStats(BaseModel):
    node_count: int
    edge_count: int
    paper_count: int | None = None
    author_count: int | None = None
    venue_count: int | None = None
    keyword_count: int | None = None


class GraphDataResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: GraphStats


class RebuildGraphResponse(BaseModel):
    task_id: str
    message: str
