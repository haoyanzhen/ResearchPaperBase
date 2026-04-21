"""
ORM 基类 — 所有模型的公共 DeclarativeBase

使用方式：
  from app.models.base import Base
  class MyModel(Base): ...

所有子模型在 app/models/__init__.py 中统一导入，
确保 SQLAlchemy 在执行迁移前已注册完整的 metadata。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
