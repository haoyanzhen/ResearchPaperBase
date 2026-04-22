"""
构建模式阶段 2 — 多源论文检索与汇总（FR-012）

职责：
  1. 读取已选中的检索词（is_selected=True）
  2. 按用户配置的数据库列表并发检索（arXiv / OpenAlex / Semantic Scholar）
  3. 三路去重（DOI / arXiv ID / 小写标题）
  4. 新论文写入 papers 表 + project_paper_relations 表
  5. 更新 keywords 的检索统计（searched_papers_total, is_searched）
  6. 将阶段标记为 paused
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event, get_retrieval_config
from app.agents.construction.pipeline import get_pipeline_params, mark_stage_paused
from app.models.paper import Paper, ProjectPaperRelation
from app.models.project import Keyword
from app.models.stage import StageRecord
from app.utils.ids import new_id

logger = logging.getLogger(__name__)

# arXiv Atom XML 命名空间
_ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


# =============================================================================
# API 解析函数
# =============================================================================

def _parse_arxiv(xml_text: str, keyword_id: str) -> list[dict]:
    """解析 arXiv Atom XML，返回论文 dict 列表。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("arXiv XML parse error: %s", e)
        return []

    papers = []
    for entry in root.findall("atom:entry", _ARXIV_NS):
        raw_id = entry.findtext("atom:id", namespaces=_ARXIV_NS, default="") or ""
        arxiv_id = re.sub(r"v\d+$", "", raw_id.rsplit("/", 1)[-1])

        title_raw = entry.findtext("atom:title", namespaces=_ARXIV_NS, default="") or ""
        title = re.sub(r"\s+", " ", title_raw).strip()
        abstract = (entry.findtext("atom:summary", namespaces=_ARXIV_NS, default="") or "").strip()

        authors = [
            (a.findtext("atom:name", namespaces=_ARXIV_NS) or "").strip()
            for a in entry.findall("atom:author", _ARXIV_NS)
        ]

        published = entry.findtext("atom:published", namespaces=_ARXIV_NS, default="") or ""
        pub_date_str = published[:10] if published else None

        doi_el = entry.find("arxiv:doi", _ARXIV_NS)
        doi = (doi_el.text or "").strip() if doi_el is not None else None

        if not title:
            continue

        papers.append({
            "arxiv_id": arxiv_id or None,
            "doi": doi or None,
            "title": title,
            "abstract": abstract or None,
            "authors": [a for a in authors if a],
            "pub_date": pub_date_str,
            "venue": "arXiv",
            "source": "arxiv",
            "_keyword_id": keyword_id,
        })
    return papers


def _rebuild_abstract(inverted_index: dict) -> str | None:
    """从 OpenAlex 倒排索引重建摘要。"""
    if not inverted_index:
        return None
    max_pos = max(pos for positions in inverted_index.values() for pos in positions)
    word_list: list[str | None] = [None] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            word_list[pos] = word
    return " ".join(w for w in word_list if w)


def _parse_openalex(data: dict, keyword_id: str) -> list[dict]:
    """解析 OpenAlex works 响应。"""
    papers = []
    for work in data.get("results", []):
        doi_raw = work.get("doi", "") or ""
        doi = doi_raw.replace("https://doi.org/", "").strip() or None

        # 尝试从 locations 中找 arXiv ID
        arxiv_id = None
        for loc in work.get("locations", []):
            url = loc.get("landing_page_url", "") or ""
            if "arxiv.org" in url:
                arxiv_id = url.rsplit("/", 1)[-1]
                break

        title = (work.get("title") or "").strip()
        if not title:
            continue

        abstract = _rebuild_abstract(work.get("abstract_inverted_index"))
        authors = [
            (a.get("author", {}).get("display_name") or "")
            for a in work.get("authorships", [])
        ]

        pub_year = work.get("publication_year")
        pub_date_str = f"{pub_year}-01-01" if pub_year else None
        venue = (
            work.get("primary_location", {}).get("source", {}).get("display_name") or ""
        ).strip()

        papers.append({
            "arxiv_id": arxiv_id,
            "doi": doi,
            "title": title,
            "abstract": abstract,
            "authors": [a for a in authors if a],
            "pub_date": pub_date_str,
            "venue": venue or "OpenAlex",
            "source": "openalex",
            "_keyword_id": keyword_id,
        })
    return papers


def _parse_semantic_scholar(data: dict, keyword_id: str) -> list[dict]:
    """解析 Semantic Scholar paper search 响应。"""
    papers = []
    for paper in data.get("data", []):
        ext_ids = paper.get("externalIds") or {}
        doi = ext_ids.get("DOI")
        arxiv_id = ext_ids.get("ArXiv")
        title = (paper.get("title") or "").strip()
        if not title:
            continue

        authors = [(a.get("name") or "") for a in (paper.get("authors") or [])]
        year = paper.get("year")
        pub_date_str = f"{year}-01-01" if year else None
        venue = (paper.get("venue") or "").strip()
        abstract = (paper.get("abstract") or "").strip() or None

        papers.append({
            "arxiv_id": arxiv_id,
            "doi": doi,
            "title": title,
            "abstract": abstract,
            "authors": [a for a in authors if a],
            "pub_date": pub_date_str,
            "venue": venue or "Semantic Scholar",
            "source": "semantic_scholar",
            "_keyword_id": keyword_id,
        })
    return papers


# =============================================================================
# API 请求函数
# =============================================================================

async def _fetch_arxiv(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
    timeout: float,
    keyword_id: str,
) -> list[dict]:
    cfg = get_retrieval_config("arxiv")
    base = cfg.get("base_url", "http://export.arxiv.org/api/query")
    url = f"{base}?search_query={quote(query)}&max_results={max_results}&sortBy=submittedDate"
    try:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return _parse_arxiv(resp.text, keyword_id)
    except Exception as exc:
        logger.warning("arXiv fetch error for query '%s': %s", query, exc)
        return []


async def _fetch_openalex(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
    timeout: float,
    api_key: str | None,
    keyword_id: str,
) -> list[dict]:
    cfg = get_retrieval_config("openalex")
    base = cfg.get("base_url", "https://api.openalex.org/works")
    email = cfg.get("polite_email", "app@paperpush.local")
    params: dict = {
        "filter": f"title.search:{query}",
        "per-page": min(max_results, 200),
        "mailto": email,
    }
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = await client.get(base, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return _parse_openalex(resp.json(), keyword_id)
    except Exception as exc:
        logger.warning("OpenAlex fetch error for query '%s': %s", query, exc)
        return []


async def _fetch_semantic_scholar(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
    timeout: float,
    api_key: str | None,
    keyword_id: str,
) -> list[dict]:
    cfg = get_retrieval_config("semantic_scholar")
    base = cfg.get("base_url", "https://api.semanticscholar.org/graph/v1/paper/search")
    fields = cfg.get("fields", "title,authors,year,venue,abstract,externalIds")
    params: dict = {"query": query, "limit": min(max_results, 100), "fields": fields}
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        resp = await client.get(base, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return _parse_semantic_scholar(resp.json(), keyword_id)
    except Exception as exc:
        logger.warning("Semantic Scholar fetch error for query '%s': %s", query, exc)
        return []


# =============================================================================
# 去重与 DB 写入
# =============================================================================

def _dedup(papers: list[dict]) -> list[dict]:
    """
    三路去重（DOI / arXiv ID / 小写标题），在内存中执行。
    返回去重后的列表（保留每路第一次出现的记录）。
    """
    seen_doi: set[str] = set()
    seen_arxiv: set[str] = set()
    seen_title: set[str] = set()
    result = []
    for p in papers:
        doi = (p.get("doi") or "").strip().lower()
        arxiv = (p.get("arxiv_id") or "").strip().lower()
        title = (p.get("title") or "").strip().lower()

        if doi and doi in seen_doi:
            continue
        if arxiv and arxiv in seen_arxiv:
            continue
        if title and title in seen_title:
            continue

        if doi:
            seen_doi.add(doi)
        if arxiv:
            seen_arxiv.add(arxiv)
        if title:
            seen_title.add(title)
        result.append(p)
    return result


async def _save_papers(
    db: AsyncSession,
    project_id: str,
    papers: list[dict],
) -> int:
    """
    将论文写入 papers + project_paper_relations 表，返回实际新增数量。
    对 unique 冲突（DOI / arxiv_id / title）使用 ON CONFLICT DO NOTHING。
    """
    now = datetime.now(timezone.utc)
    added = 0

    for p in papers:
        # 小写 title 用于去重（schema.sql 定义 title UNIQUE 小写）
        title_lower = (p.get("title") or "").strip().lower()
        if not title_lower:
            continue

        pub_date_obj: date | None = None
        if p.get("pub_date"):
            try:
                pub_date_obj = date.fromisoformat(p["pub_date"])
            except ValueError:
                pass

        paper_id = new_id("paper")
        paper_stmt = (
            pg_insert(Paper)
            .values(
                id=paper_id,
                doi=p.get("doi") or None,
                arxiv_id=p.get("arxiv_id") or None,
                title=title_lower,
                authors=p.get("authors") or [],
                pub_date=pub_date_obj,
                venue=p.get("venue") or None,
                abstract=p.get("abstract") or None,
                source=p.get("source"),
                retrieved_at=now,
                download_status="not_downloaded",
                ai_analysis_status="not_analyzed",
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        result = await db.execute(paper_stmt)
        # rowcount > 0 means a new row was inserted
        if result.rowcount == 0:
            # 已存在，取已有 ID
            existing = await db.execute(
                select(Paper.id).where(Paper.title == title_lower)
            )
            row = existing.scalar_one_or_none()
            if row is None:
                continue
            paper_id = row
        else:
            added += 1

        # 建立课题-论文关联（已存在则跳过）
        rel_stmt = (
            pg_insert(ProjectPaperRelation)
            .values(
                id=new_id("ppr"),
                project_id=project_id,
                paper_id=paper_id,
                is_valid=False,
                push_status=False,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing()
        )
        await db.execute(rel_stmt)

    await db.commit()
    return added


# =============================================================================
# 阶段主入口
# =============================================================================

async def run(
    db: AsyncSession,
    project_id: str,
    user_id: str,
    record: StageRecord,
    modifications: dict[str, Any],
) -> None:
    """
    阶段 2 执行逻辑。

    modifications 可包含：
      {"removed_ids": ["paper_id_1", ...]}  — 从结果中移除指定论文（在阶段2后已检索的情况下使用）
    """
    pipeline_params = await get_pipeline_params(db, project_id)
    databases: list[str] = pipeline_params["databases"]

    # ── 读取已选中的检索词 ─────────────────────────────────────────────────
    kw_res = await db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id, Keyword.is_selected == True)
        .order_by(Keyword.created_at)
    )
    keywords = kw_res.scalars().all()

    if not keywords:
        raise RuntimeError("没有启用的检索词，请先在阶段1生成或添加检索词")

    # ── 从用户 configs 读取各数据库 API key ────────────────────────────────
    from app.services.config_service import get_config
    openalex_key = await get_config(db, user_id, "database.openalex.api_key")
    ss_key = await get_config(db, user_id, "database.semantic_scholar.api_key")

    emit_sse_event(project_id, "stage_progress", {
        "stage": 2, "progress": 5,
        "detail": f"开始检索 {len(keywords)} 个检索词 × {len(databases)} 个数据库..."
    })

    # ── 并发检索（每个关键词×数据库一个任务）────────────────────────────────
    cfg_arxiv = get_retrieval_config("arxiv")
    cfg_oa = get_retrieval_config("openalex")
    cfg_ss = get_retrieval_config("semantic_scholar")

    all_raw: list[dict] = []
    source_counts: dict[str, int] = {}
    total_tasks = len(keywords) * len(databases)
    completed_tasks = 0

    async with httpx.AsyncClient() as client:
        for kw in keywords:
            # 选择此数据库的 boolean_expression，回退到 search_word
            be = kw.boolean_expressions or {}

            tasks = []
            db_names = []

            if "arxiv" in databases:
                query = be.get("arxiv") or kw.search_word
                tasks.append(_fetch_arxiv(
                    client, query,
                    cfg_arxiv.get("max_results_per_keyword", 100),
                    cfg_arxiv.get("request_timeout_seconds", 30),
                    kw.id,
                ))
                db_names.append("arxiv")

            if "openalex" in databases:
                query = be.get("openalex") or kw.search_word
                tasks.append(_fetch_openalex(
                    client, query,
                    cfg_oa.get("max_results_per_keyword", 100),
                    cfg_oa.get("request_timeout_seconds", 30),
                    openalex_key,
                    kw.id,
                ))
                db_names.append("openalex")

            if "semantic_scholar" in databases:
                query = be.get("semantic_scholar") or kw.search_word
                tasks.append(_fetch_semantic_scholar(
                    client, query,
                    cfg_ss.get("max_results_per_keyword", 100),
                    cfg_ss.get("request_timeout_seconds", 30),
                    ss_key,
                    kw.id,
                ))
                db_names.append("semantic_scholar")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            kw_counts: dict[str, int] = {}
            for db_name, res in zip(db_names, results):
                if isinstance(res, Exception):
                    logger.warning("DB %s retrieval failed for keyword '%s': %s", db_name, kw.search_word, res)
                    kw_counts[db_name] = 0
                else:
                    papers_batch = res
                    all_raw.extend(papers_batch)
                    kw_counts[db_name] = len(papers_batch)
                    source_counts[db_name] = source_counts.get(db_name, 0) + len(papers_batch)

            # 更新关键词检索统计
            kw.is_searched = True
            kw.searched_papers_arxiv = kw.searched_papers_arxiv + kw_counts.get("arxiv", 0)
            kw.searched_papers_openalex = kw.searched_papers_openalex + kw_counts.get("openalex", 0)
            kw.searched_papers_semanticscholar = kw.searched_papers_semanticscholar + kw_counts.get("semantic_scholar", 0)
            kw.searched_papers_total = (
                kw.searched_papers_arxiv
                + kw.searched_papers_openalex
                + kw.searched_papers_semanticscholar
                + kw.searched_papers_ads
            )
            await db.commit()

            completed_tasks += len(db_names)
            progress = int(5 + 60 * completed_tasks / max(total_tasks, 1))
            detail_parts = [f"{src}: {cnt}" for src, cnt in kw_counts.items()]
            emit_sse_event(project_id, "stage_progress", {
                "stage": 2,
                "progress": progress,
                "detail": f"已检索 '{kw.search_word[:40]}': {', '.join(detail_parts)}",
            })

    # ── 三路去重 ──────────────────────────────────────────────────────────
    emit_sse_event(project_id, "stage_progress", {
        "stage": 2, "progress": 70, "detail": f"共检索 {len(all_raw)} 条记录，正在去重..."
    })
    deduped = _dedup(all_raw)
    logger.info("Stage2: %d raw → %d after dedup", len(all_raw), len(deduped))

    # ── 写入 DB ────────────────────────────────────────────────────────────
    emit_sse_event(project_id, "stage_progress", {
        "stage": 2, "progress": 80, "detail": f"写入 {len(deduped)} 篇论文到数据库..."
    })
    new_count = await _save_papers(db, project_id, deduped)

    # retry 路径：处理 removed_ids（confirm 路径的 removed_ids 由 apply_stage_action 提前应用）
    removed_ids: set[str] = set(modifications.get("removed_ids") or [])
    if removed_ids:
        from sqlalchemy import delete
        await db.execute(
            delete(ProjectPaperRelation).where(
                ProjectPaperRelation.project_id == project_id,
                ProjectPaperRelation.paper_id.in_(removed_ids),
            )
        )
        await db.commit()

    # ── 获取当前课题关联论文总数 ────────────────────────────────────────────
    from sqlalchemy import func
    count_res = await db.execute(
        select(func.count(ProjectPaperRelation.id)).where(
            ProjectPaperRelation.project_id == project_id
        )
    )
    total_associated = count_res.scalar_one()

    stage_result = {
        "total_papers": total_associated,
        "new_papers": new_count,
        "removed_papers": len(removed_ids),
        "sources": source_counts,
    }

    await mark_stage_paused(db, record.id, stage_result)

    emit_sse_event(project_id, "stage_pause", {
        "stage": 2,
        "status": "paused",
        "result": stage_result,
    })
    logger.info("Stage2 paused: %d total papers (%d new)", total_associated, new_count)
