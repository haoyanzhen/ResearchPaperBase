"""
Pydantic 请求/响应 Schema — 综述模式（FR-020~024）

对齐：docs/api.md §7
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


# =============================================================================
# 启动综述流程
# =============================================================================

class StartReviewRequest(BaseModel):
    topic_hint: str | None = None   # 用户对综述的额外说明（可选）


class StartReviewResponse(BaseModel):
    task_id: str
    outline_id: str
    stage: int
    status: str


# =============================================================================
# 综述架构（review_outlines）
# =============================================================================

class OutlineSummary(BaseModel):
    outline_id: str
    version: int
    status: str
    confirmed_at: datetime | None
    created_at: datetime


class OutlineDetail(OutlineSummary):
    topic_expansion: str | None
    outline: dict | None          # ReviewOutlineContent: title / abstract_hint / sections[]


class UpdateOutlineRequest(BaseModel):
    topic_expansion: str | None = None
    outline: dict | None = None   # 完整替换 outline JSONB


class ConfirmOutlineResponse(BaseModel):
    outline_id: str
    status: str
    confirmed_at: datetime
    message: str


# =============================================================================
# 综述章节（review_chapters）
# =============================================================================

class ChapterSummary(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str
    status: str
    iteration_count: int
    completed_at: datetime | None


class ChapterDetail(ChapterSummary):
    content: str | None
    citations: list[dict] | None    # ChapterCitation[]
    review_history: list[dict] | None
    created_at: datetime
    updated_at: datetime


class UpdateChapterRequest(BaseModel):
    content: str | None = None
    citations: list[dict] | None = None


class TriggerChapterReviewResponse(BaseModel):
    chapter_id: str
    status: str
    message: str


# =============================================================================
# 综述汇总与导出
# =============================================================================

class CompileResponse(BaseModel):
    task_id: str
    message: str


class ReviewStatusResponse(BaseModel):
    """综述模式当前状态（对应 GET /review/status）"""
    project_id: str
    current_stage: int | None
    stage_name: str | None
    stage_status: str | None
    outline_id: str | None
    outline_status: str | None
    total_chapters: int
    completed_chapters: int
