"""
深度研究模式 — 知识图谱构建器（FR-025）

FR-025 要求：深度研究模式以只读方式使用知识图谱，不向图数据库写入数据。

实现策略（无 ChromaDB / NetworkX 依赖的轻量版本）：
  - 从 PostgreSQL 论文库动态构建图数据，无需单独图数据库
  - 节点类型：paper（论文）、keyword（检索词）、author（作者）、venue（期刊/会议）
  - 边类型：authored_by、has_keyword、in_venue
  - rebuild_graph：仅重新计算统计数据，不持久化到外部数据库（存根）

后续迭代可替换为真正的 NetworkX + ChromaDB 集成。
"""

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Keyword

logger = logging.getLogger(__name__)

# 节点 ID 前缀规范
_PAPER_PREFIX  = ""           # paper.id 本身即节点 ID
_AUTHOR_PREFIX = "au_"
_KW_PREFIX     = "kw_"
_VENUE_PREFIX  = "v_"


def _normalize(s: str) -> str:
    """将字符串规范化为合法节点 ID：小写、空格→下划线、删除特殊字符。"""
    s = s.lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w\-]", "", s)
    return s[:80]  # 截断防止超长


async def build_graph_data(
    db: AsyncSession,
    project_id: str,
    node_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    从数据库动态构建知识图谱 JSON 数据。

    node_types: 若指定，仅返回指定类型的节点（及其边）；None 返回全部。
    返回：{"nodes": [...], "edges": [...], "stats": {...}}
    """
    requested = set(node_types) if node_types else {"paper", "keyword", "author", "venue"}

    # ── 1. 获取有效论文 ────────────────────────────────────────────────────────
    res = await db.execute(
        select(Paper, ProjectPaperRelation)
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
        )
        .order_by(ProjectPaperRelation.total_score.desc())
    )
    rows = list(res.all())

    # ── 2. 获取构建模式生成的检索词 ───────────────────────────────────────────
    kw_res = await db.execute(
        select(Keyword).where(Keyword.project_id == project_id)
    )
    search_keywords = list(kw_res.scalars().all())

    nodes: list[dict] = []
    edges: list[dict] = []

    # 去重辅助
    seen_authors: set[str] = set()
    seen_venues:  set[str] = set()
    seen_kws:     set[str] = set()
    seen_edges:   set[tuple] = set()

    def add_edge(src: str, tgt: str, etype: str, weight: float = 1.0) -> None:
        key = (src, tgt, etype)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"source": src, "target": tgt, "type": etype, "weight": weight})

    # ── 3. 论文节点 ───────────────────────────────────────────────────────────
    if "paper" in requested:
        for paper, rel in rows:
            nodes.append({
                "id": paper.id,
                "type": "paper",
                "label": paper.title,
                "score": rel.total_score or 0,
            })

    # ── 4. 作者节点 + authored_by 边 ─────────────────────────────────────────
    if "author" in requested:
        for paper, rel in rows:
            for author in (paper.authors or []):
                norm = _normalize(author)
                if not norm:
                    continue
                au_id = f"{_AUTHOR_PREFIX}{norm}"
                if au_id not in seen_authors:
                    seen_authors.add(au_id)
                    nodes.append({"id": au_id, "type": "author", "label": author})
                if "paper" in requested:
                    add_edge(paper.id, au_id, "authored_by")

    # ── 5. 期刊/会议节点 + in_venue 边 ───────────────────────────────────────
    if "venue" in requested:
        for paper, rel in rows:
            if not paper.venue:
                continue
            norm = _normalize(paper.venue)
            v_id = f"{_VENUE_PREFIX}{norm}"
            if v_id not in seen_venues:
                seen_venues.add(v_id)
                nodes.append({"id": v_id, "type": "venue", "label": paper.venue})
            if "paper" in requested:
                add_edge(paper.id, v_id, "in_venue")

    # ── 6. 检索词节点 + has_keyword 边 ───────────────────────────────────────
    if "keyword" in requested:
        for kw in search_keywords:
            norm = _normalize(kw.search_word)
            kw_id = f"{_KW_PREFIX}{norm}"
            if kw_id not in seen_kws:
                seen_kws.add(kw_id)
                nodes.append({"id": kw_id, "type": "keyword", "label": kw.search_word})

        # 将论文与检索词连接：若检索词出现在论文标题中
        if "paper" in requested:
            for paper, rel in rows:
                title_lower = (paper.title or "").lower()
                for kw in search_keywords:
                    if kw.search_word.lower() in title_lower:
                        kw_id = f"{_KW_PREFIX}{_normalize(kw.search_word)}"
                        add_edge(paper.id, kw_id, "has_keyword")

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "paper_count": sum(1 for n in nodes if n["type"] == "paper"),
            "author_count": len(seen_authors),
            "venue_count": len(seen_venues),
            "keyword_count": len(seen_kws),
        },
    }


async def get_graphml(
    db: AsyncSession,
    project_id: str,
) -> str:
    """
    导出 GraphML 格式的知识图谱。
    不依赖 networkx，手动生成 GraphML XML。
    """
    data = await build_graph_data(db, project_id)
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/graphml"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://graphml.graphdrawing.org/graphml '
        'http://graphml.graphdrawing.org/graphml/1.0/graphml.xsd">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="type"  for="node" attr.name="type"  attr.type="string"/>',
        '  <key id="score" for="node" attr.name="score" attr.type="double"/>',
        '  <key id="etype" for="edge" attr.name="type"  attr.type="string"/>',
        '  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>',
        f'  <graph id="G" edgedefault="directed">',
    ]

    for node in data["nodes"]:
        nid = node["id"].replace('"', "&quot;")
        label = (node.get("label") or "").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        score = node.get("score", 0)
        ntype = node.get("type", "")
        lines.append(f'    <node id="{nid}">')
        lines.append(f'      <data key="label">{label}</data>')
        lines.append(f'      <data key="type">{ntype}</data>')
        lines.append(f'      <data key="score">{score}</data>')
        lines.append(f'    </node>')

    for i, edge in enumerate(data["edges"]):
        src = edge["source"].replace('"', "&quot;")
        tgt = edge["target"].replace('"', "&quot;")
        etype = edge.get("type", "")
        weight = edge.get("weight", 1.0)
        lines.append(f'    <edge id="e{i}" source="{src}" target="{tgt}">')
        lines.append(f'      <data key="etype">{etype}</data>')
        lines.append(f'      <data key="weight">{weight}</data>')
        lines.append(f'    </edge>')

    lines.append("  </graph>")
    lines.append("</graphml>")
    return "\n".join(lines)


async def rebuild_graph_stub(project_id: str) -> dict:
    """
    知识图谱重建存根（FR-025）。

    FR-025 说明：深度研究模式以只读方式使用知识图谱；
    实际的图数据库写入应在构建模式 stage6_storage 中进行。
    此处仅返回一个任务 ID 表示"已接受重建请求"。

    后续迭代可在此触发 ChromaDB embedding 重建 + NetworkX 图更新。
    """
    from app.utils.ids import new_id
    task_id = new_id("gt")
    logger.info("graph rebuild requested for project %s (stub, task_id=%s)", project_id, task_id)
    return {"task_id": task_id, "message": "知识图谱重建任务已提交"}
