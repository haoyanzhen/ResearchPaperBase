from datetime import datetime

from pydantic import BaseModel


class CreateProjectRequest(BaseModel):
    name: str
    description: str | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    mode: str
    status: str
    total_papers: int
    valid_papers: int
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectSummary):
    description: str | None
    auto_push: bool
    push_interval: int | None
    last_push_at: datetime | None
    next_push_at: datetime | None


class ProjectListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ProjectSummary]


class ModeSwitchRequest(BaseModel):
    target_mode: str
    reason: str | None = None
    running_task_action: str | None = None  # "stay" | "leave_and_cancel"


class ModeSwitchResponse(BaseModel):
    project_id: str
    previous_mode: str
    current_mode: str
    switched_at: datetime


# ── 论文关联 (FR-007) ──────────────────────────────────────────────────────────

class PaperItem(BaseModel):
    paper_id: str
    title: str
    authors: list[str] | None
    pub_date: str | None
    venue: str | None
    abstract: str | None
    total_score: int | None
    reference_score: int | None
    technical_score: int | None
    is_valid: bool
    push_status: bool
    download_status: str
    ai_analysis: dict | None


class PaperDetail(PaperItem):
    """论文完整详情（含 pdf_path、ai_analysis 等全部字段）"""
    doi: str | None
    arxiv_id: str | None
    source: str | None
    pdf_path: str | None
    text_path: str | None
    download_error: str | None
    ai_analysis_status: str
    scoring_reason: str | None
    pushed_at: datetime | None
    retrieved_at: datetime
    created_at: datetime
    updated_at: datetime


class PaperListResponse(BaseModel):
    total: int
    items: list[PaperItem]


class AddPaperRequest(BaseModel):
    doi: str | None = None
    arxiv_id: str | None = None
    pdf_file: str | None = None   # base64，三选一


class AddPaperResponse(BaseModel):
    paper_id: str
    title: str
    status: str
    message: str


class UpdatePaperScoreRequest(BaseModel):
    reference_score: int   # 0-5
    technical_score: int   # 0-5
    scoring_reason: str | None = None


class PaperScoreResponse(BaseModel):
    paper_id: str
    reference_score: int
    technical_score: int
    total_score: int
    is_valid: bool
    scoring_reason: str | None


# ── 数据导出 (FR-009) ──────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    export_type: str          # "excel" | "pdf_zip"
    is_valid: bool | None = None
    push_status: bool | None = None


class ExportResponse(BaseModel):
    task_id: str
    status: str = "pending"
    message: str


# ── 定时任务配置 (FR-010) ──────────────────────────────────────────────────────

class ScheduleConfigRequest(BaseModel):
    auto_push: bool
    push_interval: int | None = None  # 1/3/7/14/30 天


class ScheduleConfigResponse(BaseModel):
    auto_push: bool
    push_interval: int | None
    next_push_at: datetime | None


# ── 任务管理 (FR-008) ──────────────────────────────────────────────────────────

class TaskItem(BaseModel):
    task_id: str         # stage_record.id
    project_id: str
    task_type: str       # "construction" | "review"
    status: str
    stage: int | None
    created_at: datetime
    updated_at: datetime | None = None  # 最近状态变更时间（ended_at / paused_at 等）
    error: str | None = None            # 失败或取消原因


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskItem]


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    message: str | None = None  # 操作附加说明（如失败原因）


# ── 推荐模块 (FR-011) ──────────────────────────────────────────────────────────

class CreateRecommendationRequest(BaseModel):
    content_type: str
    title: str
    content: str
    tags: list[str] | None = None
    contact_info: str | None = None
    dialogue_id: str | None = None


class RecommendationItem(BaseModel):
    recommendation_id: str
    user_id: str
    username: str
    content_type: str
    title: str
    content: str
    tags: list[str] | None
    contact_info: str | None
    view_count: int
    like_count: int
    created_at: datetime


class RecommendationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RecommendationItem]
