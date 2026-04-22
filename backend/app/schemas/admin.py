"""
Pydantic Schema — 管理员配置面板（FR-029）
"""

from datetime import datetime

from pydantic import BaseModel


# ── 用户管理 ──────────────────────────────────────────────────────────────────

class AdminUserItem(BaseModel):
    """用户列表条目（不含密码）。"""
    user_id: str
    username: str
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class SetUserActiveRequest(BaseModel):
    is_active: bool


class SetUserAdminRequest(BaseModel):
    is_admin: bool


class ResetPasswordResponse(BaseModel):
    email_sent: bool
    target_email: str
    temp_password: str | None = None   # 仅在邮件发送失败时返回，供管理员手动转告
    email_error: str | None = None


# ── 系统级 LLM 配置 ───────────────────────────────────────────────────────────

class CreateSystemLLMRequest(BaseModel):
    provider: str
    url: str
    api_key: str
    default_model: str
    temperature: float = 0.7
    max_tokens: int = 4096


class UpdateSystemLLMRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None


# ── 系统级数据库配置 ───────────────────────────────────────────────────────────

class UpdateSystemDatabaseRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    rate_limit: int | None = None
    endpoint: str | None = None
