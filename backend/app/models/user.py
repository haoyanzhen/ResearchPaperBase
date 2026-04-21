"""
ORM 模型 — 用户层（tables 1-2）

对应 schema.sql：
  Table 1: users        — 系统用户基本信息
  Table 2: user_configs — Key-Value 用户配置（LLM/数据库/邮件等）
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    """
    用户表（users）

    全局唯一：username / email 各有 UNIQUE 约束。
    级联删除：删除用户时 user_configs / projects 一并删除（ON DELETE CASCADE）。
    """

    __tablename__ = "users"

    id:            Mapped[str]            = mapped_column(String(50),  primary_key=True)
    username:      Mapped[str]            = mapped_column(String(50),  unique=True, nullable=False)
    email:         Mapped[str]            = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str]            = mapped_column(String(255), nullable=False)
    created_at:    Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:    Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── 关联 ──────────────────────────────────────────────────────────────────
    configs:  Mapped[list["UserConfig"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    projects: Mapped[list["Project"]] = relationship(  # type: ignore[name-defined]
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )


class UserConfig(Base):
    """
    用户配置表（user_configs）

    Key-Value 结构，每行一个配置项。
    同一用户下 config_name 唯一（UNIQUE (user_id, config_name)）。

    config_name 命名约定（见 config_service.py docstring）：
      llm.provider.{provider}.url / api_key / default_model / ...
      database.{db_name}.enabled / api_key / rate_limit
      email.smtp.host / port / sender_email / sender_password
      email.recipients          → JSON 数组字符串
    """

    __tablename__ = "user_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "config_name", name="uq_user_configs_user_config"),
    )

    id:                Mapped[str]      = mapped_column(String(50),  primary_key=True)
    user_id:           Mapped[str]      = mapped_column(
        String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    config_name:       Mapped[str]      = mapped_column(String(100), nullable=False)
    config_value:      Mapped[str]      = mapped_column(Text,        nullable=False)
    # 系统内置默认值标记；用户修改后仍保留此标记，仅供参考
    is_system_default: Mapped[bool]     = mapped_column(Boolean,     nullable=False, default=False)
    created_at:        Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at:        Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="configs", lazy="noload")
