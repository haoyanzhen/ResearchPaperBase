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

from rpb.adapters import construction_slots, ingestion_preview
from rpb.adapters import paper_analysis as analysis
from rpb.adapters import paper_deduplication as dedup
from rpb.adapters import paper_processing as processing
from rpb.adapters import paper_screening as screening
from rpb.adapters.baseline_match_preview import baseline_match_preview, match_scope_digest
from rpb.adapters.knowledge_rebuild import preview_dependency_digest, rebuild_requested
from rpb.adapters.llm import event_record, require_revision, uuid_value
from rpb.adapters.llm import public_error as config_error
from rpb.adapters.run_tables import commands, runs
from rpb.adapters.search_terms import TermStore, load, now, save, stable
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
    has_slot = isinstance(run.get("slot_epoch"), int)
    if has_slot and not construction_slots.is_current(conn, run):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    previous_row = (
        conn.execute(
            sa.select(runs.c.status, runs.c.payload)
            .where(runs.c.id == UUID(run["id"]))
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    previous = previous_row["status"] if previous_row else None
    if (
        previous_row
        and screening.content_locked(previous_row["payload"])
        and not screening.content_locked(run)
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if has_slot:
        if previous not in {"queued", "running", "waiting_user"}:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    elif run["status"] in {"running", "waiting_user", "succeeded"} or previous != "queued":
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if run["status"] in {"failed", "cancelled", "succeeded"}:
        construction_slots.release(conn, run)
    conn.execute(
        runs.update()
        .where(runs.c.id == UUID(run["id"]))
        .values(status=run["status"], revision=UUID(run["revision"]), payload=run)
    )


def transition(run: Any, status: str, error: str | None = None) -> None:
    run.update(status=status, revision=str(uuid4()), updated_at=now(), error=error)
    if status in {"failed", "cancelled"}:
        run["finished_at"] = now()
    if status in {"cancelled", "succeeded"}:
        from rpb.adapters.run_temporary_cleanup import new_job

        run.setdefault("temporary_cleanup", new_job())
    if status == "cancelled":
        for key in ("vector_build_claim", "graph_build_claim"):
            claim = run.get(key)
            if claim and claim.get("state") in {"running", "unknown"}:
                claim.update(state="cancelled", error=error)
        run["deduplication_summary"] = dedup.summary(run)
        run["screening_summary"] = screening.summary(run)
        from rpb.adapters.search_term_worker import TermWorker

        for job in [*run.get("scoring_jobs", {}).values(), *run.get("analysis_jobs", {}).values()]:
            if job["state"] in {"queued", "running"}:
                TermWorker.finish(job, "cancelled", error)

        if not any(
            c.get("deduplication", {}).get("history")
            or screening.has_human_content(c)
            or analysis.protected(c)
            or c.get("processing")
            or c.get("cleanup_pending")
            or c.get("document_refs")
            or run.get("retrieval_confirmation")
            for c in run["candidates"]
        ):
            run["cleaned_candidate_count"] = len(run["candidates"])
            run["candidates"] = []
            for job in run.get("scoring_jobs", {}).values():
                job["input"] = {}
                job["results"] = []
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

    def publication_available(self, run: Any) -> bool:
        snapshot = run["input_snapshot"]
        return getattr(self, "first_publication_enabled", False) and (
            snapshot["base_knowledge_version_id"] is None
            or (
                snapshot.get("graph_mode") in {"incremental", "rebuild"}
                and snapshot.get("mode") == "retrieval"
                and snapshot.get("pending_revision_ids") == []
                and snapshot.get("supplement_ids") == []
                and (
                    bool((run.get("analysis_confirmation") or {}).get("candidate_ids"))
                    or bool(run.get("matched_screening"))
                )
            )
        )

    def waiting(self, run: Any, *, matched: dict[str, Any] | None = None) -> list[Any]:
        if run["status"] != "waiting_user":
            return []
        wait = run["waiting"]
        if (
            processing.busy(run)
            or analysis.busy(run)
            or screening.busy(run)
            or (
                run.get("phase") == "analysis"
                and not any(analysis.valid(c) for c in processing.eligible(run))
            )
            or (
                run.get("phase") == "screening"
                and (
                    (not matched and not processing.eligible(run))
                    or any(
                        c.get("deduplication", {}).get("state") == "needs_existing_resolution"
                        for c in run["candidates"]
                    )
                )
            )
            or (
                run.get("phase") == "processing"
                and not any(
                    c.get("processing", {}).get("status") in {"available", "degraded"}
                    for c in processing.eligible(run)
                )
            )
        ):
            return [
                {
                    "id": wait["id"],
                    "kind": run.get("phase"),
                    "revision": wait["revision"],
                    "allowed_actions": [],
                    "confirmation": None,
                }
            ]
        kind = run.get("phase", "retrieval")
        action = "confirm_" + kind
        expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        basis = ":".join(
            [run["owner_id"], run["project_id"], wait["id"], wait["revision"], expires]
        )
        if matched:
            basis += ":" + match_scope_digest(run, matched)
        token = hmac.new(run["confirmation_secret"].encode(), basis.encode(), "sha256").hexdigest()
        ingestion = kind == "ingestion_preview"
        decision = run.get("matched_screening") or {}
        stale_exclusion = (
            ingestion
            and (decision.get("scope") or {}).get("excluded_paper_count")
            and decision.get("digest") != match_scope_digest(run, decision["scope"])
        )
        blocked = (
            ["筛选排除依据已变化，请重新核对"]
            if stale_exclusion
            else ["保留论文的来源或访问依据不可用，请检查基线和当前权限"]
            if ingestion and rebuild_requested(run) and not run.get("rebuild_preview_digest")
            else ["知识构建和发布能力尚未就绪"]
            if ingestion and not self.publication_available(run)
            else []
        )
        if ingestion:
            from rpb.adapters.ingestion_confirmation import signature

            token = signature(run, run["owner_id"], expires)
        return [
            {
                "id": wait["id"],
                "kind": kind,
                "revision": wait["revision"],
                "allowed_actions": [] if blocked else [action],
                "confirmation": {
                    "confirmation_id": stable(token),
                    "action": action,
                    "target": {"type": "waiting_item", "id": wait["id"]},
                    "subject_revision": run["candidate_revision"]
                    if ingestion
                    else run["effective_input_revision"],
                    "impact_revision": wait["revision"],
                    "knowledge_version_id": None,
                    "candidate_revision": run["candidate_revision"],
                    "risks": (
                        [{"id": "ABSTRACT_ONLY", "message": "部分论文使用摘要降级文本"}]
                        if ingestion
                        and any(
                            c.get("processing", {}).get("status") == "degraded"
                            and c["id"]
                            in run.get("analysis_confirmation", {}).get("candidate_ids", [])
                            for c in run["candidates"]
                        )
                        else []
                    ),
                    "expires_at": expires,
                    "confirmation_token": expires + "." + token,
                    "affected_items": [],
                    "retained_items": [],
                    "blocked_reasons": blocked,
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
            "stage": run.get("phase", "retrieval"),
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
            **({"rerun_of": run["rerun_of"]} if run.get("rerun_of") else {}),
            "phase": run.get("phase", "retrieval"),
            "base_knowledge_version_id": (run.get("input_snapshot") or {}).get(
                "base_knowledge_version_id"
            ),
            "published_knowledge_version_id": run.get("published_knowledge_version_id"),
            "completion": run.get("completion"),
            **(
                {"temporary_cleanup": run["temporary_cleanup"]}
                if run.get("temporary_cleanup")
                else {}
            ),
            "steps": [
                {
                    "id": run["task_id"],
                    "kind": "association_removal" if run.get("removal") else "retrieval",
                    "state": run["status"],
                    "result_summary": {
                        "candidate_count": len(run["candidates"])
                        + run.get("cleaned_candidate_count", 0),
                        "sources": run["source_results"],
                        "resolution": run.get("resolution"),
                        "deduplication": dedup.summary(run),
                        "screening": screening.summary(run),
                        "processing": processing.summary(run),
                        "analysis": analysis.summary(run),
                    },
                    "error": public_error(run["error"]) if run.get("error") else None,
                }
            ],
            "waiting_items": self.waiting(run),
            "scoring_tasks": [
                screening.task_view(run, job, self.task(run))
                for job in run.get("scoring_jobs", {}).values()
            ],
            "analysis_tasks": [
                analysis.task_view(run, job, self.task(run))
                for job in run.get("analysis_jobs", {}).values()
            ],
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
                            runs.c.owner_id == actor,
                            sa.or_(
                                runs.c.payload["task_id"].astext == target,
                                runs.c.payload["scoring_jobs"].has_key(target),
                                runs.c.payload["analysis_jobs"].has_key(target),
                            ),
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
                if target in run.get("analysis_jobs", {}):
                    job = run["analysis_jobs"][target]
                    view = analysis.task_view(run, job, self.task(run))
                    return (
                        {"view": view, "events": job["events"]} if operation == "events" else view
                    )
                if target in run.get("scoring_jobs", {}):
                    job = run["scoring_jobs"][target]
                    view = screening.task_view(run, job, self.task(run))
                    return (
                        {"view": view, "events": job["events"]} if operation == "events" else view
                    )
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

            if operation == "pending_removals":
                removals = conn.scalars(
                    sa.select(runs.c.payload["removal"]["revisions"])
                    .where(runs.c.project_id == project["id"], runs.c.payload.has_key("removal"))
                    .order_by(runs.c.created_at.desc(), runs.c.id.desc())
                )
                return paginate([item for revisions in removals for item in revisions])
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
                lookup = sa.select(runs).where(
                    runs.c.id == uuid_value(data["run_id"]), runs.c.project_id == project["id"]
                )
                if operation == "temporary_cleanup":
                    lookup = lookup.with_for_update()
                row = conn.execute(lookup).mappings().first()
                if not row:
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                run = copy.deepcopy(row["payload"])
                self.revoke(conn, project, run)
                if (
                    operation in {"read_run", "ingestion_preview"}
                    and run.get("phase") == "ingestion_preview"
                    and run["status"] == "waiting_user"
                    and actor == UUID(run["owner_id"])
                    and rebuild_requested(run)
                ):
                    try:
                        run["rebuild_preview_digest"] = preview_dependency_digest(
                            conn, project, actor, run
                        )
                    except AccountError:
                        # Keep cancellation available while the dependency is unavailable.
                        pass
                if operation == "read_run":
                    detail = self.view(run)
                    preview = baseline_match_preview(conn, run)
                    if preview is not None:
                        detail["baseline_match_preview"] = preview
                        if actor == UUID(run["owner_id"]) and getattr(
                            self, "first_publication_enabled", False
                        ):
                            detail["waiting_items"] = self.waiting(run, matched=preview)
                    return detail
                if operation == "ingestion_preview":
                    return ingestion_preview.preview(
                        run, self.waiting(run)[0] if run.get("status") == "waiting_user" else None
                    )
                if operation in {"file_access", "file_download"}:
                    return processing.file_view(conn, run, data, operation == "file_download")
                if operation == "processing_text":
                    return processing.text_view(conn, run, data["candidate_id"])
                if operation == "candidates":
                    values = copy.deepcopy(run["candidates"])
                    errors = analysis.latest_errors(run)
                    for c in values:
                        c["analysis_current"] = analysis.valid(c)
                        c["analysis_error"] = errors.get(c["id"])
                        if c.get("analysis") and not c["analysis_current"]:
                            c["retained_analysis"] = c["analysis"]
                            c["analysis"] = None
                            c["analysis_basis"] = None
                        pending = c.get("cleanup_pending")
                        if pending and pending["document_asset_id"] in state["sources"]:
                            pending["material_classification"] = state["sources"][
                                pending["document_asset_id"]
                            ]["classification"]
                        doc = c.get("processing", {}).get("basis", {}).get("document_asset_id")
                        if doc in state["sources"]:
                            c["processing"]["material_classification"] = state["sources"][doc][
                                "classification"
                            ]
                        if c["id"] in state["sources"]:
                            c["material_classification"] = state["sources"][c["id"]][
                                "classification"
                            ]
                    return paginate(values, run["revision"])
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
            if operation in {"preview_removal", "confirm_removal"} and not getattr(
                self, "association_removal_enabled", False
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            if operation == "preview_removal":
                from rpb.adapters.association_removal import preview as preview_exclusion

                return preview_exclusion(conn, actor, project, state, body)
            if operation == "preview_analysis" and run:
                return analysis.preview(run, body)
            if operation == "preview_score" and run:
                return screening.preview(run, body)
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
            if operation == "confirm_removal":
                from rpb.adapters.association_removal import confirm

                value = confirm(conn, self, actor, project, state, body)
            elif operation == "start":
                source_id = None
                requested = body
                if "rerun_of" in body:
                    if set(body) != {"rerun_of", "expected_revision"}:
                        raise AccountError("VALIDATION_FIELD_INVALID", 422)
                    source = conn.scalar(
                        sa.select(runs.c.payload)
                        .where(
                            runs.c.project_id == project["id"],
                            runs.c.owner_id == actor,
                            runs.c.id == uuid_value(body["rerun_of"]),
                        )
                        .with_for_update()
                    )
                    if source is None:
                        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                    require_revision(source["revision"], body["expected_revision"])
                    if source["status"] != "failed":
                        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                    source_id = source["id"]
                    requested = copy.deepcopy(source["request"])
                try:
                    inputs = start_input(requested)
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
                    **({"rerun_of": source_id} if source_id else {}),
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
            elif (
                operation == "confirm_retrieval" and run and run.get("phase") == "ingestion_preview"
            ):
                from rpb.adapters.ingestion_confirmation import accept_locked

                if not self.publication_available(run):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                accepted = accept_locked(
                    conn,
                    self,
                    actor,
                    project["id"],
                    UUID(run["id"]),
                    {k: v for k, v in body.items() if k != "run_id"},
                )
                value = {"run": self.view(accepted), "task": self.task(accepted)}
            elif operation == "confirm_retrieval" and run:
                required = {
                    "run_id",
                    "waiting_item_id",
                    "expected_revision",
                    "subject_revision",
                    "candidate_revision",
                    "confirmation_token",
                    "acknowledged_risk_ids",
                }
                if set(body) != required or body["acknowledged_risk_ids"] != []:
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                if run["status"] != "waiting_user" or run.get("phase", "retrieval") not in {
                    "retrieval",
                    "screening",
                    "processing",
                    "analysis",
                }:
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                wait = run["waiting"]
                if body["waiting_item_id"] != wait["id"]:
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                require_revision(wait["revision"], body["expected_revision"])
                require_revision(run["effective_input_revision"], body["subject_revision"])
                require_revision(run["candidate_revision"], body["candidate_revision"])
                # Issued claims persist across reads and expire; HMAC binds the exact input.
                token = body["confirmation_token"]
                if not isinstance(token, str) or "." not in token:
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                expires, signature = token.rsplit(".", 1)
                basis = ":".join(
                    [run["owner_id"], run["project_id"], wait["id"], wait["revision"], expires]
                )
                matched = (
                    baseline_match_preview(conn, run) if run.get("phase") == "screening" else None
                )
                if matched:
                    basis += ":" + match_scope_digest(run, matched)
                expected = hmac.new(
                    run["confirmation_secret"].encode(), basis.encode(), "sha256"
                ).hexdigest()
                try:
                    valid = datetime.fromisoformat(expires.replace("Z", "+00:00")) > datetime.now(
                        UTC
                    )
                except ValueError, TypeError:
                    valid = False
                if (
                    not valid
                    or not signature.isascii()
                    or not hmac.compare_digest(signature, expected)
                ):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                if run.get("phase") == "analysis":
                    analysis.confirm(run, actor)
                    transition(run, "waiting_user")
                elif run.get("phase") == "screening":
                    if matched is None:
                        processing.accept(run, actor)
                    else:
                        if (
                            str(actor) != run["owner_id"]
                            or not getattr(self, "first_publication_enabled", False)
                            or screening.busy(run)
                            or processing.busy(run)
                            or analysis.busy(run)
                        ):
                            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                        run["matched_screening"] = {
                            "scope": matched,
                            "digest": match_scope_digest(run, matched),
                            "actor_id": str(actor),
                            "at": now(),
                            "candidate_revision": run["candidate_revision"],
                        }
                        run["phase"] = "ingestion_preview"
                        run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}
                        transition(run, "waiting_user")
                elif run.get("phase") == "processing":
                    processing.confirm(run, actor)
                    transition(run, "waiting_user")
                else:
                    run["retrieval_confirmation"] = {
                        "actor_id": str(actor),
                        "at": now(),
                        "candidate_revision": run["candidate_revision"],
                        "input_revision": run["effective_input_revision"],
                    }
                    screening.register_sources(run, state)
                    save(conn, project, state)
                    from rpb.adapters.knowledge_baseline_papers import baseline_papers

                    dedup.initialize(run, baseline_papers(conn, run))
                    transition(run, "waiting_user")
                persist(conn, run)
                value = {"run": self.view(run), "task": self.task(run)}
            elif operation == "generate_analysis" and run:
                job = analysis.accept(conn, run, body, state, project)
                value = analysis.task_view(run, job, self.task(run))
                transition(run, "waiting_user")
                persist(conn, run)
            elif operation in {"score", "edit_candidate"} and run:
                if operation == "score":
                    job = screening.accept(run, body, state, project)
                    value = screening.task_view(run, job, self.task(run))
                    transition(run, "waiting_user")
                    persist(conn, run)
                else:
                    value = copy.deepcopy(
                        analysis.edit(run, body, actor)
                        if "analysis" in body
                        else screening.edit(run, body, actor)
                    )
                    transition(run, "waiting_user")
                    persist(conn, run)
            elif operation == "correct_deduplication" and run:
                screening.writable(run)
                value = copy.deepcopy(dedup.correct(run, body, actor))
                transition(run, "waiting_user")
                persist(conn, run)
            elif operation == "temporary_cleanup" and run:
                from rpb.adapters.run_temporary_cleanup import request_cleanup

                request_cleanup(conn, actor, run, body)
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
