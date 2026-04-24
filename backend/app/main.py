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

    from app.agents.construction.pipeline import run_stage, get_pipeline_params
    from app.services import construction_service, project_service

    import asyncio

    for project in projects:
        try:
            # 读取上次构建使用的数据库列表；找不到则用全套默认值
            async with AsyncSessionLocal() as db:
                try:
                    params = await get_pipeline_params(db, project.id)
                    databases = params.get("databases") or ["arxiv", "openalex", "semantic_scholar"]
                    score_threshold = params.get("score_threshold") or 7
                except Exception:
                    databases = ["arxiv", "openalex", "semantic_scholar"]
                    score_threshold = 7

                record, err = await construction_service.start_construction(
                    db=db,
                    project_id=project.id,
                    user_id=project.user_id,
                    databases=databases,
                    score_threshold=score_threshold,
                )
                if err:
                    logger.warning("auto_push start_construction error for %s: %s", project.id, err)
                    continue

                # P0 Fix：立即推进 next_push_at 防止调度循环重复触发
                # （Stage 7 完成后会再次精确重算；此处仅防止短期重入）
                await project_service.update_schedule(
                    db, project, project.auto_push, project.push_interval
                )

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
