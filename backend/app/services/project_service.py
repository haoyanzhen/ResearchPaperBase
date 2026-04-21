from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import ProjectPaperRelation
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.utils.ids import new_id


async def list_projects(
    db: AsyncSession,
    user_id: str,
    status: str | None,
    mode: str | None,
    page: int,
    page_size: int,
) -> tuple[int, list[Project]]:
    query = select(Project).where(Project.user_id == user_id)
    if status:
        query = query.where(Project.status == status)
    if mode:
        query = query.where(Project.mode == mode)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    items_result = await db.execute(
        query.order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return total, list(items_result.scalars().all())


async def get_project(db: AsyncSession, project_id: str, user_id: str) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_project(db: AsyncSession, user_id: str, name: str, description: str | None) -> Project:
    project = Project(
        id=new_id("p"),
        user_id=user_id,
        name=name,
        description=description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def update_project(
    db: AsyncSession, project: Project, name: str | None, description: str | None
) -> Project:
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    await db.delete(project)
    await db.commit()


async def switch_mode(
    db: AsyncSession, project: Project, target_mode: str
) -> Project:
    """
    切换研究模式（FR-005）。
    前置检查（status=running 时应由路由层先处理）。
    """
    project.mode = target_mode
    await db.commit()
    await db.refresh(project)
    return project


async def update_schedule(
    db: AsyncSession,
    project: Project,
    auto_push: bool,
    push_interval: int | None,
) -> Project:
    project.auto_push = auto_push
    project.push_interval = push_interval
    if auto_push and push_interval:
        from datetime import timedelta
        project.next_push_at = datetime.now(timezone.utc) + timedelta(days=push_interval)
    else:
        project.next_push_at = None
    await db.commit()
    await db.refresh(project)
    return project


async def list_papers(
    db: AsyncSession,
    project_id: str,
    is_valid: bool | None,
    push_status: bool | None,
    keyword: str | None,
    order_by: str,
    page: int,
    page_size: int,
) -> tuple[int, list[ProjectPaperRelation]]:
    from app.models.paper import Paper

    query = (
        select(ProjectPaperRelation)
        .join(Paper, ProjectPaperRelation.paper_id == Paper.id)
        .where(ProjectPaperRelation.project_id == project_id)
    )
    if is_valid is not None:
        query = query.where(ProjectPaperRelation.is_valid == is_valid)
    if push_status is not None:
        query = query.where(ProjectPaperRelation.push_status == push_status)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            Paper.title.ilike(like) | Paper.abstract.ilike(like)
        )

    sort_col = {
        "total_score": ProjectPaperRelation.total_score.desc(),
        "pub_date": Paper.pub_date.desc(),
        "created_at": ProjectPaperRelation.created_at.desc(),
    }.get(order_by, ProjectPaperRelation.created_at.desc())

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    items_result = await db.execute(
        query.order_by(sort_col).offset((page - 1) * page_size).limit(page_size)
    )
    return total, list(items_result.scalars().all())


async def get_paper_with_relation(
    db: AsyncSession,
    project_id: str,
    paper_id: str,
) -> tuple["Paper | None", "ProjectPaperRelation | None"]:  # type: ignore[name-defined]
    from app.models.paper import Paper

    paper_result = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = paper_result.scalar_one_or_none()
    if not paper:
        return None, None

    rel_result = await db.execute(
        select(ProjectPaperRelation).where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.paper_id == paper_id,
        )
    )
    relation = rel_result.scalar_one_or_none()
    return paper, relation


async def update_paper_score(
    db: AsyncSession,
    project_id: str,
    paper_id: str,
    reference_score: int,
    technical_score: int,
    scoring_reason: str | None,
) -> ProjectPaperRelation | None:
    result = await db.execute(
        select(ProjectPaperRelation).where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.paper_id == paper_id,
        )
    )
    relation = result.scalar_one_or_none()
    if not relation:
        return None

    relation.reference_score = reference_score
    relation.technical_score = technical_score
    relation.total_score = reference_score + technical_score
    relation.is_valid = (reference_score + technical_score) >= 7
    if scoring_reason is not None:
        relation.scoring_reason = scoring_reason
    await db.commit()
    await db.refresh(relation)
    return relation


async def remove_paper(db: AsyncSession, project_id: str, paper_id: str) -> bool:
    """FR-007: 移除关联记录，全局 papers 表不受影响"""
    result = await db.execute(
        select(ProjectPaperRelation).where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.paper_id == paper_id,
        )
    )
    relation = result.scalar_one_or_none()
    if not relation:
        return False
    await db.delete(relation)
    await db.commit()
    return True


# ── 推荐模块 (FR-011) ──────────────────────────────────────────────────────────

async def create_recommendation(
    db: AsyncSession, user_id: str, data: dict
) -> Recommendation:
    rec = Recommendation(
        id=new_id("rec"),
        user_id=user_id,
        dialogue_id=data.get("dialogue_id"),
        content_type=data["content_type"],
        title=data["title"],
        content=data["content"],
        tags=data.get("tags"),
        contact_info=data.get("contact_info"),
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_recommendations(
    db: AsyncSession,
    content_type: str | None,
    keyword: str | None,
    order_by: str,
    page: int,
    page_size: int,
) -> tuple[int, list[Recommendation]]:
    query = select(Recommendation).where(Recommendation.is_visible.is_(True))
    if content_type:
        query = query.where(Recommendation.content_type == content_type)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            Recommendation.title.ilike(like) | Recommendation.content.ilike(like)
        )

    sort_col = {
        "like_count": Recommendation.like_count.desc(),
        "view_count": Recommendation.view_count.desc(),
    }.get(order_by, Recommendation.created_at.desc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    items_result = await db.execute(
        query.order_by(sort_col).offset((page - 1) * page_size).limit(page_size)
    )
    return total, list(items_result.scalars().all())


async def delete_recommendation(
    db: AsyncSession, rec_id: str, user_id: str
) -> bool:
    """软删除（is_visible=False），只允许作者操作"""
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == rec_id,
            Recommendation.user_id == user_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        return False
    rec.is_visible = False
    await db.commit()
    return True


async def increment_view(db: AsyncSession, rec_id: str) -> None:
    result = await db.execute(select(Recommendation).where(Recommendation.id == rec_id))
    rec = result.scalar_one_or_none()
    if rec:
        rec.view_count += 1
        await db.commit()


async def toggle_like(db: AsyncSession, rec_id: str, delta: int) -> Recommendation | None:
    result = await db.execute(select(Recommendation).where(Recommendation.id == rec_id))
    rec = result.scalar_one_or_none()
    if rec:
        rec.like_count = max(0, rec.like_count + delta)
        await db.commit()
        await db.refresh(rec)
    return rec
