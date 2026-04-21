"""
ORM 模型 — 深度研究模式层（tables 8-9）

对应 schema.sql：
  Table 8: research_dialogues — 深度研究对话会话（每课题可有多个）
  Table 9: dialogue_turns     — 对话轮次（每行 = 用户输入 + Agent 回复）

深度研究对话不改变 projects.status，对话期间 status 保持 idle。
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ResearchDialogue(Base):
    """
    深度研究对话会话表（research_dialogues）

    一个课题可包含多个对话会话，具体轮次存储在 dialogue_turns。
    summary 为 Agent 生成的 AgentSummary JSON 字符串（FR-028），
    由 API 层负责序列化/反序列化，DB 层存储为 TEXT。
    """

    __tablename__ = "research_dialogues"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','archived')",
            name="chk_research_dialogues_status",
        ),
    )

    id:         Mapped[str] = mapped_column(String(50), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title:      Mapped[str | None] = mapped_column(String(255))   # 用户自定义或首轮自动生成
    status:     Mapped[str]        = mapped_column(String(20), nullable=False, default="active")
    turn_count: Mapped[int]        = mapped_column(Integer,    nullable=False, default=0)
    # JSON 字符串，结构为 AgentSummary（progress/key_findings/pending_issues/next_steps）
    summary:    Mapped[str | None] = mapped_column(Text)
    tags:       Mapped[list | None] = mapped_column(JSONB)   # 用户标签列表（JSON 数组）

    created_at:     Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:     Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        back_populates="dialogues", lazy="noload"
    )
    turns: Mapped[list["DialogueTurn"]] = relationship(
        back_populates="dialogue", cascade="all, delete-orphan", lazy="noload"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(  # type: ignore[name-defined]
        back_populates="dialogue", lazy="noload"
    )


class DialogueTurn(Base):
    """
    对话轮次表（dialogue_turns）

    每行 = 用户发言一次 + Agent 回复一次（一轮）。
    turn_index 从 1 开始自增，UNIQUE (dialogue_id, turn_index) 保证轮次顺序可还原。
    sub_mode 决定注入不同的 system prompt 引导 LLM 风格。

    project_id 冗余存储：允许直接按课题查询轮次，避免 JOIN research_dialogues。
    """

    __tablename__ = "dialogue_turns"
    __table_args__ = (
        UniqueConstraint("dialogue_id", "turn_index", name="uq_dialogue_turns_index"),
        CheckConstraint(
            "sub_mode IN ('theory','technical','experiment')",
            name="chk_dialogue_turns_sub_mode",
        ),
    )

    id:          Mapped[str] = mapped_column(String(50), primary_key=True)
    dialogue_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("research_dialogues.id", ondelete="CASCADE"), nullable=False
    )
    # 冗余 project_id，便于直接按课题查询，无需 JOIN
    project_id:  Mapped[str] = mapped_column(
        String(50), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)   # 会话内从 1 开始
    sub_mode:   Mapped[str] = mapped_column(String(20), nullable=False) # theory/technical/experiment

    user_content:      Mapped[str]       = mapped_column(Text, nullable=False)
    assistant_content: Mapped[str]       = mapped_column(Text, nullable=False)
    # Agent 回复引用的论文 ID 列表（JSON 数组，用于前端高亮引用）
    referenced_papers: Mapped[list | None] = mapped_column(JSONB)
    # Graph-RAG 扩展命中的知识图谱节点 ID 列表
    graph_nodes_used:  Mapped[list | None] = mapped_column(JSONB)
    # token 用量（用于 LLM 成本追踪，允许为 NULL）
    input_tokens:  Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dialogue: Mapped["ResearchDialogue"] = relationship(
        back_populates="turns", lazy="noload"
    )
