"""
结构化 JSON 日志模块（qa_design.md §9）

提供：
  - JsonFormatter      — 将 LogRecord 序列化为单行 JSON
  - setup_logging()    — 在应用启动时配置根日志器
  - log_context        — contextvars.ContextVar，存储请求级别上下文字段
  - bind_log_context() — 上下文管理器，自动注入 project_id / user_id
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ── 请求级上下文（通过 contextvars 在协程间传递，无竞态）──────────────────────
_log_context: ContextVar[dict[str, Any]] = ContextVar("_log_context", default={})


def get_log_context() -> dict[str, Any]:
    """返回当前协程的日志上下文字段（只读视图）。"""
    return dict(_log_context.get())


@contextmanager
def bind_log_context(**fields: Any):
    """
    上下文管理器：在作用域内合并额外字段到日志上下文。
    退出时自动恢复原始上下文，不污染父协程。

    用法：
        async with bind_log_context(project_id="proj_abc", user_id="u_xyz"):
            logger.info("doing work")   # 日志自动携带 project_id / user_id
    """
    token = _log_context.set({**_log_context.get(), **fields})
    try:
        yield
    finally:
        _log_context.reset(token)


# ── JSON Formatter ──────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """
    将 LogRecord 序列化为单行 JSON。

    固定字段（每条日志都有）：
      timestamp, level, logger, message

    上下文字段（从 _log_context 合并，或从 record.__dict__ 中读取额外键）：
      project_id, user_id, stage, stage_record_id, error_code,
      latency_ms, attempt, max_attempts, batch_index, elapsed_seconds,
      prompt_key, message_count, output_tokens

    异常信息（exc_info=True 时追加）：
      exc_type, exc_message, traceback
    """

    # 标准 LogRecord 属性，不应透传到 JSON extra 字段
    _STD_ATTRS = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        doc: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }

        # 注入当前协程上下文字段
        doc.update(_log_context.get())

        # 注入 record 上的额外字段（由调用方通过 extra={} 传入）
        for key, val in record.__dict__.items():
            if key not in self._STD_ATTRS and not key.startswith("_"):
                doc[key] = val

        # 异常信息
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, exc_val, exc_tb = record.exc_info
            doc["exc_type"] = exc_type.__name__ if exc_type else None
            doc["exc_message"] = str(exc_val)
            doc["traceback"] = "".join(
                traceback.format_exception(exc_type, exc_val, exc_tb)
            ).rstrip()

        return json.dumps(doc, ensure_ascii=False, default=str)


# ── 配置函数 ─────────────────────────────────────────────────────────────────

def setup_logging(level: str | None = None) -> None:
    """
    配置根日志器，使用 JsonFormatter 输出到 stdout。

    level 参数优先级：
      1. 显式传入的 level 参数
      2. APP_ENV == "development" → DEBUG
      3. 其他（production / staging）→ INFO

    调用时机：FastAPI app 启动时（main.py 顶层）。
    多次调用幂等（只添加一次 handler）。
    """
    from app.core.config import settings

    if level is None:
        level = "DEBUG" if settings.APP_ENV == "development" else "INFO"

    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    root = logging.getLogger()

    # 幂等保护：已配置过 JsonFormatter 则跳过
    for h in root.handlers:
        if isinstance(h.formatter, JsonFormatter):
            root.setLevel(numeric_level)
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # 降低第三方库的噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
