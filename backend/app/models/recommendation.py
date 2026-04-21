"""
ORM 模型 — 推荐模块层（table 12）

对应 schema.sql：
  Table 12: recommendations — 用户发表研究观点和洞察（基础层，不依赖特定模式）

功能约束（FR-011）：
  - 单向展示，禁止评论 / 回复 / 讨论
  - is_visible=False 时前端不展示（软删除机制）
  - contact_info 只允许存储用户名或邮箱，禁止其他联系方式
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Recommendation(Base):
    """
    推荐内容表（recommendations）

    dialogue_id 可为空，支持独立发布（不绑定特定对话）。
    删除关联对话 → dialogue_id 置为 NULL（ON DELETE SET NULL），推荐内容保留。
    删除用户 → ON DELETE CASCADE，用户的所有推荐一并删除。
    """

    __tablename__ = "recommendations"

    id:           Mapped[str]       = mapped_column(String(50),  primary_key=True)
    user_id:      Mapped[str]       = mapped_column(
        String(50), ForeignKey("users.id",               ondelete="CASCADE"),   nullable=False
    )
    # 可为空：支持独立发布；关联对话被删除时置 NULL
    dialogue_id:  Mapped[str | None] = mapped_column(
        String(50), ForeignKey("research_dialogues.id",  ondelete="SET NULL"),  nullable=True
    )
    # insight / conclusion / experiment_design 等（扩展类型允许自定义字符串）
    content_type: Mapped[str]       = mapped_column(String(50),  nullable=False)
    title:        Mapped[str]       = mapped_column(String(255), nullable=False)
    content:      Mapped[str]       = mapped_column(Text,        nullable=False)
    tags:         Mapped[list | None] = mapped_column(JSONB)     # 标签列表（JSON 数组）
    # 仅允许用户名或邮箱，用于私下联系
    contact_info: Mapped[str | None] = mapped_column(String(255))
    view_count:   Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    like_count:   Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    # 内容审核开关：False = 软删除，前端不展示
    is_visible:   Mapped[bool]      = mapped_column(Boolean, nullable=False, default=True)
    created_at:   Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:   Mapped[datetime]  = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    dialogue: Mapped["ResearchDialogue | None"] = relationship(  # type: ignore[name-defined]
        back_populates="recommendations", lazy="noload"
    )
