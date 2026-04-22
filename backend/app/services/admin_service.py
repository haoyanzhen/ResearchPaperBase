"""
管理员服务 — FR-029

职责：
  - 用户账号管理（列表 / 启停 / 提权 / 删除 / 重置密码）
  - 系统级配置读写已在 config_service 中实现，本模块提供用户管理专项逻辑

权限：所有函数仅供已验证管理员身份的路由调用（deps.get_current_admin 保证）。
"""

import random
import secrets
import smtplib
import string
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.services.config_service import get_config


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# 用户列表
# =============================================================================

async def list_users(db: AsyncSession) -> list[dict]:
    """返回所有用户的基本信息（不含 password_hash）。"""
    result = await db.execute(
        select(User).order_by(User.created_at)
    )
    users = result.scalars().all()
    return [
        {
            "user_id": u.id,
            "username": u.username,
            "email": u.email,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "last_login_at": u.last_login_at,
        }
        for u in users
    ]


# =============================================================================
# 账号启用 / 禁用
# =============================================================================

async def set_user_active(
    db: AsyncSession,
    target_id: str,
    is_active: bool,
    requesting_user_id: str,
) -> tuple[dict | None, str]:
    """
    启用或禁用目标用户账号。

    规则：
      - 管理员不能禁用自身账号（启用自己是合法的，禁用才拒绝）
    返回 (user_dict, error_msg)。
    """
    if not is_active and target_id == requesting_user_id:
        return None, "管理员不能禁用自身账号"

    result = await db.execute(select(User).where(User.id == target_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None, "用户不存在"

    user.is_active = is_active
    await db.commit()
    return {"user_id": user.id, "is_active": user.is_active}, ""


# =============================================================================
# 管理员权限提升 / 撤销
# =============================================================================

async def set_user_admin(
    db: AsyncSession,
    target_id: str,
    is_admin: bool,
    requesting_user_id: str,
) -> tuple[dict | None, str]:
    """
    提升或撤销目标用户的管理员权限。

    规则：
      - 不能撤销系统中最后一位管理员的权限
    """
    result = await db.execute(select(User).where(User.id == target_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None, "用户不存在"

    # 撤销权限时，检查是否是最后一位管理员
    if not is_admin and user.is_admin:
        admin_count_result = await db.execute(
            select(func.count(User.id)).where(User.is_admin == True)
        )
        if admin_count_result.scalar_one() <= 1:
            return None, "系统至少需要保留一位管理员，无法撤销最后一位管理员的权限"

    user.is_admin = is_admin
    await db.commit()
    return {"user_id": user.id, "is_admin": user.is_admin}, ""


# =============================================================================
# 删除用户
# =============================================================================

async def delete_user(
    db: AsyncSession,
    target_id: str,
    requesting_user_id: str,
) -> tuple[bool, str]:
    """
    删除目标用户账号（级联删除所有关联数据）。

    规则：
      - 管理员不能删除自身账号
      - 不能删除系统最后一位管理员
    """
    if target_id == requesting_user_id:
        return False, "管理员不能删除自身账号"

    result = await db.execute(select(User).where(User.id == target_id))
    user = result.scalar_one_or_none()
    if user is None:
        return False, "用户不存在"

    # 删除管理员时，确保不会让系统无管理员
    if user.is_admin:
        admin_count_result = await db.execute(
            select(func.count(User.id)).where(User.is_admin == True)
        )
        if admin_count_result.scalar_one() <= 1:
            return False, "系统至少需要保留一位管理员，无法删除最后一位管理员账号"

    await db.delete(user)
    await db.commit()
    return True, ""


# =============================================================================
# 重置密码
# =============================================================================

def _generate_temp_password(length: int = 12) -> str:
    """生成含大小写字母与数字的随机临时密码。"""
    alphabet = string.ascii_letters + string.digits
    # 保证包含至少一个大写、一个小写、一个数字
    parts = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        *(secrets.choice(alphabet) for _ in range(length - 3)),
    ]
    random.shuffle(parts)
    return "".join(parts)


async def reset_user_password(
    db: AsyncSession,
    target_id: str,
    requesting_user_id: str,
) -> tuple[dict | None, str]:
    """
    重置目标用户密码：生成临时密码 → 更新哈希 → 通过邮件发送给目标用户。

    邮件配置取自管理员（requesting_user_id）的用户配置；
    若管理员无邮件配置则返回临时密码（不发送邮件，由调用方告知前端）。

    返回 (result_dict, error_msg)：
      result_dict 含 email_sent(bool)，email_sent=False 时含 temp_password 明文（管理员手动转告）。
    """
    result = await db.execute(select(User).where(User.id == target_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None, "用户不存在"

    temp_pwd = _generate_temp_password()
    user.password_hash = hash_password(temp_pwd)
    await db.commit()

    # 尝试通过管理员的 SMTP 配置发送邮件
    smtp_host = await get_config(db, requesting_user_id, "email.smtp.host")
    smtp_port_raw = await get_config(db, requesting_user_id, "email.smtp.port")
    sender = await get_config(db, requesting_user_id, "email.smtp.sender_email")
    sender_pwd = await get_config(db, requesting_user_id, "email.smtp.sender_password")

    if not smtp_host or not sender:
        # 无邮件配置，返回临时密码供管理员手动转告
        return {"email_sent": False, "temp_password": temp_pwd, "target_email": user.email}, ""

    body = (
        f"您好 {user.username}，\n\n"
        f"管理员已为您重置密码，临时密码为：\n\n"
        f"    {temp_pwd}\n\n"
        f"请登录后立即修改密码。\n\n"
        f"— Research Paper Base 系统通知"
    )
    msg = (
        f"From: {sender}\r\n"
        f"To: {user.email}\r\n"
        f"Subject: =?UTF-8?B?5a6h5YWD5a+55YWl6YKu55Sf6YKu56iL?=\r\n\r\n"
        + body
    )
    try:
        smtp_port = int(smtp_port_raw) if smtp_port_raw else 587
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            if sender_pwd:
                s.login(sender, sender_pwd)
            s.sendmail(sender, [user.email], msg.encode("utf-8"))
        return {"email_sent": True, "target_email": user.email}, ""
    except Exception as exc:
        # 邮件发送失败时仍返回临时密码，不回滚密码重置
        return {"email_sent": False, "temp_password": temp_pwd, "target_email": user.email,
                "email_error": str(exc)}, ""
