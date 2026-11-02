"""Durable analysis with current authorization at read, dispatch and commit."""

import copy
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters import paper_analysis as analysis
from rpb.adapters import paper_screening as screening
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.project import projects
from rpb.adapters.run_tables import runs
from rpb.adapters.runs import RunStore, persist, transition
from rpb.adapters.search_term_worker import TermWorker
from rpb.adapters.search_terms import load, material_basis, now
from rpb.modules.construction.domain.analysis import paper_analysis


class AnalysisWorker:
    def __init__(self, store: RunStore, provider: Any) -> None:
        self.store, self.provider = store, provider
        self.guard = TermWorker(store.terms, None)

    def check(self, conn: Any, project: Any, run: Any, job: Any, boundary: str) -> str:
        if screening.content_locked(run) or not screening.baseline_ready(run):
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        if run["status"] != "waiting_user" or run.get("phase") not in {
            "analysis",
            "ingestion_preview",
        }:
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        c = analysis.candidate(run, job["candidate_id"])
        if (
            c["revision"] != job["candidate_revision"]
            or c.get("processing", {}).get("basis") != job["processing_basis"]
            or c.get("processing_stale")
            or not run.get("processing_confirmation")
        ):
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        state = load(conn, project)
        secret = ""
        for sid in job["source_ids"]:
            if (
                state["sources"]
                .get(sid, {})
                .get("classification", {})
                .get("source", {})
                .get("content_revision")
                != job["source_revisions"][sid]
            ):
                raise ProviderFailure("STATE_REVISION_CONFLICT")
            audit = material_basis(state, job["owner_id"], project, sid, boundary)
            job.setdefault("material_audit", []).append(audit)
            _, secret = self.guard.check(conn, project, state, {**job, "source_id": sid})
        return secret

    @contextmanager
    def dispatch(self, run_id: str, job_id: str, attempt: str, secret: str) -> Any:
        failure = None
        with self.store.account.engine.begin() as conn:
            self.guard.lock(conn)
            row = (
                conn.execute(sa.select(runs).where(runs.c.id == UUID(run_id)).with_for_update())
                .mappings()
                .first()
            )
            if row is None:
                raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
            run = copy.deepcopy(row["payload"])
            job = run.get("analysis_jobs", {}).get(job_id)
            if (
                not job
                or job["state"] != "running"
                or job["attempt_id"] != attempt
                or datetime.fromisoformat(job["lease_until"]) <= datetime.now(UTC)
            ):
                raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
            project = (
                conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                .mappings()
                .one()
            )
            try:
                if self.check(conn, project, run, job, "dispatch") != secret:
                    raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
                yield
            except Exception as exc:
                failure = exc
            persist(conn, run)
        if failure:
            raise failure

    def run_once(self) -> bool:
        selected = None
        with self.store.account.engine.begin() as conn:
            self.guard.lock(conn)
            for row in conn.execute(
                sa.select(runs).where(runs.c.status == "waiting_user").with_for_update()
            ).mappings():
                run = copy.deepcopy(row["payload"])
                project = (
                    conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                    .mappings()
                    .one()
                )
                changed = False
                for job in run.get("analysis_jobs", {}).values():
                    if job["state"] == "running" and datetime.fromisoformat(
                        job["lease_until"]
                    ) <= datetime.now(UTC):
                        self.guard.finish(job, "failed", "PROVIDER_RESULT_UNKNOWN")
                        changed = True
                    if job["state"] != "queued" or selected:
                        continue
                    try:
                        secret = self.check(conn, project, run, job, "read")
                    except ProviderFailure as exc:
                        self.guard.finish(job, "failed", exc.code)
                        changed = True
                        continue
                    job.update(
                        state="running",
                        revision=str(uuid4()),
                        started_at=now(),
                        lease_until=(
                            datetime.now(UTC)
                            + timedelta(seconds=job["config"]["timeout_seconds"] + 30)
                        ).isoformat(),
                    )
                    from rpb.adapters.llm import event_record

                    job["events"].append(
                        event_record("running", UUID(job["revision"]), datetime.now(UTC))
                    )
                    selected = (run["id"], copy.deepcopy(job), secret)
                    changed = True
                if changed:
                    persist(conn, run)
        if selected is None:
            return False
        run_id, job, secret = selected
        result, error = None, None
        try:
            result = paper_analysis(
                self.provider.generate(
                    job["config"],
                    job["model_selection"]["model_id"],
                    secret,
                    job["input"],
                    lambda: self.dispatch(run_id, job["id"], job["attempt_id"], secret),
                )
            )
            if secret and secret in json.dumps(result):
                raise ValueError("credential echo")
        except ProviderFailure as exc:
            error = exc.code
        except Exception:
            error = "PROVIDER_RESPONSE_INVALID"
        with self.store.account.engine.begin() as conn:
            self.guard.lock(conn)
            final_row = (
                conn.execute(sa.select(runs).where(runs.c.id == UUID(run_id)).with_for_update())
                .mappings()
                .first()
            )
            if final_row is None:
                return True
            run = copy.deepcopy(final_row["payload"])
            live = run.get("analysis_jobs", {}).get(job["id"])
            if not live or live["state"] != "running" or live["attempt_id"] != job["attempt_id"]:
                return True
            project = (
                conn.execute(sa.select(projects).where(projects.c.id == final_row["project_id"]))
                .mappings()
                .one()
            )
            try:
                self.check(conn, project, run, live, "commit")
                if datetime.fromisoformat(live["lease_until"]) <= datetime.now(UTC):
                    raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
            except ProviderFailure as exc:
                self.guard.finish(live, "failed", exc.code)
                persist(conn, run)
                return True
            c = analysis.candidate(run, job["candidate_id"])
            if error:
                c["analysis_error"] = error
            else:
                analysis.save_content(
                    run,
                    c,
                    result,
                    job["owner_id"],
                    "agent_draft",
                    {
                        "kind": "agent",
                        "job_id": live["id"],
                        "attempt_id": live["attempt_id"],
                        "source_ids": copy.deepcopy(live["source_ids"]),
                        "source_revisions": copy.deepcopy(live["source_revisions"]),
                        "material_audit": copy.deepcopy(live.get("material_audit", [])),
                        "model_selection": copy.deepcopy(live["model_selection"]),
                        "config_revision": live["config_revision"],
                    },
                )
            self.guard.finish(live, "failed" if error else "succeeded", error)
            transition(run, "waiting_user")
            persist(conn, run)
        return True
