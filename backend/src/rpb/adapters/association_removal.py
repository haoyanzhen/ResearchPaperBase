"""Bind an explicit association exclusion to exact published revisions and writer conflicts."""

import base64
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.association_removal_inputs import pinned_manifest
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_tables import heads
from rpb.adapters.llm import event_record, require_revision
from rpb.adapters.run_tables import runs
from rpb.adapters.search_terms import now
from rpb.modules.account_config.application.ports import AccountError


def _scope(conn: Any, project: Any, selection: Any) -> Any:
    project_id = project["id"]
    version = conn.scalar(sa.select(heads.c.version_id).where(heads.c.project_id == project_id))
    if version is None:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    members = sorted(
        pinned_manifest(conn, project_id, version)["manifest"]["papers"],
        key=lambda p: p["project_paper_id"],
    )
    invalid = AccountError("VALIDATION_FIELD_INVALID", 422)
    if not isinstance(selection, dict):
        raise invalid
    if selection.get("scope") == "selected" and set(selection) == {"scope", "targets"}:
        requested = selection["targets"]
        if (
            not isinstance(requested, list)
            or not requested
            or any(
                not isinstance(t, dict)
                or set(t) != {"kind", "id"}
                or t["kind"] not in ("paper", "material")
                or not isinstance(t["id"], str)
                for t in requested
            )
        ):
            raise invalid
        try:
            ids = {(t["kind"], str(UUID(t["id"]))) for t in requested}
        except ValueError:
            raise invalid from None
        if len(ids) != len(requested):
            raise invalid
        if not ids <= {("paper", p["project_paper_id"]) for p in members}:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    elif (
        selection.get("scope") == "all"
        and set(selection) == {"scope", "kind"}
        and selection["kind"] in ("all", "paper", "material")
    ):
        ids = {("paper", p["project_paper_id"]) for p in members if selection["kind"] != "material"}
    else:
        raise invalid
    targets = [
        {"kind": "paper", "id": p["project_paper_id"], "asset_revision": p["paper_revision_id"]}
        for p in members
        if ("paper", p["project_paper_id"]) in ids
    ]
    if not targets:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    # A frozen retrieval writer inherits every published paper on this baseline.
    # Other queued retrievals freeze their own baseline after they acquire the slot.
    conflicts = []
    for run in conn.scalars(
        sa.select(runs.c.payload).where(
            runs.c.project_id == project_id, runs.c.status.in_(["running", "waiting_user"])
        )
    ):
        frozen = run.get("input_snapshot") or {}
        if (
            frozen.get("base_knowledge_version_id") == str(version)
            and frozen.get("mode") == "retrieval"
        ):
            conflicts.append(
                {
                    "run_id": run["id"],
                    "revision": run["revision"],
                    "attempt_id": run["attempt_id"],
                    "reason": "当前构建将继承待移除成员",
                }
            )
    return {
        "targets": targets,
        "base_knowledge_version_id": str(version),
        "conflicts": conflicts,
        "will_be_empty": len(targets) == len(members),
    }


def _sign(state: Any, encoded: str) -> str:
    return hmac.new(state["cursor_secret"].encode(), encoded.encode(), "sha256").hexdigest()


def preview(conn: Any, actor: UUID, project: Any, state: Any, data: Any) -> Any:
    require_revision(state["revision"], data.get("expected_revision"))
    if set(data) != {"expected_revision", "selection"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    scope = _scope(conn, project, data["selection"])
    pid = str(project["id"])
    base = scope["base_knowledge_version_id"]
    risks = [
        {"id": "EXCLUDE_MEMBERS", "message": "成功发布后从新版本移除所选成员，历史版本与引用保留。"}
    ]
    if scope["will_be_empty"]:
        risks.append({"id": "EMPTY_VERSION", "message": "新版本将不含任何知识证据。"})
    if scope["conflicts"]:
        risks.append({"id": "CANCEL_CONSTRUCTION", "message": "将取消预览列明的冲突构建。"})
    expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    identity = str(uuid4())
    claims = {
        "actor": str(actor),
        "project": pid,
        "epoch": project["authority_epoch"],
        "revision": state["revision"],
        "selection": data["selection"],
        "scope": content_digest(scope),
        "member_scope": content_digest([base, scope["targets"]]),
        "base": base,
        "targets": scope["targets"],
        "risks": [r["id"] for r in risks],
        "expires": expires,
        "id": identity,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).decode()

    def ref(kind: str, rid: str, revision: str | None) -> Any:
        return {"type": kind, "id": rid, "project_id": pid, "revision": revision, "read_url": None}

    return {
        "confirmation_id": identity,
        "action": "clear_associations",
        "target": {
            "type": "construction_workspace",
            "id": str(project["construction_workspace_id"]),
        },
        "subject_revision": state["revision"],
        "impact_revision": str(UUID(claims["scope"][:32])),
        "knowledge_version_id": base,
        "candidate_revision": None,
        "risks": risks,
        "expires_at": expires,
        "confirmation_token": encoded + "." + _sign(state, encoded),
        "targets": scope["targets"],
        "will_be_empty": scope["will_be_empty"],
        "base_knowledge_version_id": base,
        "conflicting_runs": [
            {k: v for k, v in r.items() if k != "attempt_id"} for r in scope["conflicts"]
        ],
        "affected_items": [
            {
                "kind": "association_removal",
                "object": ref(t["kind"], t["id"], t["asset_revision"]),
                "asset_kind": t["kind"],
                "asset_revision": t["asset_revision"],
                "base_knowledge_version_id": base,
            }
            for t in scope["targets"]
        ]
        + [
            {
                "kind": "execution_revocation",
                "object": ref("construction_run", r["run_id"], r["revision"]),
                "attempt_id": r["attempt_id"],
                "reason": r["reason"],
            }
            for r in scope["conflicts"]
        ],
        "retained_items": [
            {
                "kind": "object",
                "object": ref("knowledge_version", base, None),
                "reason": "旧版本、证据及引用保留",
            },
            {"kind": "protected_scope", "scope": "shared_identity", "reason": "共享论文身份保留"},
        ],
        "blocked_reasons": [],
    }


def confirm(conn: Any, store: Any, actor: UUID, project: Any, state: Any, data: Any) -> Any:
    from rpb.adapters.runs import persist, transition

    require_revision(state["revision"], data.get("expected_revision"))
    stale = AccountError("STATE_CONFIRMATION_STALE", 409)
    if set(data) != {"expected_revision", "confirmation_token", "acknowledged_risk_ids"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    try:
        encoded, sig = data["confirmation_token"].split(".")
        if not hmac.compare_digest(_sign(state, encoded), sig):
            raise stale
        claims = json.loads(base64.urlsafe_b64decode(encoded))
        if (
            claims["actor"] != str(actor)
            or claims["project"] != str(project["id"])
            or claims["epoch"] != project["authority_epoch"]
            or claims["revision"] != state["revision"]
            or claims["risks"] != data["acknowledged_risk_ids"]
        ):
            raise stale
    except ValueError, AttributeError, KeyError, TypeError:
        raise stale from None
    previous = conn.scalar(
        sa.select(runs.c.payload).where(
            runs.c.project_id == project["id"],
            runs.c.owner_id == actor,
            sa.or_(
                runs.c.payload["removal"]["confirmation_id"].astext == claims["id"],
                sa.and_(
                    runs.c.payload["removal"]["base_version"].astext == claims["base"],
                    runs.c.payload["removal"]["targets"].contains(claims["targets"]),
                    runs.c.status.in_(["queued", "running", "succeeded"]),
                ),
            ),
        )
    )
    if previous:
        requested = {(t["id"], t["asset_revision"]) for t in claims["targets"]}
        return {
            "run": store.view(previous),
            "task": store.task(previous),
            "pending_revisions": [
                r
                for r in previous["removal"]["revisions"]
                if (r["target_id"], r["base_asset_revision"]) in requested
            ],
        }
    if datetime.fromisoformat(claims["expires"]) <= datetime.now(UTC):
        raise stale
    scope = _scope(conn, project, claims["selection"])
    if content_digest(scope) != claims["scope"]:
        raise stale
    for conflict in scope["conflicts"]:
        old = conn.scalar(
            sa.select(runs.c.payload).where(runs.c.id == UUID(conflict["run_id"])).with_for_update()
        )
        transition(old, "cancelled", "STATE_OPERATION_NOT_ALLOWED")
        persist(conn, old)
    rid, revision, stamp = str(uuid4()), str(uuid4()), now()
    revisions = [
        {
            "id": str(uuid4()),
            "revision": str(uuid4()),
            "created_at": stamp,
            "updated_at": stamp,
            "target_kind": t["kind"],
            "target_id": t["id"],
            "base_asset_revision": t["asset_revision"],
            "operation": "exclude",
            "changes": {},
            "reason": "用户确认移除项目关联",
            "submitted_by": str(actor),
            "inclusion_status": "pending",
            "assigned_run_id": rid,
            "published_version_id": None,
            "confirmations": [],
        }
        for t in scope["targets"]
    ]
    run = {
        "id": rid,
        "revision": revision,
        "project_id": str(project["id"]),
        "owner_id": str(actor),
        "authority_epoch": project["authority_epoch"],
        "task_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "created_at": stamp,
        "updated_at": stamp,
        "status": "queued",
        "phase": "association_removal",
        "request": {"mode": "revision_only"},
        "confirmation_secret": secrets.token_hex(32),
        "input_snapshot": None,
        "effective_input_revision": None,
        "candidate_revision": None,
        "candidate_version": None,
        "config_snapshot": None,
        "candidates": [],
        "source_results": [],
        "events": [event_record("queued", UUID(revision), datetime.now(UTC))],
        "removal": {
            "confirmation_id": claims["id"],
            "member_scope": claims["member_scope"],
            "base_version": scope["base_knowledge_version_id"],
            "targets": scope["targets"],
            "revisions": revisions,
            "acknowledged_risk_ids": claims["risks"],
            "confirmed_at": stamp,
        },
    }
    conn.execute(
        runs.insert().values(
            id=UUID(rid),
            project_id=project["id"],
            owner_id=actor,
            status="queued",
            revision=UUID(revision),
            created_at=datetime.now(UTC),
            payload=run,
        )
    )
    return {"run": store.view(run), "task": store.task(run), "pending_revisions": revisions}
