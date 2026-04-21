from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.utils.ids import new_id


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_credential(db: AsyncSession, credential: str) -> User | None:
    """credential 可以是 username 或 email"""
    result = await db.execute(
        select(User).where(or_(User.username == credential, User.email == credential))
    )
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, username: str, email: str, password: str) -> User:
    user = User(
        id=new_id("u"),
        username=username,
        email=email,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, credential: str, password: str) -> User | None:
    user = await get_user_by_credential(db, credential)
    if not user or not verify_password(password, user.password_hash):
        return None
    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    username: str | None,
    email: str | None,
    password: str | None,
) -> User:
    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    if password is not None:
        user.password_hash = hash_password(password)
    await db.commit()
    await db.refresh(user)
    return user


async def username_exists(db: AsyncSession, username: str) -> bool:
    result = await db.execute(select(User.id).where(User.username == username))
    return result.scalar_one_or_none() is not None


async def email_exists(db: AsyncSession, email: str) -> bool:
    result = await db.execute(select(User.id).where(User.email == email))
    return result.scalar_one_or_none() is not None
