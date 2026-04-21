"""
Alembic 异步迁移环境配置 — Research Paper Base

支持两种运行模式：
  - offline：生成纯 SQL 脚本，不连接数据库
  - online （async）：直接连接 PostgreSQL 执行迁移

数据库 URL 从 app.core.config.settings.DATABASE_URL 读取，
支持 .env 文件覆盖（通过 pydantic-settings）。
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── 加载日志配置 ───────────────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 注册所有 ORM 模型，使 autogenerate 能感知完整表结构 ─────────────────────────
from app.models import Base  # noqa: E402  (import 所有子模块已在 __init__ 完成)

target_metadata = Base.metadata

# ── 从 app 配置读取 DATABASE_URL（覆盖 alembic.ini 的空值）────────────────────
from app.core.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


# ── Offline 模式（生成 SQL 脚本）──────────────────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # PostgreSQL 特有：JSONB / TIMESTAMPTZ 等类型名称保持原样
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online 模式（异步连接执行）────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── 入口 ──────────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
