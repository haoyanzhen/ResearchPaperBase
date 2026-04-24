from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.logging import setup_logging

# 在所有其他初始化之前配置结构化日志（qa_design §9）
setup_logging()

app = FastAPI(
    title="Research Paper Base API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
