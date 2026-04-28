"""
Pydantic 响应 Schema — 健康检查与诊断（qa_design.md §5-6）

端点：
  GET /api/v1/health                       ShallowHealthResponse
  GET /api/v1/health/db                    DbHealthResponse
  GET /api/v1/health/deep                  DeepHealthResponse
  GET /api/v1/health/pipeline/{project_id} PipelineHealthResponse
  GET /api/v1/projects/{id}/inspect        InspectResponse
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, Field, model_validator


# =============================================================================
# 通用检查结果
# =============================================================================

class CheckResult(BaseModel):
    """单个依赖项的探测结果。"""
    status: str                  # ok / error / degraded / not_configured
    latency_ms: float | None = None
    message: str | None = None
    code: str | None = None      # AppErrorCode.value，仅 error 时填写
    suggestion: str | None = None
    last_success_at: str | None = None


# =============================================================================
# GET /health（浅层探针）
# =============================================================================

class ShallowHealthResponse(BaseModel):
    status: str          # ok
    version: str
    timestamp: str       # ISO UTC


# =============================================================================
# GET /health/db（数据库连通性探针）
# =============================================================================

class DbChecks(BaseModel):
    postgresql: CheckResult


class DbHealthResponse(BaseModel):
    status: str          # ok / error
    checks: DbChecks


# =============================================================================
# GET /health/deep（全依赖探针）
# =============================================================================

class DeepChecks(BaseModel):
    llm_primary: CheckResult
    llm_fallback: CheckResult
    arxiv: CheckResult
    openalex: CheckResult
    semantic_scholar: CheckResult
    ads: CheckResult
    smtp: CheckResult


class DeepHealthResponse(BaseModel):
    status: str          # ok / degraded / error
    checks: DeepChecks
    summary: str         # 人类可读的一句话摘要


# =============================================================================
# GET /health/pipeline/{project_id}（流水线状态快照）
# =============================================================================

class StageSnapshot(BaseModel):
    """单个活跃阶段记录的快照。"""
    stage_record_id: str
    stage: int
    mode: str
    status: str          # running / paused / completed / failed
    started_at: str
    elapsed_seconds: float | None = None
    result_preview: dict[str, Any] | None = None   # result 的前几个字段
    error_preview: str | None = None               # error 的前200字符
    pending_user_action: str | None = None         # 当 status=paused 时填写


class PipelineHealthResponse(BaseModel):
    project_id: str
    project_status: str
    mode: str
    active_stages: list[StageSnapshot]
    last_error: dict[str, Any] | None = None       # 最近一次 failed 的 ErrorEnvelope


# =============================================================================
# GET /projects/{project_id}/inspect（诊断快照）
# =============================================================================

class StageHistoryItem(BaseModel):
    """诊断快照中的单条阶段历史。"""
    stage_record_id: str
    stage: int
    mode: str
    status: str
    started_at: str
    completed_at: str | None = None
    failed_at: str | None = None
    elapsed_seconds: float | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None   # ErrorEnvelope dict，或 {"raw": str} 若格式不兼容


class KeywordSummary(BaseModel):
    total: int
    search_done: int = Field(validation_alias=AliasChoices("search_done", "selected"))
    pending: int

    @model_validator(mode="before")
    @classmethod
    def fill_pending(cls, data: Any) -> Any:
        if isinstance(data, dict) and "pending" not in data:
            total = int(data.get("total", 0) or 0)
            search_done = int(data.get("search_done", data.get("selected", 0)) or 0)
            data = {**data, "pending": max(total - search_done, 0)}
        return data


class PaperSummary(BaseModel):
    total: int = Field(validation_alias=AliasChoices("total", "total_in_db"))
    valid: int
    invalid: int
    downloaded: int = Field(validation_alias=AliasChoices("downloaded", "download_success"))
    analyzed: int = Field(validation_alias=AliasChoices("analyzed", "ai_analyzed"))

    @model_validator(mode="before")
    @classmethod
    def fill_invalid(cls, data: Any) -> Any:
        if isinstance(data, dict) and "invalid" not in data:
            total = int(data.get("total", data.get("total_in_db", 0)) or 0)
            valid = int(data.get("valid", 0) or 0)
            data = {**data, "invalid": max(total - valid, 0)}
        return data


class ConfigStatus(BaseModel):
    llm_configured: bool
    llm_active_provider: str | None = Field(
        validation_alias=AliasChoices("llm_active_provider", "llm_provider")
    )
    paper_db_sources: list[str] = Field(default_factory=list)
    smtp_configured: bool = Field(
        validation_alias=AliasChoices("smtp_configured", "email_configured")
    )

    @model_validator(mode="before")
    @classmethod
    def fill_sources(cls, data: Any) -> Any:
        if isinstance(data, dict) and "paper_db_sources" not in data:
            sources: list[str] = []
            if data.get("arxiv_configured"):
                sources.append("arxiv")
            if data.get("openalex_configured"):
                sources.append("openalex")
            if data.get("semantic_scholar_configured"):
                sources.append("semantic_scholar")
            if data.get("ads_configured"):
                sources.append("ads")
            data = {**data, "paper_db_sources": sources}
        return data


class InspectResponse(BaseModel):
    snapshot_at: str
    project: dict[str, Any]
    stage_history: list[StageHistoryItem]
    keyword_summary: KeywordSummary
    paper_summary: PaperSummary
    config_status: ConfigStatus
    recommendations: list[str]
