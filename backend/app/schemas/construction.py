"""
Pydantic schemas — 构建模式（FR-012~019）

对应 api.md 第 4 节。所有请求/响应字段与 api.md 保持严格一致。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# 启动构建 (POST /construction/start)
# =============================================================================

class StartConstructionRequest(BaseModel):
    databases: list[str] = Field(
        default=["arxiv", "openalex", "semantic_scholar"],
        description="参与检索的数据库列表",
    )
    score_threshold: int = Field(
        default=7, ge=1, le=10,
        description="有效论文评分阈值，总分≥此值视为 is_valid=True",
    )


class StartConstructionResponse(BaseModel):
    task_id: str
    project_id: str
    stage: int
    status: str
    message: str


# =============================================================================
# 构建状态查询 (GET /construction/status)
# =============================================================================

class ConstructionStatusResponse(BaseModel):
    current_stage: int | None
    stage_name: str | None
    status: str                          # idle / running / paused / error
    stage_result: dict[str, Any] | None
    started_at: datetime | None


# =============================================================================
# 检索词管理 (GET / PATCH /construction/keywords)
# =============================================================================

class KeywordItemResponse(BaseModel):
    keyword_id: str
    search_word: str
    boolean_expressions: dict[str, str] | None
    is_selected: bool
    is_searched: bool
    searched_papers_total: int


class KeywordUpdateItem(BaseModel):
    keyword_id: str | None = None        # None 表示新增；有值表示更新已有
    search_word: str
    boolean_expressions: dict[str, str] | None = None
    is_selected: bool = True


class UpdateKeywordsRequest(BaseModel):
    keywords: list[KeywordUpdateItem]


# =============================================================================
# 阶段用户操作 (POST /construction/stages/{stage}/action)
# =============================================================================

class StageActionRequest(BaseModel):
    action: str = Field(
        description="confirm=确认继续 / retry=重新执行 / skip=跳过",
    )
    # 各阶段可选修改内容（结构见 api.md §4 阶段对应的 modifications）
    modifications: dict[str, Any] | None = None


class StageActionResponse(BaseModel):
    stage: int
    action: str
    next_stage: int | None               # None 表示已是最后阶段（stage 7 完成）
    status: str
    message: str
