from pydantic import BaseModel

# ── LLM 配置 ──────────────────────────────────────────────────────────────────

class LLMConfig(BaseModel):
    provider: str
    url: str
    models: list[str] = []
    default_model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    is_active: bool = True


class CreateLLMConfigRequest(BaseModel):
    provider: str
    url: str
    api_key: str
    default_model: str
    temperature: float = 0.7
    max_tokens: int = 4096


class UpdateLLMConfigRequest(BaseModel):
    api_key: str | None = None
    default_model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None


class TestLLMResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    model_list: list[str] = []
    error: str | None = None


# ── 学术数据库配置 ─────────────────────────────────────────────────────────────

class DatabaseConfig(BaseModel):
    enabled: bool
    api_key: str | None = None
    rate_limit: int = 5
    endpoint: str | None = None


class DatabasesConfigResponse(BaseModel):
    arxiv: DatabaseConfig
    openalex: DatabaseConfig
    semantic_scholar: DatabaseConfig
    ads: DatabaseConfig


class UpdateDatabaseConfigRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    rate_limit: int | None = None
    endpoint: str | None = None


# ── 邮件配置 ──────────────────────────────────────────────────────────────────

class EmailConfigResponse(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    sender_email: str | None = None
    recipients: list[str] = []


class UpdateEmailConfigRequest(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    sender_email: str | None = None
    sender_password: str | None = None
    recipients: list[str] | None = None


class TestEmailResponse(BaseModel):
    success: bool
    message: str
