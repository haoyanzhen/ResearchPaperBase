"""
ORM 模型 — 主题综述模式层（tables 10-11）

对应 schema.sql：
  Table 10: review_outlines  — 综述架构版本，status=confirmed 后方可进入章节撰写
  Table 11: review_chapters  — 综述章节，每章独立追踪撰写状态和审查迭代历史
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
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


class ReviewOutline(Base):
    """
    综述架构版本表（review_outlines）

    每次发起新综述流程生成一条记录，version 在同一课题内自增。
    topic_expansion：阶段 1 产出，LLM 扩写后经用户确认的课题描述。
    outline：阶段 2 产出，JSONB 结构含 title / abstract_hint / sections 数组。
    status 流转：draft → confirmed → archived（confirmed 后章节撰写才可开始）。
    """

    __tablename__ = "review_outlines"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_review_outlines_version"),
        CheckConstraint(
            "status IN ('draft','confirmed','archived')",
            name="chk_review_outlines_status",
        ),
    )

    id:         Mapped[str] = mapped_column(String(50), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version:         Mapped[int]            = mapped_column(Integer, nullable=False, default=1)
    topic_expansion: Mapped[str | None]     = mapped_column(Text)
    # JSONB 结构：ReviewOutlineContent（title / abstract_hint / sections[]）
    outline:         Mapped[dict | None]    = mapped_column(JSONB)
    status:          Mapped[str]            = mapped_column(String(20), nullable=False, default="draft")
    confirmed_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:      Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:      Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        back_populates="review_outlines", lazy="noload"
    )
    chapters: Mapped[list["ReviewChapter"]] = relationship(
        back_populates="outline", cascade="all, delete-orphan", lazy="noload"
    )


class ReviewChapter(Base):
    """
    综述章节表（review_chapters）

    chapter_index 与 review_outlines.outline.sections[].index 对应。
    content 为章节正文（Markdown 格式），NULL 表示尚未生成。
    citations：JSONB 数组，元素含 paper_id / citation_key / format_apa / context。
    review_history：JSONB 数组，记录每次自动审查的 issues / suggestions / accepted。

    project_id 冗余存储：允许直接按课题查询章节，避免 JOIN review_outlines。
    """

    __tablename__ = "review_chapters"
    __table_args__ = (
        UniqueConstraint("outline_id", "chapter_index", name="uq_review_chapters_index"),
        CheckConstraint(
            "status IN ('pending','writing','reviewing','completed')",
            name="chk_review_chapters_status",
        ),
    )

    id:         Mapped[str] = mapped_column(String(50), primary_key=True)
    outline_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("review_outlines.id", ondelete="CASCADE"), nullable=False
    )
    # 冗余 project_id，便于直接按课题查询，无需 JOIN
    project_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.id",        ondelete="CASCADE"), nullable=False
    )
    chapter_index:   Mapped[int]            = mapped_column(SmallInteger, nullable=False)
    title:           Mapped[str]            = mapped_column(String(255),  nullable=False)
    content:         Mapped[str | None]     = mapped_column(Text)         # Markdown 正文
    # JSONB 数组：ChapterCitation[]（paper_id / citation_key / format_apa / context）
    citations:       Mapped[list | None]    = mapped_column(JSONB)
    iteration_count: Mapped[int]            = mapped_column(SmallInteger, nullable=False, default=0)
    # JSONB 数组：ReviewIteration[]（iteration / issues / suggestions / accepted / revised_at）
    review_history:  Mapped[list | None]    = mapped_column(JSONB)
    status:          Mapped[str]            = mapped_column(String(20), nullable=False, default="pending")
    completed_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:      Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:      Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    outline: Mapped["ReviewOutline"] = relationship(back_populates="chapters", lazy="noload")
