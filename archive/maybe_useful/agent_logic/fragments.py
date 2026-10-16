"""v1.0 — 隔离留存的 Agent 片段；不是新核心或运行入口。"""

from copy import deepcopy
from datetime import date
from html import escape
import json
import re


def decode_json_text(text: str):
    """只解开完整外围 Markdown fence；JSON Schema 由未来调用方验证。"""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    # JSON 标准不含 NaN/Infinity；不要把它们当成合法候选。
    def reject_constant(value):
        raise ValueError(f"non-JSON constant: {value}")
    return json.loads(stripped, parse_constant=reject_constant)


def semantic_scholar_fields(record: dict, retrieval_batch: str) -> dict:
    """单条已解码响应的字段投影；不负责请求、去重、身份确认或入库。"""
    if not isinstance(record, dict):
        raise TypeError("record must be dict")
    if not isinstance(retrieval_batch, str) or not retrieval_batch.strip():
        raise ValueError("retrieval_batch must be a nonempty string")
    warnings = []

    def optional_text(value, field):
        if value is None:
            return None
        if not isinstance(value, str):
            warnings.append(f"{field}: expected string")
            return None
        return value.strip() or None

    external = record.get("externalIds")
    if external is None:
        external = {}
    elif not isinstance(external, dict):
        warnings.append("externalIds: expected object")
        external = {}
    authors_input = record.get("authors")
    if authors_input is None:
        authors_input = []
    elif not isinstance(authors_input, list):
        warnings.append("authors: expected array")
        authors_input = []
    authors = []
    for index, author in enumerate(authors_input):
        if not isinstance(author, dict):
            warnings.append(f"authors[{index}]: expected object")
            continue
        name = optional_text(author.get("name"), f"authors[{index}].name")
        if name:
            authors.append(name)
    title = optional_text(record.get("title"), "title")
    if title is None:
        warnings.append("title: missing usable title")
    publication_date = optional_text(record.get("publicationDate"), "publicationDate")
    precision = None
    if publication_date:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_date):
                raise ValueError
            date.fromisoformat(publication_date)
            precision = "day"
        except ValueError:
            warnings.append("publicationDate: invalid date")
            publication_date = None
    year = record.get("year")
    valid_year = type(year) is int and 1 <= year <= 9999
    if year is not None and not valid_year:
        warnings.append("year: expected integer in 1..9999")
    if publication_date and valid_year and int(publication_date[:4]) != year:
        warnings.append("year: conflicts with publicationDate")
    if not publication_date and valid_year:
        publication_date, precision = f"{year:04d}", "year"
    return {
        "provider": "semantic_scholar",
        "provider_id": optional_text(record.get("paperId"), "paperId"),
        "retrieval_batch": retrieval_batch,
        "doi": optional_text(external.get("DOI"), "externalIds.DOI"),
        "arxiv_id": optional_text(external.get("ArXiv"), "externalIds.ArXiv"),
        "title": title,
        "authors": authors,
        "abstract": optional_text(record.get("abstract"), "abstract"),
        "venue": optional_text(record.get("venue"), "venue"),
        "publication_date": publication_date,
        "date_precision": precision,
        "raw_record": deepcopy(record),
        "warnings": warnings,
    }


def filter_citation_markers(text: str, allowed_ids: set[str]) -> dict:
    """按首次出现顺序分离已允许/未知标记；不证明引用内容有证据支持。"""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if not isinstance(allowed_ids, (set, frozenset)) or any(
        not isinstance(item, str) for item in allowed_ids
    ):
        raise TypeError("allowed_ids must be a set of strings")
    allowed, unknown, seen = [], [], set()
    for marker in re.findall(r"\[([^\[\]\r\n]+)\]", text):
        if marker not in seen:
            seen.add(marker)
            (allowed if marker in allowed_ids else unknown).append(marker)
    return {"allowed": allowed, "unknown": unknown}


def render_paper_email(project_name: str, papers: list[dict]) -> str:
    """仅 HTML 布局素材。空列表可渲染，不代表应当发送邮件。"""
    def html(value):
        return escape(str(value), quote=True)

    rows = []
    for index, paper in enumerate(papers, 1):
        authors = "、".join(str(author) for author in (paper.get("authors") or [])) or "未知作者"
        title = html(paper.get("title") or "（无标题）")
        venue = html(paper.get("venue") or "未知期刊")
        pub_date = html(paper.get("publication_date") or "")
        summary = html(paper.get("summary") or "（暂无 AI 分析）")
        rows.append(f'<tr><td>{index}</td><td><strong>{title}</strong><br>'
                    f'<small>{html(authors)} · {venue} · {pub_date}</small></td>'
                    f'<td>{summary}</td></tr>')
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
            '<body style="font-family:Arial,sans-serif;color:#333;max-width:800px;'
            'margin:auto;padding:20px;overflow-wrap:anywhere;word-break:break-word">'
            f'<h2>📚 论文推送 — {html(project_name)}</h2>'
            f'<p>本次共推送 <strong>{len(papers)}</strong> 篇有效论文：</p>'
            '<table style="width:100%;table-layout:fixed;border-collapse:collapse">'
            '<thead><tr><th>#</th><th>论文信息</th><th>AI 摘要</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></body></html>')
