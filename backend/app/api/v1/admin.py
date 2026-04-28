"""
HTTP 路由 — 管理员配置面板（FR-029）

所有端点均通过 get_current_admin 依赖确认调用方为 is_admin=TRUE 的用户。

端点清单：
  用户管理：
    GET    /admin/users                             列出所有用户
    PATCH  /admin/users/{user_id}/status            启用/禁用账号
    PATCH  /admin/users/{user_id}/role              提升/撤销管理员
    DELETE /admin/users/{user_id}                   删除用户（级联）
    POST   /admin/users/{user_id}/reset-password    重置密码并发邮件

  系统级 LLM 配置（子模块一）：
    GET    /admin/system-config/llm                 列出所有系统 LLM 提供商
    POST   /admin/system-config/llm                 新增系统 LLM 提供商
    PATCH  /admin/system-config/llm/{provider}      更新系统 LLM 提供商
    DELETE /admin/system-config/llm/{provider}      删除系统 LLM 提供商
    POST   /admin/system-config/llm/{provider}/test 测试连通性

  系统级数据库配置（子模块二）：
    GET    /admin/system-config/databases            列出所有系统数据库配置
    PATCH  /admin/system-config/databases/{db_name} 更新某个系统数据库配置

  系统级邮件配置（子模块四）：
    GET    /admin/system-config/email                获取系统发件邮箱配置
    PATCH  /admin/system-config/email                更新系统发件邮箱配置
"""

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.user import User
from app.schemas.admin import (
    AdminUserItem,
    CreateSystemLLMRequest,
    ResetPasswordResponse,
    SetUserActiveRequest,
    SetUserAdminRequest,
    SystemEmailConfigResponse,
    UpdateSystemDatabaseRequest,
    UpdateSystemEmailConfigRequest,
    UpdateSystemLLMRequest,
)
from app.schemas.common import ok
from app.schemas.config import TestLLMResponse
from app.services import admin_service, config_service

router = APIRouter(prefix="/admin", tags=["管理员"])

_VALID_DB_NAMES = {"arxiv", "openalex", "semantic_scholar", "ads"}


# =============================================================================
# 用户管理（子模块三）
# =============================================================================

@router.get("/users")
async def list_users(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出所有注册用户（不含密码）。"""
    users = await admin_service.list_users(db)
    return ok([AdminUserItem(**u) for u in users])


@router.patch("/users/{user_id}/status")
async def set_user_status(
    user_id: str,
    body: SetUserActiveRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """启用或禁用目标用户账号。"""
    result, error = await admin_service.set_user_active(
        db, user_id, body.is_active, current_admin.id
    )
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    return ok(result)


@router.patch("/users/{user_id}/role")
async def set_user_role(
    user_id: str,
    body: SetUserAdminRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """提升指定用户为管理员，或撤销其管理员权限。"""
    result, error = await admin_service.set_user_admin(
        db, user_id, body.is_admin, current_admin.id
    )
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    return ok(result)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    删除目标用户及其所有关联数据（级联删除）。
    操作不可逆，调用前端需二次确认。
    """
    success, error = await admin_service.delete_user(db, user_id, current_admin.id)
    if not success:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    return ok({"message": "deleted"})


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """重置目标用户密码并尝试通过 SMTP 发送临时密码邮件。"""
    result, error = await admin_service.reset_user_password(db, user_id, current_admin.id)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    return ok(ResetPasswordResponse(**result))


# =============================================================================
# 系统级 LLM 配置（子模块一）
# =============================================================================

@router.get("/system-config/llm")
async def get_system_llm_configs(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出所有系统级 LLM 提供商配置。"""
    providers = await config_service.get_all_system_llm_providers(db)
    for p in providers:
        p.pop("api_key", None)   # 不返回 api_key 明文
    return ok(providers)


@router.post("/system-config/llm", status_code=status.HTTP_201_CREATED)
async def add_system_llm_config(
    body: CreateSystemLLMRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """新增或覆盖系统级 LLM 提供商配置。"""
    await config_service.save_system_llm_provider(db, current_admin.id, body.model_dump())
    providers = await config_service.get_all_system_llm_providers(db)
    result = next((p for p in providers if p["provider"] == body.provider), {})
    result.pop("api_key", None)
    return ok(result)


@router.patch("/system-config/llm/{provider}")
async def update_system_llm_config(
    provider: str,
    body: UpdateSystemLLMRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新系统级 LLM 提供商配置中的指定字段。"""
    await config_service.update_system_llm_provider(
        db, current_admin.id, provider, body.model_dump(exclude_none=True)
    )
    providers = await config_service.get_all_system_llm_providers(db)
    result = next((p for p in providers if p["provider"] == provider), None)
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "系统 LLM 提供商不存在")
    result.pop("api_key", None)
    return ok(result)


@router.delete("/system-config/llm/{provider}")
async def delete_system_llm_config(
    provider: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除系统级 LLM 提供商配置。"""
    await config_service.delete_system_llm_provider(db, provider)
    return ok({"message": "deleted"})


@router.post("/system-config/llm/{provider}/test")
async def test_system_llm_config(
    provider: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """测试系统级 LLM 提供商的连通性（GET /models）。"""
    url = await config_service.get_system_config(db, f"llm.provider.{provider}.url")
    api_key = await config_service.get_system_config(db, f"llm.provider.{provider}.api_key")
    if not url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "系统 LLM 提供商不存在")

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            models = [m["id"] for m in resp.json().get("data", [])]
            return ok(TestLLMResponse(success=True, latency_ms=latency, model_list=models))
        return ok(TestLLMResponse(success=False, latency_ms=latency, error=f"HTTP {resp.status_code}"))
    except Exception as exc:
        return ok(TestLLMResponse(success=False, error=str(exc)))


# =============================================================================
# 系统级数据库配置（子模块二）
# =============================================================================

@router.get("/system-config/databases")
async def get_system_databases_config(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出所有系统级学术数据库配置。"""
    configs = await config_service.get_system_databases_config(db)
    return ok(configs)


@router.patch("/system-config/databases/{db_name}")
async def update_system_database_config(
    db_name: str,
    body: UpdateSystemDatabaseRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新指定系统级学术数据库配置。"""
    if db_name not in _VALID_DB_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"未知数据库: {db_name}")
    await config_service.update_system_database_config(
        db, current_admin.id, db_name, body.model_dump(exclude_none=True)
    )
    configs = await config_service.get_system_databases_config(db)
    return ok(configs[db_name])


# =============================================================================
# 系统级邮件配置（子模块四）
# =============================================================================

@router.get("/system-config/email")
async def get_system_email_config(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """读取系统级发件邮箱配置。"""
    config = await config_service.get_system_email_config(db)
    return ok(SystemEmailConfigResponse(**config))


@router.patch("/system-config/email")
async def update_system_email_config(
    body: UpdateSystemEmailConfigRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新系统级发件邮箱配置。"""
    await config_service.update_system_email_config(
        db, current_admin.id, body.model_dump(exclude_none=True)
    )
    config = await config_service.get_system_email_config(db)
    return ok(SystemEmailConfigResponse(**config))
