"""
顶层测试 Fixtures（qa_design.md §7）

提供：
  - mock_llm_complete     — 正常返回固定字符串的 LLMClient.complete mock
  - mock_llm_rate_limit   — 模拟 LLM 429 限流错误
  - mock_llm_raise        — 注入任意异常
  - parse_sse_event_type  — 解析 SSE 格式字符串，提取 event_type
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


# ── LLM mock fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_complete():
    """
    将 LLMClient.complete 替换为立即返回 JSON 占位字符串的 AsyncMock。

    用法：
        async def test_something(mock_llm_complete):
            mock_llm_complete.return_value = '{"key": "value"}'
            ...
    """
    with patch(
        "app.agents.base.LLMClient.complete",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = '{"result": "mocked"}'
        yield mock


@pytest.fixture
def mock_llm_rate_limit():
    """将 LLMClient.complete 替换为抛出速率限制异常的 AsyncMock。"""
    with patch(
        "app.agents.base.LLMClient.complete",
        new_callable=AsyncMock,
    ) as mock:
        mock.side_effect = RuntimeError(
            "LLM 请求失败（已重试 3 次）: 429 Too Many Requests - rate limit exceeded"
        )
        yield mock


@pytest.fixture
def mock_llm_raise():
    """
    返回一个可配置 side_effect 的 AsyncMock。

    用法：
        async def test_something(mock_llm_raise):
            mock_llm_raise.side_effect = ValueError("bad config")
            ...
    """
    with patch(
        "app.agents.base.LLMClient.complete",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


# ── SSE 解析工具 ──────────────────────────────────────────────────────────────

def parse_sse_event_type(raw: str) -> str | None:
    """
    从 SSE 格式字符串中解析 event_type。

    SSE 格式：
        event: <event_type>\ndata: <json>\n\n

    返回 event_type 字符串，未找到时返回 None。
    """
    for line in raw.splitlines():
        if line.startswith("event:"):
            return line[len("event:"):].strip()
    return None


@pytest.fixture
def sse_event_type_parser():
    """以 fixture 形式暴露 parse_sse_event_type 函数。"""
    return parse_sse_event_type
