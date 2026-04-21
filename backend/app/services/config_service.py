"""
用户配置服务 — 基于 user_configs 键值表的配置读写。

config_name 命名约定（来自 spec 6.4.3）：
  llm.provider.{provider}.url         → LLM 提供商 URL
  llm.provider.{provider}.api_key     → LLM API Key（加密存储）
  llm.provider.{provider}.default_model
  llm.provider.{provider}.temperature
  llm.provider.{provider}.max_tokens
  llm.provider.{provider}.is_active
  database.{db_name}.enabled
  database.{db_name}.api_key
  database.{db_name}.rate_limit
  email.smtp.host
  email.smtp.port
  email.smtp.sender_email
  email.smtp.sender_password          → 加密存储
  email.recipients                    → JSON 数组字符串
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserConfig
from app.utils.ids import new_id

_DB_NAMES = ("arxiv", "openalex", "semantic_scholar", "ads")


async def get_config(db: AsyncSession, user_id: str, name: str) -> str | None:
    result = await db.execute(
        select(UserConfig.config_value).where(
            UserConfig.user_id == user_id, UserConfig.config_name == name
        )
    )
    return result.scalar_one_or_none()


async def set_config(db: AsyncSession, user_id: str, name: str, value: str) -> None:
    result = await db.execute(
        select(UserConfig).where(
            UserConfig.user_id == user_id, UserConfig.config_name == name
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.config_value = value
    else:
        db.add(UserConfig(id=new_id("cfg"), user_id=user_id, config_name=name, config_value=value))
    await db.commit()


async def get_all_llm_providers(db: AsyncSession, user_id: str) -> list[dict]:
    result = await db.execute(
        select(UserConfig.config_name, UserConfig.config_value).where(
            UserConfig.user_id == user_id,
            UserConfig.config_name.like("llm.provider.%"),
        )
    )
    rows = result.all()

    providers: dict[str, dict] = {}
    for name, value in rows:
        # name pattern: llm.provider.{provider}.{field}
        parts = name.split(".")
        if len(parts) < 4:
            continue
        provider = parts[2]
        field = ".".join(parts[3:])
        if provider not in providers:
            providers[provider] = {"provider": provider}
        if field in ("temperature", "max_tokens"):
            providers[provider][field] = float(value) if field == "temperature" else int(value)
        elif field == "is_active":
            providers[provider][field] = value.lower() == "true"
        elif field == "models":
            providers[provider][field] = json.loads(value)
        else:
            providers[provider][field] = value

    return list(providers.values())


async def save_llm_provider(db: AsyncSession, user_id: str, data: dict) -> None:
    provider = data["provider"]
    fields = {
        "url": data.get("url", ""),
        "api_key": data.get("api_key", ""),
        "default_model": data.get("default_model", ""),
        "temperature": str(data.get("temperature", 0.7)),
        "max_tokens": str(data.get("max_tokens", 4096)),
        "is_active": "true",
    }
    for field, value in fields.items():
        await set_config(db, user_id, f"llm.provider.{provider}.{field}", value)


async def update_llm_provider(db: AsyncSession, user_id: str, provider: str, updates: dict) -> None:
    for field, value in updates.items():
        if value is not None:
            await set_config(db, user_id, f"llm.provider.{provider}.{field}", str(value))


async def delete_llm_provider(db: AsyncSession, user_id: str, provider: str) -> None:
    result = await db.execute(
        select(UserConfig).where(
            UserConfig.user_id == user_id,
            UserConfig.config_name.like(f"llm.provider.{provider}.%"),
        )
    )
    for row in result.scalars().all():
        await db.delete(row)
    await db.commit()


async def get_databases_config(db: AsyncSession, user_id: str) -> dict:
    configs = {}
    for db_name in _DB_NAMES:
        enabled = await get_config(db, user_id, f"database.{db_name}.enabled")
        api_key = await get_config(db, user_id, f"database.{db_name}.api_key")
        rate_limit = await get_config(db, user_id, f"database.{db_name}.rate_limit")
        configs[db_name] = {
            "enabled": enabled.lower() == "true" if enabled else db_name != "ads",
            "api_key": api_key,
            "rate_limit": int(rate_limit) if rate_limit else 5,
        }
    return configs


async def update_database_config(
    db: AsyncSession, user_id: str, db_name: str, updates: dict
) -> None:
    for field, value in updates.items():
        if value is not None:
            await set_config(db, user_id, f"database.{db_name}.{field}", str(value))


async def get_email_config(db: AsyncSession, user_id: str) -> dict:
    recipients_raw = await get_config(db, user_id, "email.recipients")
    return {
        "smtp_host": await get_config(db, user_id, "email.smtp.host"),
        "smtp_port": int(p) if (p := await get_config(db, user_id, "email.smtp.port")) else None,
        "sender_email": await get_config(db, user_id, "email.smtp.sender_email"),
        "recipients": json.loads(recipients_raw) if recipients_raw else [],
    }


async def update_email_config(db: AsyncSession, user_id: str, updates: dict) -> None:
    mapping = {
        "smtp_host": "email.smtp.host",
        "smtp_port": "email.smtp.port",
        "sender_email": "email.smtp.sender_email",
        "sender_password": "email.smtp.sender_password",
    }
    for field, config_name in mapping.items():
        if updates.get(field) is not None:
            await set_config(db, user_id, config_name, str(updates[field]))
    if updates.get("recipients") is not None:
        await set_config(db, user_id, "email.recipients", json.dumps(updates["recipients"]))
