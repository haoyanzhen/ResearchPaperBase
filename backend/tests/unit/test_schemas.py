"""
单元测试：Pydantic Schema 校验（qa_design §7）

覆盖：
  - CheckResult / ShallowHealthResponse / DbHealthResponse
  - DeepHealthResponse / PipelineHealthResponse
  - ErrorEnvelope JSON 序列化/反序列化往返
  - InspectResponse recommendations 字段
"""

import pytest
from pydantic import ValidationError

from app.core.errors import ErrorEnvelope
from app.schemas.health import (
    CheckResult,
    DbChecks,
    DbHealthResponse,
    DeepChecks,
    DeepHealthResponse,
    InspectResponse,
    PipelineHealthResponse,
    ShallowHealthResponse,
    StageSnapshot,
)


# ── CheckResult ───────────────────────────────────────────────────────────────

class TestCheckResult:
    def test_ok_minimal(self):
        cr = CheckResult(status="ok")
        assert cr.status == "ok"
        assert cr.latency_ms is None
        assert cr.code is None

    def test_error_with_code(self):
        cr = CheckResult(status="error", code="ERR-LLM-001", suggestion="update key")
        assert cr.code == "ERR-LLM-001"
        assert cr.suggestion == "update key"

    def test_valid_statuses(self):
        for status in ("ok", "error", "degraded", "not_configured"):
            cr = CheckResult(status=status)
            assert cr.status == status


# ── ShallowHealthResponse ────────────────────────────────────────────────────

class TestShallowHealthResponse:
    def test_required_fields(self):
        r = ShallowHealthResponse(status="ok", version="1.0.0", timestamp="2026-04-24T00:00:00+00:00")
        assert r.status == "ok"
        assert r.version == "1.0.0"

    def test_missing_version_raises(self):
        with pytest.raises(ValidationError):
            ShallowHealthResponse(status="ok", timestamp="2026-04-24T00:00:00Z")


# ── DbHealthResponse ──────────────────────────────────────────────────────────

class TestDbHealthResponse:
    def test_valid(self):
        r = DbHealthResponse(
            status="ok",
            checks=DbChecks(postgresql=CheckResult(status="ok", latency_ms=3.2)),
        )
        assert r.checks.postgresql.latency_ms == 3.2

    def test_error_status(self):
        r = DbHealthResponse(
            status="error",
            checks=DbChecks(postgresql=CheckResult(status="error", message="timeout")),
        )
        assert r.status == "error"


# ── DeepHealthResponse ────────────────────────────────────────────────────────

class TestDeepHealthResponse:
    def _make_check(self, status="ok"):
        return CheckResult(status=status)

    def test_all_ok(self):
        r = DeepHealthResponse(
            status="ok",
            checks=DeepChecks(
                llm_primary=self._make_check("ok"),
                llm_fallback=self._make_check("ok"),
                arxiv=self._make_check("ok"),
                openalex=self._make_check("ok"),
                semantic_scholar=self._make_check("ok"),
                ads=self._make_check("ok"),
                smtp=self._make_check("ok"),
            ),
            summary="All systems operational",
        )
        assert r.status == "ok"

    def test_degraded_status(self):
        r = DeepHealthResponse(
            status="degraded",
            checks=DeepChecks(
                llm_primary=self._make_check("ok"),
                llm_fallback=self._make_check("not_configured"),
                arxiv=self._make_check("error"),
                openalex=self._make_check("ok"),
                semantic_scholar=self._make_check("ok"),
                ads=self._make_check("not_configured"),
                smtp=self._make_check("ok"),
            ),
            summary="1 service unavailable",
        )
        assert r.status == "degraded"


# ── PipelineHealthResponse ────────────────────────────────────────────────────

class TestPipelineHealthResponse:
    def test_minimal(self):
        r = PipelineHealthResponse(
            project_id="proj_abc",
            project_status="running",
            mode="construction",
            active_stages=[],
            last_error=None,
        )
        assert r.project_id == "proj_abc"
        assert r.active_stages == []

    def test_with_stage_snapshot(self):
        snap = StageSnapshot(
            stage_record_id="sr_001",
            stage=3,
            mode="construction",
            status="running",
            started_at="2026-04-24T10:00:00+00:00",
            elapsed_seconds=120,
            result_preview=None,
            error_preview=None,
            pending_user_action=None,
        )
        r = PipelineHealthResponse(
            project_id="proj_abc",
            project_status="running",
            mode="construction",
            active_stages=[snap],
            last_error=None,
        )
        assert r.active_stages[0].stage == 3


# ── ErrorEnvelope JSON 往返 ───────────────────────────────────────────────────

class TestErrorEnvelopeRoundTrip:
    def test_serialize_deserialize(self):
        env = ErrorEnvelope(
            code="ERR-LLM-002",
            message="rate limited",
            retryable=True,
            suggestion="wait and retry",
            occurred_at="2026-04-24T00:00:00+00:00",
            project_id="proj_xyz",
            stage_record_id="sr_003",
        )
        json_str = env.model_dump_json()
        restored = ErrorEnvelope.model_validate_json(json_str)
        assert restored.code == env.code
        assert restored.retryable is True
        assert restored.project_id == "proj_xyz"

    def test_partial_fields_roundtrip(self):
        env = ErrorEnvelope(code="ERR-VAL-001", message="not found")
        data = env.model_dump()
        restored = ErrorEnvelope(**data)
        assert restored.message == "not found"
        assert restored.traceback is None


# ── InspectResponse recommendations ─────────────────────────────────────────

class TestInspectResponseRecommendations:
    def test_recommendations_is_list(self):
        r = InspectResponse(
            snapshot_at="2026-04-24T00:00:00+00:00",
            project={"id": "proj_abc", "name": "Test", "status": "idle"},
            stage_history=[],
            keyword_summary={"total": 0, "search_done": 0, "pending": 0},
            paper_summary={
                "total": 0, "valid": 0, "invalid": 0,
                "downloaded": 0, "analyzed": 0,
            },
            config_status={
                "llm_configured": False,
                "llm_active_provider": None,
                "paper_db_sources": [],
                "smtp_configured": False,
            },
            recommendations=["[FATAL] LLM 未配置，所有 Agent 任务将失败"],
        )
        assert isinstance(r.recommendations, list)
        assert len(r.recommendations) == 1
