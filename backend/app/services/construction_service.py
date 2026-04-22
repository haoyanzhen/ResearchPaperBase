"""
业务逻辑 — 构建模式（FR-012~019）

职责：
  - 关键词 CRUD（list_keywords / upsert_keywords）
  - 阶段记录管理（get_active_record / get_latest_record / get_pipeline_params）
  - 构建启动（start_construction）
  - 构建状态查询（get_construction_status）
  - 阶段用户操作（apply_stage_action）
  - 阶段7自动执行（execute_stage7 / send_stage7_email）— FR-018

Agent Worker 相关（向量检索、LLM 调用、PDF 解析等）均为存根，
实际逻辑由后续 Agent 链实现。
"""

import json
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete as sa_delete

from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Keyword, Project
from app.models.stage import StageRecord
from app.services.config_service import get_config, get_email_config
from app.utils.ids import new_id

# ── 阶段名称映射（构建模式 1-7）────────────────────────────────────────────────
STAGE_NAMES: dict[int, str] = {
    1: "检索词生成",
    2: "检索与汇总",
    3: "评分与筛选",
    4: "下载与解析",
    5: "总结生成",
    6: "格式化与储存",
    7: "邮件发送",
}

# 第 7 阶段全自动，不暂停等待用户操作；1-6 阶段执行完毕后暂停
AUTO_STAGE = 7


# =============================================================================
# 工具函数
# =============================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _get_project(db: AsyncSession, project_id: str, user_id: str) -> Project | None:
    """校验项目归属并返回 Project；不属于该用户返回 None。"""
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


# =============================================================================
# 关键词管理（FR-019 阶段1交互）
# =============================================================================

async def list_keywords(
    db: AsyncSession,
    project_id: str,
    user_id: str,
) -> list[Keyword] | None:
    """
    返回项目全部关键词，按 created_at 升序。
    项目不存在或无权限返回 None。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None
    result = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id)
        .order_by(Keyword.created_at)
    )
    return list(result.scalars().all())


async def upsert_keywords(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    items: list[dict[str, Any]],
) -> list[Keyword] | None:
    """
    批量新增或更新关键词（FR-019 阶段1交互）。

    items 字段：keyword_id（None=新增）、search_word、boolean_expressions、is_selected
    已存在的 keyword_id 仅更新 search_word / boolean_expressions / is_selected；
    新条目（keyword_id=None）创建新行。
    项目不存在或无权限返回 None。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    now = _utcnow()
    for item in items:
        kw_id = item.get("keyword_id")
        if kw_id:
            # 更新已有关键词
            result = await db.execute(
                select(Keyword).where(Keyword.id == kw_id, Keyword.project_id == project_id)
            )
            kw = result.scalar_one_or_none()
            if kw is None:
                continue  # 非法 ID 静默跳过
            kw.search_word = item["search_word"]
            if "boolean_expressions" in item:
                kw.boolean_expressions = item.get("boolean_expressions")
            kw.is_selected = item.get("is_selected", kw.is_selected)
        else:
            # 新增关键词
            kw = Keyword(
                id=new_id("kw"),
                project_id=project_id,
                search_word=item["search_word"],
                boolean_expressions=item.get("boolean_expressions"),
                is_selected=item.get("is_selected", True),
                is_searched=False,
                searched_papers_total=0,
                searched_papers_arxiv=0,
                searched_papers_openalex=0,
                searched_papers_semanticscholar=0,
                searched_papers_ads=0,
                created_at=now,
                last_search_at=now,
            )
            db.add(kw)

    await db.commit()
    return await list_keywords(db, project_id, user_id)


# =============================================================================
# 阶段记录管理
# =============================================================================

async def get_active_record(
    db: AsyncSession,
    project_id: str,
    mode: str = "construction",
) -> StageRecord | None:
    """
    返回该项目当前处于 running 或 paused 状态的构建阶段记录。
    若无活跃记录返回 None（project.status 为 idle/error/archived）。
    """
    result = await db.execute(
        select(StageRecord)
        .where(
            StageRecord.project_id == project_id,
            StageRecord.mode == mode,
            StageRecord.status.in_(["running", "paused"]),
        )
        .order_by(StageRecord.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_latest_record(
    db: AsyncSession,
    project_id: str,
    mode: str = "construction",
) -> StageRecord | None:
    """返回最新的阶段记录（含已完成/失败状态），用于状态查询。"""
    result = await db.execute(
        select(StageRecord)
        .where(StageRecord.project_id == project_id, StageRecord.mode == mode)
        .order_by(StageRecord.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_pipeline_params(
    db: AsyncSession,
    project_id: str,
) -> dict[str, Any] | None:
    """
    从阶段1的 result JSONB 中检索本次管道启动参数（databases / score_threshold）。
    用于阶段3（评分）等后续阶段读取 score_threshold。
    若找不到阶段1记录则返回默认值。
    """
    result = await db.execute(
        select(StageRecord)
        .where(
            StageRecord.project_id == project_id,
            StageRecord.mode == "construction",
            StageRecord.stage == 1,
        )
        .order_by(StageRecord.started_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record and record.result:
        return {
            "databases": record.result.get("databases", ["arxiv", "openalex", "semantic_scholar"]),
            "score_threshold": record.result.get("score_threshold", 7),
        }
    return {"databases": ["arxiv", "openalex", "semantic_scholar"], "score_threshold": 7}


# =============================================================================
# 构建启动
# =============================================================================

async def start_construction(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    databases: list[str],
    score_threshold: int,
) -> tuple[StageRecord, str] | tuple[None, str]:
    """
    启动构建流程第 1 阶段（检索词生成）。

    前置检查：
      - 项目存在且属于当前用户
      - 项目当前 status 不为 running/paused（避免重复启动）
      - 项目不处于 archived 状态

    成功时：
      - 创建 stage=1 的 StageRecord（status=running）
      - 将 project.status 改为 running
      - 在 result 中记录启动参数（databases / score_threshold），供后续阶段通过 get_pipeline_params 读取

    返回 (StageRecord, error_msg)；error_msg 为空字符串表示成功。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None, "项目不存在"
    if project.status == "archived":
        return None, "已归档项目不能启动构建"
    if project.status in ("running", "paused"):
        return None, "当前已有构建任务在执行，请先暂停或取消"

    now = _utcnow()
    record = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode="construction",
        stage=1,
        status="running",
        started_at=now,
        result={
            "databases": databases,
            "score_threshold": score_threshold,
        },
    )
    db.add(record)
    project.status = "running"
    await db.commit()
    await db.refresh(record)
    return record, ""


# =============================================================================
# 构建状态查询
# =============================================================================

async def get_construction_status(
    db: AsyncSession,
    project_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """
    返回构建状态 dict，对应 ConstructionStatusResponse。
    status 映射到 spec 规定值：idle / running / paused / error。
    项目不存在/无权限返回 None。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    record = await get_latest_record(db, project_id, mode="construction")
    if record is None:
        return {
            "current_stage": None,
            "stage_name": None,
            "status": "idle",
            "stage_result": None,
            "started_at": None,
        }

    # 将 stage_record.status 映射到管道级状态
    # "completed" 表示该记录完成，实际管道状态从 project.status 读取
    # "failed" 映射为 "error" 以符合 spec 的允许值
    status_map = {
        "running":   "running",
        "paused":    "paused",
        "completed": project.status if project.status in ("idle", "running", "paused") else "idle",
        "failed":    "error",
    }
    pipeline_status = status_map.get(record.status, "idle")

    return {
        "current_stage": record.stage,
        "stage_name": STAGE_NAMES.get(record.stage),
        "status": pipeline_status,
        "stage_result": record.result,
        "started_at": record.started_at,
    }


# =============================================================================
# 阶段用户操作（FR-019）
# =============================================================================

async def _apply_stage_modifications(
    db: AsyncSession,
    project_id: str,
    stage: int,
    modifications: dict[str, Any] | None,
) -> None:
    """
    在用户 confirm/skip 时，将修改立即写入数据库（不等待下一阶段 Agent 处理）。

    - 阶段2 confirm: 删除用户排除的论文关联（removed_ids）
    - 阶段3 confirm: 更新论文 AI 评分，并按阈值重算 is_valid（score_overrides）
    - 阶段5 confirm: 合并更新论文 AI 分析（analysis_overrides）
    """
    if not modifications:
        return

    if stage == 2:
        removed_ids: list[str] = modifications.get("removed_ids") or []
        if removed_ids:
            await db.execute(
                sa_delete(ProjectPaperRelation).where(
                    ProjectPaperRelation.project_id == project_id,
                    ProjectPaperRelation.paper_id.in_(removed_ids),
                )
            )

    elif stage == 3:
        score_overrides: dict[str, float] = modifications.get("score_overrides") or {}
        if score_overrides:
            # 取阈值（用于重算 is_valid）
            params = await get_pipeline_params(db, project_id)
            threshold = params.get("score_threshold", 7)

            result = await db.execute(
                select(ProjectPaperRelation).where(
                    ProjectPaperRelation.project_id == project_id,
                    ProjectPaperRelation.paper_id.in_(list(score_overrides.keys())),
                )
            )
            for rel in result.scalars().all():
                new_score = float(score_overrides[rel.paper_id])
                rel.ai_score = new_score
                rel.is_valid = new_score >= threshold

    elif stage == 5:
        analysis_overrides: dict[str, dict] = modifications.get("analysis_overrides") or {}
        if analysis_overrides:
            result = await db.execute(
                select(Paper).where(Paper.id.in_(list(analysis_overrides.keys())))
            )
            for paper in result.scalars().all():
                existing = paper.ai_analysis or {}
                paper.ai_analysis = {**existing, **analysis_overrides[paper.id]}


_STAGE_ACTION_MESSAGES: dict[tuple[int, str], str] = {
    (1, "confirm"): "已确认检索词，开始检索与汇总...",
    (1, "retry"):   "重新生成检索词...",
    (1, "skip"):    "已跳过检索词生成，使用默认词",
    (2, "confirm"): "已确认检索结果，开始评分与筛选...",
    (2, "retry"):   "重新执行检索...",
    (2, "skip"):    "已跳过检索阶段",
    (3, "confirm"): "已确认评分，开始下载与解析...",
    (3, "retry"):   "重新执行评分...",
    (3, "skip"):    "已跳过评分筛选",
    (4, "confirm"): "已确认下载，开始总结生成...",
    (4, "retry"):   "重新下载指定论文...",
    (4, "skip"):    "已跳过下载阶段",
    (5, "confirm"): "已确认 AI 分析，开始格式化与储存...",
    (5, "retry"):   "重新生成摘要...",
    (5, "skip"):    "已跳过总结生成",
    (6, "confirm"): "已确认，开始邮件发送...",
    (6, "retry"):   "重新格式化与储存...",
    (6, "skip"):    "已跳过格式化阶段，开始邮件发送...",
}


async def apply_stage_action(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    stage: int,
    action: str,
    modifications: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    """
    处理阶段用户操作（confirm / retry / skip）。

    逻辑：
      - confirm/skip: 关闭当前记录(completed)，推进到 next_stage，创建新 StageRecord(running)
      - retry:        关闭当前记录(failed)，创建同阶段新 StageRecord(running)

    stage=6 confirm/skip → next_stage=7（邮件发送，全自动，由调用方触发 execute_stage7 背景任务）
    stage=7 不允许手动操作。

    返回 (result_dict, error_msg)。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None, "项目不存在"

    if stage == AUTO_STAGE:
        return None, "第 7 阶段全自动执行，无需操作"

    if action not in ("confirm", "retry", "skip"):
        return None, f"不合法的操作: {action}"

    # 找到当前 paused 的阶段记录
    result = await db.execute(
        select(StageRecord).where(
            StageRecord.project_id == project_id,
            StageRecord.mode == "construction",
            StageRecord.stage == stage,
            StageRecord.status == "paused",
        ).order_by(StageRecord.started_at.desc()).limit(1)
    )
    current_record = result.scalar_one_or_none()
    if current_record is None:
        return None, f"阶段 {stage} 未处于暂停状态，无法操作"

    now = _utcnow()

    # 记录用户操作到 user_actions JSONB 列（审计用）
    action_entry = {"action": action, "timestamp": now.isoformat(), "modifications": modifications}
    current_record.user_actions = (current_record.user_actions or []) + [action_entry]

    if action == "retry":
        # 标记为 failed，创建同阶段新记录重新执行
        current_record.status = "failed"
        current_record.failed_at = now
        current_record.error = "用户请求重试"

        new_record = StageRecord(
            id=new_id("sr"),
            project_id=project_id,
            mode="construction",
            stage=stage,
            status="running",
            started_at=now,
            result=modifications,
        )
        db.add(new_record)
        project.status = "running"
        next_stage: int | None = stage  # retry 不推进

    else:  # confirm 或 skip
        current_record.status = "completed"
        current_record.completed_at = now

        # 立即将用户修改写入数据库（removed_ids / score_overrides / analysis_overrides）
        await _apply_stage_modifications(db, project_id, stage, modifications)

        next_stage = stage + 1 if stage < 7 else None
        if next_stage is not None:
            new_record = StageRecord(
                id=new_id("sr"),
                project_id=project_id,
                mode="construction",
                stage=next_stage,
                status="running",
                started_at=now,
                result=None,  # 修改已立即应用，不再传给下一阶段
            )
            db.add(new_record)
            project.status = "running"
        else:
            project.status = "idle"

    await db.commit()

    message = _STAGE_ACTION_MESSAGES.get((stage, action), f"阶段 {stage} 操作已执行")
    return {
        "stage": stage,
        "action": action,
        "next_stage": next_stage,
        "status": "running" if next_stage is not None else "completed",
        "message": message,
    }, ""


# =============================================================================
# 阶段7：邮件发送（FR-018，全自动执行）
# =============================================================================

def _build_email_html(project_name: str, papers: list[dict]) -> str:
    """
    构建 HTML 邮件正文。

    papers 字段：title, authors, venue, pub_date, ai_summary
    """
    rows = ""
    for i, p in enumerate(papers, 1):
        authors = "、".join(p.get("authors") or []) or "未知作者"
        venue = p.get("venue") or "未知期刊"
        pub_date = str(p.get("pub_date") or "")
        summary = p.get("ai_summary") or "（暂无 AI 分析）"
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee">{i}</td>
          <td style="padding:8px;border-bottom:1px solid #eee"><strong>{p['title']}</strong><br>
            <small>{authors} · {venue} · {pub_date}</small></td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#555">{summary}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#333;max-width:800px;margin:auto;padding:20px">
  <h2 style="color:#1a73e8">📚 论文推送 — {project_name}</h2>
  <p>本次共推送 <strong>{len(papers)}</strong> 篇有效论文：</p>
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="background:#f5f5f5">
        <th style="padding:8px;text-align:left">#</th>
        <th style="padding:8px;text-align:left">论文信息</th>
        <th style="padding:8px;text-align:left">AI 摘要</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <hr style="margin-top:30px">
  <p style="color:#999;font-size:12px">此邮件由 Research Paper Base 自动发送</p>
</body>
</html>"""


async def send_stage7_email(
    db: AsyncSession,
    project_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    FR-018：邮件发送阶段核心逻辑。

    步骤：
      1. 查询该课题所有 is_valid=True, push_status=False 的论文（含 Paper 元数据）
      2. 若无未推送论文，跳过发送（不发空邮件），直接返回
      3. 读取用户邮件配置（SMTP 设置 + recipients）
      4. 构建 HTML 邮件并发送
      5. 将已发送论文的 push_status 更新为 True，pushed_at 写入当前时间
      6. 更新 project.last_push_at

    返回包含 {sent_count, skipped, error} 的 dict。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return {"sent_count": 0, "skipped": True, "error": "项目不存在"}

    # 1. 查询所有未推送的有效论文
    result = await db.execute(
        select(ProjectPaperRelation, Paper)
        .join(Paper, ProjectPaperRelation.paper_id == Paper.id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
            ProjectPaperRelation.push_status == False,
        )
    )
    rows = result.all()

    # 2. 无未推送论文时跳过
    if not rows:
        return {"sent_count": 0, "skipped": True, "error": None}

    # 3. 读取邮件配置
    email_cfg = await get_email_config(db, user_id)
    smtp_host = email_cfg.get("smtp_host")
    smtp_port = email_cfg.get("smtp_port") or 587
    sender = email_cfg.get("sender_email")
    recipients: list[str] = email_cfg.get("recipients") or []
    sender_password = await get_config(db, user_id, "email.smtp.sender_password")

    if not smtp_host or not sender or not recipients:
        return {"sent_count": 0, "skipped": False, "error": "邮件配置不完整，请先配置 SMTP"}

    # 4. 构建邮件数据
    papers_data = []
    relations = []
    for rel, paper in rows:
        ai_summary = None
        if paper.ai_analysis and isinstance(paper.ai_analysis, dict):
            ai_summary = paper.ai_analysis.get("summary")
        papers_data.append({
            "title": paper.title,
            "authors": paper.authors,
            "venue": paper.venue,
            "pub_date": paper.pub_date,
            "ai_summary": ai_summary,
        })
        relations.append(rel)

    html_body = _build_email_html(project.name, papers_data)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"论文推送 — {project.name}（{len(papers_data)} 篇）"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 5. 发送邮件
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as s:
            s.starttls()
            if sender_password:
                s.login(sender, sender_password)
            s.sendmail(sender, recipients, msg.as_string())
    except Exception as exc:
        return {"sent_count": 0, "skipped": False, "error": str(exc)}

    # 6. 更新推送状态
    now = _utcnow()
    for rel in relations:
        rel.push_status = True
        rel.pushed_at = now
    project.last_push_at = now
    await db.commit()

    return {"sent_count": len(relations), "skipped": False, "error": None}


async def execute_stage7(
    project_id: str,
    user_id: str,
    stage7_record_id: str,
) -> None:
    """
    阶段7全自动执行入口（由 BackgroundTasks 调用，见 construction.py）。

    自行创建数据库会话（BackgroundTask 不能复用 HTTP 请求的 session）。
    执行邮件发送；无论成功与否都将 stage7 记录标记为 completed 或 failed，
    并将 project.status 恢复为 idle（pipeline 结束）。
    """
    from app.core.database import AsyncSessionLocal
    from app.agents.base import emit_sse_event

    async with AsyncSessionLocal() as db:
        # 获取 stage7 记录
        result = await db.execute(
            select(StageRecord).where(StageRecord.id == stage7_record_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return

        now = _utcnow()
        email_result = await send_stage7_email(db, project_id, user_id)

        # 刷新 project（send_stage7_email 内部已 commit，需重新加载）
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()

        if email_result.get("error"):
            record.status = "failed"
            record.failed_at = now
            record.error = email_result["error"]
            if project:
                project.status = "error"
            emit_sse_event(project_id, "stage_error", {
                "stage": 7, "error": email_result["error"], "retryable": True
            })
        else:
            record.status = "completed"
            record.completed_at = now
            record.result = {
                "sent_count": email_result["sent_count"],
                "skipped": email_result["skipped"],
            }
            if project:
                project.status = "idle"
            emit_sse_event(project_id, "pipeline_complete", {
                "total_papers": project.total_papers if project else 0,
                "valid_papers": project.valid_papers if project else 0,
                "email_sent": not email_result["skipped"],
                "sent_count": email_result["sent_count"],
            })

        await db.commit()
