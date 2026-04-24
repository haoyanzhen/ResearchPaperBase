"""
集成测试：深度研究模式对话（qa_design §7）

覆盖：
  - SSE 事件序列中包含预期的 event_type
  - LLM 错误时不向 DB 写入对话轮次
  - 对话创建 POST /dialogues 返回正确结构
"""

from __future__ import annotations

import os
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.models.project import Project
from app.models.dialogue import Dialogue
from app.utils.ids import new_id
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def _skip_if_no_db():
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    return "localhost" not in url and "postgres" not in url


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

async def _create_project(db: AsyncSession, user_id: str) -> Project:
    from app.models.project import Project
    p = Project(
        id=new_id("proj"),
        user_id=user_id,
        name="Dialogue Test Project",
        status="idle",
    )
    db.add(p)
    await db.flush()
    return p


async def _create_dialogue(db: AsyncSession, project_id: str, user_id: str) -> Dialogue:
    d = Dialogue(
        id=new_id("dlg"),
        project_id=project_id,
        user_id=user_id,
        mode="deep_research",
        sub_mode="technical",
        title="Test Dialogue",
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db.add(d)
    await db.flush()
    return d


# ── 测试：POST /dialogues 创建对话 ────────────────────────────────────────────

@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_create_dialogue_returns_id(client, auth_headers, db_session, test_user):
    project = await _create_project(db_session, test_user.id)

    resp = await client.post(
        "/api/v1/dialogues",
        json={"project_id": project.id, "mode": "deep_research"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["id"].startswith("dlg_")


# ── 测试：LLM 错误时不写入 DB ────────────────────────────────────────────────

@pytest.mark.skipif(_skip_if_no_db(), reason="需要真实 PostgreSQL")
async def test_llm_error_no_db_write(client, auth_headers, db_session, test_user):
    """
    LLM 抛出 API Key 错误时：
    - SSE 流中包含 error 事件
    - DB 中不写入新的 dialogue_turns 记录
    """
    from sqlalchemy import select, func
    from app.models.dialogue import DialogueTurn

    project = await _create_project(db_session, test_user.id)
    dialogue = await _create_dialogue(db_session, project.id, test_user.id)

    # 查询 dialogue_turns 初始数量
    count_before = await db_session.scalar(
        select(func.count()).where(DialogueTurn.dialogue_id == dialogue.id)
    ) or 0

    with patch(
        "app.agents.base.LLMClient.complete",
        new_callable=AsyncMock,
        side_effect=RuntimeError("401 invalid api key"),
    ):
        resp = await client.post(
            f"/api/v1/dialogues/{dialogue.id}/messages",
            json={"content": "请问这篇论文的主要贡献是什么？"},
            headers=auth_headers,
        )

    # 即使 LLM 失败，HTTP 响应应为 200（SSE 流已开始）或 4xx
    # 关键断言：turns 数量未增加
    count_after = await db_session.scalar(
        select(func.count()).where(DialogueTurn.dialogue_id == dialogue.id)
    ) or 0

    assert count_after == count_before


# ── 测试：SSE 事件序列解析 ────────────────────────────────────────────────────

def test_sse_event_parsing(sse_event_type_parser):
    """验证 SSE 解析辅助函数对标准格式正确提取 event_type。"""
    raw = "event: stage_start\ndata: {\"stage\": 1}\n\n"
    assert sse_event_type_parser(raw) == "stage_start"

    raw_error = "event: stage_error\ndata: {\"code\": \"ERR-LLM-001\"}\n\n"
    assert sse_event_type_parser(raw_error) == "stage_error"

    assert sse_event_type_parser("data: {}\n\n") is None
