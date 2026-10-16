"""v1.0 — 隔离存档辅助片段，不接入任何应用入口。"""
from contextlib import contextmanager
from contextvars import ContextVar
import re
import secrets

_CONTEXT = ContextVar("archived_support_context", default=None)
_FIELDS = frozenset({"trace_id", "operation_id", "project_id", "user_id"})
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_PREFIX = re.compile(r"[a-z][a-z0-9]{0,15}\Z")


def context_snapshot() -> dict[str, str]:
    """返回副本；调用方必须确保 ID 本身不含秘密。"""
    return dict(_CONTEXT.get() or {})


@contextmanager
def scoped_context(**fields: str):
    """同步 with 作用域，也可在协程内使用；嵌套退出时恢复原值。"""
    if fields.keys() - _FIELDS:
        raise ValueError("unsupported context field")
    if any(not isinstance(value, str) or not _TOKEN.fullmatch(value)
           for value in fields.values()):
        raise ValueError("context values must be bounded opaque identifiers")
    token = _CONTEXT.set({**context_snapshot(), **fields})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def random_identifier(prefix: str) -> str:
    """受控内部前缀 + 128 位随机数；不是数据库唯一性保证。"""
    if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
        raise ValueError("invalid internal prefix")
    return f"{prefix}_{secrets.token_hex(16)}"


def quote_identifier(value: str) -> str:
    """单个 PostgreSQL 标识符的双引号转义；不适用于 SQL 值或路径。"""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("identifier must be a nonempty string without NUL")
    if len(value.encode("utf-8")) > 63:
        raise ValueError("identifier exceeds candidate's 63-byte limit")
    return '"' + value.replace('"', '""') + '"'
