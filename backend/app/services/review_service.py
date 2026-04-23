"""
业务逻辑 — 综述模式（FR-020~024）

职责：
  - 启动综述流程（start_review）
  - 综述架构 CRUD（list_outlines / get_outline / update_outline / confirm_outline）
  - 章节 CRUD（list_chapters / get_chapter / update_chapter）
  - 触发单章节审查（trigger_chapter_review）
  - 触发综述汇总（compile_outline）
  - 综述状态查询（get_review_status）
  - 导出综述文章（export_outline：Markdown / PDF stub / DOCX stub）
"""

import io
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.review import ReviewChapter, ReviewOutline
from app.models.stage import StageRecord
from app.utils.ids import new_id
from app.agents.review.pipeline import REVIEW_STAGE_NAMES

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# 辅助：项目权限校验
# =============================================================================

async def _get_project(db: AsyncSession, project_id: str, user_id: str) -> Project | None:
    res = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return res.scalar_one_or_none()


# =============================================================================
# 启动综述流程（FR-020）
# =============================================================================

async def start_review(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    topic_hint: str | None,
) -> tuple[ReviewOutline, StageRecord] | tuple[None, None]:
    """
    创建新版本综述架构，创建阶段 1 记录，设置 project.status = running。
    返回 (outline, stage_record)；项目不存在或无权限返回 (None, None)。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None, None

    # 计算新版本号
    ver_res = await db.execute(
        select(func.max(ReviewOutline.version)).where(ReviewOutline.project_id == project_id)
    )
    last_version = ver_res.scalar_one_or_none() or 0

    outline = ReviewOutline(
        id=new_id("ol"),
        project_id=project_id,
        version=last_version + 1,
        topic_expansion=topic_hint,   # 用户提示暂存，阶段1将扩写
        status="draft",
    )
    db.add(outline)
    await db.flush()

    record = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode="review",
        stage=1,
        status="running",
        started_at=_utcnow(),
    )
    db.add(record)
    project.status = "running"
    await db.commit()
    await db.refresh(outline)
    await db.refresh(record)
    return outline, record


# =============================================================================
# 综述架构查询（FR-020 / FR-024）
# =============================================================================

async def list_outlines(
    db: AsyncSession, project_id: str, user_id: str
) -> list[ReviewOutline] | None:
    """返回项目所有综述架构版本（按版本降序），项目不存在/无权限返回 None。"""
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None
    res = await db.execute(
        select(ReviewOutline)
        .where(ReviewOutline.project_id == project_id)
        .order_by(ReviewOutline.version.desc())
    )
    return list(res.scalars().all())


async def get_outline(
    db: AsyncSession, project_id: str, outline_id: str, user_id: str
) -> ReviewOutline | None:
    """返回指定综述架构，归属校验失败返回 None。"""
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None
    res = await db.execute(
        select(ReviewOutline).where(
            ReviewOutline.id == outline_id,
            ReviewOutline.project_id == project_id,
        )
    )
    return res.scalar_one_or_none()


async def update_outline(
    db: AsyncSession,
    outline: ReviewOutline,
    topic_expansion: str | None,
    outline_data: dict | None,
) -> ReviewOutline:
    """更新综述架构内容（用户在阶段2暂停后修改）。"""
    if topic_expansion is not None:
        outline.topic_expansion = topic_expansion
    if outline_data is not None:
        outline.outline = outline_data
    await db.commit()
    await db.refresh(outline)
    return outline


async def confirm_outline(
    db: AsyncSession,
    project_id: str,
    outline: ReviewOutline,
) -> tuple[ReviewOutline, StageRecord]:
    """
    确认综述架构：
      1. outline.status → confirmed
      2. 根据 outline.sections 创建 review_chapters 记录（pending）
      3. 创建阶段 3 记录，project.status → running
    """
    now = _utcnow()
    outline.status = "confirmed"
    outline.confirmed_at = now

    # 创建章节记录
    sections = (outline.outline or {}).get("sections", [])
    for section in sections:
        # 幂等：若章节已存在则跳过
        exists = await db.execute(
            select(ReviewChapter).where(
                ReviewChapter.outline_id == outline.id,
                ReviewChapter.chapter_index == section["index"],
            )
        )
        if exists.scalar_one_or_none() is None:
            chapter = ReviewChapter(
                id=new_id("ch"),
                outline_id=outline.id,
                project_id=project_id,
                chapter_index=section["index"],
                title=section["title"],
                status="pending",
            )
            db.add(chapter)

    record = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode="review",
        stage=3,
        status="running",
        started_at=now,
    )
    db.add(record)

    proj_res = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_res.scalar_one_or_none()
    if project:
        project.status = "running"

    await db.commit()
    await db.refresh(outline)
    await db.refresh(record)
    return outline, record


# =============================================================================
# 章节 CRUD（FR-021~022）
# =============================================================================

async def list_chapters(
    db: AsyncSession, outline_id: str
) -> list[ReviewChapter]:
    """返回 outline 下所有章节，按 chapter_index 升序。"""
    res = await db.execute(
        select(ReviewChapter)
        .where(ReviewChapter.outline_id == outline_id)
        .order_by(ReviewChapter.chapter_index)
    )
    return list(res.scalars().all())


async def get_chapter(
    db: AsyncSession, outline_id: str, chapter_id: str
) -> ReviewChapter | None:
    res = await db.execute(
        select(ReviewChapter).where(
            ReviewChapter.id == chapter_id,
            ReviewChapter.outline_id == outline_id,
        )
    )
    return res.scalar_one_or_none()


async def update_chapter(
    db: AsyncSession,
    chapter: ReviewChapter,
    content: str | None,
    citations: list[dict] | None,
) -> ReviewChapter:
    """用户手动修改章节内容或引用列表。"""
    if content is not None:
        chapter.content = content
    if citations is not None:
        chapter.citations = citations
    await db.commit()
    await db.refresh(chapter)
    return chapter


# =============================================================================
# 单章节审查触发（FR-022）
# =============================================================================

async def trigger_chapter_review(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    chapter: ReviewChapter,
) -> ReviewChapter:
    """
    手动触发单章节审查（独立于 stage 系统）。
    将 chapter.status 设为 reviewing 并异步执行审查逻辑。
    实际审查在 BackgroundTask 中调用 stage4_auto_review.review_chapter_once()。
    此处仅更新状态为 reviewing 并 commit。
    """
    chapter.status = "reviewing"
    await db.commit()
    await db.refresh(chapter)
    return chapter


# =============================================================================
# 综述汇总（FR-023）
# =============================================================================

async def compile_outline(
    db: AsyncSession,
    project_id: str,
    outline_id: str,
    user_id: str,
) -> StageRecord | None:
    """
    创建阶段 5 记录，触发综述汇总。
    outline 不存在或项目无权限返回 None。
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    outline_res = await db.execute(
        select(ReviewOutline).where(
            ReviewOutline.id == outline_id,
            ReviewOutline.project_id == project_id,
            ReviewOutline.status == "confirmed",
        )
    )
    if outline_res.scalar_one_or_none() is None:
        return None

    record = StageRecord(
        id=new_id("sr"),
        project_id=project_id,
        mode="review",
        stage=5,
        status="running",
        started_at=_utcnow(),
    )
    db.add(record)
    project.status = "running"
    await db.commit()
    await db.refresh(record)
    return record


# =============================================================================
# 状态查询（FR-020）
# =============================================================================

async def get_review_status(
    db: AsyncSession,
    project_id: str,
    user_id: str,
) -> dict | None:
    """返回综述模式当前状态。项目不存在/无权限返回 None。"""
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    # 最新综述 outline
    outline_res = await db.execute(
        select(ReviewOutline)
        .where(ReviewOutline.project_id == project_id)
        .order_by(ReviewOutline.version.desc())
        .limit(1)
    )
    outline = outline_res.scalar_one_or_none()

    # 最新 review stage record
    stage_res = await db.execute(
        select(StageRecord)
        .where(StageRecord.project_id == project_id, StageRecord.mode == "review")
        .order_by(StageRecord.started_at.desc())
        .limit(1)
    )
    stage = stage_res.scalar_one_or_none()

    total_chapters = 0
    completed_chapters = 0
    if outline:
        count_res = await db.execute(
            select(func.count(ReviewChapter.id)).where(ReviewChapter.outline_id == outline.id)
        )
        total_chapters = count_res.scalar_one()
        done_res = await db.execute(
            select(func.count(ReviewChapter.id)).where(
                ReviewChapter.outline_id == outline.id,
                ReviewChapter.status == "completed",
            )
        )
        completed_chapters = done_res.scalar_one()

    return {
        "project_id": project_id,
        "current_stage": stage.stage if stage else None,
        "stage_name": REVIEW_STAGE_NAMES.get(stage.stage) if stage else None,
        "stage_status": stage.status if stage else None,
        "outline_id": outline.id if outline else None,
        "outline_status": outline.status if outline else None,
        "total_chapters": total_chapters,
        "completed_chapters": completed_chapters,
    }


# =============================================================================
# 导出综述文章（FR-023~024）
# =============================================================================

async def export_outline(
    db: AsyncSession,
    project_id: str,
    outline_id: str,
    user_id: str,
    fmt: str,
) -> tuple[bytes, str] | None:
    """
    导出综述文章。
    返回 (content_bytes, media_type)，找不到或无权限返回 None，
    格式未实现（pdf/docx）也返回 None（由路由层区分 404 vs 501）。

    fmt:
      markdown → 直接从 compiled_content 取；未汇总时动态拼接
      pdf      → 存根（返回 Markdown 文本，Content-Type text/markdown）
      docx     → 存根（同上）
    """
    project = await _get_project(db, project_id, user_id)
    if project is None:
        return None

    outline_res = await db.execute(
        select(ReviewOutline).where(
            ReviewOutline.id == outline_id,
            ReviewOutline.project_id == project_id,
        )
    )
    outline = outline_res.scalar_one_or_none()
    if outline is None:
        return None

    outline_data = outline.outline or {}

    # 取已汇总内容或动态拼接
    compiled = outline_data.get("compiled_content")
    if not compiled:
        # 动态拼接
        chapters_res = await db.execute(
            select(ReviewChapter)
            .where(ReviewChapter.outline_id == outline_id)
            .order_by(ReviewChapter.chapter_index)
        )
        chapters = list(chapters_res.scalars().all())
        title = outline_data.get("title", project.name)
        abstract = outline_data.get("abstract", "")
        keywords = outline_data.get("keywords", [])

        parts = [f"# {title}\n"]
        if abstract:
            parts.append(f"**摘要**：{abstract}\n")
        if keywords:
            parts.append(f"**关键词**：{'，'.join(keywords)}\n")
        parts.append("---\n")
        for ch in chapters:
            parts.append(f"## {ch.chapter_index}. {ch.title}\n")
            parts.append((ch.content or "（章节尚未生成）") + "\n")
        compiled = "\n".join(parts)

    content_bytes = compiled.encode("utf-8")

    if fmt == "markdown":
        return content_bytes, "text/markdown; charset=utf-8"
    # PDF / DOCX: 存根，尚未实现，返回 None 由路由层报 501
    # TODO: 后续迭代接入 WeasyPrint / python-docx
    return None
