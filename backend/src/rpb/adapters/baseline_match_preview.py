"""Read-only screening preview for a complete retrieval containing only existing papers."""

from collections import Counter
from typing import Any
from uuid import UUID

from rpb.adapters.knowledge_baseline_papers import content_digest, pinned_revisions
from rpb.adapters.knowledge_paper_tables import paper_revisions
from rpb.adapters.paper_screening import baseline_ready


def _complete_retrieval(run: Any) -> bool:
    snapshot = run["input_snapshot"]
    resolution = run["resolution"]
    terms = resolution["executable"]
    if (
        resolution["valid"] is not True
        or resolution["failed"]
        or not terms
        or any(term["rejected"] or not term["sources"] for term in terms)
        or Counter(t["term_id"] for t in terms)
        != Counter(t["term_id"] for t in snapshot["selected_terms"])
    ):
        return False
    expected = [(t["term_id"], s["source"], s["config_id"]) for t in terms for s in t["sources"]]
    frozen_sources = {
        (s["provider_config_ref"]["source"], s["provider_config_ref"]["config_id"])
        for s in snapshot["resolved_sources"]
    }
    if {(source, config) for _, source, config in expected} != frozen_sources or len(
        expected
    ) != len(set(expected)):
        return False
    selected = {t["term_id"]: t["content"]["source_policy"] for t in snapshot["selected_terms"]}
    for term in terms:
        policy = selected[term["term_id"]]
        if policy["mode"] == "selected" and (
            {(r["source"], r["config_id"]) for r in policy["source_refs"]}
            != {(r["source"], r["config_id"]) for r in term["sources"]}
        ):
            return False
    results = run["source_results"]
    if any(
        r["status"] != "succeeded"
        or r["error"] is not None
        or r["limited"] is not False
        or type(r["count"]) is not int
        or r["count"] < 0
        or r["skipped_date"] != 0
        for r in results
    ):
        return False
    counts = {(r["term_id"], r["source"], r["config_id"]): r["count"] for r in results}
    # Only a newly attested exhausted search can support this preview; legacy results lack it.
    attested = Counter(tuple(fact) for fact in run.get("exhausted_sources", []))
    if (
        len(counts) != len(results)
        or counts.keys() != set(expected)
        or attested != Counter((*key, count) for key, count in counts.items())
    ):
        return False
    observed = Counter(
        (
            c["source"]["search_term_id"],
            c["source"]["provider_config_ref"]["source"],
            c["source"]["provider_config_ref"]["config_id"],
        )
        for c in run["candidates"]
    )
    return observed == Counter(counts)


def baseline_match_preview(conn: Any, run: Any) -> dict[str, Any] | None:
    if run["status"] != "waiting_user" or run.get("phase") != "screening":
        return None
    return matched_baseline_scope(conn, run)


def match_scope_digest(run: Any, scope: dict[str, Any]) -> str:
    keys = (
        "id",
        "owner_id",
        "project_id",
        "slot_epoch",
        "effective_input_revision",
        "candidate_revision",
        "input_snapshot",
        "config_snapshot",
        "model_config",
        "source_configs",
        "resolution",
        "source_results",
        "exhausted_sources",
        "candidates",
        "baseline_papers",
        "baseline_loaded_version_id",
        "dedup_group_leaders",
        "retrieval_confirmation",
    )
    # The candidate state advances during verification; its revision is bound separately.
    return content_digest({"scope": scope, "facts": {key: run.get(key) for key in keys}})


def matched_baseline_scope(conn: Any, run: Any) -> dict[str, Any] | None:
    if not baseline_ready(run):
        return None
    snapshot = run["input_snapshot"]
    base = snapshot["base_knowledge_version_id"]
    if (
        not base
        or snapshot.get("mode") != "retrieval"
        or snapshot.get("graph_mode") != "incremental"
        or snapshot.get("supplement_ids") != []
        or snapshot.get("pending_revision_ids") != []
        or not run["candidates"]
    ):
        return None
    try:
        decisions = {c["id"]: c["deduplication"] for c in run["candidates"] if c["kind"] == "paper"}
        if len(decisions) != len(run["candidates"]):
            return None
        assets = set()
        for cid, decision in decisions.items():
            group = decision["group_id"]
            leader_id = run["dedup_group_leaders"][group]
            leader = decisions[leader_id]
            if (
                not group
                or group != leader["group_id"]
                or leader["matched_candidate_id"] is not None
            ):
                return None
            if decision["state"] == "match":
                if decision["matched_candidate_id"] != leader_id or cid == leader_id:
                    return None
            elif cid != leader_id or decision["state"] != "match_existing":
                return None
            if leader["state"] != "match_existing" or not leader["matched_project_asset_id"]:
                return None
            assets.add(leader["matched_project_asset_id"])
        if not _complete_retrieval(run):
            return None
        pinned = {
            (str(p), str(r))
            for p, r in conn.execute(
                pinned_revisions(UUID(run["project_id"]), UUID(base)).with_only_columns(
                    paper_revisions.c.project_paper_id, paper_revisions.c.id
                )
            )
        }
        cached = {p["project_paper_id"]: p["paper_revision_id"] for p in run["baseline_papers"]}
        if (
            len(cached) != len(run["baseline_papers"])
            or set(cached.items()) != pinned
            or not assets <= cached.keys()
        ):
            return None
    except AttributeError, KeyError, ValueError, TypeError:
        # Older or incomplete retrieval records remain available for manual review.
        return None
    return {
        "base_knowledge_version_id": base,
        "candidate_count": len(decisions),
        "matched_paper_count": len(assets),
    }
