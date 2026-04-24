"""
单元测试：app.agents.base（qa_design §7）

覆盖：
  - parse_json_response() — 正常 JSON、markdown 包装、无效输入
  - emit_sse_event()      — 格式验证、队列满时降级
  - emit_error_event()    — ErrorEnvelope 序列化进 SSE
"""

import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock

from app.agents.base import emit_sse_event, emit_error_event, parse_json_response, get_sse_queue
from app.core.errors import AppErrorCode, ErrorEnvelope, make_envelope


# ── parse_json_response() ─────────────────────────────────────────────────────

class TestParseJsonResponse:
    def test_plain_json(self):
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_markdown_block(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        result = parse_json_response(text)
        assert result["key"] == "value"

    def test_json_in_plain_code_block(self):
        text = "```\n{\"items\": [1,2,3]}\n```"
        result = parse_json_response(text)
        assert result["items"] == [1, 2, 3]

    def test_leading_trailing_whitespace(self):
        result = parse_json_response("  \n  {\"a\": 1}  \n  ")
        assert result["a"] == 1

    def test_list_json(self):
        result = parse_json_response('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("not json")

    def test_empty_string_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            parse_json_response("")


# ── emit_sse_event() ──────────────────────────────────────────────────────────

class TestEmitSseEvent:
    def test_event_format(self):
        queue = get_sse_queue("_test_proj_emit")
        # 清空旧事件
        while not queue.empty():
            queue.get_nowait()

        emit_sse_event("_test_proj_emit", "chapter_complete", {"progress": 50})
        raw = queue.get_nowait()

        assert "event: chapter_complete" in raw
        assert '"progress": 50' in raw
        assert raw.endswith("\n\n")

    def test_data_is_valid_json(self):
        queue = get_sse_queue("_test_proj_json")
        while not queue.empty():
            queue.get_nowait()

        payload = {"stage": 3, "title": "方法论"}
        emit_sse_event("_test_proj_json", "stage_start", payload)
        raw = queue.get_nowait()

        data_line = next(l for l in raw.splitlines() if l.startswith("data:"))
        data = json.loads(data_line[len("data:"):].strip())
        assert data["stage"] == 3
        assert data["title"] == "方法论"

    def test_queue_full_does_not_raise(self):
        """队列满时 emit_sse_event 静默降级，不抛异常。"""
        queue = get_sse_queue("_test_proj_full")
        # 填满队列
        while True:
            try:
                queue.put_nowait("x")
            except asyncio.QueueFull:
                break

        # 不应抛出异常
        emit_sse_event("_test_proj_full", "test_event", {"key": "val"})


# ── emit_error_event() ────────────────────────────────────────────────────────

class TestEmitErrorEvent:
    def test_stage_error_event_type(self):
        queue = get_sse_queue("_test_proj_err")
        while not queue.empty():
            queue.get_nowait()

        envelope = make_envelope(
            AppErrorCode.LLM_RATE_LIMIT_EXCEEDED,
            "rate limited",
            project_id="_test_proj_err",
            stage_record_id="sr_test",
        )
        emit_error_event("_test_proj_err", envelope)
        raw = queue.get_nowait()

        assert "event: stage_error" in raw

    def test_error_event_data_contains_code(self):
        queue = get_sse_queue("_test_proj_code")
        while not queue.empty():
            queue.get_nowait()

        envelope = make_envelope(AppErrorCode.LLM_API_KEY_INVALID, "bad key")
        emit_error_event("_test_proj_code", envelope)
        raw = queue.get_nowait()

        data_line = next(l for l in raw.splitlines() if l.startswith("data:"))
        data = json.loads(data_line[len("data:"):].strip())
        assert data["code"] == "ERR-LLM-001"
        assert data["retryable"] is False
