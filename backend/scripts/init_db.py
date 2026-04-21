"""
数据库初始化脚本 — Research Paper Base

用途：
  开发环境一键建库，等价于执行 `alembic upgrade head`，
  但额外提供数据库连接检查和友好的错误提示。

用法：
  cd backend
  python scripts/init_db.py

生产环境请使用 Alembic 管理迁移：
  alembic upgrade head
"""

import asyncio
import sys
from pathlib import Path

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import command
from alembic.config import Config


def run() -> None:
    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    print("▶ 正在执行数据库迁移 (alembic upgrade head)...")
    try:
        command.upgrade(alembic_cfg, "head")
        print("✓ 数据库初始化完成，所有表已创建。")
    except Exception as exc:
        print(f"✗ 迁移失败：{exc}")
        print("\n排查步骤：")
        print("  1. 确认 PostgreSQL 服务已启动")
        print("  2. 确认 backend/.env 中 DATABASE_URL 配置正确")
        print("  3. 确认数据库已存在（CREATE DATABASE paperpush;）")
        sys.exit(1)


if __name__ == "__main__":
    run()
