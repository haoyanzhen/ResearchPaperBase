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

import json
import logging
import os
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event
from app.agents.construction.pipeline import mark_stage_paused
from app.core.config import settings
from app.models.paper import Paper, ProjectPaperRelation
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """规范化字符串为合法节点 ID：小写、空格→下划线、删除特殊字符。"""
    s = s.lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w\-]", "", s)
    return s[:80]


async def _sync_chromadb(project_id: str, papers: list[Paper]) -> dict:
    """
    将论文元数据序列化为 JSON 缓存（轻量替代方案，无 ChromaDB 依赖）。

    存储路径：STORAGE_DIR/chroma_cache/{project_id}.json
    每条文档包含 id、title、abstract、venue、pub_date、authors、ai_summary，
    供 graph_rag_retrieve() 作为全文检索基础。
    """
    cache_dir = os.path.join(settings.STORAGE_DIR, "chroma_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{project_id}.json")

    docs = []
    for p in papers:
        docs.append({
            "id": p.id,
            "title": p.title,
            "abstract": p.abstract or "",
            "venue": p.venue or "",
            "pub_date": str(p.pub_date) if p.pub_date else None,
            "authors": p.authors or [],
            "ai_summary": (p.ai_analysis or {}).get("summary", ""),
        })

    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump({"project_id": project_id, "docs": docs}, fh, ensure_ascii=False, default=str)

    logger.info("Chroma cache written: %d docs → %s", len(docs), cache_path)
    return {
        "chromadb_synced": True,
        "chromadb_count": len(docs),
        "chromadb_note": "JSON 元数据缓存（轻量替代，无向量嵌入）",
    }


async def _update_networkx_graph(project_id: str, papers: list[Paper]) -> dict:
    """
    构建 NetworkX DiGraph 并序列化为 JSON 持久化存储。

    节点类型：paper、author、venue
    边类型：authored_by（paper→author）、in_venue（paper→venue）、co_author（author↔author）

    存储路径：STORAGE_DIR/graphs/{project_id}.json（node-link 格式）
    """
    try:
        import networkx as nx
    except ImportError:
        logger.warning("networkx not installed; skipping graph update for project %s", project_id)
        return {
            "graph_updated": False,
            "graph_node_count": 0,
            "graph_note": "networkx 未安装，跳过图更新",
        }

    G: nx.DiGraph = nx.DiGraph()

    # 建立论文节点与 author/venue 节点及边
    for paper in papers:
        G.add_node(paper.id, type="paper", title=(paper.title or "")[:120],
                   pub_date=str(paper.pub_date) if paper.pub_date else "")

        author_ids: list[str] = []
        for author in (paper.authors or []):
            au_id = f"au_{_normalize(author)}"
            if not G.has_node(au_id):
                G.add_node(au_id, type="author", name=author)
            G.add_edge(paper.id, au_id, type="authored_by")
            author_ids.append(au_id)

        # co_author 边（同一篇论文的作者互连）
        for i in range(len(author_ids)):
            for j in range(i + 1, len(author_ids)):
                if not G.has_edge(author_ids[i], author_ids[j]):
                    G.add_edge(author_ids[i], author_ids[j], type="co_author")

        if paper.venue:
            v_id = f"v_{_normalize(paper.venue)}"
            if not G.has_node(v_id):
                G.add_node(v_id, type="venue", name=paper.venue)
            G.add_edge(paper.id, v_id, type="in_venue")

    graph_dir = os.path.join(settings.STORAGE_DIR, "graphs")
    os.makedirs(graph_dir, exist_ok=True)
    graph_path = os.path.join(graph_dir, f"{project_id}.json")

    graph_data = nx.node_link_data(G)
    with open(graph_path, "w", encoding="utf-8") as fh:
        json.dump(graph_data, fh, ensure_ascii=False, default=str)

    logger.info(
        "NetworkX graph written: %d nodes, %d edges → %s",
        G.number_of_nodes(), G.number_of_edges(), graph_path,
    )
    return {
        "graph_updated": True,
        "graph_node_count": G.number_of_nodes(),
        "graph_edge_count": G.number_of_edges(),
        "graph_path": graph_path,
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
