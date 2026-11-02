"""Durable text-cleanup orchestration on the original processing job."""

import copy
import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters import paper_screening as screening
from rpb.adapters import pdf_cleanup_budget as budget
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.pdf_cleanup_capacity import effective_config, plan_for_model
from rpb.adapters.pdf_text_cleanup import CleanupInvalid, reconstruct
from rpb.adapters.processing_tables import objects
from rpb.adapters.project import projects
from rpb.adapters.run_tables import runs
from rpb.adapters.runs import persist, transition
from rpb.adapters.search_term_worker import TermWorker
from rpb.adapters.search_terms import classification, load, material_basis, save
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.domain.parameters import ParameterError

ENGINE = "llm_text_cleanup"


def cleanup_config(run: Any) -> Any:
    return run.get("cleanup_model_config", run["model_config"])


class CleanupWorker:
    def __init__(self, store: Any, pdf: Any, provider: Any) -> None:
        self.store, self.pdf, self.provider = store, pdf, provider
        self.guard = TermWorker(store.terms, None)
        self.processing = ProcessingWorker(store, pdf)

    def current(self, conn: Any, run_id: str) -> tuple[Any, Any, Any]:
        self.guard.lock(conn)
        row = (
            conn.execute(sa.select(runs).where(runs.c.id == UUID(run_id)).with_for_update())
            .mappings()
            .one()
        )
        run = copy.deepcopy(row["payload"])
        project = (
            conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
            .mappings()
            .one()
        )
        return run, project, load(conn, project)

    def check(self, conn: Any, project: Any, run: Any, job_id: str) -> None:
        if screening.content_locked(run) or not screening.baseline_ready(run):
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        job = run.get("processing_job", {})
        if (
            not self.store.terms.llm.permitted_actor(conn, UUID(run["owner_id"]))
            or project["status"] != "active"
            or project["authority_epoch"] != run["authority_epoch"]
        ):
            raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
        if (
            run["status"] not in {"running", "waiting_user"}
            or run.get("phase") != "processing"
            or job.get("id") != job_id
            or job.get("state") not in {"queued", "running", "waiting_classification"}
            or job["candidate_revision"] != run["candidate_revision"]
            or job["input_revision"] != run["effective_input_revision"]
        ):
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        group = job["groups"][job.get("group_index", 0)]
        current = {c["id"]: c for c in run["candidates"]}
        if not group["reuse"] and any(
            source["id"] not in current
            or any(
                current[source["id"]][key] != source[key]
                for key in ("revision", "metadata", "source")
            )
            for source in group["sources"]
        ):
            raise ProviderFailure("STATE_REVISION_CONFLICT")

    def model_check(self, conn: Any, project: Any, state: Any, run: Any, boundary: str) -> str:
        job = run["processing_job"]
        return self.dependency_check(
            conn,
            project,
            state,
            run,
            job["prepared"]["document_asset_id"],
            job["classification_revision"],
            boundary,
        )

    def recheck_dependencies(
        self, conn: Any, project: Any, state: Any, run: Any, boundary: str
    ) -> None:
        for dependency in run["processing_job"].get("material_dependencies", []):
            self.dependency_check(
                conn,
                project,
                state,
                run,
                dependency["source_id"],
                dependency["classification_revision"],
                boundary,
            )

    def dependency_check(
        self,
        conn: Any,
        project: Any,
        state: Any,
        run: Any,
        source: str,
        revision: str,
        boundary: str,
    ) -> str:
        job = run["processing_job"]
        try:
            current = classification(state, project, source)
        except AccountError:
            raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE") from None
        if revision != current["revision"]:
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        audit = material_basis(state, UUID(run["owner_id"]), project, source, boundary)
        job.setdefault("material_audit", []).append(audit)
        _, secret = self.guard.check(
            conn,
            project,
            state,
            {
                "owner_id": run["owner_id"],
                "authority_epoch": run["authority_epoch"],
                "source_id": source,
                "model_selection": run["config_snapshot"]["model_selection"],
                "config": run["model_config"],
            },
        )
        return secret

    def fail(self, conn: Any, run: Any, error: ProviderFailure) -> None:
        run["processing_job"]["state"] = "failed"
        transition(
            run,
            "cancelled" if error.code == "PERMISSION_RESOURCE_UNAVAILABLE" else "failed",
            error.code,
        )
        persist(conn, run)

    @contextmanager
    def dispatch(self, run_id: str, job_id: str, attempt: str, secret: str | None = None) -> Any:
        with self.store.account.engine.begin() as conn:
            run, project, state = self.current(conn, run_id)
            self.check(conn, project, run, job_id)
            self.recheck_dependencies(conn, project, state, run, "dispatch_dependencies")
            job = run["processing_job"]
            if (
                job.get("attempt") != attempt
                or job["state"] != "running"
                or datetime.fromisoformat(job["lease_until"]) <= datetime.now(UTC)
            ):
                raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
            if (
                secret is not None
                and self.model_check(conn, project, state, run, "dispatch") != secret
            ):
                raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
            # The reservation was committed before entering this transaction.
            yield
            persist(conn, run)

    def raw_object(self, conn: Any, run: Any, identity: str) -> Any:
        row = (
            conn.execute(
                sa.select(objects).where(
                    objects.c.id == UUID(identity),
                    objects.c.project_id == UUID(run["project_id"]),
                    objects.c.run_id == UUID(run["id"]),
                    objects.c.candidate_id
                    == UUID(
                        run["processing_job"]["groups"][run["processing_job"]["group_index"]][
                            "candidate_id"
                        ]
                    ),
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["file_bytes"] is None
            or hashlib.sha256(bytes(row["file_bytes"])).hexdigest() != row["digest"]
        ):
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        prepared = run["processing_job"].get("prepared")
        if (
            prepared
            and prepared["document_asset_id"] == identity
            and (
                not isinstance(row["text"], str)
                or hashlib.sha256(row["text"].encode()).hexdigest() != prepared["raw_text_digest"]
            )
        ):
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        return row

    def store_file(self, conn: Any, run: Any, state: Any, result: Any) -> Any:
        job = run["processing_job"]
        group = job["groups"][job["group_index"]]
        c = next(c for c in run["candidates"] if c["id"] == group["candidate_id"])
        identity, revision = str(uuid4()), str(uuid4())
        raw = result["raw"]
        conn.execute(
            objects.insert().values(
                id=UUID(identity),
                run_id=UUID(run["id"]),
                candidate_id=UUID(c["id"]),
                project_id=UUID(run["project_id"]),
                file_bytes=raw,
                text=result.get("text"),
                digest=hashlib.sha256(raw).hexdigest(),
            )
        )
        c.setdefault("document_refs", []).append(identity)
        state["sources"][identity] = {
            "content": {},
            "classification": {
                "source": {
                    "project_id": run["project_id"],
                    "source_id": identity,
                    "content_revision": revision,
                },
                "classification": "private",
                "confirmation_status": "unconfirmed",
                "revision": str(uuid4()),
                "confirmation": None,
                "provenance": {
                    "kind": "retrieved_content",
                    "submission_scope_id": None,
                    "dependency_status": "complete",
                },
            },
        }
        return {
            "document_asset_id": identity,
            "file_revision": revision,
            "source_id": result["source_id"],
            "segments": result.get("segments", []),
            "raw_text_digest": hashlib.sha256((result.get("text") or "").encode()).hexdigest(),
        }

    def finish_group(self, conn: Any, run: Any, state: Any, result: Any) -> None:
        job = run["processing_job"]
        group = job["groups"][job["group_index"]]
        c = next(c for c in run["candidates"] if c["id"] == group["candidate_id"])
        if not group["reuse"]:
            self.processing.commit_result(conn, run, c, group, result, state)
        c.pop("cleanup_pending", None)
        job.setdefault("group_history", []).append(
            {"candidate_id": c["id"], "budget": job["budget"]}
        )
        job["group_index"] += 1
        for key in (
            "prepared",
            "classification_revision",
            "replies",
            "attempt",
            "fallback",
            "material_dependencies",
        ):
            job.pop(key, None)
        job.update(
            source_index=0,
            diagnostics=[],
            budget=budget.new_budget(run.get("cleanup_settings", {}).get("budget_limits")),
            step="fetch",
        )
        if job["group_index"] == len(job["groups"]):
            job["state"] = "succeeded"
            run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}
            transition(run, "waiting_user")
        else:
            job["state"] = "queued"
            transition(run, "running")

    def fallback(self, conn: Any, run: Any, blocked: bool = False) -> Any:
        job = run["processing_job"]
        group = job["groups"][job["group_index"]]
        result = {
            "text": None,
            "raw": None,
            "kind": None,
            "source_id": None,
            "diagnostics": job["diagnostics"],
            "engine_id": ENGINE,
            "budget_blocked": blocked,
        }
        if not blocked:
            for source in group["sources"]:
                text = source["metadata"].get("abstract")
                if isinstance(text, str) and text.strip():
                    result.update(text=text, kind="abstract_fallback", source_id=source["id"])
                    break
        if job.get("fallback"):
            retained = self.raw_object(conn, run, job["fallback"]["document_asset_id"])
            result["fallback_file"] = {
                "raw": bytes(retained["file_bytes"]),
                "source_id": job["fallback"]["source_id"],
            }
        return result

    def run_once(self) -> bool:
        result: Any
        chosen = None
        with self.store.account.engine.begin() as conn:
            self.guard.lock(conn)
            rows = list(
                conn.execute(
                    sa.select(runs)
                    .where(runs.c.status.in_(["running", "waiting_user"]))
                    .order_by(runs.c.created_at)
                    .with_for_update()
                ).mappings()
            )
            for row in rows:
                run = copy.deepcopy(row["payload"])
                if (
                    run.get("phase") != "processing"
                    or run.get("request", {}).get("pdf_extraction_engine") != ENGINE
                ):
                    continue
                job = run["processing_job"]
                if job["state"] in {"succeeded", "failed"}:
                    continue
                project = (
                    conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                    .mappings()
                    .one()
                )
                state = load(conn, project)
                try:
                    self.check(conn, project, run, job["id"])
                    self.recheck_dependencies(conn, project, state, run, "resume_dependencies")
                    if job["state"] == "running":
                        if datetime.fromisoformat(job["lease_until"]) <= datetime.now(UTC):
                            raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
                        continue
                    if "group_index" not in job:
                        job.update(
                            group_index=0,
                            source_index=0,
                            diagnostics=[],
                            budget=budget.new_budget(
                                run.get("cleanup_settings", {}).get("budget_limits")
                            ),
                            step="fetch",
                        )
                    group = job["groups"][job["group_index"]]
                    if group["reuse"]:
                        self.finish_group(conn, run, state, None)
                        persist(conn, run)
                        save(conn, project, state)
                        return True
                    if job["state"] == "waiting_classification":
                        current = classification(
                            state, project, job["prepared"]["document_asset_id"]
                        )
                        if current["confirmation_status"] != "confirmed":
                            continue
                        job["classification_revision"] = current["revision"]
                        job.setdefault("material_dependencies", []).append(
                            {
                                "source_id": job["prepared"]["document_asset_id"],
                                "classification_revision": current["revision"],
                            }
                        )
                        job.update(step="cleanup", state="queued", replies=[])
                        transition(run, "running")
                    if job["step"] == "fetch" and job["source_index"] >= len(group["sources"]):
                        self.finish_group(conn, run, state, self.fallback(conn, run))
                        persist(conn, run)
                        save(conn, project, state)
                        return True
                    secret, batch, timeout = None, None, 30.0
                    if job["step"] == "cleanup":
                        secret = self.model_check(conn, project, state, run, "read")
                        prepared = job["prepared"]
                        raw = self.raw_object(conn, run, prepared["document_asset_id"])
                        model = run["config_snapshot"]["model_selection"]["model_id"]
                        try:
                            plan = plan_for_model(
                                raw["text"], prepared["segments"], cleanup_config(run), model
                            )
                            if len(plan.batches) > job["budget"]["limits"]["source_calls"]:
                                raise CleanupInvalid("source needs too many calls")
                        except CleanupInvalid, ParameterError:
                            job["diagnostics"].append(
                                {"source_id": prepared["source_id"], "reason": "capacity_exceeded"}
                            )
                            job.update(step="fetch", source_index=job["source_index"] + 1)
                            persist(conn, run)
                            return True
                        if len(job["replies"]) == len(plan.batches):
                            try:
                                cleaned = reconstruct(plan, job["replies"])
                            except CleanupInvalid:
                                job["diagnostics"].append(
                                    {"source_id": prepared["source_id"], "reason": "cleanup_failed"}
                                )
                                job.update(step="fetch", source_index=job["source_index"] + 1)
                                persist(conn, run)
                                return True
                            _, output, defaulted = effective_config(cleanup_config(run), model)
                            defaulted = run.get("cleanup_settings", {}).get(
                                "output_defaulted", defaulted
                            )
                            result = {
                                **cleaned,
                                "raw": bytes(raw["file_bytes"]),
                                "source_id": prepared["source_id"],
                                "kind": "full_text",
                                "diagnostics": job["diagnostics"],
                                "prepared_document": prepared,
                                "cleanup_provenance": {
                                    "engine_revision": "1",
                                    "prompt_revision": "1",
                                    "model_selection": run["config_snapshot"]["model_selection"],
                                    "config_revision": run["config_snapshot"]["config_revision"],
                                    "parameter_digest": hashlib.sha256(
                                        json.dumps(
                                            cleanup_config(run)["parameters"],
                                            sort_keys=True,
                                            separators=(",", ":"),
                                        ).encode()
                                    ).hexdigest(),
                                    "output_tokens": output,
                                    "output_defaulted": defaulted,
                                },
                            }
                            self.model_check(conn, project, state, run, "commit")
                            self.finish_group(conn, run, state, result)
                            persist(conn, run)
                            save(conn, project, state)
                            return True
                        batch = plan.batches[len(job["replies"])]
                        try:
                            reservation = budget.reserve(
                                job["budget"],
                                prepared["source_id"],
                                min(30, run["model_config"]["timeout_seconds"]),
                            )
                        except budget.BudgetBlocked as exc:
                            if str(exc) == "outcome_unknown":
                                raise ProviderFailure("PROVIDER_RESULT_UNKNOWN") from None
                            if str(exc) == "group_exhausted":
                                if (
                                    job["budget"]["sources"]
                                    .get(prepared["source_id"], {})
                                    .get("calls", 0)
                                ):
                                    job["diagnostics"].append(
                                        {
                                            "source_id": prepared["source_id"],
                                            "reason": "budget_exhausted",
                                        }
                                    )
                                self.finish_group(
                                    conn, run, state, self.fallback(conn, run, blocked=True)
                                )
                            else:
                                job["diagnostics"].append(
                                    {
                                        "source_id": prepared["source_id"],
                                        "reason": "budget_exhausted",
                                    }
                                )
                                job.update(step="fetch", source_index=job["source_index"] + 1)
                            persist(conn, run)
                            save(conn, project, state)
                            return True
                        timeout = reservation["timeout"]
                    elif (
                        job["budget"]["calls"] >= job["budget"]["limits"]["group_calls"]
                        or job["budget"]["seconds"] >= job["budget"]["limits"]["group_seconds"]
                    ):
                        self.finish_group(conn, run, state, self.fallback(conn, run, blocked=True))
                        persist(conn, run)
                        save(conn, project, state)
                        return True
                    job.update(
                        state="running",
                        attempt=str(uuid4()),
                        lease_until=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                    )
                    persist(conn, run)
                    chosen = (copy.deepcopy(run), batch, secret, timeout)
                    break
                except (ProviderFailure, AccountError) as exc:
                    self.fail(conn, run, ProviderFailure(exc.code))
        if chosen is None:
            return False
        run, batch, secret, timeout = chosen
        job = run["processing_job"]
        group = job["groups"][job["group_index"]]
        result, error = None, None
        started = monotonic()
        try:
            if batch is None:
                result = self.pdf.prepare(
                    [group["sources"][job["source_index"]]],
                    lambda: self.dispatch(run["id"], job["id"], job["attempt"]),
                )
            else:
                result = self.provider.propose(
                    cleanup_config(run),
                    run["config_snapshot"]["model_selection"]["model_id"],
                    secret,
                    batch,
                    timeout,
                    lambda: self.dispatch(run["id"], job["id"], job["attempt"], secret),
                )
        except (ProviderFailure, CleanupInvalid, ParameterError) as exc:
            error = exc
        elapsed = monotonic() - started
        with self.store.account.engine.begin() as conn:
            current, project, state = self.current(conn, run["id"])
            active = current["processing_job"]
            if (
                current["status"] not in {"running", "waiting_user"}
                or active.get("attempt") != job["attempt"]
                or active["state"] != "running"
            ):
                return True
            try:
                self.check(conn, project, current, job["id"])
                self.recheck_dependencies(conn, project, state, current, "result_dependencies")
                if datetime.fromisoformat(active["lease_until"]) <= datetime.now(UTC):
                    raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
                if batch is not None:
                    self.model_check(conn, project, state, current, "result")
                    budget.settle(active["budget"], job["budget"]["pending"]["id"], elapsed)
                    if error is None:
                        active["replies"].append(result)
                    else:
                        active["diagnostics"].append(
                            {
                                "source_id": active["prepared"]["source_id"],
                                "reason": "cleanup_failed",
                            }
                        )
                        active.update(step="fetch", source_index=active["source_index"] + 1)
                    active["state"] = "queued"
                elif error is None and result and result.get("kind") == "full_text":
                    active["prepared"] = self.store_file(conn, current, state, result)
                    c = next(c for c in current["candidates"] if c["id"] == group["candidate_id"])
                    c["cleanup_pending"] = {**active["prepared"], "state": "waiting_classification"}
                    active["state"] = "waiting_classification"
                    current["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}
                    transition(current, "waiting_user")
                else:
                    active["diagnostics"].extend(
                        (result or {}).get("diagnostics", [])
                        or [
                            {
                                "source_id": group["sources"][active["source_index"]]["id"],
                                "reason": "source_unavailable",
                            }
                        ]
                    )
                    fallback = (result or {}).get("fallback_file")
                    if fallback and not active.get("fallback"):
                        active["fallback"] = self.store_file(conn, current, state, fallback)
                    active.update(state="queued", source_index=active["source_index"] + 1)
                persist(conn, current)
                save(conn, project, state)
            except ProviderFailure as exc:
                self.fail(conn, current, exc)
        return True
