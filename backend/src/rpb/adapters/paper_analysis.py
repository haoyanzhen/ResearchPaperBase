"""Run-local analysis commands. No knowledge writes or implicit content adoption."""

import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters import paper_processing as processing
from rpb.adapters import paper_screening as screening
from rpb.adapters.llm import event_record, require_revision
from rpb.adapters.processing_tables import objects
from rpb.adapters.search_terms import allowed, now, source_for, stable
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.analysis import paper_analysis


def busy(run: Any) -> bool:
    return any(j["state"] in {"queued", "running"} for j in run.get("analysis_jobs", {}).values())


def candidate(run: Any, identity: str) -> Any:
    c = next((c for c in run["candidates"] if c["id"] == identity), None)
    if c is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    return c


def writable(run: Any, body: Any) -> Any:
    if busy(run) or screening.busy(run) or processing.busy(run):
        raise AccountError("LOCK_CONTENT_BUSY", 409)
    if run["status"] != "waiting_user" or run.get("phase") not in {"analysis", "ingestion_preview"}:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    c = candidate(run, body["candidate_id"])
    require_revision(c["revision"], body["expected_revision"])
    basis = c.get("processing", {}).get("basis", {})
    if (
        c not in processing.eligible(run)
        or c.get("processing_stale")
        or c.get("processing", {}).get("status") not in {"available", "degraded"}
        or not run.get("processing_confirmation")
        or not basis.get("confirmed_revision")
        or basis["confirmed_revision"] != basis["processing_revision"]
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    return c


def protected(c: Any) -> bool:
    return c.get("analysis_state") in {"manual_edit", "confirmed"}


def proof(run: Any, c: Any, expires: str) -> str:
    data = json.dumps(
        [
            "generate_analysis",
            run["owner_id"],
            run["project_id"],
            run["id"],
            c["id"],
            c["revision"],
            run["candidate_revision"],
            c["processing"]["basis"],
            expires,
        ],
        sort_keys=True,
    )
    return hmac.new(run["confirmation_secret"].encode(), data.encode(), "sha256").hexdigest()


def preview(run: Any, body: Any) -> Any:
    if (
        set(body) != {"run_id", "candidate_id", "expected_revision", "action"}
        or body["action"] != "generate"
    ):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    c = writable(run, body)
    expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    signature = proof(run, c, expires)
    return dict(
        confirmation_id=stable(signature),
        action="generate",
        target={"type": "construction_candidate", "id": c["id"]},
        subject_revision=c["revision"],
        impact_revision=run["candidate_revision"],
        candidate_revision=run["candidate_revision"],
        knowledge_version_id=None,
        expires_at=expires,
        confirmation_token=expires + "." + signature,
        risks=[{"id": "replace_analysis", "message": "将替换当前已保存或已确认的论文分析"}]
        if protected(c)
        else [],
        affected_items=[
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
                "content_state": c["analysis_state"],
                "content_scope": ["analysis"],
                "reason": "成功生成后替换当前分析并重新确认",
            }
        ]
        if protected(c)
        else [],
        retained_items=[
            {
                "kind": "protected_scope",
                "scope": "existing_content",
                "reason": "失败或取消保留原分析；处理文本不变",
            }
        ],
        blocked_reasons=[],
    )


def accept(conn: Any, run: Any, body: Any, state: Any, project: Any) -> Any:
    required = {"run_id", "candidate_id", "expected_revision", "acknowledged_risk_ids"}
    if not required <= body.keys() or set(body) - required - {"confirmation_token"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    c = writable(run, body)
    if protected(c):
        try:
            expires, signature = body.get("confirmation_token", "").rsplit(".", 1)
            if (
                not signature.isascii()
                or not hmac.compare_digest(signature, proof(run, c, expires))
                or datetime.fromisoformat(expires) <= datetime.now(UTC)
                or body["acknowledged_risk_ids"] != ["replace_analysis"]
            ):
                raise ValueError("confirmation")
        except ValueError, TypeError, AttributeError:
            raise AccountError("STATE_CONFIRMATION_STALE", 409) from None
    elif body["acknowledged_risk_ids"] != []:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    p = c["processing"]
    topic = source_for(project)["source_id"]
    source_ids = list(
        dict.fromkeys([topic, p["selected_source_id"], p["basis"]["document_asset_id"]])
    )
    source_ids = [sid for sid in source_ids if sid is not None]
    if any(not allowed(state, run["owner_id"], project, sid) for sid in source_ids):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    row = (
        conn.execute(
            sa.select(objects).where(
                objects.c.id == UUID(p["basis"]["text_revision_id"]),
                objects.c.run_id == UUID(run["id"]),
                objects.c.project_id == UUID(run["project_id"]),
                objects.c.candidate_id == UUID(c["id"]),
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or not row["text"]
        or hashlib.sha256(row["text"].encode()).hexdigest() != p["text_digest"]
    ):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    identity, revision = str(uuid4()), str(uuid4())
    job = dict(
        id=identity,
        revision=revision,
        attempt_id=str(uuid4()),
        state="queued",
        owner_id=run["owner_id"],
        authority_epoch=run["authority_epoch"],
        candidate_id=c["id"],
        candidate_revision=c["revision"],
        processing_basis=copy.deepcopy(p["basis"]),
        source_ids=source_ids,
        source_revisions={
            sid: state["sources"][sid]["classification"]["source"]["content_revision"]
            for sid in source_ids
        },
        input={
            "topic": copy.deepcopy(state["sources"][topic]["content"]),
            "text": row["text"],
            "text_source_kind": p["text_source_kind"],
        },
        model_selection=copy.deepcopy(run["config_snapshot"]["model_selection"]),
        config=copy.deepcopy(run["model_config"]),
        config_revision=run["config_snapshot"]["config_revision"],
        created_at=now(),
        started_at=None,
        finished_at=None,
        error=None,
        events=[event_record("queued", UUID(revision), datetime.now(UTC))],
    )
    run.setdefault("analysis_jobs", {})[identity] = job
    return job


def valid(c: Any) -> bool:
    b = c.get("analysis_basis")
    p = c.get("processing", {}).get("basis", {})
    return bool(
        c.get("analysis")
        and b
        and not c.get("processing_stale")
        and p.get("confirmed_revision")
        and b["processing_revision"] == p["processing_revision"]
        and b["processing_confirmation_revision"] == p["confirmed_revision"]
        and b["text_revision_id"] == p["text_revision_id"]
    )


def save_content(run: Any, c: Any, value: Any, actor: str, source: str) -> None:
    value = paper_analysis(value)
    if c.get("analysis"):
        c.setdefault("analysis_history", []).append(
            {
                "analysis": copy.deepcopy(c["analysis"]),
                "basis": copy.deepcopy(c.get("analysis_basis")),
                "state": c.get("analysis_state"),
                "actor_id": c.get("analysis_modified_by"),
                "at": c.get("analysis_modified_at"),
            }
        )
    basis = c["processing"]["basis"]
    c.update(
        analysis=value,
        analysis_state=source,
        analysis_error=None,
        analysis_modified_by=actor,
        analysis_modified_at=now(),
        analysis_basis={
            "analysis_revision": str(uuid4()),
            "candidate_revision": c["revision"],
            "processing_revision": basis["processing_revision"],
            "processing_confirmation_revision": basis["confirmed_revision"],
            "text_revision_id": basis["text_revision_id"],
        },
        revision=str(uuid4()),
    )
    run.pop("analysis_confirmation", None)
    run["phase"] = "analysis"
    run["candidate_revision"] = str(uuid4())
    run["candidate_version"]["revision"] = run["candidate_revision"]
    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}


def edit(run: Any, body: Any, actor: Any) -> Any:
    if set(body) != {"run_id", "candidate_id", "expected_revision", "analysis"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    c = writable(run, body)
    try:
        value = paper_analysis(body["analysis"])
    except ValueError, UnicodeError:
        raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
    save_content(run, c, value, str(actor), "manual_edit")
    return c


def confirm(run: Any, actor: Any) -> None:
    if busy(run) or run.get("phase") != "analysis":
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    chosen = [c for c in processing.eligible(run) if valid(c)]
    if not chosen:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    for c in chosen:
        if c.get("analysis_state") != "manual_edit":
            c["analysis_state"] = "confirmed"
        c["analysis_confirmed_revision"] = c["analysis_basis"]["analysis_revision"]
        c["analysis_confirmed_by"], c["analysis_confirmed_at"] = str(actor), now()
    run["analysis_confirmation"] = {
        "candidate_ids": [c["id"] for c in chosen],
        "candidate_revision": run["candidate_revision"],
        "actor_id": str(actor),
        "at": now(),
    }
    run["phase"] = "ingestion_preview"
    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}


def latest_errors(run: Any) -> dict[str, str]:
    latest = {}
    for job in sorted(run.get("analysis_jobs", {}).values(), key=lambda j: j["created_at"]):
        latest[job["candidate_id"]] = job
    revisions = {c["id"]: c["revision"] for c in run["candidates"]}
    return {
        identity: job["error"]
        for identity, job in latest.items()
        if job["state"] == "failed"
        and job.get("error")
        and job["candidate_revision"] == revisions.get(identity)
    }


def summary(run: Any) -> Any:
    candidates = processing.eligible(run)
    errors = latest_errors(run)
    return dict(
        completed=sum(valid(c) for c in candidates),
        failed=sum(c["id"] in errors for c in candidates),
        pending=sum(not valid(c) for c in candidates),
        manual=sum(c.get("analysis_state") == "manual_edit" for c in candidates),
        confirmed=bool(run.get("analysis_confirmation")),
        busy=busy(run),
    )


def task_view(run: Any, job: Any, base: Any) -> Any:
    value = screening.task_view(run, job, base)
    value.update(operation_id="Construction.GenerateAnalysis", stage="analysis")
    if value["error"]:
        value["error"]["message"] = "分析未完成；已有内容保留，可重试或人工补全。"
    return value
