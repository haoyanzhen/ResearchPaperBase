"""
深度研究模式 Agent 公共基础设施（FR-026~028）

提供：
  - SUB_MODE_NAMES       — 子模式名称映射
  - load_deep_research_prompts() — lru_cache YAML 加载器
  - get_project_valid_papers()   — 获取课题有效论文列表
  - graph_rag_retrieve()         — 简单关键词匹配上下文检索（Graph-RAG 简化版）
  - build_history_text()         — 将对话轮次格式化为 LLM 历史上下文
  - extract_referenced_papers()  — 从 LLM 回复中提取 [paper_id] 引用
"""

import re
import logging
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Project

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config"

# 对话子模式中文名称
SUB_MODE_NAMES: dict[str, str] = {
    "theory": "理论分析",
    "technical": "技术讨论",
    "experiment": "实验方案设计",
}

# Graph-RAG 上下文最大论文数
_MAX_CONTEXT_PAPERS = 8
# 每篇论文摘要截断长度（chars）
_ABSTRACT_TRUNCATE = 400
# 对话历史最多携带轮数
_MAX_HISTORY_TURNS = 8


@lru_cache(maxsize=1)
def load_deep_research_prompts() -> dict:
    """加载并缓存深度研究模式提示词配置（config/deep_research_prompts.yaml）。"""
    with open(_CONFIG_DIR / "deep_research_prompts.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def get_project_valid_papers(
    db: AsyncSession,
    project_id: str,
) -> list[tuple]:
    """
    获取课题内所有有效论文（is_valid=True），按 total_score 降序。
    返回 list of (Paper, ProjectPaperRelation)。
    """
    res = await db.execute(
        select(Paper, ProjectPaperRelation)
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
        )
        .order_by(ProjectPaperRelation.total_score.desc())
    )
    return list(res.all())


async def graph_rag_retrieve(
    db: AsyncSession,
    project_id: str,
    query: str,
    top_k: int = _MAX_CONTEXT_PAPERS,
) -> list[dict]:
    """
    简化版 Graph-RAG 检索：基于关键词匹配从论文库中找出最相关的论文。

    实现策略（ChromaDB 不可用时的降级方案）：
      1. 将 query 按空格/标点分词，取长度 ≥ 3 的词
      2. 对 papers.title / papers.abstract 进行 ILIKE 匹配
      3. 按命中关键词数 + is_valid 排序，取 top_k 篇
      4. 返回论文元数据列表供 LLM 上下文构建

    返回 list of dict：
      {paper_id, title, authors, venue, pub_date, abstract_snippet, total_score, matched_keywords}
    """
    # 分词：取长度≥3的字母数字词
    words = re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", query)
    keywords = list({w.lower() for w in words if len(w) >= 2})[:10]

    rows = await get_project_valid_papers(db, project_id)

    scored: list[tuple[int, dict]] = []
    seen_ids: set[str] = set()
    for paper, rel in rows:
        if paper.id in seen_ids:
            continue
        seen_ids.add(paper.id)

        # 计算关键词命中数
        text_lower = ((paper.title or "") + " " + (paper.abstract or "")).lower()
        hits = sum(1 for kw in keywords if kw in text_lower)

        scored.append((hits, {
            "paper_id": paper.id,
            "title": paper.title,
            "authors": (paper.authors or [])[:3],
            "venue": paper.venue or "",
            "pub_date": str(paper.pub_date)[:4] if paper.pub_date else "",
            "abstract_snippet": (paper.abstract or "")[:_ABSTRACT_TRUNCATE],
            "total_score": rel.total_score or 0,
            "matched_keywords": hits,
        }))

    # 先按命中数降序，再按总分降序
    scored.sort(key=lambda x: (x[0], x[1]["total_score"]), reverse=True)
    return [item for _, item in scored[:top_k]]


def build_context_from_papers(papers: list[dict]) -> str:
    """将检索到的论文列表格式化为 LLM 可读的上下文字符串。"""
    if not papers:
        return "（当前课题暂无有效论文可供参考，请先完成构建模式的论文收集）"

    lines: list[str] = []
    for p in papers:
        authors_str = "、".join(p["authors"]) if p["authors"] else "未知作者"
        lines.append(
            f"[{p['paper_id']}] {p['title']}\n"
            f"  作者: {authors_str}  来源: {p['venue']} ({p['pub_date']})\n"
            f"  摘要: {p['abstract_snippet']}"
        )
    return "\n\n".join(lines)


def build_history_text(turns: list, max_turns: int = _MAX_HISTORY_TURNS) -> str:
    """
    将最近 max_turns 轮对话格式化为历史文本供 LLM 使用。
    turns: list of DialogueTurn ORM 实例（已按 turn_index 升序排列）
    """
    if not turns:
        return "（无历史对话）"

    recent = turns[-max_turns:]
    parts: list[str] = []
    for t in recent:
        parts.append(f"用户（轮{t.turn_index}）：{t.user_content}")
        parts.append(f"助手（轮{t.turn_index}）：{t.assistant_content[:500]}{'...' if len(t.assistant_content) > 500 else ''}")
    return "\n\n".join(parts)


def extract_referenced_papers(content: str, paper_ids: set[str]) -> list[str]:
    """
    从 LLM 回复正文中提取 [paper_id] 格式的引用。
    只收录 paper_ids 集合内存在的 ID（防止幻觉引用）。
    """
    cited = re.findall(r'\[([^\]]+)\]', content)
    return [pid for pid in cited if pid in paper_ids]
