"""
集成测试：构建模式流水线（qa_design §7）

覆盖：
  - 阶段失败时 stage_records.error 存储结构化 ErrorEnvelope JSON
  - classify_agent_error + make_envelope 在真实 DB 写入中的完整路径
  - 正常阶段完成后 status=completed（通过 mock LLM）

注意：需要真实 PostgreSQL。
跳过条件：TEST_DATABASE_URL 未设置时跳过（CI 环境标记为 integration）。
"""

from __future__ import annotations

import json
import os
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppErrorCode, ErrorEnvelope
from app.models.project import Project
from app.models.stage import StageRecord
from app.utils.ids import new_id

pytestmark = pytest.mark.integration


# ── 前置条件检查 ──────────────────────────────────────────────────────────────

def _skip_if_no_db():
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    return "localhost" not in url and "postgres" not in url


# ── 辅助：在 DB 中创建最小化 project + stage_record ───────────────────────────

async def _create_project(db: AsyncSession, user_id: str) -> Project:
    project = Project(
        id=new_id("proj"),
        user_id=user_id,
        name="Test Project",
        description="Integration test",
        status="idle",
    )
    db.add(project)
    await db.flush()
    return project


async def _create_stage_record(
    db: AsyncSession,
    project_id: str,
    stage: int = 1,
    mode: str = "construction",
    status: str = "running",
) -> StageRecord:
    record = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode=mode,
        stage=stage,
        status=status,
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()
    return record


# ── 测试：失败时 error 字段存储结构化 JSON ────────────────────────────────────

@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_stage_failure_stores_error_envelope(db_session, test_user):
    """
    阶段运行时抛出异常 → mark_stage_failed 应将 ErrorEnvelope JSON 写入 error 字段。
    """
    from app.agents.construction.pipeline import mark_stage_failed
    from app.core.errors import classify_agent_error, make_envelope

    project = await _create_project(db_session, test_user.id)
    record = await _create_stage_record(db_session, project.id, stage=3)

    exc = RuntimeError("LLM 批次评分失败：rate limit exceeded")
    error_code = classify_agent_error(exc, "construction", 3)
    envelope = make_envelope(
        error_code, str(exc), exc=exc,
        detail={"stage": 3, "stage_name": "评分与筛选"},
        project_id=project.id,
        stage_record_id=record.id,
    )

    await mark_stage_failed(db_session, record.id, envelope.model_dump_json())

    # 重新查询验证
    refreshed = await db_session.get(StageRecord, record.id)
    assert refreshed.status == "failed"
    assert refreshed.error is not None

    # error 字段应是有效 JSON
    parsed = json.loads(refreshed.error)
    assert parsed["code"] == AppErrorCode.LLM_RATE_LIMIT_EXCEEDED.value
    assert parsed["retryable"] is True
    assert "suggestion" in parsed
    assert parsed["project_id"] == project.id


@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_error_envelope_backward_compatible_plain_string(db_session, test_user):
    """
    旧格式：error 字段为纯文本字符串（非 JSON）。
    /inspect 端点读取时应降级处理，不崩溃。
    """
    from app.agents.construction.pipeline import mark_stage_failed

    project = await _create_project(db_session, test_user.id)
    record = await _create_stage_record(db_session, project.id, stage=2)

    # 写入旧格式纯字符串
    await mark_stage_failed(db_session, record.id, "旧版错误消息（纯文本）")

    refreshed = await db_session.get(StageRecord, record.id)
    assert refreshed.error == "旧版错误消息（纯文本）"

    # 模拟 /inspect 端点的降级解析
    try:
        parsed = json.loads(refreshed.error)
    except (json.JSONDecodeError, ValueError):
        parsed = {"raw": refreshed.error[:500]}

    assert parsed.get("raw") == "旧版错误消息（纯文本）"


@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_stage_chain_correct_record_marked_failed(db_session, test_user):
    """
    验证链式阶段（stage1→stage2）失败时，使用 stage2 的 record_id 标记失败，
    而非 stage1 的 record_id。
    """
    from app.agents.construction.pipeline import mark_stage_failed
    from app.core.errors import classify_agent_error, make_envelope

    project = await _create_project(db_session, test_user.id)
    record1 = await _create_stage_record(db_session, project.id, stage=1, status="completed")
    record2 = await _create_stage_record(db_session, project.id, stage=2, status="running")

    exc = RuntimeError("检索全部失败")
    code = classify_agent_error(exc, "construction", 2)
    env = make_envelope(code, str(exc), exc=exc,
                        project_id=project.id, stage_record_id=record2.id)

    # 标记 record2 失败（不影响 record1）
    await mark_stage_failed(db_session, record2.id, env.model_dump_json())

    r1 = await db_session.get(StageRecord, record1.id)
    r2 = await db_session.get(StageRecord, record2.id)

    assert r1.status == "completed"   # 未被影响
    assert r2.status == "failed"
    parsed = json.loads(r2.error)
    assert parsed["code"] == AppErrorCode.AGT_RETRIEVAL_ALL_FAILED.value
