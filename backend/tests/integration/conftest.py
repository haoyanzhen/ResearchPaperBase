"""
集成测试基础 Fixtures（qa_design §7）

依赖：
  - 真实 PostgreSQL（通过 DATABASE_URL 环境变量）
  - pytest-asyncio（asyncio_mode=auto）
  - httpx.AsyncClient（直接驱动 FastAPI app）

Fixtures：
  - engine        — 独立 AsyncEngine（使用 test DB）
  - db_session    — 每个测试独立事务，测试后回滚
  - client        — AsyncClient with lifespan
  - test_user     — 创建并返回测试用户行
  - auth_headers  — 带有效 JWT 的请求头
"""

from __future__ import annotations

import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.core.deps import get_db
from app.models.base import Base
from app.models.user import User
from app.core.security import create_access_token, get_password_hash
from app.utils.ids import new_id


# ── 数据库引擎（使用独立测试数据库）────────────────────────────────────────────

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/paperpush_test"),
)


@pytest_asyncio.fixture(scope="session")
async def engine():
    """会话级别的独立测试引擎，在 session 开始时建表，结束时不删表（保留调试）。"""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """
    每个测试独立事务，测试后自动回滚，保证测试隔离。
    同时将 app 的 get_db 依赖覆盖为使用同一个 session。
    """
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        async with session.begin():
            # 覆盖依赖注入
            async def _override_get_db():
                yield session

            app.dependency_overrides[get_db] = _override_get_db
            yield session
            # 回滚而非提交，保证测试隔离
            await session.rollback()

    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def client(db_session):
    """使用 ASGI Transport 创建 httpx.AsyncClient，无需启动真实服务器。"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── 用户与认证 Fixtures ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """在测试 DB 中创建一个测试用户，测试后随事务回滚清除。"""
    user = User(
        id=new_id("u"),
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """管理员测试用户。"""
    user = User(
        id=new_id("u"),
        username="adminuser",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpassword"),
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def auth_headers(test_user):
    """返回带有效 JWT 的 Authorization 请求头。"""
    token = create_access_token({"sub": test_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers(admin_user):
    """管理员 JWT 请求头。"""
    token = create_access_token({"sub": admin_user.id})
    return {"Authorization": f"Bearer {token}"}
