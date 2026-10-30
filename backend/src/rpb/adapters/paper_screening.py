"""Run-scoped screening commands; grouping never silently selects a human judgment."""

import copy
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from rpb.adapters.llm import event_record, public_error, require_revision
from rpb.adapters.search_terms import allowed, now, source_for, stable
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.runs import initial_screening


def proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "score",
        "theoretical",
        "technical",
        "relevance",
    }:
        raise ValueError("fields")
    initial_screening(value["score"])
    if any(
        not isinstance(value[k], str) or not 1 <= len(value[k].strip()) <= 10000
        for k in ("theoretical", "technical", "relevance")
    ):
        raise ValueError("reasons")
    return copy.deepcopy(value)


def busy(run: Any) -> bool:
    return any(j["state"] in {"queued", "running"} for j in run.get("scoring_jobs", {}).values())


def writable(run: Any) -> None:
    from rpb.adapters.paper_processing import busy as processing_busy

    if processing_busy(run):
        raise AccountError("LOCK_CONTENT_BUSY", 409)
    if run["status"] != "waiting_user" or run.get("phase") not in {
        "screening",
        "processing",
        "analysis",
    }:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if busy(run):
        raise AccountError("LOCK_CONTENT_BUSY", 409)


def register_sources(run: Any, state: Any) -> None:
    for c in run["candidates"]:
        source = {
            "project_id": run["project_id"],
            "source_id": c["id"],
            "content_revision": c["revision"],
        }
        state["sources"].setdefault(
            c["id"],
            {
                "content": {},
                "classification": {
                    "source": source,
                    "classification": "public",
                    "confirmation_status": "unconfirmed",
                    "revision": str(uuid4()),
                    "confirmation": None,
                    "provenance": {
                        "kind": "retrieved_content",
                        "submission_scope_id": None,
                        "dependency_status": "complete",
                    },
                },
            },
        )


def targets(run: Any, body: Any) -> list[Any]:
    writable(run)
    require_revision(run["candidate_revision"], body.get("expected_revision"))
    ids = body.get("candidate_ids")
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 100
        or any(not isinstance(i, str) for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    by_id = {c["id"]: c for c in run["candidates"]}
    if any(i not in by_id for i in ids):
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    chosen = [by_id[i] for i in ids]
    if any(c["deduplication"]["state"] != "distinct" for c in chosen):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    return chosen


def members(run: Any, c: Any) -> list[Any]:
    return [
        x
        for x in run["candidates"]
        if x["deduplication"]["group_id"] == c["deduplication"]["group_id"]
    ]


def protected(c: Any) -> bool:
    return c.get("screening_state") in {"manual_edit", "manual_confirm"}


def has_human_content(c: Any) -> bool:
    return protected(c) or any(
        entry.get("state") in {"manual_edit", "manual_confirm"}
        for entry in c.get("screening_history", [])
    )


def preview(run: Any, body: Any) -> Any:
    if (
        set(body) != {"run_id", "action", "expected_revision", "candidate_ids"}
        or body["action"] != "score"
    ):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    chosen = targets(run, body)
    affected = []
    for leader in chosen:
        for c in members(run, leader):
            if protected(c):
                affected.append(
                    {
                        "kind": "content_change",
                        "object": {
                            "type": "construction_candidate",
                            "id": c["id"],
                            "project_id": run["project_id"],
                            "revision": c["revision"],
                            "read_url": (
                                f"/api/v1/projects/{run['project_id']}"
                                f"/construction-runs/{run['id']}/candidates"
                            ),
                        },
                        "operation": "replace",
                        "content_state": c.get("screening_state", "manual_edit"),
                        "content_scope": ["screening"],
                        "reason": "替换所选论文组的评分与有效性；原判断保留历史",
                    }
                )
    for leader in chosen:
        basis = leader.get("processing", {}).get("basis", {})
        if basis.get("confirmed_revision"):
            affected.append(
                {
                    "kind": "confirmation_invalidation",
                    "object": {
                        "type": "construction_candidate",
                        "id": leader["id"],
                        "project_id": run["project_id"],
                        "revision": leader["revision"],
                        "read_url": (
                            f"/api/v1/projects/{run['project_id']}"
                            f"/construction-runs/{run['id']}/candidates"
                        ),
                    },
                    "confirmation_revision": basis["confirmed_revision"],
                    "reason": "新评分成功后需重新确认受影响的文本处理；原确认保留历史",
                }
            )
    expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    basis = json.dumps(
        [
            run["owner_id"],
            run["id"],
            run["candidate_revision"],
            sorted(body["candidate_ids"]),
            expires,
        ]
    )
    signature = hmac.new(run["confirmation_secret"].encode(), basis.encode(), "sha256").hexdigest()
    return {
        "confirmation_id": stable(signature),
        "action": "score",
        "target": {"type": "construction_run", "id": run["id"]},
        "subject_revision": run["candidate_revision"],
        "impact_revision": run["candidate_revision"],
        "knowledge_version_id": None,
        "candidate_revision": run["candidate_revision"],
        "risks": [{"id": "replace_screening", "message": "将替换所选论文组的人工评分/有效性"}]
        if affected
        else [],
        "expires_at": expires,
        "confirmation_token": expires + "." + signature,
        "affected_items": affected,
        "retained_items": [
            {
                "kind": "protected_scope",
                "scope": "existing_content",
                "reason": "失败/取消保留原判断；历史与原始来源保留",
            }
        ],
        "blocked_reasons": [],
    }


def accept(run: Any, body: Any, state: Any, project: Any) -> Any:
    required = {"run_id", "expected_revision", "candidate_ids", "acknowledged_risk_ids"}
    if not required <= body.keys() or set(body) - required - {"confirmation_token"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    chosen = targets(run, body)
    has_human = any(protected(c) for leader in chosen for c in members(run, leader))
    if has_human:
        token = body.get("confirmation_token")
        try:
            expires, signature = token.rsplit(".", 1)
            basis = json.dumps(
                [
                    run["owner_id"],
                    run["id"],
                    run["candidate_revision"],
                    sorted(body["candidate_ids"]),
                    expires,
                ]
            )
            expected = hmac.new(
                run["confirmation_secret"].encode(), basis.encode(), "sha256"
            ).hexdigest()
            if (
                not signature.isascii()
                or not hmac.compare_digest(signature, expected)
                or datetime.fromisoformat(expires) <= datetime.now(UTC)
                or body["acknowledged_risk_ids"] != ["replace_screening"]
            ):
                raise ValueError("confirmation")
        except ValueError, TypeError, AttributeError:
            raise AccountError("STATE_CONFIRMATION_STALE", 409) from None
    elif body["acknowledged_risk_ids"] != []:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    topic_id = source_for(project)["source_id"]
    source_ids = [topic_id] + [c["id"] for leader in chosen for c in members(run, leader)]
    if any(not allowed(state, run["owner_id"], project, sid) for sid in source_ids):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    identity, revision = str(uuid4()), str(uuid4())
    groups = [
        {
            "candidate_id": c["id"],
            "group_id": c["deduplication"]["group_id"],
            "sources": [
                {
                    "candidate_id": x["id"],
                    "revision": x["revision"],
                    "source": copy.deepcopy(x["source"]),
                    "metadata": copy.deepcopy(x["metadata"]),
                }
                for x in members(run, c)
            ],
        }
        for c in chosen
    ]
    job = {
        "id": identity,
        "owner_id": run["owner_id"],
        "attempt_id": str(uuid4()),
        "revision": revision,
        "state": "queued",
        "created_at": now(),
        "started_at": None,
        "finished_at": None,
        "authority_epoch": run["authority_epoch"],
        "candidate_revision": run["candidate_revision"],
        "source_ids": source_ids,
        "source_id": topic_id,
        "input": {"topic": copy.deepcopy(state["sources"][topic_id]["content"]), "groups": groups},
        "model_selection": copy.deepcopy(run["config_snapshot"]["model_selection"]),
        "config": copy.deepcopy(run["model_config"]),
        "config_revision": run["config_snapshot"]["config_revision"],
        "error": None,
        "confirmed_overwrite": has_human,
        "events": [event_record("queued", UUID(revision), datetime.now(UTC))],
        "results": [],
    }
    job["return_phase"] = run.get("phase", "screening")
    run["phase"] = "screening"
    run.setdefault("scoring_jobs", {})[identity] = job
    return job


def bump(run: Any, changed_ids: set[str]) -> None:
    run["phase"] = "screening"
    if run.get("processing_confirmation"):
        run.setdefault("processing_confirmation_history", []).append(
            run.pop("processing_confirmation")
        )
    for candidate in run["candidates"]:
        if candidate["id"] in changed_ids and candidate.get("processing", {}).get("basis"):
            candidate["processing_stale"] = True
            if candidate["processing"]["basis"]["confirmed_revision"]:
                candidate.setdefault("processing_history", []).append(
                    copy.deepcopy(candidate["processing"])
                )
            candidate["processing"]["basis"]["confirmed_revision"] = None
    revision = str(uuid4())
    run["candidate_revision"] = revision
    run["candidate_version"]["revision"] = revision
    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}


def edit(run: Any, body: Any, actor: Any) -> Any:
    writable(run)
    if set(body) != {"run_id", "candidate_id", "expected_revision", "screening"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    c = next((c for c in run["candidates"] if c["id"] == body["candidate_id"]), None)
    if c is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    require_revision(c["revision"], body["expected_revision"])
    if c["deduplication"]["state"] != "distinct":
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    patch = body["screening"]
    if (
        not isinstance(patch, dict)
        or set(patch) - {"score", "valid", "reason"}
        or not ({"score", "valid"} & patch.keys())
        or not isinstance(patch.get("reason"), str)
        or not 1 <= len(patch["reason"].strip()) <= 10000
        or ("valid" in patch and type(patch["valid"]) is not bool)
    ):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    if "score" in patch:
        try:
            initial_screening(patch["score"])
        except ValueError:
            raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
    value = copy.deepcopy(c["screening"])
    if c.get("screening_stale"):
        value = dict(score=None, score_scale=None, valid=None, threshold_source=None, reason=None)
    value.update(patch)
    if "score" in patch:
        value.update(score_scale={"min": 0, "max": 10}, threshold_source="system_default")
        if "valid" not in patch:
            value["valid"] = initial_screening(patch["score"])["valid"]
    for item in members(run, c):
        archive(item, "manual_edit", str(actor))
        item.update(
            screening=copy.deepcopy(value),
            screening_state="manual_edit",
            screening_stale=False,
            screening_error=None,
            revision=str(uuid4()),
            screening_modified_by=str(actor),
            screening_modified_at=now(),
        )
    bump(run, {item["id"] for item in members(run, c)})
    return c


def archive(c: Any, action: str, actor: str) -> None:
    if c["screening"].get("score") is not None or c["screening"].get("valid") is not None:
        c.setdefault("screening_history", []).append(
            {
                "screening": copy.deepcopy(c["screening"]),
                "state": c.get("screening_state", "agent_draft"),
                "revision": c["revision"],
                "action": action,
                "actor_id": actor,
                "at": now(),
            }
        )


def summary(run: Any) -> Any:
    if run.get("phase") not in {"screening", "processing", "analysis"}:
        return None
    if run["status"] == "cancelled" and "screening_summary" in run:
        return run["screening_summary"]
    leaders = [c for c in run["candidates"] if c["deduplication"]["state"] == "distinct"]
    valid = sum(c["screening"]["valid"] is True and not c.get("screening_stale") for c in leaders)
    invalid = sum(
        c["screening"]["valid"] is False and not c.get("screening_stale") for c in leaders
    )
    return {
        "valid_count": valid,
        "invalid_count": invalid,
        "pending_count": len(leaders) - valid - invalid,
        "failed_count": sum(bool(c.get("screening_error")) for c in leaders),
    }


def task_view(run: Any, job: Any, base: Any) -> Any:
    value = copy.deepcopy(base)
    root = "/api/v1/tasks/" + job["id"]
    value["error"] = public_error(job["error"]) if job.get("error") else None
    if value["error"]:
        value["error"]["message"] = (
            "资源不可用"
            if job["error"] == "PERMISSION_RESOURCE_UNAVAILABLE"
            else "评分未完成；已有判断保留，请查看原因后重试。"
        )
    value.update(
        task_id=job["id"],
        attempt_id=job["attempt_id"],
        operation_id="Construction.ScoreCandidates",
        execution_status=job["state"],
        status_url=root,
        events_url=root + "/events",
        cancel_url=None,
        revision=job["revision"],
        created_at=job["created_at"],
        updated_at=job.get("finished_at") or job.get("started_at") or job["created_at"],
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        waiting_items=[],
        stage="screening",
        event_cursor=job["events"][-1]["cursor"],
    )
    return value
