import smtplib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.common import ok
from app.schemas.config import (
    CreateLLMConfigRequest,
    DatabasesConfigResponse,
    EmailConfigResponse,
    TestEmailResponse,
    TestLLMResponse,
    UpdateDatabaseConfigRequest,
    UpdateEmailConfigRequest,
    UpdateLLMConfigRequest,
)
from app.services import config_service

router = APIRouter(prefix="/config", tags=["配置"])

_VALID_DB_NAMES = {"arxiv", "openalex", "semantic_scholar", "ads"}


# ── LLM 配置 (FR-002) ─────────────────────────────────────────────────────────

@router.get("/llm")
async def get_llm_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    providers = await config_service.get_all_llm_providers(db, current_user.id)
    for p in providers:
        p.pop("api_key", None)
    return ok(providers)


@router.post("/llm", status_code=status.HTTP_201_CREATED)
async def add_llm_config(
    body: CreateLLMConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await config_service.save_llm_provider(db, current_user.id, body.model_dump())
    providers = await config_service.get_all_llm_providers(db, current_user.id)
    result = next((p for p in providers if p["provider"] == body.provider), {})
    result.pop("api_key", None)   # 不返回 api_key 明文
    return ok(result)


@router.patch("/llm/{provider}")
async def update_llm_config(
    provider: str,
    body: UpdateLLMConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await config_service.update_llm_provider(db, current_user.id, provider, body.model_dump(exclude_none=True))
    providers = await config_service.get_all_llm_providers(db, current_user.id)
    result = next((p for p in providers if p["provider"] == provider), None)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LLM 提供商不存在")
    result.pop("api_key", None)
    return ok(result)


@router.delete("/llm/{provider}")
async def delete_llm_config(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await config_service.delete_llm_provider(db, current_user.id, provider)
    return ok({"message": "deleted"})


@router.post("/llm/{provider}/test")
async def test_llm_config(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import time

    url = await config_service.get_config(db, current_user.id, f"llm.provider.{provider}.url")
    api_key = await config_service.get_config(db, current_user.id, f"llm.provider.{provider}.api_key")
    if not url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LLM 提供商不存在")

    import httpx
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{url.rstrip('/')}/models", headers={"Authorization": f"Bearer {api_key}"})
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            models = [m["id"] for m in resp.json().get("data", [])]
            return ok(TestLLMResponse(success=True, latency_ms=latency, model_list=models))
        return ok(TestLLMResponse(success=False, latency_ms=latency, error=f"HTTP {resp.status_code}"))
    except Exception as e:
        return ok(TestLLMResponse(success=False, error=str(e)))


# ── 学术数据库配置 (FR-003) ────────────────────────────────────────────────────

@router.get("/databases")
async def get_databases_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    configs = await config_service.get_databases_config(db, current_user.id)
    return ok(configs)


@router.patch("/databases/{db_name}")
async def update_database_config(
    db_name: str,
    body: UpdateDatabaseConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if db_name not in _VALID_DB_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"未知数据库: {db_name}")
    await config_service.update_database_config(db, current_user.id, db_name, body.model_dump(exclude_none=True))
    configs = await config_service.get_databases_config(db, current_user.id)
    return ok(configs[db_name])


# ── 邮件配置 (FR-004) ─────────────────────────────────────────────────────────

@router.get("/email")
async def get_email_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await config_service.get_email_config(db, current_user.id)
    return ok(EmailConfigResponse(**config))


@router.patch("/email")
async def update_email_config(
    body: UpdateEmailConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await config_service.update_email_config(db, current_user.id, body.model_dump(exclude_none=True))
    config = await config_service.get_email_config(db, current_user.id)
    return ok(EmailConfigResponse(**config))


@router.post("/email/test")
async def test_email(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await config_service.get_email_config(db, current_user.id)
    if not config.get("smtp_host") or not config.get("recipients"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮件配置不完整")

    sender_email = config.get("sender_email") or ""
    sender_pwd = await config_service.get_config(db, current_user.id, "email.smtp.sender_password")
    to = config["recipients"][0]
    try:
        with smtplib.SMTP(config["smtp_host"], config.get("smtp_port") or 587, timeout=10) as s:
            s.starttls()
            s.login(sender_email, sender_pwd or "")
            msg = (
                f"From: {sender_email}\r\n"
                f"To: {to}\r\n"
                f"Subject: =?UTF-8?B?UmVzZWFyY2ggUGFwZXIgQmFzZSDmb1fjgIHpovnmuLzpn6noibI=?=\r\n\r\n"
                "这是来自 Research Paper Base 的测试邮件，配置正确。"
            )
            s.sendmail(sender_email, [to], msg.encode("utf-8"))
        return ok(TestEmailResponse(success=True, message=f"测试邮件已发送至 {to}"))
    except Exception as e:
        return ok(TestEmailResponse(success=False, message=str(e)))
