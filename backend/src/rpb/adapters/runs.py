"""Atomic manual retrieval acceptance and immutable Run projections."""

import base64
import binascii
import copy
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.llm import event_record, require_revision, uuid_value
from rpb.adapters.llm import public_error as config_error
from rpb.adapters.run_tables import commands, runs
from rpb.adapters.search_terms import TermStore, load, now, stable
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.runs import RunInputError, start_input
from rpb.modules.construction.domain.terms import resolve_terms


def public_error(code: str) -> dict[str, Any]:
    result = config_error(code)
    if code == "PERMISSION_RESOURCE_UNAVAILABLE":
        result["message"] = "资源不可用"
    return result


ACTIVE = {"queued", "running", "waiting_user"}


def page(items: list[Any], data: Any, secret: str, scope: list[str]) -> Any:
    size = data.get("page_size", 20)
    if type(size) is not int or not 1 <= size <= 100:
        raise AccountError("VALIDATION_BAD_REQUEST", 400)
    expires = int(datetime.now(UTC).timestamp()) + 3600
    cursor = data.get("cursor")
    if cursor:
        try:
            raw, signature = cursor.split(".")
            expected = hmac.new(secret.encode(), raw.encode(), "sha256").hexdigest()
            if len(cursor) > 4096 or not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            claim = json.loads(base64.urlsafe_b64decode(raw))
            if claim["scope"] != scope:
                raise ValueError("scope")
            expires = claim["expires"]
            if expires <= datetime.now(UTC).timestamp():
                raise AccountError("VALIDATION_CURSOR_EXPIRED", 400)
            matches = [
                i
                for i, item in enumerate(items)
                if item.get("id", item.get("revision")) == claim["last"]
            ]
            if not matches:
                raise ValueError("boundary")
            items = items[matches[0] + 1 :]
        except ValueError, KeyError, TypeError, binascii.Error, UnicodeError:
            raise AccountError("VALIDATION_CURSOR_MISMATCH", 400) from None
    chosen = items[:size]
    next_cursor = None
    if len(items) > size:
        raw = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "scope": scope,
                    "expires": expires,
                    "last": chosen[-1].get("id", chosen[-1].get("revision")),
                }
            ).encode()
        ).decode()
        next_cursor = raw + "." + hmac.new(secret.encode(), raw.encode(), "sha256").hexdigest()
    return {"items": chosen, "next_cursor": next_cursor}


def persist(conn: Any, run: Any) -> None:
    conn.execute(
        runs.update()
        .where(runs.c.id == UUID(run["id"]))
        .values(status=run["status"], revision=UUID(run["revision"]), payload=run)
    )


def transition(run: Any, status: str, error: str | None = None) -> None:
    run.update(status=status, revision=str(uuid4()), updated_at=now(), error=error)
    if status in {"failed", "cancelled"}:
        run["finished_at"] = now()
    if status == "cancelled":
        run["cleaned_candidate_count"] = len(run["candidates"])
        run["candidates"] = []
    if status == "cancelled" and run["candidate_version"]:
        run["candidate_version"].update(
            state="discarded", closing_reason={"code": "cancelled", "message": "构建已取消"}
        )
    run["events"].append(event_record(status, UUID(run["revision"]), datetime.now(UTC)))


class RunStore:
    def __init__(self, terms: TermStore) -> None:
        self.terms, self.account = terms, terms.account

    def resolve(self, conn: Any, actor: Any, project: Any, data: Any) -> Any:
        state = load(conn, project)
        selected, resolutions = [], []
        for ref in data["selected_terms"]:
            term = self.terms.term(state, ref["term_id"])
            if term["confirmed_revision"] is None:
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            require_revision(term["confirmed_revision"], ref["confirmed_revision"])
            if term["confirmed_revision"] != term["revision"]:
                raise AccountError("STATE_REVISION_CONFLICT", 412)
            content = copy.deepcopy(term["confirmation_history"][-1]["content"])
            selected.append({**ref, "content": content})
            try:
                resolution = self.terms.sources.resolve_on(conn, actor, content["source_policy"])
            except AccountError as exc:
                if exc.status != 409:
                    raise
                resolution = {
                    "sources": [],
                    "rejected": [{"reason_code": exc.code}],
                    "valid": False,
                }
            resolutions.append(
                {
                    "term_id": ref["term_id"],
                    "source_policy": content["source_policy"],
                    "resolution": resolution,
                }
            )
        result = resolve_terms(resolutions)
        if not result["valid"]:
            raise AccountError("CONFIG_CONNECTION_FAILED", 409)
        _, model = self.terms.model(conn, actor, data["model_selection"])
        return selected, result, model

    def waiting(self, run: Any) -> list[Any]:
        if run["status"] != "waiting_user":
            return []
        wait = run["waiting"]
        expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        basis = ":".join(
            [run["owner_id"], run["project_id"], wait["id"], wait["revision"], expires]
        )
        token = hmac.new(run["confirmation_secret"].encode(), basis.encode(), "sha256").hexdigest()
        return [
            {
                "id": wait["id"],
                "kind": "retrieval",
                "revision": wait["revision"],
                "allowed_actions": [],
                "confirmation": {
                    "confirmation_id": stable(token),
                    "action": "confirm_retrieval",
                    "target": {"type": "waiting_item", "id": wait["id"]},
                    "subject_revision": run["effective_input_revision"],
                    "impact_revision": wait["revision"],
                    "knowledge_version_id": None,
                    "candidate_revision": run["candidate_revision"],
                    "risks": [],
                    "expires_at": expires,
                    "confirmation_token": token,
                    "affected_items": [],
                    "retained_items": [],
                    "blocked_reasons": [],
                },
            }
        ]

    def task(self, run: Any) -> Any:
        base = "/api/v1/tasks/" + run["task_id"]
        return {
            "task_id": run["task_id"],
            "attempt_id": run["attempt_id"],
            "operation_id": "Construction.Start",
            "target": {"type": "construction_run", "id": run["id"]},
            "project_id": run["project_id"],
            "knowledge_version_id": None,
            "execution_status": run["status"],
            "status_url": base,
            "events_url": base + "/events",
            "cancel_url": (
                f"/api/v1/projects/{run['project_id']}/construction-runs/{run['id']}/cancel"
            )
            if run["status"] in ACTIVE
            else None,
            "result_refs": [],
            "revision": run["revision"],
            "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "stage": "retrieval",
            "business_state": run["status"],
            "waiting_items": [
                {
                    "kind": "construction_step",
                    "subject": {"type": "waiting_item", "id": w["id"]},
                    "subject_revision": w["revision"],
                    "owner": {"type": "construction_run", "id": run["id"]},
                    "read_url": (
                        f"/api/v1/projects/{run['project_id']}/construction-runs/{run['id']}"
                    ),
                    "allowed_actions": [],
                }
                for w in self.waiting(run)
            ],
            "cancel_requested_at": run.get("cancel_requested_at"),
            "error": public_error(run["error"]) if run.get("error") else None,
            "warnings": [],
            "event_cursor": run["events"][-1]["cursor"],
            "partial_result_ref": None,
            "target_location": {
                "parent_type": "project",
                "parent_id": run["project_id"],
                "read_url": (f"/api/v1/projects/{run['project_id']}/construction-runs/{run['id']}"),
            },
            "material_use_notices": [],
        }

    def view(self, run: Any) -> Any:
        return {
            **{
                k: copy.deepcopy(run.get(k))
                for k in (
                    "id",
                    "revision",
                    "created_at",
                    "updated_at",
                    "status",
                    "input_snapshot",
                    "config_snapshot",
                    "candidate_version",
                    "candidate_revision",
                    "effective_input_revision",
                )
            },
            "phase": "retrieval",
            "base_knowledge_version_id": None,
            "published_knowledge_version_id": None,
            "completion": None,
            "steps": [
                {
                    "id": run["task_id"],
                    "kind": "retrieval",
                    "state": run["status"],
                    "result_summary": {
                        "candidate_count": len(run["candidates"])
                        + run.get("cleaned_candidate_count", 0),
                        "sources": run["source_results"],
                        "resolution": run.get("resolution"),
                    },
                    "error": public_error(run["error"]) if run.get("error") else None,
                }
            ],
            "waiting_items": self.waiting(run),
            "task": self.task(run),
            "available_actions": [
                {
                    "action": "cancel",
                    "enabled": run["status"] in ACTIVE,
                    "reason_code": None
                    if run["status"] in ACTIVE
                    else "STATE_OPERATION_NOT_ALLOWED",
                }
            ],
        }

    def invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None = None,
    ) -> Any:
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and str(actor) != expected_actor:
                raise AccountError("AUTH_SESSION_INVALID", 401)
            if operation in {"task", "events", "result"}:
                row = (
                    conn.execute(
                        sa.select(runs).where(
                            runs.c.owner_id == actor, runs.c.payload["task_id"].astext == target
                        )
                    )
                    .mappings()
                    .first()
                )
                if not row or operation == "result":
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                project = self.terms.project(conn, actor, row["project_id"])
                run = copy.deepcopy(row["payload"])
                self.revoke(conn, project, run)
                return (
                    {"view": self.task(run), "events": run["events"]}
                    if operation == "events"
                    else self.task(run)
                )
            project = self.terms.project(conn, actor, uuid_value(str(target)), csrf is not None)
            state = load(conn, project)

            def paginate(items: list[Any], revision: str = "") -> Any:
                return page(
                    items,
                    data,
                    state["cursor_secret"],
                    [str(actor), str(project["id"]), operation, data.get("run_id", ""), revision],
                )

            if operation == "list_runs":
                rows = conn.execute(
                    sa.select(runs)
                    .where(runs.c.project_id == project["id"])
                    .order_by(runs.c.created_at.desc(), runs.c.id.desc())
                ).mappings()
                result = []
                for row in rows:
                    run = copy.deepcopy(row["payload"])
                    self.revoke(conn, project, run)
                    result.append(self.view(run))
                return paginate(result)
            run = None
            if "run_id" in data:
                row = (
                    conn.execute(
                        sa.select(runs).where(
                            runs.c.id == uuid_value(data["run_id"]),
                            runs.c.project_id == project["id"],
                        )
                    )
                    .mappings()
                    .first()
                )
                if not row:
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                run = copy.deepcopy(row["payload"])
                self.revoke(conn, project, run)
                if operation == "read_run":
                    return self.view(run)
                if operation == "candidates":
                    return paginate(copy.deepcopy(run["candidates"]), run["revision"])
                if operation == "input_revisions":
                    return paginate(
                        []
                        if not run["input_snapshot"]
                        else [
                            {
                                "revision": run["effective_input_revision"],
                                "source_revision": None,
                                "created_at": run["input_snapshot"]["frozen_at"],
                                "reason": "initial",
                                "input_snapshot": run["input_snapshot"],
                            }
                        ],
                        run["revision"],
                    )
            request_id = data.get("_request_id", str(uuid4()))
            body = {k: v for k, v in data.items() if k != "_request_id"}
            if not key or not 16 <= len(key) <= 128 or any(not 32 <= ord(c) <= 126 for c in key):
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            command = {
                "project_id": project["id"],
                "actor_id": actor,
                "operation": operation,
                "key": key,
            }
            condition = sa.and_(*(commands.c[k] == v for k, v in command.items()))
            old = conn.execute(sa.select(commands).where(condition)).mappings().first()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                return old["payload"]
            if operation == "start":
                try:
                    inputs = start_input(body)
                except RunInputError:
                    raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
                self.resolve(conn, actor, project, inputs)
                # queued registrations may coexist; occupied writers may not.
                for active in conn.execute(
                    sa.select(runs).where(
                        runs.c.project_id == project["id"], runs.c.status.in_(ACTIVE)
                    )
                ).mappings():
                    current = copy.deepcopy(active["payload"])
                    self.revoke(conn, project, current)
                    if current["status"] in {"running", "waiting_user"}:
                        raise AccountError("LOCK_CONSTRUCTION_OCCUPIED", 409)
                identity, task_id, timestamp = str(uuid4()), str(uuid4()), now()
                run = {
                    "id": identity,
                    "project_id": str(project["id"]),
                    "owner_id": str(actor),
                    "authority_epoch": project["authority_epoch"],
                    "status": "queued",
                    "revision": str(uuid4()),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "task_id": task_id,
                    "attempt_id": str(uuid4()),
                    "request": inputs,
                    "input_snapshot": None,
                    "config_snapshot": None,
                    "effective_input_revision": None,
                    "candidate_revision": None,
                    "candidate_version": None,
                    "candidates": [],
                    "source_results": [],
                    "events": [],
                    "confirmation_secret": secrets.token_hex(32),
                    "error": None,
                }
                run["events"].append(
                    event_record("queued", UUID(run["revision"]), datetime.now(UTC))
                )
                conn.execute(
                    runs.insert().values(
                        id=UUID(identity),
                        project_id=project["id"],
                        owner_id=actor,
                        status="queued",
                        revision=UUID(run["revision"]),
                        payload=run,
                        created_at=datetime.now(UTC),
                    )
                )
                value = {"run": self.view(run), "task": self.task(run)}
            elif operation == "cancel" and run:
                if set(body) != {"run_id", "expected_revision", "attempt_id"}:
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                require_revision(run["revision"], body["expected_revision"])
                if body["attempt_id"] != run["attempt_id"]:
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                if run["status"] not in ACTIVE | {"cancelled"}:
                    raise AccountError("STATE_NOT_CANCELLABLE", 409)
                if run["status"] != "cancelled":
                    run["cancel_requested_at"] = now()
                    transition(run, "cancelled")
                    persist(conn, run)
                value = {"run": self.view(run), "task": self.task(run)}
            else:
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            receipt = {
                "value": value,
                "original_request_id": request_id,
                "expires_at": (datetime.now(UTC) + timedelta(hours=24))
                .isoformat()
                .replace("+00:00", "Z"),
            }
            conn.execute(
                commands.insert().values(**command, fingerprint=fingerprint, payload=receipt)
            )
            return receipt

    def revoke(self, conn: Any, project: Any, run: Any) -> None:
        if run["status"] in ACTIVE and (
            project["status"] != "active" or project["authority_epoch"] != run["authority_epoch"]
        ):
            transition(run, "cancelled", "PERMISSION_RESOURCE_UNAVAILABLE")
            persist(conn, run)


def cancel_project_runs(conn: Any, project_id: Any) -> None:
    """Called inside governance's existing transaction, before write eligibility returns."""
    for row in conn.execute(
        sa.select(runs)
        .where(runs.c.project_id == project_id, runs.c.status.in_(ACTIVE))
        .with_for_update()
    ).mappings():
        run = copy.deepcopy(row["payload"])
        transition(run, "cancelled", "PERMISSION_RESOURCE_UNAVAILABLE")
        persist(conn, run)
