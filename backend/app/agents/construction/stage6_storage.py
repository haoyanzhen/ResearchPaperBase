"""
构建模式阶段 6 — 格式化与数据库存储（FR-017）

职责：
  1. 确认课题有效论文已完整写入 PostgreSQL（前序阶段已完成，此处做完整性校验）
  2. 同步向量数据到 ChromaDB（存根：ChromaDB 客户端尚未集成，记录待办）
  3. 触发 NetworkX 知识图谱增量更新（存根：NetworkX 尚未集成）
  4. 统计并返回本次存储摘要
  5. 将阶段标记为 paused（等待用户确认后触发 stage 7 邮件发送）

ChromaDB 和 NetworkX 的实际集成需要在添加相应依赖后实现（见 TODO 注释）。
论文关系型数据（papers / project_paper_relations）已由前序阶段写入。
"""

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event
from app.agents.construction.pipeline import mark_stage_paused
from app.models.paper import Paper, ProjectPaperRelation
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


async def _sync_chromadb(project_id: str, papers: list[Paper]) -> dict:
    """
    TODO: ChromaDB 向量同步存根。
    添加 chromadb>=0.4.0 依赖并实现后替换此函数。

    预期实现：
      1. 使用 Paper.ai_analysis["summary"] + abstract 构建文档文本
      2. 调用 embedding API（复用 LLM provider）生成向量
      3. 将 (paper_id, vector, metadata) 写入 ChromaDB collection = project_id
    """
    logger.info(
        "ChromaDB sync stub: would sync %d papers for project %s (not implemented)",
        len(papers), project_id
    )
    return {
        "chromadb_synced": False,
        "chromadb_count": 0,
        "chromadb_note": "ChromaDB 集成待实现（缺少依赖 chromadb）",
    }


async def _update_networkx_graph(project_id: str, papers: list[Paper]) -> dict:
    """
    TODO: NetworkX 知识图谱增量更新存根。
    添加 networkx>=3.0 依赖并实现后替换此函数。

    预期实现：
      1. 每篇论文作为节点（paper_id, title, pub_date, venue 等属性）
      2. 相同作者的论文间建立 co-author 边
      3. 同一期刊的论文间建立 co-venue 边
      4. 序列化为 JSON（或 GraphML）持久化存储
    """
    logger.info(
        "NetworkX graph update stub: would update %d nodes for project %s (not implemented)",
        len(papers), project_id
    )
    return {
        "graph_updated": False,
        "graph_node_count": 0,
        "graph_note": "NetworkX 图数据库集成待实现（缺少依赖 networkx）",
    }


async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 6 执行逻辑。

    modifications：stage 6 无可修改内容，直接 confirm 进入 stage 7。
    """
    emit_sse_event(project_id, "stage_progress", {
        "stage": 6, "progress": 10, "detail": "正在校验数据完整性..."
    })

    # ── 统计当前有效论文 ──────────────────────────────────────────────────
    count_res = await db.execute(
        select(func.count())
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
        )
    )
    valid_count = count_res.scalar_one()

    analyzed_count_res = await db.execute(
        select(func.count(Paper.id))
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
            Paper.ai_analysis_status == "success",
        )
    )
    analyzed_count = analyzed_count_res.scalar_one()

    downloaded_count_res = await db.execute(
        select(func.count(Paper.id))
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
            Paper.download_status == "success",
        )
    )
    downloaded_count = downloaded_count_res.scalar_one()

    emit_sse_event(project_id, "stage_progress", {
        "stage": 6, "progress": 30, "detail": f"有效论文 {valid_count} 篇，已下载 {downloaded_count} 篇，已分析 {analyzed_count} 篇"
    })

    # ── 获取有效论文列表（用于 ChromaDB / NetworkX）─────────────────────
    valid_papers_res = await db.execute(
        select(Paper)
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
        )
    )
    valid_papers = valid_papers_res.scalars().all()

    # ── ChromaDB 同步（存根）──────────────────────────────────────────────
    emit_sse_event(project_id, "stage_progress", {
        "stage": 6, "progress": 50, "detail": "同步向量数据库（ChromaDB）..."
    })
    chromadb_result = await _sync_chromadb(project_id, valid_papers)

    # ── NetworkX 图更新（存根）──────────────────────────────────────────────
    emit_sse_event(project_id, "stage_progress", {
        "stage": 6, "progress": 75, "detail": "更新知识图谱（NetworkX）..."
    })
    graph_result = await _update_networkx_graph(project_id, valid_papers)

    emit_sse_event(project_id, "stage_progress", {
        "stage": 6, "progress": 95, "detail": "存储完成，等待用户确认后发送邮件..."
    })

    stage_result = {
        "valid_papers": valid_count,
        "downloaded": downloaded_count,
        "analyzed": analyzed_count,
        **chromadb_result,
        **graph_result,
    }

    await mark_stage_paused(db, record.id, stage_result)

    emit_sse_event(project_id, "stage_pause", {
        "stage": 6,
        "status": "paused",
        "result": stage_result,
    })
    logger.info(
        "Stage6 paused: %d valid papers (downloaded=%d, analyzed=%d)",
        valid_count, downloaded_count, analyzed_count
    )
