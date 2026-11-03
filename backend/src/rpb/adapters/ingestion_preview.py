"""Read-only view of the currently confirmed paper analysis subset."""

from typing import Any

from rpb.adapters import paper_analysis as analysis
from rpb.adapters import paper_processing as processing
from rpb.adapters import paper_screening as screening
from rpb.modules.account_config.application.ports import AccountError


def preview(run: Any, waiting_item: Any) -> dict[str, Any]:
    if (
        run["status"] != "waiting_user"
        or run.get("phase") != "ingestion_preview"
        or analysis.busy(run)
        or processing.busy(run)
        or screening.busy(run)
        or not screening.baseline_ready(run)
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    confirmation = run.get("analysis_confirmation") or run.get("matched_screening") or {}
    if confirmation.get("candidate_revision") != run.get("candidate_revision"):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    confirmed = set(confirmation.get("candidate_ids", []))
    eligible = {c["id"] for c in processing.eligible(run)}
    papers, skipped, failed, degraded = [], [], [], []
    errors = analysis.latest_errors(run)
    for c in run["candidates"]:
        identity = c["id"]
        if identity not in eligible:
            if c.get("screening_error"):
                failed.append({"candidate_id": identity, "reason": c["screening_error"]})
            else:
                state = c.get("deduplication", {}).get("state")
                reason = (
                    "筛选依据已失效，需重新筛选"
                    if c.get("screening_stale")
                    else "重复候选"
                    if state in {"match", "match_existing"}
                    else "未通过筛选"
                    if c["screening"].get("valid") is False
                    else "去重或筛选尚未完成"
                )
                if state == "distinct" and (confirmation.get("scope") or {}).get(
                    "excluded_paper_count"
                ):
                    rationale = c["screening"].get("reason")
                    if not isinstance(rationale, str) or not rationale.strip():
                        failed.append(
                            {"candidate_id": identity, "reason": "筛选排除理由缺失，请重新核对"}
                        )
                        continue
                    reason = "筛选排除：" + rationale
                skipped.append({"candidate_id": identity, "reason": reason})
        elif (
            identity in confirmed
            and analysis.valid(c)
            and c.get("analysis_confirmed_revision") == c["analysis_basis"]["analysis_revision"]
        ):
            papers.append(identity)
            if c.get("processing", {}).get("status") == "degraded":
                degraded.append({"candidate_id": identity, "reason": "使用摘要降级文本"})
        else:
            failed.append(
                {
                    "candidate_id": identity,
                    "reason": errors.get(identity)
                    or c.get("processing", {}).get("failure_reason")
                    or "分析未确认或已失效",
                }
            )
    for result in run.get("source_results", []):
        if result["status"] in {"failed", "skipped"}:
            target = failed if result["status"] == "failed" else skipped
            target.append(
                {
                    "term_id": result["term_id"],
                    "config_id": result["config_id"],
                    "reason": result.get("error") or result["status"],
                }
            )
    for term in (run.get("resolution") or {}).get("failed", []):
        rejected = term.get("resolution", {}).get("rejected", [])
        if not rejected:
            failed.append({"term_id": term["term_id"], "reason": "检索词来源不可执行"})
        for source in rejected:
            failed.append(
                {
                    "term_id": term["term_id"],
                    "config_id": source.get("config_id"),
                    "reason": source.get("reason_code", "来源不可执行"),
                }
            )
    for term in (run.get("resolution") or {}).get("executable", []):
        for source in term.get("rejected", []):
            skipped.append(
                {
                    "term_id": term["term_id"],
                    "config_id": source.get("config_id"),
                    "reason": source.get("reason_code", "来源不可执行"),
                }
            )
    if set(papers) != confirmed:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    return {
        "revision": run["candidate_revision"],
        "base_knowledge_version_id": (run.get("input_snapshot") or {}).get(
            "base_knowledge_version_id"
        ),
        "valid_papers": papers,
        "valid_materials": [],
        "skipped": skipped,
        "failed": failed,
        "degraded": degraded,
        "non_knowledge_items": [],
        "risks": (
            [{"id": "ABSTRACT_ONLY", "message": "部分论文使用摘要降级文本"}] if degraded else []
        ),
        "waiting_item": waiting_item,
    }
