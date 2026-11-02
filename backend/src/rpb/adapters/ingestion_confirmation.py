"""Bind an ingestion preview to its complete frozen input, without accepting it."""

import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters import ingestion_preview
from rpb.adapters.analysis_lineage import currently_usable
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.construction_slots import is_current
from rpb.adapters.knowledge_baseline_papers import baseline_papers
from rpb.adapters.knowledge_tables import heads
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.search_terms import load, now
from rpb.modules.account_config.application.ports import AccountError


def signature(run: Any, actor: str, expires: str) -> str:
    preview = ingestion_preview.preview(run, None)
    preview.pop("waiting_item")
    basis = {
        "action": "confirm_ingestion_preview",
        "actor_id": actor,
        "project_id": run["project_id"],
        "run_id": run["id"],
        "attempt_id": run["attempt_id"],
        "slot_epoch": run["slot_epoch"],
        "waiting": run["waiting"],
        "effective_input_revision": run["effective_input_revision"],
        "candidate_revision": run["candidate_revision"],
        "input_snapshot": run.get("input_snapshot"),
        "config_snapshot": run.get("config_snapshot"),
        "model_config": run.get("model_config"),
        "source_configs": run.get("source_configs"),
        "source_results": run.get("source_results"),
        "analysis_confirmation": run.get("analysis_confirmation"),
        "processing_confirmation": run.get("processing_confirmation"),
        "analysis_lineage": run.get("analysis_lineage", {}),
        "preview": preview,
        "candidates": run["candidates"],
        "expires_at": expires,
    }
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hmac.new(run["confirmation_secret"].encode(), encoded, hashlib.sha256).hexdigest()


def validate(run: Any, actor: str, token: str, risk_ids: list[str]) -> bool:
    try:
        expires, supplied = token.rsplit(".", 1)
        deadline = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        expected_risks = [item["id"] for item in ingestion_preview.preview(run, None)["risks"]]
        return (
            deadline.tzinfo is not None
            and deadline > datetime.now(UTC)
            and risk_ids == expected_risks
            and supplied.isascii()
            and hmac.compare_digest(supplied, signature(run, actor, expires))
        )
    except AccountError, ValueError, TypeError, AttributeError, KeyError:
        return False


def accept_locked(
    conn: Any, store: Any, actor: UUID, project_id: UUID, run_id: UUID, body: dict[str, Any]
) -> dict[str, Any]:
    """Accept within an authenticated transaction; not exposed until a builder exists."""
    from rpb.adapters.runs import persist, transition

    conn.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK})
    project = store.terms.project(conn, actor, project_id, write=True)
    conn.execute(sa.select(slots).where(slots.c.project_id == project_id).with_for_update()).first()
    row = (
        conn.execute(
            sa.select(runs)
            .where(runs.c.id == run_id, runs.c.project_id == project_id, runs.c.owner_id == actor)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    run: dict[str, Any] = copy.deepcopy(row["payload"])
    if (
        not store.terms.llm.permitted_actor(conn, actor)
        or project["authority_epoch"] != run["authority_epoch"]
        or run["status"] != "waiting_user"
        or run.get("phase") != "ingestion_preview"
        or (run.get("candidate_version") or {}).get("state") != "preparing"
        or (run.get("candidate_version") or {}).get("content_locked")
        or not is_current(conn, run)
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    required = {
        "waiting_item_id",
        "expected_revision",
        "subject_revision",
        "candidate_revision",
        "confirmation_token",
        "acknowledged_risk_ids",
    }
    if set(body) != required:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    wait = run["waiting"]
    if (
        body["waiting_item_id"] != wait["id"]
        or body["expected_revision"] != wait["revision"]
        or body["subject_revision"] != run["candidate_revision"]
        or body["candidate_revision"] != run["candidate_revision"]
        or not validate(run, str(actor), body["confirmation_token"], body["acknowledged_risk_ids"])
    ):
        raise AccountError("STATE_CONFIRMATION_STALE", 409)
    preview = ingestion_preview.preview(run, None)
    latest = conn.scalar(sa.select(heads.c.version_id).where(heads.c.project_id == project_id))
    if preview["base_knowledge_version_id"] != (str(latest) if latest else None):
        raise AccountError("STATE_CONFIRMATION_STALE", 409)
    state = load(conn, project)
    selected = set(preview["valid_papers"])
    if (not selected and preview["base_knowledge_version_id"] is None) or any(
        not currently_usable(run, candidate, state, project, actor)
        for candidate in run["candidates"]
        if candidate["id"] in selected
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if latest and (
        run["input_snapshot"].get("mode") != "retrieval"
        or run["input_snapshot"].get("pending_revision_ids") != []
        or run["input_snapshot"].get("supplement_ids") != []
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    retained = baseline_papers(conn, run, papers_only=True)
    if retained != run.get("baseline_papers"):
        raise AccountError("STATE_CONFIRMATION_STALE", 409)
    accepted_attempt = run["attempt_id"]
    run["attempt_id"] = str(uuid4())
    run["lease_until"] = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    run["ingestion_confirmation"] = {
        "actor_id": str(actor),
        "at": now(),
        "attempt_id": run["attempt_id"],
        "accepted_attempt_id": accepted_attempt,
        "input_revision": run["effective_input_revision"],
        "candidate_revision": run["candidate_revision"],
        "input_snapshot": copy.deepcopy(run["input_snapshot"]),
        "config_snapshot": copy.deepcopy(run["config_snapshot"]),
        "model_config": copy.deepcopy(run["model_config"]),
        "source_configs": copy.deepcopy(run["source_configs"]),
        "preview": preview,
        "retained_papers": [
            {key: paper[key] for key in ("project_paper_id", "paper_revision_id")}
            for paper in retained
        ],
        "candidate_snapshot": copy.deepcopy(run["candidates"]),
        "acknowledged_risk_ids": copy.deepcopy(body["acknowledged_risk_ids"]),
    }
    run["candidate_version"]["content_locked"] = True
    run["phase"] = "knowledge_build"
    transition(run, "running")
    persist(conn, run)
    return run
