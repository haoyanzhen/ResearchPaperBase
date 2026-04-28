"""
数据库初始化脚本 — Research Paper Base

用途：
  开发环境一键初始化数据库：
  1. 读取 backend/.env 中的 DATABASE_URL
  2. 检查目标数据库是否存在
  3. 若不存在，则自动创建
  4. 执行 `alembic upgrade head`

用法：
  cd backend
  python scripts/init_db.py

可选环境变量：
  INIT_DB_ADMIN_DATABASE=postgres
    用于创建目标数据库时，先连接到哪个已存在的管理数据库。
    默认为 postgres；若你的环境禁用了 postgres 库，可改为 template1。

生产环境请使用受控迁移流程，不建议直接依赖本脚本自动建库。
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


async def ensure_database_exists() -> None:
    url = make_url(settings.DATABASE_URL)
    target_db = url.database
    admin_db = os.getenv("INIT_DB_ADMIN_DATABASE", "postgres")

    if not target_db:
        raise RuntimeError("DATABASE_URL 未包含数据库名")

    if url.get_backend_name() != "postgresql":
        raise RuntimeError("当前 init_db.py 仅支持 PostgreSQL")

    connect_kwargs = {
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "database": admin_db,
    }

    conn = await asyncpg.connect(**connect_kwargs)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            target_db,
        )
        if exists:
            print(f"✓ 数据库已存在：{target_db}", flush=True)
            return

        print(f"▶ 数据库不存在，正在创建：{target_db}", flush=True)
        await conn.execute(f"CREATE DATABASE {quote_ident(target_db)}")
        print(f"✓ 数据库创建完成：{target_db}", flush=True)
    finally:
        await conn.close()


def run() -> None:
    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    try:
        asyncio.run(ensure_database_exists())
        print("▶ 正在执行数据库迁移 (alembic upgrade head)...", flush=True)
        command.upgrade(alembic_cfg, "head")
        print("✓ 数据库初始化完成，所有表已创建。", flush=True)
    except Exception as exc:
        print(f"✗ 初始化失败：{exc}", flush=True)
        print("\n排查步骤：", flush=True)
        print("  1. 确认 PostgreSQL 服务已启动", flush=True)
        print("  2. 确认 backend/.env 中 DATABASE_URL 配置正确", flush=True)
        print("  3. 确认 DATABASE_URL 中的用户有 CREATE DATABASE 权限", flush=True)
        print("  4. 若 postgres 库不可用，设置 INIT_DB_ADMIN_DATABASE=template1 后重试", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
