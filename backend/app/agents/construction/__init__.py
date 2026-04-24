"""
构建模式 Agent 入口

run_stage() 是对外暴露的唯一公共接口，由 FastAPI BackgroundTasks 调用。
它创建独立的数据库会话（不复用 HTTP 请求的会话），按阶段分发到对应的 stage 模块。
"""

import logging

from app.agents.base import emit_error_event, emit_sse_event
from app.agents.construction import (
    stage1_keyword_gen,
    stage2_retrieval,
    stage3_scoring,
    stage4_download,
    stage5_analysis,
    stage6_storage,
)
from app.agents.construction.pipeline import (
    get_record,
    mark_stage_failed,
)
from app.core.database import AsyncSessionLocal
from app.core.errors import classify_agent_error, make_envelope
from app.services.construction_service import STAGE_NAMES

logger = logging.getLogger(__name__)

_STAGE_HANDLERS = {
    1: stage1_keyword_gen.run,
    2: stage2_retrieval.run,
    3: stage3_scoring.run,
    4: stage4_download.run,
    5: stage5_analysis.run,
    6: stage6_storage.run,
}


async def run_stage(
    project_id: str,
    user_id: str,
    stage: int,
    record_id: str,
) -> None:
    """
    构建模式阶段执行入口（BackgroundTask）。

    - 自行创建和关闭 AsyncSession（不依赖 HTTP 请求作用域的 session）
    - 分发到对应 stage 处理函数
    - 任何未捕获异常均标记阶段为 failed，project 为 error，并推送 SSE 错误事件
    """
    handler = _STAGE_HANDLERS.get(stage)
    if handler is None:
        logger.error("run_stage: unknown stage %d", stage)
        return

    async with AsyncSessionLocal() as db:
        record = await get_record(db, record_id)
        if record is None:
            logger.error("run_stage: record %s not found", record_id)
            return

        # retry 操作将 modifications 写入 record.result；confirm/skip 时 result=None
        modifications = record.result or {}

        # 发送 stage_start SSE 事件
        emit_sse_event(project_id, "stage_start", {
            "stage": stage,
            "stage_name": STAGE_NAMES.get(stage, f"阶段{stage}"),
            "started_at": record.started_at.isoformat(),
        })

        try:
            await handler(db, project_id, user_id, record, modifications)
        except Exception as exc:
            logger.exception("Stage %d failed for project %s: %s", stage, project_id, exc)
            error_code = classify_agent_error(exc, "construction", stage)
            envelope = make_envelope(
                error_code,
                str(exc),
                exc=exc,
                detail={
                    "stage": stage,
                    "stage_name": STAGE_NAMES.get(stage, f"阶段{stage}"),
                },
                project_id=project_id,
                stage_record_id=record_id,
            )
            # 持久化结构化错误信封（JSON 字符串写入 stage_records.error）
            await mark_stage_failed(db, record_id, envelope.model_dump_json())
            # SSE 推送完整 ErrorEnvelope 给前端 Inspector Panel
            emit_error_event(project_id, envelope)
