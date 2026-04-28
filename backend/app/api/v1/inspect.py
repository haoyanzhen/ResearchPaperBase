"""
HTTP 路由 — 诊断快照端点（qa_design.md §6）

端点：
  GET /projects/{project_id}/inspect

返回项目的完整诊断快照：
  - 项目基本信息（project）
  - 所有阶段执行历史（stage_history），含 ErrorEnvelope 解析
  - 关键词摘要（keyword_summary）
  - 论文统计（paper_summary）
  - 配置状态（config_status）
  - 自动生成的修复建议（recommendations）

权限：项目所有者 或 管理员。
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import AppErrorCode
from app.models.dialogue import ResearchDialogue
from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Keyword, Project
from app.models.stage import StageRecord
from app.models.user import User
from app.schemas.common import ok
from app.schemas.health import (
    ConfigStatus,
    InspectResponse,
    KeywordSummary,
    PaperSummary,
    StageHistoryItem,
)
from app.services.config_service import (
    get_all_llm_providers,
    get_databases_config,
    get_effective_email_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["诊断"])


# =============================================================================
# GET /projects/{project_id}/inspect
# =============================================================================

@router.get("/projects/{project_id}/inspect", summary="项目诊断快照")
async def inspect_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    返回项目的完整诊断快照（qa_design.md §6）。

    访问限制：项目所有者或管理员（非所有者且非管理员返回 404，避免信息泄露）。
    """
    # ── 1. 获取项目，权限校验 ────────────────────────────────────────────────
    proj_res = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_res.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    if project.user_id != current_user.id and not current_user.is_admin:
        # 对非所有者返回 404，防止项目 ID 枚举
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    user_id = project.user_id   # 读取配置时用项目所有者 ID

    # ── 2. 并发获取所有诊断数据 ──────────────────────────────────────────────
    import asyncio
    (
        stage_records,
        keyword_stats,
        paper_stats,
        providers,
        db_cfgs,
        email_cfg,
    ) = await asyncio.gather(
        _get_stage_history(db, project_id),
        _get_keyword_summary(db, project_id),
        _get_paper_summary(db, project_id),
        get_all_llm_providers(db, user_id),
        get_databases_config(db, user_id),
        get_effective_email_config(db, user_id),
        return_exceptions=True,
    )

    # 容错：单个查询失败不影响整体
    if isinstance(stage_records, Exception):
        logger.warning("inspect: stage_records query failed: %s", stage_records)
        stage_records = []
    if isinstance(keyword_stats, Exception):
        keyword_stats = {"total": 0, "search_done": 0, "pending": 0}
    if isinstance(paper_stats, Exception):
        paper_stats = {"total": 0, "valid": 0, "invalid": 0, "downloaded": 0, "analyzed": 0}
    if isinstance(providers, Exception):
        providers = []
    if isinstance(db_cfgs, Exception):
        db_cfgs = {}
    if isinstance(email_cfg, Exception):
        email_cfg = {}

    # ── 3. 构建 config_status ────────────────────────────────────────────────
    active_llm = next((p for p in providers if p.get("is_active")), None) or (providers[0] if providers else None)
    paper_db_sources = [
        db_name for db_name, config in db_cfgs.items()
        if config.get("enabled")
    ]
    config_status = ConfigStatus(
        llm_configured=active_llm is not None,
        llm_active_provider=active_llm.get("provider") if active_llm else None,
        paper_db_sources=paper_db_sources,
        smtp_configured=bool(email_cfg.get("smtp_host")),
    )

    # ── 4. 构建 stage_history 列表 ───────────────────────────────────────────
    history_items = [_build_history_item(r) for r in stage_records]

    # ── 5. 自动生成修复建议 ──────────────────────────────────────────────────
    recommendations = _generate_recommendations(
        project=project,
        stage_records=stage_records,
        paper_stats=paper_stats,
        config_status=config_status,
    )

    # ── 6. 组装响应 ──────────────────────────────────────────────────────────
    project_dict = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "mode": project.mode,
        "status": project.status,
        "total_papers": project.total_papers,
        "valid_papers": project.valid_papers,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }

    return ok(InspectResponse(
        snapshot_at=datetime.now(timezone.utc).isoformat(),
        project=project_dict,
        stage_history=history_items,
        keyword_summary=KeywordSummary(**keyword_stats),
        paper_summary=PaperSummary(**paper_stats),
        config_status=config_status,
        recommendations=recommendations,
    ))


# =============================================================================
# 内部查询辅助函数
# =============================================================================

async def _get_stage_history(db, project_id: str) -> list[StageRecord]:
    """获取项目所有阶段记录，按 started_at 降序（最近在前）。"""
    res = await db.execute(
        select(StageRecord)
        .where(StageRecord.project_id == project_id)
        .order_by(StageRecord.started_at.desc())
    )
    return list(res.scalars().all())


async def _get_keyword_summary(db, project_id: str) -> dict:
    """统计关键词数量。"""
    res = await db.execute(
        select(
            func.count().label("total"),
            func.sum(Keyword.is_searched.cast(int)).label("search_done"),
        ).where(Keyword.project_id == project_id)
    )
    row = res.one()
    total = int(row.total or 0)
    search_done = int(row.search_done or 0)
    return {
        "total": total,
        "search_done": search_done,
        "pending": max(total - search_done, 0),
    }


async def _get_paper_summary(db, project_id: str) -> dict:
    """统计项目关联论文的各状态数量。"""
    res = await db.execute(
        select(
            func.count().label("total_in_db"),
            func.sum(ProjectPaperRelation.is_valid.cast(int)).label("valid"),
        ).where(ProjectPaperRelation.project_id == project_id)
    )
    rel_row = res.one()

    # 下载成功：papers.download_status = 'success'，通过 JOIN 统计
    dl_res = await db.execute(
        select(func.count())
        .select_from(ProjectPaperRelation)
        .join(Paper, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            Paper.download_status == "success",
        )
    )
    download_success = dl_res.scalar() or 0

    # AI 分析完成：papers.ai_analysis_status = 'success'
    ai_res = await db.execute(
        select(func.count())
        .select_from(ProjectPaperRelation)
        .join(Paper, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            Paper.ai_analysis_status == "success",
        )
    )
    ai_analyzed = ai_res.scalar() or 0

    return {
        "total": int(rel_row.total_in_db or 0),
        "valid": int(rel_row.valid or 0),
        "invalid": max(int(rel_row.total_in_db or 0) - int(rel_row.valid or 0), 0),
        "downloaded": download_success,
        "analyzed": ai_analyzed,
    }


def _build_history_item(record: StageRecord) -> StageHistoryItem:
    """将 StageRecord ORM 对象转换为 StageHistoryItem schema。"""
    elapsed: float | None = None
    start = record.started_at
    end = record.completed_at or record.failed_at
    if start and end:
        elapsed = round((end - start).total_seconds(), 1)

    # 解析 error 字段：尝试 JSON → ErrorEnvelope dict，失败则 {"raw": str}
    error_data: dict | None = None
    if record.error:
        try:
            parsed = json.loads(record.error)
            if isinstance(parsed, dict):
                error_data = parsed
            else:
                error_data = {"raw": str(parsed)[:500]}
        except (json.JSONDecodeError, TypeError):
            error_data = {"raw": record.error[:500]}

    return StageHistoryItem(
        stage_record_id=record.id,
        stage=record.stage,
        mode=record.mode,
        status=record.status,
        started_at=record.started_at.isoformat() if record.started_at else "",
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        failed_at=record.failed_at.isoformat() if record.failed_at else None,
        elapsed_seconds=elapsed,
        result=record.result,
        error=error_data,
    )


# =============================================================================
# 修复建议自动生成
# =============================================================================

_CONSTRUCTION_STAGE_NAMES: dict[int, str] = {
    1: "检索词生成", 2: "检索与汇总", 3: "评分与筛选",
    4: "下载与解析", 5: "总结生成", 6: "格式化与储存", 7: "邮件发送",
}

_REVIEW_STAGE_NAMES: dict[int, str] = {
    1: "课题扩写", 2: "架构生成", 3: "章节撰写", 4: "自动审查", 5: "综述汇总",
}


def _stage_name(mode: str, stage: int) -> str:
    if mode == "construction":
        return _CONSTRUCTION_STAGE_NAMES.get(stage, f"阶段{stage}")
    if mode == "review":
        return _REVIEW_STAGE_NAMES.get(stage, f"综述阶段{stage}")
    return f"阶段{stage}"


def _generate_recommendations(
    project: Project,
    stage_records: list[StageRecord],
    paper_stats: dict,
    config_status: ConfigStatus,
) -> list[str]:
    """
    根据当前项目状态自动生成人类可读的修复/优化建议。
    建议按优先级排序（错误 > 配置缺失 > 优化建议）。
    """
    recs: list[str] = []

    # ── 1. LLM 未配置（最高优先级）────────────────────────────────────────────
    if not config_status.llm_configured:
        recs.append(
            "[FATAL] LLM 未配置，所有 Agent 任务将立即失败，请在「设置 → LLM 配置」添加模型"
        )

    # ── 2. 最近失败的阶段记录 ────────────────────────────────────────────────
    failed_records = [r for r in stage_records if r.status == "failed"]
    if failed_records:
        latest_failed = failed_records[0]  # 已按 started_at desc 排序
        sname = _stage_name(latest_failed.mode, latest_failed.stage)
        error_info = ""
        suggestion_text = ""
        if latest_failed.error:
            try:
                env = json.loads(latest_failed.error)
                error_info = env.get("message", latest_failed.error[:100])
                suggestion_text = env.get("suggestion", "")
                retryable = env.get("retryable", False)
                retry_hint = "点击「重试」按钮可重新执行。" if retryable else "此错误需手动处理后重试。"
            except (json.JSONDecodeError, TypeError):
                error_info = latest_failed.error[:150]
                retry_hint = "可尝试重新执行该阶段。"
                retryable = True
        else:
            error_info = "未知错误"
            retry_hint = ""

        rec = f"[ERROR] 最近阶段 {latest_failed.mode}-stage{latest_failed.stage} 失败：{error_info}"
        if suggestion_text:
            rec += f" 建议：{suggestion_text}"
        if retry_hint:
            rec += f" {retry_hint}"
        recs.append(rec)

    # ── 3. 论文库为空（切换模式前置检查） ────────────────────────────────────
    if project.valid_papers == 0 and project.mode in ("deep_research", "review"):
        recs.append(
            "[WARNING] 当前模式缺少有效论文，深度研究和综述功能将无法引用论文，请先完成构建模式"
        )

    # ── 4. 检索到论文但全部未通过评分 ────────────────────────────────────────
    total = paper_stats.get("total_in_db", 0)
    valid = paper_stats.get("valid", 0)
    if total > 20 and valid == 0:
        recs.append(
            f"[WARNING] 已检索到 {total} 篇论文但有效论文数为 0，建议降低评分阈值或重新评分"
        )
    elif total > 0 and valid == 0 and total <= 20:
        recs.append(
            f"[INFO] 共 {total} 篇论文但有效数为 0，检索词可能过于精确，建议扩大检索范围"
        )

    # ── 5. 配置不完整的数据源 ────────────────────────────────────────────────
    unconfigured_apis: list[str] = []
    for name in ("openalex", "semantic_scholar", "ads"):
        if name not in config_status.paper_db_sources:
            unconfigured_apis.append(name)
    if unconfigured_apis:
        recs.append(
            f"[INFO] {', '.join(unconfigured_apis)} 未配置，构建模式会跳过这些数据源，可能影响论文覆盖度"
        )

    # ── 6. 邮件未配置 ────────────────────────────────────────────────────────
    if not config_status.smtp_configured:
        recs.append(
            "[INFO] 邮件 SMTP 未配置，构建模式第 7 阶段会跳过邮件推送"
        )

    # ── 7. 全部正常 ──────────────────────────────────────────────────────────
    if not recs:
        recs.append("[INFO] 所有检查正常，项目状态健康")

    return recs
