"""
ORM 模型 — 研究主题层（tables 3-4）

对应 schema.sql：
  Table 3: projects  — 核心实体，所有功能以 project_id 为轴心
  Table 4: keywords  — 课题检索词，支持各学术数据库布尔表达式
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# projects.mode 允许值（与 CHECK 约束保持同步）
_VALID_MODES    = ("construction", "deep_research", "review")
# projects.status 允许值（与 CHECK 约束保持同步）
_VALID_STATUSES = ("idle", "running", "paused", "error", "archived")


class Project(Base):
    """
    研究主题表（projects）

    状态机（status）—— 只由构建/综述 Agent 链写入，深度研究对话期间保持 idle：
      idle     → 初始值；任务完成/失败后回归；用户手动取消后
      running  → 启动构建/综述阶段任务；定时调度器触发
      paused   → 构建/综述完成某阶段，等待用户交互
      error    → LLM 重试失败，需用户介入
      archived → 用户主动归档，禁止启动新任务

    current_stage 不在本表存储，通过查询 stage_records 获取最新记录。
    """

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('construction','deep_research','review')",
            name="chk_projects_mode",
        ),
        CheckConstraint(
            "status IN ('idle','running','paused','error','archived')",
            name="chk_projects_status",
        ),
    )

    id:            Mapped[str]            = mapped_column(String(50),  primary_key=True)
    user_id:       Mapped[str]            = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name:          Mapped[str]            = mapped_column(String(255), nullable=False)
    description:   Mapped[str | None]     = mapped_column(Text)
    mode:          Mapped[str]            = mapped_column(String(20),  nullable=False, default="construction")
    status:        Mapped[str]            = mapped_column(String(20),  nullable=False, default="idle")
    total_papers:  Mapped[int]            = mapped_column(Integer,     nullable=False, default=0)
    # valid_papers 为 0 时，前端拦截切换到深度研究/综述模式（FR-005）
    valid_papers:  Mapped[int]            = mapped_column(Integer,     nullable=False, default=0)
    auto_push:     Mapped[bool]           = mapped_column(Boolean,     nullable=False, default=False)
    # push_interval 单位：天，auto_push=True 时有效（FR-010）
    push_interval: Mapped[int | None]     = mapped_column(SmallInteger)
    last_push_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # next_push_at 由定时调度器写入，API 层只读（FR-010）
    next_push_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:    Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:    Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ── 关联（均为 lazy="noload"，按需显式加载）────────────────────────────────
    user:            Mapped["User"] = relationship(  # type: ignore[name-defined]
        back_populates="projects", lazy="noload"
    )
    keywords:        Mapped[list["Keyword"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    stage_records:   Mapped[list["StageRecord"]] = relationship(  # type: ignore[name-defined]
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    paper_relations: Mapped[list["ProjectPaperRelation"]] = relationship(  # type: ignore[name-defined]
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    dialogues:       Mapped[list["ResearchDialogue"]] = relationship(  # type: ignore[name-defined]
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )
    review_outlines: Mapped[list["ReviewOutline"]] = relationship(  # type: ignore[name-defined]
        back_populates="project", cascade="all, delete-orphan", lazy="noload"
    )


class Keyword(Base):
    """
    检索词表（keywords）

    每行一个检索词，支持各学术数据库的差异化布尔表达式。
    is_selected=True 的记录用于 FR-010 定时自动任务。
    is_searched=False 表示该词尚未执行过搜索（新词默认值）。
    """

    __tablename__ = "keywords"

    id:          Mapped[str]      = mapped_column(String(50),  primary_key=True)
    project_id:  Mapped[str]      = mapped_column(
        String(50), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    search_word: Mapped[str]      = mapped_column(String(500), nullable=False)
    # JSONB 结构：{"arxiv": "...", "openalex": "...", "semantic_scholar": "...", "ads": "..."}
    boolean_expressions:              Mapped[dict | None] = mapped_column(JSONB)
    searched_papers_arxiv:            Mapped[int]         = mapped_column(SmallInteger, nullable=False, default=0)
    searched_papers_openalex:         Mapped[int]         = mapped_column(SmallInteger, nullable=False, default=0)
    searched_papers_semanticscholar:  Mapped[int]         = mapped_column(SmallInteger, nullable=False, default=0)
    searched_papers_ads:              Mapped[int]         = mapped_column(SmallInteger, nullable=False, default=0)
    searched_papers_total:            Mapped[int]         = mapped_column(SmallInteger, nullable=False, default=0)
    # False = 新词，尚未执行过任何搜索；搜索后置为 True
    is_searched:  Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    is_selected:  Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at:   Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_search_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(back_populates="keywords", lazy="noload")
