"""Read-only screening preview for a complete retrieval with no new papers."""

from collections import Counter
from typing import Any
from uuid import UUID

from rpb.adapters.knowledge_baseline_papers import content_digest, pinned_revisions
from rpb.adapters.knowledge_paper_tables import paper_revisions
from rpb.adapters.paper_screening import baseline_ready, proposal
from rpb.modules.construction.domain.runs import initial_screening, instant


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
        or type(r["skipped_date"]) is not int
        or r["skipped_date"] != 0
        for r in results
    ):
        return False
    counts = {(r["term_id"], r["source"], r["config_id"]): r["count"] for r in results}
    # Only a newly attested exhausted search can support this preview; legacy results lack it.
    facts = run.get("exhausted_sources", [])
    if any(len(fact) != 4 or type(fact[3]) is not int for fact in facts):
        return False
    attested = Counter(tuple(fact) for fact in facts)
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
    keys: tuple[str, ...] = (
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
    if "retrieval_proof_version" in run:
        keys += ("retrieval_proof_version",)
    # The candidate state advances during verification; its revision is bound separately.
    return content_digest({"scope": scope, "facts": {key: run.get(key) for key in keys}})


def _excluded_group(run: Any, leader: Any, members: list[Any]) -> bool:
    verdict = leader["screening"]
    state = leader.get("screening_state")
    if (
        verdict["valid"] is not False
        or not isinstance(verdict["reason"], str)
        or not verdict["reason"].strip()
        or any(
            item.get("screening_stale") is not False
            or item.get("screening_error") is not None
            or item.get("screening_state") != state
            or item["screening"] != verdict
            for item in members
        )
    ):
        return False
    if state == "manual_edit":
        return all(
            item.get("screening_modified_by") == run["owner_id"]
            and instant(item.get("screening_modified_at")) is not None
            for item in members
        )
    if state != "agent_draft":
        return False
    basis = leader["screening_basis"]
    job = run["scoring_jobs"][basis["task_id"]]
    group_id = leader["deduplication"]["group_id"]
    groups = [g for g in job["input"]["groups"] if g["group_id"] == group_id]
    if len(groups) != 1 or groups[0]["candidate_id"] != leader["id"]:
        return False
    sources = groups[0]["sources"]
    # The scoring worker timestamps each group member separately.
    inputs = {k: v for k, v in basis.items() if k != "at"}
    # Scoring changes candidate revisions. Compare the actual content sent for each source.
    if (
        basis["candidate_sources"] != sources
        or basis["topic"] != job["input"]["topic"]
        or len(members) != len(sources)
        or any(
            item["id"] != source["candidate_id"]
            or item["metadata"] != source["metadata"]
            or item["source"] != source["source"]
            or instant(item["screening_basis"].get("at")) is None
            or any(item["screening_basis"].get(k) != v for k, v in inputs.items())
            for item, source in zip(members, sources, strict=True)
        )
    ):
        return False
    evidence = proposal(basis["reasons"])
    expected = initial_screening(evidence["score"])
    return (
        job["state"] == "succeeded"
        and job["owner_id"] == run["owner_id"]
        and job["id"] == basis["task_id"]
        and basis["model_selection"]
        == job["model_selection"]
        == run["config_snapshot"]["model_selection"]
        and basis["config_revision"]
        == job["config_revision"]
        == run["config_snapshot"]["config_revision"]
        and basis["threshold"] == expected["threshold"]
        and expected["valid"] is False
        and all(verdict[k] == expected[k] for k in ("score", "score_scale", "threshold_source"))
        and verdict["reason"]
        == "\n".join(evidence[k] for k in ("theoretical", "technical", "relevance"))
        and {"candidate_id": leader["id"], "value": evidence, "error": None} in job["results"]
    )


def matched_baseline_scope(conn: Any, run: Any) -> dict[str, Any] | None:
    if not baseline_ready(run):
        return None
    snapshot = run["input_snapshot"]
    base = snapshot["base_knowledge_version_id"]
    if (
        not base
        or snapshot.get("mode") != "retrieval"
        or snapshot.get("graph_mode") not in {"incremental", "rebuild"}
        or snapshot.get("graph_mode") != run.get("request", {}).get("graph_mode", "incremental")
        or snapshot.get("supplement_ids") != []
        or snapshot.get("pending_revision_ids") != []
        or not isinstance(run.get("candidates"), list)
        or (not run["candidates"] and run.get("retrieval_proof_version") != 2)
    ):
        return None
    try:
        candidates = {c["id"]: c for c in run["candidates"] if c["kind"] == "paper"}
        if len(candidates) != len(run["candidates"]):
            return None
        assets = set()
        excluded: dict[str, list[Any]] = {}
        for cid, candidate in candidates.items():
            decision = candidate["deduplication"]
            group = decision["group_id"]
            leader_id = run["dedup_group_leaders"][group]
            leader = candidates[leader_id]["deduplication"]
            if (
                not group
                or group != leader["group_id"]
                or leader["matched_candidate_id"] is not None
            ):
                return None
            if decision["state"] == "match":
                if decision["matched_candidate_id"] != leader_id or cid == leader_id:
                    return None
            elif cid != leader_id:
                return None
            if leader["state"] == "distinct":
                if leader["matched_project_asset_id"] is not None:
                    return None
                excluded.setdefault(leader_id, []).append(candidate)
                continue
            if leader["state"] != "match_existing" or not leader["matched_project_asset_id"]:
                return None
            assets.add(leader["matched_project_asset_id"])
        if excluded and (
            run.get("retrieval_proof_version") != 2
            or not all(
                _excluded_group(run, candidates[cid], members) for cid, members in excluded.items()
            )
        ):
            return None
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
        "candidate_count": len(candidates),
        **({"excluded_paper_count": len(excluded)} if excluded else {}),
        "matched_paper_count": len(assets),
    }
