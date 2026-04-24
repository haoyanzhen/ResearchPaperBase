"""
HTTP 路由 — 健康检查与流水线状态（qa_design.md §5）

端点：
  GET /health                       浅层探针（无需认证，进程存活检查）
  GET /health/db                    数据库连通性探针（无需认证）
  GET /health/deep                  全依赖探针（需认证：LLM + 外部 API + SMTP）
  GET /health/pipeline/{project_id} 流水线状态快照（需认证）

状态枚举（全量）：
  ok             所有检查通过
  degraded       部分非必需依赖不可用，系统降级运行
  error          核心依赖（LLM / DB）不可用，系统不可用
  not_configured 依赖未配置（非错误）
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine, get_db
from app.core.deps import get_current_user
from app.core.errors import AppErrorCode
from app.models.project import Project
from app.models.stage import StageRecord
from app.models.user import User
from app.schemas.common import ok
from app.schemas.health import (
    CheckResult,
    DbChecks,
    DbHealthResponse,
    DeepChecks,
    DeepHealthResponse,
    PipelineHealthResponse,
    ShallowHealthResponse,
    StageSnapshot,
)
from app.services.config_service import (
    get_all_llm_providers,
    get_databases_config,
    get_email_config,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["健康检查"])

# 每个数据库的默认探测端点
_DEFAULT_ENDPOINTS: dict[str, str] = {
    "arxiv":            "https://export.arxiv.org/api/query?search_query=cat:cs.AI&max_results=1",
    "openalex":         "https://api.openalex.org/works?filter=relevance_score:>0&per-page=1&select=id",
    "semantic_scholar": "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
    "ads":              "https://api.adsabs.harvard.edu/v1/search/query?q=star&rows=1",
}

# 构建模式阶段用户操作提示
_CONSTRUCTION_PENDING_ACTIONS: dict[int, str] = {
    1: "confirm_keyword_results",
    2: "confirm_retrieval_results",
    3: "confirm_scoring_results",
    4: "confirm_download_results",
    5: "confirm_analysis_results",
    6: "confirm_storage_trigger_email",
}

# 综述模式阶段用户操作提示
_REVIEW_PENDING_ACTIONS: dict[int, str] = {
    2: "confirm_outline",
    4: "trigger_compile",
}


# =============================================================================
# 辅助：单次 HTTP 探测
# =============================================================================

async def _probe_http(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 5.0,
) -> tuple[bool, int | None, float]:
    """
    发起 GET 请求探测 URL 连通性。

    Returns:
        (ok, status_code, latency_ms)
    """
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers or {})
            latency = (time.monotonic() - start) * 1000
            return resp.status_code < 500, resp.status_code, latency
    except Exception:
        latency = (time.monotonic() - start) * 1000
        return False, None, latency


# =============================================================================
# GET /health（浅层探针，公开）
# =============================================================================

@router.get("", summary="浅层存活探针")
async def health_shallow():
    """
    无认证要求，供 Docker/K8s liveness probe 使用。
    仅验证 FastAPI 进程存活，不访问数据库。

    目标响应时间 < 50ms。
    """
    return ok(ShallowHealthResponse(
        status="ok",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))


# =============================================================================
# GET /health/db（数据库连通性探针，公开）
# =============================================================================

@router.get("/db", summary="数据库连通性探针")
async def health_db():
    """
    探测 PostgreSQL 连接状态。公开端点，供 readiness probe 使用。

    目标响应时间 < 200ms。
    """
    start = time.monotonic()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.monotonic() - start) * 1000

        # 连接池状态
        pool = engine.pool
        pool_size = getattr(pool, "size", lambda: None)()
        checked_out = getattr(pool, "checkedout", lambda: None)()

        pg_check = CheckResult(
            status="ok",
            latency_ms=round(latency, 1),
        )
        return ok(DbHealthResponse(
            status="ok",
            checks=DbChecks(postgresql=pg_check),
        ))

    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        logger.error("Health DB check failed: %s", exc)
        pg_check = CheckResult(
            status="error",
            latency_ms=round(latency, 1),
            code=AppErrorCode.DB_CONNECTION_FAILED.value,
            message=f"PostgreSQL 连接失败：{exc}",
            suggestion=AppErrorCode.DB_CONNECTION_FAILED.value,
        )
        from fastapi import Response
        from fastapi.responses import JSONResponse
        from app.schemas.common import ApiResponse
        body = ApiResponse(
            code=1,
            data=DbHealthResponse(status="error", checks=DbChecks(postgresql=pg_check)),
            message="数据库不可用",
        )
        return JSONResponse(status_code=503, content=body.model_dump())


# =============================================================================
# GET /health/deep（全依赖探针，需认证）
# =============================================================================

@router.get("/deep", summary="全依赖探针（LLM + 外部 API + SMTP）")
async def health_deep(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    并发探测所有外部依赖：LLM（主+备）、学术数据库、SMTP。

    目标响应时间 < 5s（全并发）。
    整体状态规则：
      - LLM 主模型 error → status=error
      - 其他依赖有 error → status=degraded
      - 仅有 not_configured → status=ok
      - 全部 ok → status=ok
    """
    user_id = current_user.id

    # ── 并发读取配置（不阻塞探测）────────────────────────────────────────────
    providers, db_configs, email_cfg = await asyncio.gather(
        get_all_llm_providers(db, user_id),
        get_databases_config(db, user_id),
        get_email_config(db, user_id),
        return_exceptions=True,
    )

    if isinstance(providers, Exception):
        providers = []
    if isinstance(db_configs, Exception):
        db_configs = {}
    if isinstance(email_cfg, Exception):
        email_cfg = {}

    # ── 并发执行所有探测 ────────────────────────────────────────────────────
    checks_coros = [
        _check_llm_primary(db, user_id, providers),
        _check_llm_fallback(providers),
        _check_external_db("arxiv",            db_configs),
        _check_external_db("openalex",         db_configs),
        _check_external_db("semantic_scholar",  db_configs),
        _check_external_db("ads",               db_configs),
        _check_smtp(email_cfg),
    ]
    results = await asyncio.gather(*checks_coros, return_exceptions=True)

    # 若某个探测本身抛了异常，回退为 error 状态
    def _safe(r: CheckResult | Exception, label: str) -> CheckResult:
        if isinstance(r, Exception):
            logger.warning("Health probe '%s' raised: %s", label, r)
            return CheckResult(status="error", message=str(r))
        return r

    llm_primary, llm_fallback, arxiv, openalex, ss, ads, smtp = (
        _safe(r, label) for r, label in zip(
            results,
            ["llm_primary", "llm_fallback", "arxiv", "openalex", "semantic_scholar", "ads", "smtp"]
        )
    )

    # ── 计算整体状态 ────────────────────────────────────────────────────────
    overall, summary = _compute_deep_status(
        llm_primary, llm_fallback, arxiv, openalex, ss, ads, smtp
    )

    return ok(DeepHealthResponse(
        status=overall,
        checks=DeepChecks(
            llm_primary=llm_primary,
            llm_fallback=llm_fallback,
            arxiv=arxiv,
            openalex=openalex,
            semantic_scholar=ss,
            ads=ads,
            smtp=smtp,
        ),
        summary=summary,
    ))


async def _check_llm_primary(db: AsyncSession, user_id: str, providers: list[dict]) -> CheckResult:
    """探测用户激活的 LLM 主模型，发送 1-token 测试请求。"""
    active = next((p for p in providers if p.get("is_active")), None)
    if active is None:
        active = providers[0] if providers else None
    if active is None:
        return CheckResult(
            status="not_configured",
            code=AppErrorCode.LLM_NO_CONFIG.value,
            message="未配置任何 LLM 提供商",
            suggestion="在「设置 → LLM 配置」添加模型，或联系管理员配置系统级默认模型",
        )

    provider_name = active.get("provider", "unknown")
    url = f"{active.get('url', '').rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {active.get('api_key', '')}"}
    payload = {
        "model": active.get("default_model", "gpt-4o-mini"),
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            latency = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                return CheckResult(
                    status="ok",
                    latency_ms=round(latency, 1),
                    message=f"provider={provider_name}, model={active.get('default_model')}",
                )
            elif resp.status_code == 401:
                return CheckResult(
                    status="error",
                    latency_ms=round(latency, 1),
                    code=AppErrorCode.LLM_API_KEY_INVALID.value,
                    message=f"API 密钥无效（provider={provider_name}）",
                    suggestion="在「设置 → LLM 配置」更新 API 密钥",
                )
            elif resp.status_code == 429:
                return CheckResult(
                    status="degraded",
                    latency_ms=round(latency, 1),
                    code=AppErrorCode.LLM_RATE_LIMIT_EXCEEDED.value,
                    message=f"速率限制（provider={provider_name}）",
                    suggestion="等待后重试；建议配置备用模型",
                )
            else:
                return CheckResult(
                    status="error",
                    latency_ms=round(latency, 1),
                    code=AppErrorCode.LLM_TIMEOUT.value,
                    message=f"HTTP {resp.status_code}（provider={provider_name}）",
                )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            status="error",
            latency_ms=round(latency, 1),
            code=AppErrorCode.LLM_TIMEOUT.value,
            message=f"连接失败（provider={provider_name}）：{exc}",
            suggestion="检查网络连接和 LLM 服务 URL",
        )


async def _check_llm_fallback(providers: list[dict]) -> CheckResult:
    """检查是否配置了备用 LLM（非活跃的第二个 provider）。"""
    non_active = [p for p in providers if not p.get("is_active")]
    if not non_active:
        return CheckResult(
            status="not_configured",
            message="未配置备用 LLM，主模型故障时无法自动切换",
            suggestion="建议在管理员面板配置至少一个系统级备用模型",
        )
    return CheckResult(
        status="ok",
        message=f"已配置 {len(non_active)} 个备用 LLM 提供商",
    )


async def _check_external_db(db_name: str, db_configs: dict) -> CheckResult:
    """探测学术数据库 API 连通性。"""
    cfg = db_configs.get(db_name, {})
    enabled = cfg.get("enabled", db_name != "ads")

    if not enabled:
        return CheckResult(status="not_configured", message=f"{db_name} 已禁用")

    api_key = cfg.get("api_key")
    custom_endpoint = cfg.get("endpoint")

    # 构造探测 URL
    if db_name == "arxiv":
        url = custom_endpoint or _DEFAULT_ENDPOINTS["arxiv"]
        probe_headers = {}
    elif db_name == "openalex":
        base = custom_endpoint or "https://api.openalex.org"
        url = f"{base}/works?filter=relevance_score:>0&per-page=1&select=id"
        probe_headers = {}
    elif db_name == "semantic_scholar":
        base = custom_endpoint or "https://api.semanticscholar.org"
        url = f"{base}/graph/v1/paper/search?query=test&limit=1"
        probe_headers = {"x-api-key": api_key} if api_key else {}
    elif db_name == "ads":
        if not api_key:
            return CheckResult(
                status="not_configured",
                code=AppErrorCode.ADS_KEY_INVALID.value,
                message="ADS API 密钥未配置",
                suggestion="在「设置 → 论文数据库」配置 ADS API 密钥",
            )
        base = custom_endpoint or "https://api.adsabs.harvard.edu"
        url = f"{base}/v1/search/query?q=star&rows=1"
        probe_headers = {"Authorization": f"Bearer {api_key}"}
    else:
        return CheckResult(status="not_configured", message=f"未知数据源 {db_name}")

    success, status_code, latency = await _probe_http(url, headers=probe_headers)

    if success:
        return CheckResult(status="ok", latency_ms=round(latency, 1))

    # 错误分类
    if status_code == 403 and db_name in ("openalex", "ads"):
        err_code = AppErrorCode.OPENALEX_KEY_INVALID if db_name == "openalex" else AppErrorCode.ADS_KEY_INVALID
        return CheckResult(
            status="error",
            latency_ms=round(latency, 1),
            code=err_code.value,
            message=f"HTTP 403：API 密钥无效",
            suggestion=f"在「设置 → 论文数据库」更新 {db_name} API 密钥",
        )
    if status_code is None:
        return CheckResult(
            status="error",
            latency_ms=round(latency, 1),
            code=AppErrorCode.ARXIV_UNREACHABLE.value,
            message=f"{db_name} 不可达（连接超时或 DNS 失败）",
            suggestion="检查网络连通性",
        )
    return CheckResult(
        status="error",
        latency_ms=round(latency, 1),
        code=AppErrorCode.ARXIV_UNREACHABLE.value,
        message=f"{db_name} 返回 HTTP {status_code}",
    )


async def _check_smtp(email_cfg: dict) -> CheckResult:
    """探测 SMTP 服务连通性（TCP 握手，不发送邮件）。"""
    host = email_cfg.get("smtp_host")
    port = email_cfg.get("smtp_port")

    if not host:
        return CheckResult(
            status="not_configured",
            message="SMTP 未配置，邮件推送功能不可用",
            suggestion="在「设置 → 邮件」配置 SMTP 服务器",
        )

    port = port or 587
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5.0,
        )
        writer.close()
        await writer.wait_closed()
        latency = (time.monotonic() - start) * 1000
        return CheckResult(status="ok", latency_ms=round(latency, 1), message=f"{host}:{port}")
    except asyncio.TimeoutError:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            status="error",
            latency_ms=round(latency, 1),
            code=AppErrorCode.SMTP_SEND_FAILED.value,
            message=f"SMTP 连接超时：{host}:{port}",
            suggestion="检查 SMTP 主机名和端口是否正确",
        )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return CheckResult(
            status="error",
            latency_ms=round(latency, 1),
            code=AppErrorCode.SMTP_AUTH_FAILED.value,
            message=f"SMTP 连接失败：{exc}",
            suggestion="检查 SMTP 配置并确认防火墙规则",
        )


def _compute_deep_status(
    llm_primary: CheckResult,
    llm_fallback: CheckResult,
    arxiv: CheckResult,
    openalex: CheckResult,
    ss: CheckResult,
    ads: CheckResult,
    smtp: CheckResult,
) -> tuple[str, str]:
    """
    根据各检查结果计算整体状态和摘要文字。

    Returns:
        (overall_status, summary_text)
    """
    if llm_primary.status == "error":
        return "error", f"LLM 主模型不可用（{llm_primary.message}），所有 AI 功能已停止"

    error_items = [
        name for name, check in [
            ("OpenAlex", openalex), ("Semantic Scholar", ss), ("ADS", ads), ("SMTP", smtp)
        ]
        if check.status == "error"
    ]
    degraded_items = [
        name for name, check in [
            ("arXiv", arxiv), ("LLM备用", llm_fallback)
        ]
        if check.status in ("error", "not_configured")
    ]

    if error_items:
        items_str = "、".join(error_items)
        return "degraded", f"{len(error_items)} 个依赖异常（{items_str}），系统降级运行"

    not_cfg = [
        name for name, check in [
            ("OpenAlex", openalex), ("Semantic Scholar", ss), ("ADS", ads), ("SMTP", smtp)
        ]
        if check.status == "not_configured"
    ]
    if not_cfg:
        return "ok", f"全部核心依赖正常；{len(not_cfg)} 个可选依赖未配置（{', '.join(not_cfg)}）"

    return "ok", "所有依赖正常"


# =============================================================================
# GET /health/pipeline/{project_id}（流水线状态快照，需认证）
# =============================================================================

@router.get("/pipeline/{project_id}", summary="流水线阶段状态快照")
async def health_pipeline(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回指定项目当前的流水线快照：
      - 所有 running/paused 的阶段记录（active_stages）
      - 最近一次 failed 的错误详情（last_error）
    """
    from app.services.project_service import get_project

    project = await get_project(db, project_id, current_user.id)
    if project is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    # 获取 running/paused 阶段记录
    active_res = await db.execute(
        select(StageRecord)
        .where(
            StageRecord.project_id == project_id,
            StageRecord.status.in_(["running", "paused"]),
        )
        .order_by(StageRecord.started_at.desc())
    )
    active_records = list(active_res.scalars().all())

    # 获取最近一次 failed 记录
    failed_res = await db.execute(
        select(StageRecord)
        .where(
            StageRecord.project_id == project_id,
            StageRecord.status == "failed",
        )
        .order_by(StageRecord.failed_at.desc())
        .limit(1)
    )
    last_failed = failed_res.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    def _build_snapshot(record: StageRecord) -> StageSnapshot:
        elapsed: float | None = None
        if record.started_at:
            elapsed = round((now - record.started_at).total_seconds(), 1)

        # result_preview: 取 result 中前 3 个 key
        result_preview: dict | None = None
        if record.result:
            preview_keys = list(record.result.keys())[:3]
            result_preview = {k: record.result[k] for k in preview_keys}

        # error_preview
        error_preview: str | None = None
        if record.error:
            error_preview = record.error[:200]

        # pending_user_action
        pending: str | None = None
        if record.status == "paused":
            if record.mode == "construction":
                pending = _CONSTRUCTION_PENDING_ACTIONS.get(record.stage)
            elif record.mode == "review":
                pending = _REVIEW_PENDING_ACTIONS.get(record.stage)

        return StageSnapshot(
            stage_record_id=record.id,
            stage=record.stage,
            mode=record.mode,
            status=record.status,
            started_at=record.started_at.isoformat() if record.started_at else "",
            elapsed_seconds=elapsed,
            result_preview=result_preview,
            error_preview=error_preview,
            pending_user_action=pending,
        )

    # last_error: 尝试解析为 ErrorEnvelope dict，否则返回 raw
    last_error_data: dict | None = None
    if last_failed and last_failed.error:
        try:
            last_error_data = json.loads(last_failed.error)
        except (json.JSONDecodeError, TypeError):
            last_error_data = {"raw": last_failed.error[:500]}

    return ok(PipelineHealthResponse(
        project_id=project_id,
        project_status=project.status,
        mode=project.mode,
        active_stages=[_build_snapshot(r) for r in active_records],
        last_error=last_error_data,
    ))
