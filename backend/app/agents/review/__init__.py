"""
综述模式 Agent 入口（FR-020~024）

run_stage() 是对外暴露的唯一公共接口，由 FastAPI BackgroundTasks 调用。
它创建独立的数据库会话（不复用 HTTP 请求的会话），按阶段分发到对应的 stage 模块。

综述模式阶段（mode='review'）：
  1 — 课题扩写（自动完成后链接阶段 2）
  2 — 综述架构生成（暂停，等待用户确认）
  3 — 章节内容撰写（自动完成后链接阶段 4）
  4 — 自动审查迭代（暂停，等待用户调用 compile）
  5 — 综述文章汇总（完成，项目回归 idle）

外部调用点：
  - review.py: start_review → stage 1
  - review.py: confirm_outline → stage 3
  - review.py: compile_outline → stage 5
"""

import logging

from app.agents.base import emit_sse_event
from app.agents.review import (
    stage1_topic_expansion,
    stage2_outline_gen,
    stage3_chapter_writing,
    stage4_auto_review,
    stage5_compile,
)
from app.agents.review.pipeline import (
    REVIEW_STAGE_NAMES,
    get_record,
    mark_stage_failed,
)
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_STAGE_HANDLERS = {
    1: stage1_topic_expansion.run,
    2: stage2_outline_gen.run,
    3: stage3_chapter_writing.run,
    4: stage4_auto_review.run,
    5: stage5_compile.run,
}


async def run_stage(
    project_id: str,
    user_id: str,
    stage: int,
    record_id: str,
) -> None:
    """
    综述模式阶段执行入口（BackgroundTask）。

    - 自行创建和关闭 AsyncSession（不依赖 HTTP 请求作用域的 session）
    - 分发到对应 stage 处理函数
    - 任何未捕获异常均标记阶段为 failed，project 为 error，并推送 SSE 错误事件
    """
    handler = _STAGE_HANDLERS.get(stage)
    if handler is None:
        logger.error("review run_stage: unknown stage %d", stage)
        return

    async with AsyncSessionLocal() as db:
        record = await get_record(db, record_id)
        if record is None:
            logger.error("review run_stage: record %s not found", record_id)
            return

        modifications = record.result or {}

        emit_sse_event(project_id, "stage_start", {
            "stage": stage,
            "stage_name": REVIEW_STAGE_NAMES.get(stage, f"综述阶段{stage}"),
            "started_at": record.started_at.isoformat(),
        })

        try:
            await handler(db, project_id, user_id, record, modifications)
        except Exception as exc:
            logger.exception("Review Stage %d failed for project %s: %s", stage, project_id, exc)
            await mark_stage_failed(db, record_id, str(exc))
            emit_sse_event(project_id, "stage_error", {
                "stage": stage,
                "error": str(exc),
                "retryable": True,
            })
