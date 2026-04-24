import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.logging import setup_logging

# 在所有其他初始化之前配置结构化日志（qa_design §9）
setup_logging()

logger = logging.getLogger(__name__)


async def _auto_push_job() -> None:
    """
    定时任务：检查所有启用了自动推送且 next_push_at <= now() 的课题，
    触发构建流程 stage1（FR-010）。
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import AsyncSessionLocal
    from app.models.project import Project

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Project).where(
                Project.auto_push == True,
                Project.next_push_at <= now,
                Project.status != "running",
            )
        )
        projects = list(res.scalars().all())

    if not projects:
        return

    logger.info("auto_push_job: %d project(s) due for push", len(projects))

    from app.agents.construction.pipeline import run_stage
    from app.services import construction_service

    for project in projects:
        try:
            async with AsyncSessionLocal() as db:
                record, err = await construction_service.start_construction(
                    db=db,
                    project_id=project.id,
                    user_id=project.user_id,
                    databases=["arxiv", "openalex"],
                    score_threshold=7,
                )
            if err:
                logger.warning("auto_push start_construction error for %s: %s", project.id, err)
                continue
            # 在独立协程中运行阶段，避免阻塞调度循环
            import asyncio
            asyncio.create_task(run_stage(project.id, project.user_id, 1, record.id))
            logger.info("auto_push triggered for project %s (record=%s)", project.id, record.id)
        except Exception as exc:
            logger.error("auto_push failed for project %s: %s", project.id, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 启动：配置定时调度器（FR-010）──────────────────────────────────────────
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            _auto_push_job,
            trigger="interval",
            minutes=5,
            id="auto_push_check",
            replace_existing=True,
            misfire_grace_time=60,
        )
        scheduler.start()
        logger.info("APScheduler started: auto_push_check every 5 minutes")
    except ImportError:
        logger.warning("apscheduler not installed; FR-010 auto-push scheduler disabled")
    except Exception as exc:
        logger.error("Failed to start APScheduler: %s", exc)

    yield

    # ── 关闭：停止调度器 ────────────────────────────────────────────────────────
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


app = FastAPI(
    title="Research Paper Base API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 生产环境替换为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health", tags=["健康检查"], summary="进程存活探针（根路径，供 Docker 使用）")
async def health_root():
    """
    轻量存活探针，无需认证，不访问数据库。
    详细健康检查请使用 GET /api/v1/health/*。
    """
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
