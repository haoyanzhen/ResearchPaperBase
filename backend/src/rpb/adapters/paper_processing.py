"""Confirmed screening to immutable, explicitly attributed processing proposals."""

import copy
import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters import paper_screening as screening
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.processing_tables import objects
from rpb.adapters.project import projects
from rpb.adapters.run_tables import runs
from rpb.adapters.search_term_worker import TermWorker
from rpb.adapters.search_terms import load, now, save
from rpb.modules.account_config.application.ports import AccountError


def busy(run: Any) -> bool:
    return run.get("processing_job", {}).get("state") in {
        "queued",
        "running",
        "waiting_classification",
    }


def eligible(run: Any) -> list[Any]:
    return [
        c
        for c in run["candidates"]
        if c.get("deduplication", {}).get("state") == "distinct"
        and c["screening"]["valid"] is True
        and not c.get("screening_stale")
    ]


def accept(run: Any, actor: Any) -> None:
    from rpb.adapters.runs import transition

    screening.writable(run)
    chosen = eligible(run)
    if not chosen:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    groups = []
    for c in chosen:
        sources = screening.members(run, c)
        reuse = bool(
            c.get("processing")
            and not c.get("processing_stale")
            and c["processing"]["source_ids"] == [source["id"] for source in sources]
        )
        if c.get("processing") and not reuse:
            c["processing_stale"] = True
        groups.append(
            {
                "candidate_id": c["id"],
                "reuse": reuse,
                "sources": copy.deepcopy(
                    [
                        {
                            "id": s["id"],
                            "revision": s["revision"],
                            "metadata": s["metadata"],
                            "source": s["source"],
                        }
                        for s in sources
                    ]
                ),
            }
        )
        c["screening_state"] = (
            "manual_confirm" if c.get("screening_state") != "manual_edit" else "manual_edit"
        )
    run["screening_confirmation"] = {
        "actor_id": str(actor),
        "at": now(),
        "candidate_revision": run["candidate_revision"],
        "candidate_ids": [c["id"] for c in chosen],
    }
    run["processing_job"] = {
        "state": "queued",
        "id": str(uuid4()),
        "groups": groups,
        "candidate_revision": run["candidate_revision"],
        "input_revision": run["effective_input_revision"],
    }
    run["phase"] = "processing"
    transition(run, "running")


def confirm(run: Any, actor: Any) -> None:
    if busy(run) or run.get("phase") != "processing":
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if not any(
        c.get("processing", {}).get("status") in {"available", "degraded"} for c in eligible(run)
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    for c in eligible(run):
        if c.get("processing", {}).get("basis"):
            c["processing"]["basis"]["confirmed_revision"] = c["processing"]["basis"][
                "processing_revision"
            ]
    run["processing_confirmation"] = {
        "actor_id": str(actor),
        "at": now(),
        "candidate_revision": run["candidate_revision"],
    }
    run["phase"] = "analysis"
    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}


def summary(run: Any) -> Any:
    if "processing_job" not in run:
        return None
    selected = eligible(run)

    def status(c: Any) -> Any:
        return "pending" if c.get("processing_stale") else c.get("processing", {}).get("status")

    return {
        "available": sum(status(c) == "available" for c in selected),
        "degraded": sum(status(c) == "degraded" for c in selected),
        "failed": sum(status(c) in {"failed", "unsupported"} for c in selected),
        "pending": sum(
            status(c) not in {"available", "degraded", "failed", "unsupported"} for c in selected
        ),
        "excluded": len(run["candidates"]) - len(selected),
        "confirmed": bool(run.get("processing_confirmation")),
    }


def text_view(conn: Any, run: Any, candidate_id: str) -> Any:
    c = next((c for c in run["candidates"] if c["id"] == candidate_id), None)
    if c is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    processing = c.get("processing", {})
    cleanup = processing.get("cleanup")
    if not cleanup:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    identities = [cleanup["raw_text_id"], processing["basis"]["text_revision_id"]]
    texts = []
    for identity, digest in zip(
        identities, [cleanup["raw_text_digest"], processing["text_digest"]], strict=True
    ):
        row = (
            conn.execute(
                sa.select(objects).where(
                    objects.c.id == UUID(identity),
                    objects.c.project_id == UUID(run["project_id"]),
                    objects.c.run_id == UUID(run["id"]),
                    objects.c.candidate_id == UUID(candidate_id),
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["text"] is None:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        if hashlib.sha256(row["text"].encode()).hexdigest() != digest:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        texts.append(row["text"])
    return {
        "raw_text": texts[0],
        "text": texts[1],
        "processing_revision": processing["basis"]["processing_revision"],
        "coverage": "text_layer_only",
        "line_mapping": cleanup["line_mapping"],
        "segments": processing["segments"],
    }


def file_view(conn: Any, run: Any, data: Any, download: bool = False) -> Any:
    c = next((c for c in run["candidates"] if c["id"] == data["candidate_id"]), None)
    identity = data["document_id"]
    if c is None or identity not in c.get("document_refs", []):
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    row = (
        conn.execute(
            sa.select(objects).where(
                objects.c.id == UUID(identity),
                objects.c.run_id == UUID(run["id"]),
                objects.c.candidate_id == UUID(c["id"]),
                objects.c.project_id == UUID(run["project_id"]),
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["file_bytes"] is None:
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    raw = bytes(row["file_bytes"])
    if hashlib.sha256(raw).hexdigest() != row["digest"]:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if download:
        return raw
    path = (
        f"/api/v1/projects/{run['project_id']}/construction-runs/{run['id']}"
        f"/candidates/{c['id']}/files/{identity}/download"
    )
    return {
        "document_asset_id": identity,
        "scope": {"type": "candidate", "id": c["id"], "run_id": run["id"]},
        "filename": "paper.pdf",
        "media_type": "application/pdf",
        "size_bytes": len(raw),
        "download_url": path,
    }


class ProcessingWorker:
    def __init__(self, store: Any, provider: Any) -> None:
        self.store, self.provider = store, provider

    def check(self, conn: Any, project: Any, run: Any, identity: str) -> None:
        job = run.get("processing_job", {})
        if (
            not self.store.terms.llm.permitted_actor(conn, UUID(run["owner_id"]))
            or project["status"] != "active"
            or project["authority_epoch"] != run["authority_epoch"]
        ):
            raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
        if (
            run["status"] != "running"
            or run.get("phase") != "processing"
            or job.get("id") != identity
            or job["state"] not in {"queued", "running"}
            or job["candidate_revision"] != run["candidate_revision"]
            or job["input_revision"] != run["effective_input_revision"]
        ):
            raise ProviderFailure("STATE_REVISION_CONFLICT")
        if job["state"] == "running" and datetime.fromisoformat(job["lease_until"]) <= datetime.now(
            UTC
        ):
            raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")

    @contextmanager
    def dispatch(self, run_id: str, job_id: str) -> Any:
        from rpb.adapters.runs import persist

        with self.store.account.engine.begin() as conn:
            TermWorker.lock(conn)
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
            self.check(conn, project, run, job_id)
            run["processing_job"].setdefault("boundaries", []).append("dispatch")
            yield
            persist(conn, run)

    def run_once(self) -> bool:
        from rpb.adapters.runs import persist, transition

        chosen = None
        with self.store.account.engine.begin() as conn:
            TermWorker.lock(conn)
            for row in conn.execute(
                sa.select(runs).where(runs.c.status == "running").with_for_update()
            ).mappings():
                run = copy.deepcopy(row["payload"])
                if run.get("phase") != "processing":
                    continue
                if run.get("request", {}).get("pdf_extraction_engine") == "llm_text_cleanup":
                    continue
                job = run["processing_job"]
                project = (
                    conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                    .mappings()
                    .one()
                )
                try:
                    self.check(conn, project, run, job["id"])
                except ProviderFailure as exc:
                    job["state"] = "failed"
                    transition(
                        run,
                        "cancelled" if exc.code == "PERMISSION_RESOURCE_UNAVAILABLE" else "failed",
                        exc.code,
                    )
                    persist(conn, run)
                    continue
                if job["state"] != "queued":
                    continue
                job.update(
                    state="running",
                    lease_until=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                    boundaries=["read"],
                )
                persist(conn, run)
                chosen = copy.deepcopy(run)
                break
        if chosen is None:
            return False
        job = chosen["processing_job"]
        for index, group in enumerate(job["groups"]):
            try:
                result = (
                    None
                    if group["reuse"]
                    else self.provider.prepare(
                        group["sources"], lambda: self.dispatch(chosen["id"], job["id"])
                    )
                )
            except Exception:
                result = {
                    "text": None,
                    "raw": None,
                    "source_id": None,
                    "kind": None,
                    "segments": [],
                    "diagnostics": [{"source_id": None, "reason": "source_unavailable"}],
                }
            if not self.commit_group(
                chosen["id"], job["id"], group, result, index == len(job["groups"]) - 1
            ):
                break
        return True

    def commit_group(self, run_id: str, job_id: str, group: Any, result: Any, final: bool) -> bool:
        from rpb.adapters.runs import persist, transition

        with self.store.account.engine.begin() as conn:
            TermWorker.lock(conn)
            row = (
                conn.execute(sa.select(runs).where(runs.c.id == UUID(run_id)).with_for_update())
                .mappings()
                .one()
            )
            run = copy.deepcopy(row["payload"])
            if run.get("processing_job", {}).get("id") != job_id or run["status"] != "running":
                return False
            project = (
                conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                .mappings()
                .one()
            )
            try:
                self.check(conn, project, run, job_id)
            except ProviderFailure as exc:
                run["processing_job"]["state"] = "failed"
                transition(
                    run,
                    "cancelled" if exc.code == "PERMISSION_RESOURCE_UNAVAILABLE" else "failed",
                    exc.code,
                )
                persist(conn, run)
                return False
            state = load(conn, project)
            completed = run["processing_job"].setdefault("completed_groups", [])
            if group["candidate_id"] in completed:
                return True
            c = next(c for c in run["candidates"] if c["id"] == group["candidate_id"])
            if not group["reuse"]:
                self.commit_result(conn, run, c, group, result, state)
            completed.append(group["candidate_id"])
            run["processing_job"]["boundaries"].append("commit")
            if final:
                run["processing_job"].update(state="succeeded", groups=[])
                run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}
            transition(run, "waiting_user" if final else "running")
            persist(conn, run)
            save(conn, project, state)
        return True

    def commit_result(
        self, conn: Any, run: Any, c: Any, group: Any, result: Any, state: Any
    ) -> None:
        if not isinstance(result, dict):
            result = {}
        text = result.get("text")
        source = next((s for s in group["sources"] if s["id"] == result.get("source_id")), None)
        raw = result.get("raw")
        valid = (
            isinstance(text, str)
            and 0 < len(text) <= 200_000
            and bool(text.strip())
            and source is not None
            and result.get("kind") in {"full_text", "abstract_fallback"}
        )
        if valid and source is not None and result["kind"] == "abstract_fallback":
            valid = text == source["metadata"].get("abstract") and raw is None
        if valid and result["kind"] == "full_text":
            valid = isinstance(raw, bytes) and raw.startswith(b"%PDF-") and len(raw) <= 52_428_800
        identity, revision = str(uuid4()), str(uuid4())
        prepared = result.get("prepared_document") if valid and raw else None
        if prepared:
            stored = (
                conn.execute(
                    sa.select(objects).where(
                        objects.c.id == UUID(prepared["document_asset_id"]),
                        objects.c.run_id == UUID(run["id"]),
                        objects.c.project_id == UUID(run["project_id"]),
                        objects.c.candidate_id == UUID(c["id"]),
                    )
                )
                .mappings()
                .one()
            )
            if bytes(stored["file_bytes"]) != raw:
                raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
        document_id = prepared["document_asset_id"] if prepared else identity
        file_revision = prepared["file_revision"] if prepared else revision
        status = "available" if valid and raw else "degraded" if valid else "failed"
        if status == "failed" and any(
            d.get("reason") == "parser_unavailable"
            for d in result.get("diagnostics", [])
            if isinstance(d, dict)
        ):
            status = "unsupported"
        if c.get("processing"):
            c.setdefault("processing_history", []).append(copy.deepcopy(c["processing"]))
        c["processing_stale"] = False
        c["processing"] = {
            "status": status,
            "text_source_kind": result["kind"] if valid else None,
            "failure_reason": None
            if status == "available"
            else "全文不可用，使用真实摘要"
            if valid
            else "组预算耗尽，仍有未完成的全文来源"
            if result.get("budget_blocked")
            else "无可用文本",
            "participates_in_knowledge": False,
            "selected_source_id": source["id"] if valid and source is not None else None,
            "selected_source_revision": source.get("revision")
            if valid and source is not None
            else None,
            "source_ids": [s["id"] for s in group["sources"]],
            "diagnostics": [
                {"source_id": d.get("source_id"), "reason": d["reason"]}
                for d in result.get("diagnostics", [])
                if isinstance(d, dict)
                and d.get("reason")
                in {
                    "source_unavailable",
                    "corrupt_content",
                    "encrypted_content",
                    "no_usable_text",
                    "safety_limit",
                    "parser_unavailable",
                    "cleanup_failed",
                    "capacity_exceeded",
                    "budget_exhausted",
                }
                and d.get("source_id") in {None, *[s["id"] for s in group["sources"]]}
            ],
            "text_preview": text[:2000] if valid else None,
            "basis": {
                "processing_revision": revision,
                "input_revision": run["effective_input_revision"],
                "text_revision_id": identity if valid else None,
                "document_asset_id": document_id if valid and raw else None,
                "file_revision": file_revision if valid and raw else None,
                "confirmed_revision": None,
            },
        }
        failed_sources = {d["source_id"] for d in c["processing"]["diagnostics"]}
        c["processing"]["source_attempts"] = [
            {
                "source_id": item["id"],
                "state": ("selected_full_text" if raw else "selected_abstract")
                if valid and source is not None and item["id"] == source["id"]
                else "failed"
                if item["id"] in failed_sources
                else "not_attempted",
            }
            for item in group["sources"]
        ]
        if valid:
            conn.execute(
                objects.insert().values(
                    id=UUID(identity),
                    run_id=UUID(run["id"]),
                    candidate_id=UUID(c["id"]),
                    project_id=UUID(run["project_id"]),
                    file_bytes=None if prepared else raw,
                    text=text,
                    digest=hashlib.sha256(raw or text.encode()).hexdigest(),
                )
            )
            c["processing"]["text_length_chars"] = len(text)
            c["processing"]["text_digest"] = hashlib.sha256(text.encode()).hexdigest()
            c["processing"]["segments"] = result.get("segments", []) or [
                {"start_offset": 0, "end_offset": len(text), "page": None}
            ]
            if prepared:
                c["processing"]["cleanup"] = {
                    **result["cleanup_provenance"],
                    "engine_id": "llm_text_cleanup",
                    "raw_text_digest": result["raw_text_digest"],
                    "raw_text_id": document_id,
                    "line_mapping": result["line_mapping"],
                    "coverage": "text_layer_only",
                    "raw_text_preview": result["raw_text"][:2000],
                }
            if raw and not prepared:
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
        fallback = result.get("fallback_file")
        if isinstance(fallback, dict) and fallback.get("source_id") in {
            s["id"] for s in group["sources"]
        }:
            failed_raw = fallback.get("raw")
            if (
                isinstance(failed_raw, bytes)
                and failed_raw.startswith(b"%PDF-")
                and len(failed_raw) <= 52_428_800
            ):
                file_id = str(uuid4())
                conn.execute(
                    objects.insert().values(
                        id=UUID(file_id),
                        run_id=UUID(run["id"]),
                        candidate_id=UUID(c["id"]),
                        project_id=UUID(run["project_id"]),
                        file_bytes=failed_raw,
                        text=None,
                        digest=hashlib.sha256(failed_raw).hexdigest(),
                    )
                )
                c.setdefault("document_refs", []).append(file_id)
                c["processing"]["retained_file"] = {
                    "document_asset_id": file_id,
                    "source_id": fallback["source_id"],
                    "file_revision": str(uuid4()),
                }
                state["sources"][file_id] = {
                    "content": {},
                    "classification": {
                        "source": {
                            "project_id": run["project_id"],
                            "source_id": file_id,
                            "content_revision": c["processing"]["retained_file"]["file_revision"],
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
        c["revision"] = str(uuid4())
