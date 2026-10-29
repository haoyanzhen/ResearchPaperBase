"""Run-local title identity decisions; raw source records are never merged away."""

from typing import Any
from uuid import uuid4

from rpb.adapters.llm import require_revision
from rpb.adapters.search_terms import now
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.paper_identity import normalized_paper_title
from rpb.modules.construction.domain.runs import RunInputError


def initialize(run: Any) -> None:
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
        }
        candidate["revision"] = str(uuid4())
    run["phase"] = "screening"
    refresh(run)


def refresh(run: Any) -> None:
    leaders: dict[str, str] = {}
    for candidate in run["candidates"]:
        decision = candidate["deduplication"]
        group = decision["group_id"]
        leader = leaders.setdefault(group, candidate["id"]) if group else None
        decision["matched_candidate_id"] = leader if leader != candidate["id"] else None
        decision["state"] = (
            "needs_title" if group is None else "match" if leader != candidate["id"] else "distinct"
        )
    revision = str(uuid4())
    run["candidate_revision"] = revision
    run["candidate_version"]["revision"] = revision
    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}


def correct(run: Any, body: Any, actor: Any) -> Any:
    if run["status"] != "waiting_user" or run.get("phase") != "screening":
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    required = {"run_id", "candidate_id", "expected_revision", "decision", "reason"}
    if set(body) - (
        required | {"matched_candidate_id", "matched_candidate_revision"}
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
    if body["decision"] == "distinct" and not (
        {"matched_candidate_id", "matched_candidate_revision"} & body.keys()
    ):
        group = str(uuid4())
    elif body["decision"] == "match" and isinstance(body.get("matched_candidate_id"), str):
        target = by_id.get(body["matched_candidate_id"])
        if target is None:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        require_revision(target["revision"], body.get("matched_candidate_revision"))
        group = target["deduplication"]["group_id"]
        if target["id"] == candidate["id"] or not group:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    else:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    # A group correction is a content change for every source in either affected group.
    for item in run["candidates"]:
        if item["id"] == candidate["id"] or item["deduplication"]["group_id"] in {previous, group}:
            item["revision"] = str(uuid4())
    decision = candidate["deduplication"]
    decision["history"].append(
        {
            "decision": body["decision"],
            "matched_candidate_id": body.get("matched_candidate_id"),
            "previous_group_id": previous,
            "group_id": group,
            "reason": reason,
            "actor_id": str(actor),
            "at": now(),
        }
    )
    decision.update(group_id=group, origin="human")
    refresh(run)
    return candidate


def summary(run: Any) -> dict[str, int] | None:
    if run.get("phase") != "screening":
        return None
    if run["status"] == "cancelled" and "deduplication_summary" in run:
        return dict(run["deduplication_summary"])
    decisions = [c["deduplication"] for c in run["candidates"]]
    return {
        "unique_count": sum(d["state"] == "distinct" for d in decisions),
        "duplicate_count": sum(d["state"] == "match" for d in decisions),
        "unresolved_count": sum(d["state"] == "needs_title" for d in decisions),
    }
