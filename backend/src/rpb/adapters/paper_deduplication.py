"""Run-local title identity decisions; raw source records are never merged away."""

import copy
from typing import Any
from uuid import uuid4

from rpb.adapters import paper_screening as screening
from rpb.adapters.llm import require_revision
from rpb.adapters.search_terms import now
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.paper_identity import normalized_paper_title
from rpb.modules.construction.domain.runs import RunInputError


def initialize(run: Any, baseline: list[dict[str, str]]) -> None:
    if not isinstance(baseline, list):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    run["baseline_papers"] = copy.deepcopy(baseline)
    run["baseline_loaded_version_id"] = run["input_snapshot"]["base_knowledge_version_id"]
    groups: dict[str, str] = {}
    for candidate in run["candidates"]:
        try:
            title = normalized_paper_title(candidate["metadata"]["title"])
        except RunInputError:
            title = None
        group = groups.setdefault(title, str(uuid4())) if title is not None else None
        candidate["deduplication"] = {
            "normalized_title": title,
            "group_id": group,
            "origin": "automatic",
            "history": [],
            "baseline_matches": [
                item for item in run["baseline_papers"] if item["normalized_title"] == title
            ]
            if title is not None
            else [],
            "baseline_resolution": None,
            "matched_project_asset_id": None,
        }
        candidate["revision"] = str(uuid4())
    run["phase"] = "screening"
    run["dedup_group_leaders"] = {}
    refresh(run)


def refresh(run: Any) -> None:
    groups: dict[str, list[str]] = {}
    for candidate in run["candidates"]:
        group = candidate["deduplication"]["group_id"]
        if group:
            groups.setdefault(group, []).append(candidate["id"])
    leaders = run.setdefault("dedup_group_leaders", {})
    for group, members in groups.items():
        if leaders.get(group) not in members:
            leaders[group] = members[0]
    for group in list(leaders):
        if group not in groups:
            del leaders[group]
    for candidate in run["candidates"]:
        decision = candidate["deduplication"]
        group = decision["group_id"]
        leader = leaders[group] if group else None
        decision["matched_candidate_id"] = leader if leader != candidate["id"] else None
        matches = decision.get("baseline_matches", [])
        resolution = decision.get("baseline_resolution")
        decision["state"] = (
            "needs_title"
            if group is None
            else "match"
            if leader != candidate["id"]
            else "distinct"
            if resolution == "distinct"
            else "match_existing"
            if resolution == "match" or len(matches) == 1
            else "needs_existing_resolution"
            if len(matches) > 1
            else "distinct"
        )
        if resolution is None:
            decision["matched_project_asset_id"] = (
                matches[0]["project_paper_id"] if len(matches) == 1 else None
            )
    revision = str(uuid4())
    run["candidate_revision"] = revision
    run["candidate_version"]["revision"] = revision
    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}


def correct(run: Any, body: Any, actor: Any) -> Any:
    screening.require_unlocked(run)
    if not screening.baseline_ready(run):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if run["status"] != "waiting_user" or run.get("phase") not in {
        "screening",
        "processing",
        "analysis",
    }:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    required = {"run_id", "candidate_id", "expected_revision", "decision", "reason"}
    if set(body) - (
        required
        | {"matched_candidate_id", "matched_candidate_revision", "matched_project_asset_id"}
    ) or not required <= set(body):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    reason = body["reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 10000:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    by_id = {c["id"]: c for c in run["candidates"]}
    candidate = by_id.get(body["candidate_id"])
    if candidate is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    require_revision(candidate["revision"], body["expected_revision"])
    previous = candidate["deduplication"]["group_id"]
    target_leader = candidate["id"]
    if body["decision"] == "distinct" and not (
        {"matched_candidate_id", "matched_candidate_revision", "matched_project_asset_id"}
        & body.keys()
    ):
        group = str(uuid4())
    elif body["decision"] == "match" and isinstance(body.get("matched_project_asset_id"), str):
        if {"matched_candidate_id", "matched_candidate_revision"} & body.keys() or not any(
            item["project_paper_id"] == body["matched_project_asset_id"]
            for item in run.get("baseline_papers", [])
        ):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        group = str(uuid4())
    elif body["decision"] == "match" and isinstance(body.get("matched_candidate_id"), str):
        if "matched_project_asset_id" in body:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        target = by_id.get(body["matched_candidate_id"])
        if target is None:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        require_revision(target["revision"], body.get("matched_candidate_revision"))
        group = target["deduplication"]["group_id"]
        if target["id"] == candidate["id"] or not group:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        target_leader = run.get("dedup_group_leaders", {}).get(group, target["id"])
        if previous == group and target_leader == candidate["id"]:
            target_leader = target["id"]
    else:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    leaders = run.setdefault("dedup_group_leaders", {})
    if (
        previous
        and leaders.get(previous) == candidate["id"]
        and (previous != group or target_leader != candidate["id"])
    ):
        remaining = [
            item
            for item in run["candidates"]
            if item["id"] != candidate["id"] and item["deduplication"]["group_id"] == previous
        ]
        if remaining:
            successor = next(
                (item for item in remaining if item["id"] == target_leader), remaining[0]
            )
            old_decision, inherited = candidate["deduplication"], successor["deduplication"]
            for key in (
                "baseline_matches",
                "baseline_resolution",
                "matched_project_asset_id",
                "origin",
            ):
                inherited[key] = copy.deepcopy(old_decision.get(key))
            if old_decision.get("origin") == "human" and old_decision.get("history"):
                inherited_event = copy.deepcopy(old_decision["history"][-1])
                inherited_event["inherited_from_candidate_id"] = candidate["id"]
                inherited_event["inherited_from_revision"] = candidate["revision"]
                inherited.setdefault("history", []).append(inherited_event)
            leaders[previous] = successor["id"]
    # A group correction is a content change for every source in either affected group.
    for item in run["candidates"]:
        if item["id"] == candidate["id"] or item["deduplication"]["group_id"] in {previous, group}:
            if item["screening"]["score"] is not None or item["screening"]["valid"] is not None:
                screening.archive(item, "deduplication_dependency_changed", str(actor))
                item["screening_stale"] = True
            item["revision"] = str(uuid4())
    decision = candidate["deduplication"]
    record = {
        "decision": body["decision"],
        "matched_candidate_id": body.get("matched_candidate_id"),
        "previous_group_id": previous,
        "group_id": group,
        "reason": reason,
        "actor_id": str(actor),
        "at": now(),
    }
    if body.get("matched_project_asset_id"):
        record["matched_project_asset_id"] = body["matched_project_asset_id"]
    decision["history"].append(record)
    decision.update(
        group_id=group,
        origin="human",
        baseline_resolution=(
            "distinct"
            if body["decision"] == "distinct"
            else "match"
            if body.get("matched_project_asset_id")
            else None
        ),
        matched_project_asset_id=body.get("matched_project_asset_id"),
    )
    leaders[group] = target_leader
    refresh(run)
    screening.bump(
        run,
        {
            item["id"]
            for item in run["candidates"]
            if item["id"] == candidate["id"]
            or item["deduplication"]["group_id"] in {previous, group}
        },
    )
    return candidate


def summary(run: Any) -> dict[str, int] | None:
    if run.get("phase") not in {"screening", "processing", "analysis"}:
        return None
    if run["status"] == "cancelled" and "deduplication_summary" in run:
        return dict(run["deduplication_summary"])
    decisions = [c["deduplication"] for c in run["candidates"]]
    return {
        "unique_count": sum(d["state"] == "distinct" for d in decisions),
        "duplicate_count": sum(d["state"] in {"match", "match_existing"} for d in decisions),
        "unresolved_count": sum(
            d["state"] in {"needs_title", "needs_existing_resolution"} for d in decisions
        ),
    }
