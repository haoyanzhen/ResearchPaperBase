"""
用户配置服务 — 基于 user_configs / system_configs 键值表的配置读写。

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
  email.recipients                    → JSON 数组字符串（用户级收件人）

system_configs:
  email.smtp.host
  email.smtp.port
  email.smtp.sender_email
  email.smtp.sender_password          → 系统级发件身份，仅管理员可维护
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import SystemConfig, UserConfig
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
        endpoint = await get_config(db, user_id, f"database.{db_name}.endpoint")
        configs[db_name] = {
            "enabled": enabled.lower() == "true" if enabled else db_name != "ads",
            "api_key": api_key,
            "rate_limit": int(rate_limit) if rate_limit else 5,
            "endpoint": endpoint,
        }
    return configs


async def update_database_config(
    db: AsyncSession, user_id: str, db_name: str, updates: dict
) -> None:
    for field, value in updates.items():
        if value is not None:
            await set_config(db, user_id, f"database.{db_name}.{field}", str(value))


async def get_user_email_config(db: AsyncSession, user_id: str) -> dict:
    recipients_raw = await get_config(db, user_id, "email.recipients")
    return {
        "recipients": json.loads(recipients_raw) if recipients_raw else [],
        "sender_configured": await get_system_email_ready(db),
    }


async def update_user_email_config(db: AsyncSession, user_id: str, updates: dict) -> None:
    if updates.get("recipients") is not None:
        await set_config(db, user_id, "email.recipients", json.dumps(updates["recipients"]))


# =============================================================================
# 系统级配置（管理员 FR-029） — system_configs 表
# =============================================================================

async def get_system_config(db: AsyncSession, name: str) -> str | None:
    """读取系统级配置项。"""
    result = await db.execute(
        select(SystemConfig.config_value).where(SystemConfig.config_name == name)
    )
    return result.scalar_one_or_none()


async def set_system_config(
    db: AsyncSession, name: str, value: str, admin_id: str, description: str | None = None
) -> None:
    """新增或更新系统级配置项（仅管理员调用）。"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_name == name)
    )
    row = result.scalar_one_or_none()
    if row:
        row.config_value = value
        row.updated_by = admin_id
        if description is not None:
            row.description = description
    else:
        db.add(SystemConfig(
            id=new_id("sc"),
            config_name=name,
            config_value=value,
            description=description,
            updated_by=admin_id,
        ))
    await db.commit()


async def delete_system_config(db: AsyncSession, name: str) -> None:
    """删除系统级配置项（或按前缀批量删除）。"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_name.like(f"{name}%"))
    )
    for row in result.scalars().all():
        await db.delete(row)
    await db.commit()


async def get_all_system_llm_providers(db: AsyncSession) -> list[dict]:
    """读取系统级所有 LLM 提供商配置（格式与 get_all_llm_providers 一致）。"""
    result = await db.execute(
        select(SystemConfig.config_name, SystemConfig.config_value).where(
            SystemConfig.config_name.like("llm.provider.%")
        )
    )
    rows = result.all()
    providers: dict[str, dict] = {}
    for name, value in rows:
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


async def save_system_llm_provider(db: AsyncSession, admin_id: str, data: dict) -> None:
    """新增或覆盖系统级 LLM 提供商配置。"""
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
        await set_system_config(db, f"llm.provider.{provider}.{field}", value, admin_id)


async def update_system_llm_provider(
    db: AsyncSession, admin_id: str, provider: str, updates: dict
) -> None:
    for field, value in updates.items():
        if value is not None:
            await set_system_config(db, f"llm.provider.{provider}.{field}", str(value), admin_id)


async def delete_system_llm_provider(db: AsyncSession, provider: str) -> None:
    await delete_system_config(db, f"llm.provider.{provider}.")


async def get_system_databases_config(db: AsyncSession) -> dict:
    configs = {}
    for db_name in _DB_NAMES:
        enabled = await get_system_config(db, f"database.{db_name}.enabled")
        api_key = await get_system_config(db, f"database.{db_name}.api_key")
        rate_limit = await get_system_config(db, f"database.{db_name}.rate_limit")
        endpoint = await get_system_config(db, f"database.{db_name}.endpoint")
        configs[db_name] = {
            "enabled": enabled.lower() == "true" if enabled else db_name != "ads",
            "api_key": api_key,
            "rate_limit": int(rate_limit) if rate_limit else 5,
            "endpoint": endpoint,
        }
    return configs


async def update_system_database_config(
    db: AsyncSession, admin_id: str, db_name: str, updates: dict
) -> None:
    for field, value in updates.items():
        if value is not None:
            await set_system_config(db, f"database.{db_name}.{field}", str(value), admin_id)


async def get_system_email_config(db: AsyncSession) -> dict:
    sender_password = await get_system_config(db, "email.smtp.sender_password")
    return {
        "smtp_host": await get_system_config(db, "email.smtp.host"),
        "smtp_port": int(p) if (p := await get_system_config(db, "email.smtp.port")) else None,
        "sender_email": await get_system_config(db, "email.smtp.sender_email"),
        "sender_password_configured": bool(sender_password),
    }


async def update_system_email_config(db: AsyncSession, admin_id: str, updates: dict) -> None:
    mapping = {
        "smtp_host": "email.smtp.host",
        "smtp_port": "email.smtp.port",
        "sender_email": "email.smtp.sender_email",
        "sender_password": "email.smtp.sender_password",
    }
    for field, config_name in mapping.items():
        if updates.get(field) is not None:
            await set_system_config(db, config_name, str(updates[field]), admin_id)


async def get_system_email_ready(db: AsyncSession) -> bool:
    cfg = await get_system_email_config(db)
    return bool(cfg.get("smtp_host") and cfg.get("sender_email"))


# =============================================================================
# 回落函数：用户配置 → 系统配置（FR-029 核心逻辑）
# =============================================================================

async def get_config_with_fallback(db: AsyncSession, user_id: str, name: str) -> str | None:
    """先查用户配置，找不到时回落到系统级配置。"""
    value = await get_config(db, user_id, name)
    if value is None:
        value = await get_system_config(db, name)
    return value


async def get_all_llm_providers_with_fallback(db: AsyncSession, user_id: str) -> list[dict]:
    """
    返回用户可用的 LLM 提供商列表。
    用户有个人配置时仅返回个人配置；否则回落到系统级配置。
    """
    user_providers = await get_all_llm_providers(db, user_id)
    if user_providers:
        return user_providers
    return await get_all_system_llm_providers(db)


async def get_databases_config_with_fallback(db: AsyncSession, user_id: str) -> dict:
    """
    返回用户可用的学术数据库配置。
    对每个数据库，用户未配置时回落到系统级配置。
    """
    user_cfg = await get_databases_config(db, user_id)
    sys_cfg = await get_system_databases_config(db)
    # 用户有显式配置（enabled 字段在 user_configs 中有记录）时使用用户配置
    result = {}
    for db_name in _DB_NAMES:
        user_has_config = await get_config(db, user_id, f"database.{db_name}.enabled")
        result[db_name] = user_cfg[db_name] if user_has_config else sys_cfg[db_name]
    return result


async def get_effective_email_config(db: AsyncSession, user_id: str) -> dict:
    """
    返回用户可用的邮件配置：
    - 发件 SMTP 参数来自系统级配置
    - 收件人来自用户个人配置
    """
    user_cfg = await get_user_email_config(db, user_id)
    sys_cfg = await get_system_email_config(db)
    return {
        "smtp_host": sys_cfg.get("smtp_host"),
        "smtp_port": sys_cfg.get("smtp_port"),
        "sender_email": sys_cfg.get("sender_email"),
        "recipients": user_cfg.get("recipients", []),
        "sender_password_configured": sys_cfg.get("sender_password_configured", False),
    }
