"""
ORM 模型 — 论文层（tables 5-6）

对应 schema.sql：
  Table 5: papers                  — 全局共享论文表，每篇只存一份（三路去重）
  Table 6: project_paper_relations — 课题-论文关联，评分/推送状态按课题独立存储

一致性约束（重要，禁止绕过）：
  papers + project_paper_relations 的写入须与 ChromaDB 向量写入在同一事务上下文中执行，
  任意一方失败立即整体回滚，不允许部分成功状态。
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Paper(Base):
    """
    全局论文表（papers）

    去重策略（三路，任一命中即视为重复）：
      - doi     UNIQUE（可为空）
      - arxiv_id UNIQUE（可为空）
      - title   UNIQUE，小写格式存储

    写入须与 ChromaDB 同事务（见模块 docstring）。
    """

    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint(
            "download_status IN ('not_downloaded','success','failed')",
            name="chk_papers_download_status",
        ),
        CheckConstraint(
            "ai_analysis_status IN ('not_analyzed','success','failed')",
            name="chk_papers_ai_analysis_status",
        ),
    )

    id:       Mapped[str]       = mapped_column(String(50), primary_key=True)
    # 三路去重字段（UNIQUE，允许为空）
    doi:      Mapped[str | None] = mapped_column(String(100), unique=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(50),  unique=True)
    # title 存为小写，用于大小写不敏感去重（UNIQUE）
    title:    Mapped[str]        = mapped_column(Text, nullable=False, unique=True)

    authors:      Mapped[list | None]  = mapped_column(JSONB)           # JSON 数组，如 ["Jane Doe"]
    pub_date:     Mapped[date | None]  = mapped_column(Date)
    venue:        Mapped[str | None]   = mapped_column(String(200))
    abstract:     Mapped[str | None]   = mapped_column(Text)
    source:       Mapped[str | None]   = mapped_column(String(50))      # arxiv / openalex / ...
    retrieved_at: Mapped[datetime]     = mapped_column(DateTime(timezone=True), nullable=False)

    # 下载状态：not_downloaded → success / failed
    download_status: Mapped[str]        = mapped_column(String(20), nullable=False, default="not_downloaded")
    pdf_path:        Mapped[str | None] = mapped_column(String(500))
    text_path:       Mapped[str | None] = mapped_column(String(500))
    download_error:  Mapped[str | None] = mapped_column(Text)

    # AI 分析状态：not_analyzed → success / failed（构建模式阶段 5 写入）
    ai_analysis_status: Mapped[str]         = mapped_column(String(20), nullable=False, default="not_analyzed")
    # JSONB 结构：{summary, highlights, relevance_points, technical_methods}
    ai_analysis:        Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project_relations: Mapped[list["ProjectPaperRelation"]] = relationship(
        back_populates="paper", lazy="noload"
    )


class ProjectPaperRelation(Base):
    """
    课题-论文关联表（project_paper_relations）

    多对多关联：同一论文可属于多个课题，评分/推送状态各自独立。
    删除课题 → ON DELETE CASCADE；删除论文 → ON DELETE RESTRICT（保护全局论文）。
    is_valid = (total_score >= 7)，由评分完成后显式置为 True。
    """

    __tablename__ = "project_paper_relations"
    __table_args__ = (
        UniqueConstraint("project_id", "paper_id", name="uq_ppr_project_paper"),
        # 评分范围约束（允许 NULL，表示未评分）
        CheckConstraint(
            "reference_score IS NULL OR (reference_score >= 0 AND reference_score <= 5)",
            name="chk_ppr_reference_score",
        ),
        CheckConstraint(
            "technical_score IS NULL OR (technical_score >= 0 AND technical_score <= 5)",
            name="chk_ppr_technical_score",
        ),
        CheckConstraint(
            "total_score IS NULL OR (total_score >= 0 AND total_score <= 10)",
            name="chk_ppr_total_score",
        ),
    )

    id:         Mapped[str] = mapped_column(String(50), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.id", ondelete="CASCADE"),  nullable=False
    )
    paper_id:   Mapped[str] = mapped_column(
        String(50), ForeignKey("papers.id",   ondelete="RESTRICT"), nullable=False
    )

    # 评分字段（0-5），total_score = reference_score + technical_score
    reference_score: Mapped[int | None] = mapped_column(SmallInteger)
    technical_score: Mapped[int | None] = mapped_column(SmallInteger)
    total_score:     Mapped[int | None] = mapped_column(SmallInteger)
    scoring_reason:  Mapped[str | None] = mapped_column(Text)
    # is_valid=False 时论文不进入邮件推送和 Graph-RAG 检索（FR-007）
    is_valid:    Mapped[bool]            = mapped_column(Boolean, nullable=False, default=False)
    # push_status=True 表示已发送邮件（FR-018）
    push_status: Mapped[bool]            = mapped_column(Boolean, nullable=False, default=False)
    pushed_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:  Mapped[datetime]        = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:  Mapped[datetime]        = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        back_populates="paper_relations", lazy="noload"
    )
    paper: Mapped["Paper"] = relationship(back_populates="project_relations", lazy="noload")
