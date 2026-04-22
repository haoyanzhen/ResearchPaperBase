"""
构建模式阶段 4 — PDF 下载与文本解析（FR-015）

职责：
  1. 取课题有效论文（is_valid=True）中 download_status='not_downloaded' 的记录
  2. 按来源优先级尝试下载 PDF：
       arXiv PDF 直链 → Unpaywall 开放获取链接
  3. 使用 pypdf 解析 PDF，提取文本，截断至配置上限
  4. 将 PDF 和文本文件保存到 STORAGE_DIR/papers/{paper_id}.pdf / .txt
  5. 更新 papers 表：pdf_path / text_path / download_status / download_error
  6. 处理 retry_ids 修改（指定重新下载的论文）
  7. 将阶段标记为 paused
"""

import asyncio
import logging
import os
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import emit_sse_event, get_pdf_download_config
from app.agents.construction.pipeline import get_project, mark_stage_paused
from app.core.config import settings
from app.models.paper import Paper, ProjectPaperRelation
from app.models.stage import StageRecord

logger = logging.getLogger(__name__)


def _storage_dir() -> str:
    """返回并确保 PDF 存储目录存在。"""
    pdf_dir = os.path.join(settings.STORAGE_DIR, "papers")
    os.makedirs(pdf_dir, exist_ok=True)
    return pdf_dir


def _extract_text_from_pdf(pdf_bytes: bytes, max_chars: int) -> str | None:
    """
    使用 pypdf 从 PDF 字节流提取文本。
    失败时返回 None（不中断流程）。
    """
    try:
        import pypdf
        import io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            if sum(len(p) for p in parts) >= max_chars:
                break
        full_text = "\n".join(parts)
        return full_text[:max_chars]
    except Exception as exc:
        logger.debug("pypdf extraction failed: %s", exc)
        return None


async def _try_download_arxiv(
    client: httpx.AsyncClient,
    arxiv_id: str,
    timeout: float,
) -> bytes | None:
    """尝试从 arXiv 下载 PDF（直链 https://arxiv.org/pdf/{id}）。"""
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200 and b"%PDF" in resp.content[:16]:
            return resp.content
    except Exception as exc:
        logger.debug("arXiv download failed for %s: %s", arxiv_id, exc)
    return None


async def _try_download_unpaywall(
    client: httpx.AsyncClient,
    doi: str,
    email: str,
    timeout: float,
) -> bytes | None:
    """通过 Unpaywall API 获取开放获取 PDF 链接并下载。"""
    api_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        resp = await client.get(api_url, timeout=30.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        pdf_url = (data.get("best_oa_location") or {}).get("url_for_pdf")
        if not pdf_url:
            return None
        pdf_resp = await client.get(pdf_url, timeout=timeout, follow_redirects=True)
        if pdf_resp.status_code == 200 and b"%PDF" in pdf_resp.content[:16]:
            return pdf_resp.content
    except Exception as exc:
        logger.debug("Unpaywall download failed for DOI %s: %s", doi, exc)
    return None


async def _download_paper(
    client: httpx.AsyncClient,
    paper: Paper,
    cfg: dict,
) -> tuple[bytes | None, str]:
    """
    尝试多来源下载 PDF，返回 (pdf_bytes_or_None, error_msg)。
    """
    timeout = cfg.get("request_timeout_seconds", 60)
    sources: list[str] = cfg.get("sources", ["arxiv", "unpaywall"])
    email = cfg.get("unpaywall_email", "app@paperpush.local")
    max_size = cfg.get("max_file_size_mb", 50) * 1024 * 1024

    for source in sources:
        if source == "arxiv" and paper.arxiv_id:
            pdf = await _try_download_arxiv(client, paper.arxiv_id, timeout)
            if pdf and len(pdf) <= max_size:
                return pdf, ""
        elif source == "unpaywall" and paper.doi:
            pdf = await _try_download_unpaywall(client, paper.doi, email, timeout)
            if pdf and len(pdf) <= max_size:
                return pdf, ""

    reasons = []
    if not paper.arxiv_id:
        reasons.append("无 arXiv ID")
    if not paper.doi:
        reasons.append("无 DOI")
    if reasons:
        return None, f"无法下载: {', '.join(reasons)}"
    return None, "所有下载来源均失败"


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
    阶段 4 执行逻辑。

    modifications 可包含：
      {"retry_ids": ["paper_id_1", ...]}  — 将指定论文的 download_status 重置为 not_downloaded 后重试
    """
    cfg = get_pdf_download_config()
    pdf_dir = _storage_dir()
    max_text_chars = cfg.get("max_text_chars", 100000)

    # ── 处理 retry_ids：重置指定论文的下载状态 ────────────────────────────
    retry_ids: list[str] = modifications.get("retry_ids") or []
    if retry_ids:
        retry_res = await db.execute(
            select(Paper).where(Paper.id.in_(retry_ids))
        )
        for paper in retry_res.scalars().all():
            paper.download_status = "not_downloaded"
            paper.download_error = None
        await db.commit()

    # ── 取有效论文中待下载的 ────────────────────────────────────────────────
    pending_res = await db.execute(
        select(Paper)
        .join(ProjectPaperRelation, Paper.id == ProjectPaperRelation.paper_id)
        .where(
            ProjectPaperRelation.project_id == project_id,
            ProjectPaperRelation.is_valid == True,
            Paper.download_status == "not_downloaded",
        )
    )
    pending_papers = pending_res.scalars().all()

    emit_sse_event(project_id, "stage_progress", {
        "stage": 4, "progress": 5,
        "detail": f"共 {len(pending_papers)} 篇有效论文待下载..."
    })

    success_count = 0
    failed_count = 0
    skipped_count = 0

    async with httpx.AsyncClient() as client:
        for i, paper in enumerate(pending_papers):
            emit_sse_event(project_id, "stage_progress", {
                "stage": 4,
                "progress": int(5 + 80 * i / max(len(pending_papers), 1)),
                "detail": f"正在下载 ({i+1}/{len(pending_papers)}): {paper.title[:50]}..."
            })

            pdf_bytes, err = await _download_paper(client, paper, cfg)

            if pdf_bytes is None:
                paper.download_status = "failed"
                paper.download_error = err
                failed_count += 1
                await db.commit()
                continue

            # ── 保存 PDF ──────────────────────────────────────────────────
            pdf_path = os.path.join(pdf_dir, f"{paper.id}.pdf")
            try:
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
            except OSError as exc:
                paper.download_status = "failed"
                paper.download_error = f"文件写入失败: {exc}"
                failed_count += 1
                await db.commit()
                continue

            # ── 提取文本 ──────────────────────────────────────────────────
            text = _extract_text_from_pdf(pdf_bytes, max_text_chars)
            text_path: str | None = None
            if text:
                text_path = os.path.join(pdf_dir, f"{paper.id}.txt")
                try:
                    with open(text_path, "w", encoding="utf-8") as f:
                        f.write(text)
                except OSError as exc:
                    logger.warning("Text file write failed for %s: %s", paper.id, exc)
                    text_path = None

            paper.download_status = "success"
            paper.pdf_path = pdf_path
            paper.text_path = text_path
            paper.download_error = None
            success_count += 1
            await db.commit()

            # 简短延迟避免高频下载被封
            await asyncio.sleep(0.5)

    # ── 统计 ────────────────────────────────────────────────────────────
    skipped_count = len(pending_papers) - success_count - failed_count

    stage_result = {
        "total_attempted": len(pending_papers),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }

    await mark_stage_paused(db, record.id, stage_result)

    emit_sse_event(project_id, "stage_pause", {
        "stage": 4,
        "status": "paused",
        "result": stage_result,
    })
    logger.info(
        "Stage4 paused: %d success, %d failed out of %d",
        success_count, failed_count, len(pending_papers)
    )
