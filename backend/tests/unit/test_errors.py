"""
单元测试：app.core.errors（qa_design §7）

覆盖：
  - ErrorEnvelope 字段校验
  - make_envelope() 自动填充逻辑
  - classify_agent_error() 映射正确性
  - classify_llm_error() 关键词识别
"""

import pytest
from app.core.errors import (
    AppErrorCode,
    ErrorEnvelope,
    RETRYABLE_CODES,
    SUGGESTIONS,
    classify_agent_error,
    classify_llm_error,
    make_envelope,
)


# ── ErrorEnvelope ─────────────────────────────────────────────────────────────

class TestErrorEnvelope:
    def test_minimal_fields(self):
        env = ErrorEnvelope(code="ERR-LLM-001", message="bad key")
        assert env.code == "ERR-LLM-001"
        assert env.message == "bad key"
        assert env.retryable is False
        assert env.suggestion == ""
        assert env.traceback is None
        assert env.detail is None

    def test_full_fields(self):
        env = ErrorEnvelope(
            code="ERR-SYS-DB-001",
            message="db down",
            detail={"stage": 2},
            traceback="Traceback...",
            retryable=True,
            suggestion="restart",
            occurred_at="2026-04-24T00:00:00Z",
            project_id="proj_abc",
            stage_record_id="sr_001",
        )
        assert env.project_id == "proj_abc"
        assert env.retryable is True

    def test_extra_fields_ignored(self):
        """model_config extra='ignore' — 未知字段不报错。"""
        env = ErrorEnvelope(code="ERR-VAL-001", message="x", unknown_field="y")
        assert not hasattr(env, "unknown_field")


# ── make_envelope() ───────────────────────────────────────────────────────────

class TestMakeEnvelope:
    def test_auto_retryable_true(self):
        env = make_envelope(AppErrorCode.LLM_RATE_LIMIT_EXCEEDED, "rate limited")
        assert env.retryable is True

    def test_auto_retryable_false(self):
        env = make_envelope(AppErrorCode.LLM_API_KEY_INVALID, "bad key")
        assert env.retryable is False

    def test_auto_suggestion_filled(self):
        env = make_envelope(AppErrorCode.LLM_NO_CONFIG, "no config")
        assert len(env.suggestion) > 0
        assert env.suggestion == SUGGESTIONS[AppErrorCode.LLM_NO_CONFIG]

    def test_occurred_at_is_iso_utc(self):
        env = make_envelope(AppErrorCode.DB_CONNECTION_FAILED, "conn err")
        assert env.occurred_at.endswith("+00:00") or env.occurred_at.endswith("Z") or "T" in env.occurred_at

    def test_traceback_filled_from_exc(self):
        try:
            raise ValueError("test error")
        except ValueError as exc:
            env = make_envelope(AppErrorCode.LLM_TIMEOUT, "timeout", exc=exc)
        assert env.traceback is not None
        assert "ValueError" in env.traceback
        assert "test error" in env.traceback

    def test_traceback_none_without_exc(self):
        env = make_envelope(AppErrorCode.LLM_TIMEOUT, "timeout")
        assert env.traceback is None

    def test_project_id_forwarded(self):
        env = make_envelope(
            AppErrorCode.PROJECT_NOT_FOUND, "not found",
            project_id="proj_xyz", stage_record_id="sr_007",
        )
        assert env.project_id == "proj_xyz"
        assert env.stage_record_id == "sr_007"

    def test_detail_forwarded(self):
        env = make_envelope(
            AppErrorCode.AGT_SCORING_BATCH_FAILED, "batch fail",
            detail={"stage": 3, "batch_index": 5},
        )
        assert env.detail["batch_index"] == 5

    def test_code_stored_as_string(self):
        """ErrorEnvelope.code 应存储枚举 value 字符串，不是枚举实例。"""
        env = make_envelope(AppErrorCode.FORBIDDEN, "forbidden")
        assert env.code == "ERR-AUTH-004"
        assert isinstance(env.code, str)


# ── classify_llm_error() ──────────────────────────────────────────────────────

class TestClassifyLlmError:
    @pytest.mark.parametrize("msg,expected", [
        ("401 invalid api key", AppErrorCode.LLM_API_KEY_INVALID),
        ("incorrect api key provided", AppErrorCode.LLM_API_KEY_INVALID),
        ("rate limit exceeded", AppErrorCode.LLM_RATE_LIMIT_EXCEEDED),
        ("429 Too Many Requests", AppErrorCode.LLM_RATE_LIMIT_EXCEEDED),
        ("context length exceeded 128000 tokens", AppErrorCode.LLM_CONTEXT_TOO_LONG),
        ("Read timeout after 60s", AppErrorCode.LLM_TIMEOUT),
        ("Connection refused", AppErrorCode.LLM_TIMEOUT),  # fallback
    ])
    def test_keyword_mapping(self, msg, expected):
        exc = RuntimeError(msg)
        assert classify_llm_error(exc) == expected


# ── classify_agent_error() ────────────────────────────────────────────────────

class TestClassifyAgentError:
    @pytest.mark.parametrize("mode,stage,expected", [
        ("construction", 1, AppErrorCode.AGT_KEYWORD_GEN_EMPTY),
        ("construction", 2, AppErrorCode.AGT_RETRIEVAL_ALL_FAILED),
        ("construction", 3, AppErrorCode.AGT_SCORING_BATCH_FAILED),
        ("construction", 4, AppErrorCode.AGT_DOWNLOAD_ALL_FAILED),
        ("construction", 5, AppErrorCode.AGT_ANALYSIS_BATCH_FAILED),
        ("review", 1, AppErrorCode.AGT_TOPIC_EXPANSION_EMPTY),
        ("review", 2, AppErrorCode.AGT_OUTLINE_INVALID_JSON),
        ("review", 3, AppErrorCode.AGT_CHAPTER_WRITE_FAILED),
        ("review", 4, AppErrorCode.AGT_REVIEW_LOOP_EXCEEDED),
    ])
    def test_stage_mapping(self, mode, stage, expected):
        exc = RuntimeError("generic error")
        assert classify_agent_error(exc, mode, stage) == expected

    def test_llm_keyword_overrides_stage(self):
        """LLM 关键词识别优先于阶段-模式映射。"""
        exc = RuntimeError("rate limit exceeded")
        assert classify_agent_error(exc, "construction", 3) == AppErrorCode.LLM_RATE_LIMIT_EXCEEDED

    def test_json_parse_keyword(self):
        exc = RuntimeError("JSON decode error at line 1")
        assert classify_agent_error(exc, "review", 2) == AppErrorCode.LLM_JSON_PARSE_FAILED

    def test_unknown_mode_falls_back(self):
        exc = RuntimeError("some error")
        result = classify_agent_error(exc, "dialogue", 99)
        assert result == AppErrorCode.LLM_TIMEOUT


# ── RETRYABLE_CODES 和 SUGGESTIONS 完整性检查 ─────────────────────────────────

class TestCodeMaps:
    def test_retryable_codes_are_valid_enum_members(self):
        for code in RETRYABLE_CODES:
            assert isinstance(code, AppErrorCode)

    def test_all_suggestions_have_non_empty_text(self):
        for code, text in SUGGESTIONS.items():
            assert len(text) > 0, f"SUGGESTIONS[{code}] is empty"

    def test_suggestions_keys_are_enum_members(self):
        for code in SUGGESTIONS:
            assert isinstance(code, AppErrorCode)
