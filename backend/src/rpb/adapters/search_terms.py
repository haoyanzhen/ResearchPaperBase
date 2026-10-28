"""Project-scoped durable term aggregate. All transitions serialize with governance."""

import base64
import binascii
import copy
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.auth import AccountStore
from rpb.adapters.llm import LLMStore, event_record, public_error, require_revision, uuid_value
from rpb.adapters.project import construction_workspaces, metadata, projects
from rpb.adapters.source_resolution import SourceResolver
from rpb.adapters.sources import SourceStore
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.terms import TermError, term_write

states = sa.Table(
    "construction_term_states",
    metadata,
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("payload", JSONB, nullable=False),
    sa.CheckConstraint(
        "jsonb_typeof(payload) = 'object' AND payload ? 'schema_version' "
        "AND payload->>'schema_version' = '1'",
        name="ck_term_state_schema",
    ),
)


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def stable(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, "rpb-terms:" + value))


def default_state(project: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cursor_secret": secrets.token_hex(32),
        "revision": stable(str(project["id"])),
        "auto_update_enabled": True,
        "terms": {},
        "jobs": {},
        "receipts": {},
        "sources": {},
        "policies": {},
        "discarded": [],
    }


def load(conn: Any, project: Any) -> dict[str, Any]:
    value = conn.scalar(sa.select(states.c.payload).where(states.c.project_id == project["id"]))
    if value:
        return copy.deepcopy(value)
    state = default_state(project)
    workspace = (
        conn.execute(
            sa.select(construction_workspaces).where(
                construction_workspaces.c.project_id == project["id"]
            )
        )
        .mappings()
        .one()
    )
    state.update(
        revision=str(workspace["revision"]),
        updated_at=workspace["updated_at"].isoformat().replace("+00:00", "Z"),
    )
    return state


def save(conn: Any, project: Any, state: dict[str, Any]) -> None:
    from sqlalchemy.dialects.postgresql import insert

    conn.execute(
        insert(states)
        .values(project_id=project["id"], payload=state)
        .on_conflict_do_update(index_elements=[states.c.project_id], set_={"payload": state})
    )
    conn.execute(
        construction_workspaces.update()
        .where(construction_workspaces.c.project_id == project["id"])
        .values(
            revision=UUID(state["revision"]), updated_at=datetime.fromisoformat(state["updated_at"])
        )
    )


def source_for(project: Any) -> dict[str, Any]:
    return {
        "project_id": str(project["id"]),
        "source_id": stable(str(project["id"]) + ":" + str(project["revision"])),
        "content_revision": str(project["revision"]),
    }


def policy_view(state: Any, actor: Any, project: Any) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        state["policies"].get(
            str(actor),
            {
                "user_id": str(actor),
                "project_id": str(project["id"]),
                "mode": "public_only",
                "revision": stable(str(actor) + ":policy:" + str(project["id"])),
                "risk_acknowledged_at": None,
            },
        ),
    )


def classification(state: Any, project: Any, source_id: str) -> dict[str, Any]:
    stored = state["sources"].get(source_id)
    if stored:
        return cast(dict[str, Any], stored["classification"])
    identity = source_for(project)
    if identity["source_id"] != source_id:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    return {
        "source": identity,
        "classification": "private",
        "confirmation_status": "unconfirmed",
        "revision": stable(source_id + ":classification"),
        "confirmation": None,
        "provenance": {
            "kind": "historical_input",
            "submission_scope_id": None,
            "dependency_status": "complete",
        },
    }


def allowed(state: Any, actor: Any, project: Any, source_id: str) -> bool:
    value = classification(state, project, source_id)
    return bool(
        value["confirmation_status"] == "confirmed"
        and (
            value["classification"] == "public"
            or policy_view(state, actor, project)["mode"] == "allow_private"
        )
    )


def material_basis(
    state: Any, actor: Any, project: Any, source_id: str, boundary: str
) -> dict[str, Any]:
    source = classification(state, project, source_id)
    return {
        "boundary": boundary,
        "at": now(),
        "actor_id": str(actor),
        "project_id": str(project["id"]),
        "source": source["source"],
        "classification_revision": source["revision"],
        "policy_revision": policy_view(state, actor, project)["revision"],
        "permitted": allowed(state, actor, project, source_id),
    }


class TermStore:
    def __init__(self, account: AccountStore, encryption_key: bytes | None = None) -> None:
        self.account = account
        self.sources = SourceResolver(SourceStore(account, encryption_key))
        self.llm = LLMStore(account, encryption_key)
        self.system_llm = LLMStore(account, encryption_key, system=True)

    def project(self, conn: Any, actor: Any, project_id: Any, write: bool = False) -> Any:
        project = (
            conn.execute(
                sa.select(projects)
                .where(projects.c.id == project_id, projects.c.owner_id == actor)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not project or project["status"] == "deleted":
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        if write and project["status"] != "active":
            raise AccountError("STATE_PROJECT_READ_ONLY", 409)
        return project

    def workspace(self, state: Any, project: Any) -> dict[str, Any]:
        return {
            "id": str(project["construction_workspace_id"]),
            "revision": state["revision"],
            "created_at": project["created_at"].isoformat().replace("+00:00", "Z"),
            "updated_at": state.get(
                "updated_at", project["updated_at"].isoformat().replace("+00:00", "Z")
            ),
            "auto_update_enabled": state["auto_update_enabled"],
            "scheduler_available": False,
            "occupying_run_id": state.get("occupying_run_id"),
            "pending_supplement_count": 0,
            "pending_revision_count": 0,
            "topic_source": source_for(project),
            "generation_tasks": [
                self.task_view(job, project)
                for job in sorted(state["jobs"].values(), key=lambda j: (j["created_at"], j["id"]))[
                    -20:
                ]
            ],
        }

    def term(self, state: Any, identity: str) -> Any:
        value = state["terms"].get(identity)
        if not value or value.get("deleted") or value["status"] == "discarded":
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        return value

    def term_view(self, value: Any, actor: Any, project: Any, state: Any) -> dict[str, Any]:
        result = {
            k: v
            for k, v in value.items()
            if k
            not in {"deleted", "confirmation_history", "generation_job_id", "confirmation_secret"}
        }
        result["confirmations"] = []
        if project["status"] == "active" and value["confirmed_revision"] != value["revision"]:
            expires = int(datetime.now(UTC).timestamp()) + 600
            raw = base64.urlsafe_b64encode(
                json.dumps(
                    [str(actor), str(project["id"]), value["id"], value["revision"], expires]
                ).encode()
            ).decode()
            token = (
                raw
                + "."
                + hmac.new(
                    value["confirmation_secret"].encode(), raw.encode(), "sha256"
                ).hexdigest()
            )
            result["confirmations"] = [
                {
                    "confirmation_id": stable(token),
                    "action": "confirm_search_term",
                    "target": {"type": "search_term", "id": value["id"]},
                    "subject_revision": value["revision"],
                    "impact_revision": value["revision"],
                    "knowledge_version_id": None,
                    "candidate_revision": None,
                    "risks": [],
                    "expires_at": datetime.fromtimestamp(expires, UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "confirmation_token": token,
                    "affected_items": [],
                    "retained_items": [],
                    "blocked_reasons": [],
                }
            ]
        return result

    def model(self, conn: Any, actor: Any, selection: Any) -> tuple[Any, Any]:
        if (
            not isinstance(selection, dict)
            or set(selection) != {"source", "config_id", "model_id"}
            or not isinstance(selection.get("source"), str)
            or selection.get("source") not in {"user", "system"}
        ):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        store = self.system_llm if selection["source"] == "system" else self.llm
        if not any(
            x["available"] and all(x[k] == selection[k] for k in selection)
            for x in store.options(conn, actor)
        ):
            raise AccountError("CONFIG_CONNECTION_FAILED", 409)
        config = store.config(conn, actor, selection["config_id"])
        if not store.cipher or not config["secret_ciphertext"]:
            raise AccountError("CONFIG_SECRET_UNAVAILABLE", 409)
        return store, config

    def task_view(self, job: Any, project: Any) -> dict[str, Any]:
        base = "/api/v1/tasks/" + job["id"]
        result = [
            {
                "type": "search_term",
                "id": identity,
                "url": (
                    f"/api/v1/projects/{project['id']}"
                    f"/construction-workspace/search-terms/{identity}"
                ),
            }
            for identity in job.get("term_ids", [])
        ]
        error = public_error(job["error"]) if job.get("error") else None
        if error:
            error["message"] = "检索词生成未完成，原检索词已保留。请检查配置、资料使用资格或输入。"
        return {
            "task_id": job["id"],
            "attempt_id": job["attempt_id"],
            "operation_id": "Construction.GenerateTerms",
            "target": {
                "type": "construction_workspace",
                "id": str(project["construction_workspace_id"]),
            },
            "project_id": str(project["id"]),
            "knowledge_version_id": None,
            "execution_status": job["state"],
            "status_url": base,
            "events_url": base + "/events",
            "cancel_url": None,
            "result_refs": result,
            "revision": job["revision"],
            "created_at": job["created_at"],
            "updated_at": job.get("finished_at") or job.get("started_at") or job["created_at"],
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "stage": "search_terms",
            "business_state": None,
            "waiting_items": [],
            "cancel_requested_at": None,
            "error": error,
            "warnings": [],
            "event_cursor": job["events"][-1]["cursor"],
            "partial_result_ref": None,
            "target_location": {
                "parent_type": "project",
                "parent_id": str(project["id"]),
                "read_url": f"/api/v1/projects/{project['id']}/construction-workspace",
            },
            "material_use_notices": [],
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
        if operation == "source_options":
            with self.account.authorized_connection(token, None) as (conn, actor):
                if expected_actor is not None and str(actor) != expected_actor:
                    raise AccountError("AUTH_SESSION_INVALID", 401)
                self.project(conn, actor, uuid_value(str(target)))
            return self.sources.resolve(token, expected_actor=expected_actor)
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and expected_actor != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
            if operation in {"task", "events", "result"}:
                row = (
                    conn.execute(
                        sa.select(projects)
                        .join(states, projects.c.id == states.c.project_id)
                        .where(
                            projects.c.owner_id == actor, states.c.payload["jobs"].has_key(target)
                        )
                    )
                    .mappings()
                    .first()
                )  # noqa: W601
                if not row:
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                project = self.project(conn, actor, row["id"])
                state = load(conn, project)
                job = state["jobs"][target]
                if operation == "result":
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                view = self.task_view(job, project)
                return {"view": view, "events": job["events"]} if operation == "events" else view
            data = dict(data)
            request_id = data.pop("_request_id", str(uuid4()))
            project = self.project(conn, actor, uuid_value(str(target)), csrf is not None)
            state = load(conn, project)
            term_id = str(data.get("term_id", ""))
            if operation == "workspace":
                from rpb.adapters.run_tables import runs

                occupying = conn.scalar(
                    sa.select(runs.c.id).where(
                        runs.c.project_id == project["id"],
                        runs.c.status.in_(["running", "waiting_user"]),
                    )
                )
                state["occupying_run_id"] = str(occupying) if occupying else None
                return self.workspace(state, project)
            if operation == "list_terms":
                values = sorted(
                    (
                        v
                        for v in state["terms"].values()
                        if not v.get("deleted") and v["status"] != "discarded"
                    ),
                    key=lambda v: (v["created_at"], v["id"]),
                )
                cursor = data.get("cursor")
                if cursor:
                    try:
                        raw, signature = cursor.split(".")
                        expected = hmac.new(
                            state["cursor_secret"].encode(), raw.encode(), "sha256"
                        ).hexdigest()
                        if not hmac.compare_digest(signature, expected):
                            raise ValueError("signature")
                        scope, owner, created, identity = json.loads(base64.urlsafe_b64decode(raw))
                        if scope != str(project["id"]) or owner != str(actor):
                            raise ValueError("scope")
                        values = [
                            v for v in values if (v["created_at"], v["id"]) > (created, identity)
                        ]
                    except ValueError, TypeError, binascii.Error:
                        raise AccountError("VALIDATION_BAD_REQUEST", 400) from None
                size = data.get("page_size", 20)
                page, next_cursor = values[:size], None
                if len(values) > size:
                    last = page[-1]
                    raw = base64.urlsafe_b64encode(
                        json.dumps(
                            [str(project["id"]), str(actor), last["created_at"], last["id"]]
                        ).encode()
                    ).decode()
                    next_cursor = (
                        raw
                        + "."
                        + hmac.new(
                            state["cursor_secret"].encode(), raw.encode(), "sha256"
                        ).hexdigest()
                    )
                return {
                    "items": [self.term_view(v, actor, project, state) for v in page],
                    "next_cursor": next_cursor,
                }
            if operation == "read_term":
                return self.term_view(self.term(state, term_id), actor, project, state)
            if operation == "policy":
                return policy_view(state, actor, project)
            if operation == "classification":
                return classification(state, project, data["source_id"])
            fingerprint = hashlib.sha256(
                json.dumps([operation, data], sort_keys=True).encode()
            ).hexdigest()
            receipt_target = term_id or str(data.get("source_id", project["id"]))
            receipt_key = f"{actor}:{operation}:{receipt_target}:{key}"
            idempotent = operation in {
                "add_term",
                "confirm_term",
                "discard_term",
                "generate",
                "classify",
                "correct_classification",
            }
            if idempotent:
                if (
                    not key
                    or not 16 <= len(key) <= 128
                    or any(not 32 <= ord(c) <= 126 for c in key)
                ):
                    raise AccountError("VALIDATION_BAD_REQUEST", 400)
                old = state["receipts"].get(receipt_key)
                if old:
                    if old["fingerprint"] != fingerprint:
                        raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                    return old["result"]
            timestamp = now()
            if operation == "save_config":
                require_revision(state["revision"], data.get("expected_revision"))
                if (
                    set(data) - {"expected_revision", "auto_update_enabled"}
                    or type(data.get("auto_update_enabled")) is not bool
                ):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                state["auto_update_enabled"] = data["auto_update_enabled"]
                result = None
            elif operation == "add_term":
                value = self.new_term(data, timestamp, "manual_edit", "accepted")
                value["modified_by"] = str(actor)
                state["terms"][value["id"]] = value
                result = self.term_view(value, actor, project, state)
            elif operation in {"edit_term", "delete_term", "confirm_term", "discard_term"}:
                value = self.term(state, term_id)
                require_revision(value["revision"], data.get("expected_revision"))
                if operation == "edit_term":
                    try:
                        update = term_write(
                            {
                                k: v
                                for k, v in data.items()
                                if k not in {"term_id", "expected_revision"}
                            },
                            partial=True,
                        )
                    except TermError:
                        raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
                    if any(value[k] != v for k, v in update.items()):
                        value.update(
                            update,
                            revision=str(uuid4()),
                            updated_at=timestamp,
                            content_state="manual_edit",
                            confirmed_revision=None,
                            confirmed_at=None,
                            modified_by=str(actor),
                            modified_at=timestamp,
                        )
                elif operation == "delete_term":
                    value["deleted"] = True
                elif operation == "discard_term":
                    if value["status"] != "candidate":
                        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                    state["discarded"].append(
                        hashlib.sha256(value["query"].strip().casefold().encode()).hexdigest()
                    )
                    del state["terms"][term_id]
                    value["status"] = "discarded"
                else:
                    try:
                        raw, signature = data.get("confirmation_token", "").split(".")
                        if not hmac.compare_digest(
                            signature,
                            hmac.new(
                                value["confirmation_secret"].encode(), raw.encode(), "sha256"
                            ).hexdigest(),
                        ):
                            raise ValueError("signature")
                        bound = json.loads(base64.urlsafe_b64decode(raw))
                        if (
                            bound[:4]
                            != [str(actor), str(project["id"]), value["id"], value["revision"]]
                            or bound[4] <= datetime.now(UTC).timestamp()
                            or data.get("acknowledged_risk_ids") != []
                        ):
                            raise ValueError("scope")
                    except ValueError, TypeError, IndexError, AttributeError, binascii.Error:
                        raise AccountError("STATE_CONFIRMATION_STALE", 409) from None
                    value.update(
                        status="accepted",
                        confirmed_revision=value["revision"],
                        confirmed_at=timestamp,
                    )
                    if value["content_state"] != "manual_edit":
                        value["content_state"] = "manual_confirm"
                    value["confirmation_history"].append(
                        {
                            "revision": value["revision"],
                            "confirmed_by": str(actor),
                            "confirmed_at": timestamp,
                            "content_state": value["content_state"],
                            "modified_by": value["modified_by"],
                            "modified_at": value["modified_at"],
                            "content": {k: value[k] for k in term_write({"query": value["query"]})},
                        }
                    )
                result = (
                    None
                    if operation == "delete_term"
                    else (
                        {
                            "id": value["id"],
                            "revision": value["revision"],
                            "status": "discarded",
                            "discarded_at": timestamp,
                        }
                        if operation == "discard_term"
                        else self.term_view(value, actor, project, state)
                    )
                )
            elif operation == "set_policy":
                previous = policy_view(state, actor, project)
                require_revision(previous["revision"], data.get("expected_revision"))
                if (
                    set(data) != {"expected_revision", "mode", "risk_acknowledged"}
                    or not isinstance(data["mode"], str)
                    or data["mode"] not in {"public_only", "allow_private"}
                    or data["risk_acknowledged"] is not (data["mode"] == "allow_private")
                ):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                result = {
                    **previous,
                    "mode": data["mode"],
                    "revision": str(uuid4()),
                    "risk_acknowledged_at": timestamp
                    if data["mode"] == "allow_private"
                    else previous["risk_acknowledged_at"],
                }
                state["policies"][str(actor)] = result
                state.setdefault("policy_audit", []).append({**result, "at": timestamp})
            elif operation in {"classify", "correct_classification"}:
                source_id = data["source_id"]
                current = classification(state, project, source_id)
                require_revision(current["revision"], data.get("expected_revision"))
                require_revision(
                    current["source"]["content_revision"], data.get("content_revision")
                )
                if (current["confirmation_status"] == "confirmed") != (
                    operation == "correct_classification"
                ):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                if (
                    set(data)
                    != {
                        "source_id",
                        "expected_revision",
                        "content_revision",
                        "classification",
                        "basis",
                        "explicit_confirmation",
                    }
                    or not isinstance(data.get("classification"), str)
                    or data.get("classification") not in {"public", "private"}
                    or data.get("explicit_confirmation") is not True
                    or not isinstance(data.get("basis"), str)
                    or not 1 <= len(data["basis"].strip()) <= 2000
                ):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                result = {
                    **current,
                    "classification": data["classification"],
                    "confirmation_status": "confirmed",
                    "revision": str(uuid4()),
                    "confirmation": {
                        "basis": data["basis"].strip(),
                        "confirmed_by": str(actor),
                        "confirmed_at": timestamp,
                    },
                }
                content = (
                    state["sources"]
                    .get(source_id, {})
                    .get(
                        "content",
                        {k: project[k] for k in ("name", "description", "research_scope")},
                    )
                )
                state.setdefault("classification_audit", []).append(result)
                state["sources"][source_id] = {"classification": result, "content": content}
            elif operation == "generate":
                require_revision(state["revision"], data.get("expected_revision"))
                if (
                    set(data)
                    - {
                        "expected_revision",
                        "model_selection",
                        "additional_requirements",
                        "confirmation_token",
                        "acknowledged_risk_ids",
                    }
                    or data.get("acknowledged_risk_ids") != []
                    or data.get("confirmation_token")
                ):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                requirements = data.get("additional_requirements", "")
                if not isinstance(requirements, str) or len(requirements) > 10000:
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                source_id = source_for(project)["source_id"]
                if not allowed(state, actor, project, source_id):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                if any(j["state"] in {"queued", "running"} for j in state["jobs"].values()):
                    raise AccountError("LOCK_CONTENT_BUSY", 409)
                store, config = self.model(conn, actor, data.get("model_selection"))
                identity, revision = str(uuid4()), str(uuid4())
                job = {
                    "id": identity,
                    "owner_id": str(actor),
                    "attempt_id": str(uuid4()),
                    "revision": revision,
                    "state": "queued",
                    "created_at": timestamp,
                    "started_at": None,
                    "finished_at": None,
                    "source_id": source_id,
                    "material_audit": [material_basis(state, actor, project, source_id, "accept")],
                    "input": {
                        "topic": state["sources"][source_id]["content"],
                        "additional_requirements": requirements,
                        "submission_scope_id": identity,
                        "submission_actor_id": str(actor),
                        "submission_project_id": str(project["id"]),
                        "submission_kind": "current_submission",
                    },
                    "model_selection": data["model_selection"],
                    "config_revision": str(config["revision"]),
                    "config": config["data"],
                    "authority_epoch": project["authority_epoch"],
                    "events": [event_record("queued", UUID(revision), datetime.now(UTC))],
                    "error": None,
                    "term_ids": [],
                }
                state["jobs"][identity] = job
                result = self.task_view(job, project)
            else:
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            if operation in {
                "save_config",
                "add_term",
                "edit_term",
                "delete_term",
                "confirm_term",
                "discard_term",
                "generate",
            }:
                state["revision"] = str(uuid4())
                state["updated_at"] = timestamp
            if operation == "save_config":
                result = self.workspace(state, project)
            if idempotent:
                result = {
                    "value": result,
                    "expires_at": (datetime.now(UTC) + timedelta(hours=48))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "original_request_id": request_id,
                }
                state["receipts"][receipt_key] = {"fingerprint": fingerprint, "result": result}
            save(conn, project, state)
            return result

    @staticmethod
    def new_term(data: Any, timestamp: str, content_state: str, status: str) -> dict[str, Any]:
        try:
            content = term_write(data)
        except TermError:
            raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
        return {
            **content,
            "id": str(uuid4()),
            "revision": str(uuid4()),
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": status,
            "content_state": content_state,
            "confirmed_revision": None,
            "confirmed_at": None,
            "modified_by": None,
            "modified_at": timestamp,
            "confirmation_history": [],
            "confirmation_secret": secrets.token_hex(32),
        }
