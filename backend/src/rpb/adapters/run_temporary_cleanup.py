"""Release terminal Run staging in two phases. Run history and version pins survive."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import sqlalchemy as sa

from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_build_tables import (
    chunks,
    embeddings,
    graph_extractions,
    graph_supports,
    graph_views,
    publication_events,
    vector_members,
    vector_views,
)
from rpb.adapters.knowledge_paper_tables import (
    object_build_pins,
    object_lifecycle,
    objects,
    paper_revisions,
    version_object_pins,
    version_paper_pins,
)
from rpb.adapters.llm import require_revision
from rpb.adapters.processing_tables import objects as processing
from rpb.adapters.run_tables import runs
from rpb.adapters.search_terms import states
from rpb.modules.account_config.application.ports import AccountError

TERMINAL = ("cancelled", "failed", "succeeded")


def new_job() -> dict[str, Any]:
    return dict(state="queued", attempts=0, reclaimed_objects=0, retained_objects=0, error=None)


def save(conn: Any, run: Any) -> None:
    run.update(
        revision=str(uuid4()), updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    conn.execute(
        runs.update()
        .where(runs.c.id == UUID(run["id"]), runs.c.status == run["status"])
        .values(payload=run, revision=UUID(run["revision"]))
    )


def request_cleanup(conn: Any, actor: UUID, run: Any, body: Any) -> None:
    if UUID(run["owner_id"]) != actor:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    if (
        set(body) != {"run_id", "expected_revision", "explicit_confirmation"}
        or body["explicit_confirmation"] is not True
    ):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    require_revision(run["revision"], body["expected_revision"])
    job = run.get("temporary_cleanup")
    if run["status"] != "failed" and not (job and job["state"] == "failed"):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if job and job["state"] != "failed":
        return
    if job:
        job.update(state="queued", error=None)
    else:
        run["temporary_cleanup"] = new_job()
    if run["status"] == "failed" and run.get("candidate_version"):
        run["candidate_version"].update(
            state="discarded",
            closing_reason={"code": "cleanup", "message": "已按请求放弃恢复，候选已废弃"},
        )
    save(conn, run)


def used(table: Any, column: str, value: Any) -> Any:
    return sa.exists(sa.select(1).where(table.c[column] == value))


def staging_paths(run: Any) -> set[tuple[UUID, UUID]]:
    """Exact private names stage_objects can have installed before a DB rollback."""
    selected = (run.get("ingestion_confirmation") or {}).get("preview", {}).get("valid_papers", [])
    attempt = UUID(run["attempt_id"])
    return {
        (attempt, uuid5(attempt, f"{UUID(cid)}:{kind}"))
        for cid in selected
        for kind in ("text", "file")
    }


def prepare(conn: Any, run: Any, root: Path) -> None:
    project, identity = UUID(run["project_id"]), UUID(run["id"])
    job = run["temporary_cleanup"]
    if "cleanup_pending_objects" in run:
        return
    outgoing = sa.select(vector_views.c.id).where(
        vector_views.c.project_id == project,
        vector_views.c.run_id == identity,
        ~used(publication_events, "vector_view_id", vector_views.c.id),
    )
    detached_embeddings = list(
        conn.scalars(
            sa.select(vector_members.c.embedding_id).where(vector_members.c.view_id.in_(outgoing))
        )
    )
    for view, ref in ((graph_views, "graph_view_id"), (vector_views, "vector_view_id")):
        conn.execute(
            view.delete().where(
                view.c.project_id == project,
                view.c.run_id == identity,
                ~used(publication_events, ref, view.c.id),
            )
        )
    owned_chunks = sa.select(chunks.c.id).where(chunks.c.run_id == identity)
    conn.execute(
        embeddings.delete().where(
            embeddings.c.project_id == project,
            sa.or_(
                embeddings.c.chunk_id.in_(owned_chunks), embeddings.c.id.in_(detached_embeddings)
            ),
            ~used(vector_members, "embedding_id", embeddings.c.id),
        )
    )
    conn.execute(
        chunks.delete().where(
            chunks.c.project_id == project,
            chunks.c.run_id == identity,
            ~used(embeddings, "chunk_id", chunks.c.id),
            ~used(graph_extractions, "chunk_id", chunks.c.id),
            ~used(graph_supports, "chunk_id", chunks.c.id),
        )
    )
    owned_revisions = sa.select(paper_revisions.c.id).where(
        paper_revisions.c.project_id == project, paper_revisions.c.run_id == identity
    )
    owned_objects = conn.execute(
        sa.select(objects.c.id, objects.c.attempt_id)
        .join(object_lifecycle, object_lifecycle.c.object_id == objects.c.id)
        .where(objects.c.project_id == project, objects.c.paper_revision_id.in_(owned_revisions))
        .order_by(objects.c.id)
        .with_for_update(of=object_lifecycle)
    ).all()
    released = list(
        conn.scalars(
            object_build_pins.delete()
            .where(
                object_build_pins.c.project_id == project, object_build_pins.c.run_id == identity
            )
            .returning(object_build_pins.c.object_id)
        )
    )
    # A different terminal Run may have retained its own files for this
    # reader. Revisit its authorized job once the reader releases its pin.
    if released:
        owners = (
            sa.select(paper_revisions.c.run_id)
            .join(objects, objects.c.paper_revision_id == paper_revisions.c.id)
            .where(objects.c.id.in_(released), paper_revisions.c.run_id != identity)
        )
        for owner in conn.scalars(
            sa.select(runs.c.payload)
            .where(
                runs.c.project_id == project,
                runs.c.status.in_(TERMINAL),
                runs.c.id.in_(owners),
                runs.c.payload["temporary_cleanup"]["state"].astext == "completed",
            )
            .order_by(runs.c.id)
            .with_for_update()
        ):
            owner["temporary_cleanup"]["state"] = "queued"
            save(conn, owner)
    pending = []
    for obj, attempt in owned_objects:
        marked = conn.execute(
            object_lifecycle.update()
            .where(
                object_lifecycle.c.object_id == obj,
                object_lifecycle.c.project_id == project,
                object_lifecycle.c.state == "ready",
                ~used(object_build_pins, "object_id", obj),
                ~used(version_object_pins, "object_id", obj),
                ~used(
                    version_paper_pins,
                    "paper_revision_id",
                    sa.select(objects.c.paper_revision_id)
                    .where(objects.c.id == obj)
                    .scalar_subquery(),
                ),
            )
            .values(state="reclaiming")
        )
        if marked.rowcount:
            pending.append([str(attempt), str(obj)])
    # Files are installed before their object's SQL transaction commits. A
    # rollback can leave a file with no registry row. Enumerate deterministic
    # paths of confirmed candidates only; never walk a shared directory.
    files = ImmutableFileStore(root)
    orphans = []
    for attempt_id, object_id in sorted(staging_paths(run)):
        if conn.scalar(sa.select(objects.c.id).where(objects.c.id == object_id)):
            continue
        try:
            files.stamp(project, attempt_id, object_id)
        except FileNotFoundError:
            continue
        orphans.append([str(attempt_id), str(object_id)])
    run["cleanup_orphan_files"] = orphans
    job["retained_objects"] = len(owned_objects) - len(pending)
    run["cleanup_pending_objects"] = pending
    # Retain candidate documents supporting confirmed processing/analysis or human
    # classifications. Other Run-owned processing rows have no independent consumers.
    from rpb.adapters import paper_analysis, paper_screening

    retained = [
        UUID(c["id"])
        for c in run.get("candidates", [])
        if paper_analysis.protected(c)
        or paper_screening.has_human_content(c)
        or c.get("material_classification", {}).get("confirmation_status") == "confirmed"
        or c.get("processing", {}).get("basis", {}).get("confirmed_revision")
        or c.get("processing_history")
        or c.get("retained_analysis")
    ]
    workspace = conn.scalar(sa.select(states.c.payload).where(states.c.project_id == project)) or {}
    classified = [
        UUID(key)
        for key, source in workspace.get("sources", {}).items()
        if source.get("classification", {}).get("confirmation_status") == "confirmed"
    ]
    conn.execute(
        processing.delete().where(
            processing.c.project_id == project,
            processing.c.run_id == identity,
            processing.c.candidate_id.not_in(retained),
            processing.c.id.not_in(classified),
        )
    )
    save(conn, run)


def process_one(engine: Any, root: Path) -> bool:
    with engine.begin() as conn:
        conn.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )
        run = conn.scalar(
            sa.select(runs.c.payload)
            .where(
                runs.c.status.in_(TERMINAL),
                runs.c.payload["temporary_cleanup"]["state"].astext == "queued",
            )
            .order_by(runs.c.created_at, runs.c.id)
            .limit(1)
            .with_for_update()
        )
        if not run:
            return False
        try:
            with conn.begin_nested():
                prepare(conn, run, root)
        except sa.exc.SQLAlchemyError, ValueError, TypeError, KeyError, OSError:
            # Roll back every mark and release before recording a retryable outcome.
            run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(run["id"])))
            job = run["temporary_cleanup"]
            job.update(
                state="failed", error="STORAGE_FILE_UNAVAILABLE", attempts=job["attempts"] + 1
            )
            save(conn, run)
            return True
        identity = UUID(run["id"])
    try:
        finish(engine, root, identity)
    except sa.exc.SQLAlchemyError:
        # Metadata commit can fail after unlink. Preserve durable marks for an
        # idempotent retry, and let subsequent jobs run.
        with engine.begin() as conn:
            failed = conn.scalar(
                sa.select(runs.c.payload).where(runs.c.id == identity).with_for_update()
            )
            if failed and failed["temporary_cleanup"]["state"] == "queued":
                job = failed["temporary_cleanup"]
                job.update(
                    state="failed", error="STORAGE_FILE_UNAVAILABLE", attempts=job["attempts"] + 1
                )
                save(conn, failed)
    return True


def finish(engine: Any, root: Path, identity: UUID) -> None:
    # The durable job and reclamation marks commit before external deletion.
    # Lock only this terminal Run while executing, so another worker can replay
    # the same job safely after a crash without holding the governance lock.
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity).with_for_update())
        if not run or run["temporary_cleanup"]["state"] != "queued":
            return
        project = UUID(run["project_id"])
        job = run["temporary_cleanup"]
        job["attempts"] += 1
        try:
            files = ImmutableFileStore(root)
            pending = [
                (UUID(attempt), UUID(obj)) for attempt, obj in run["cleanup_pending_objects"]
            ]
            if pending:
                verified = conn.execute(
                    sa.select(objects.c.attempt_id, objects.c.id)
                    .join(paper_revisions, paper_revisions.c.id == objects.c.paper_revision_id)
                    .join(object_lifecycle, object_lifecycle.c.object_id == objects.c.id)
                    .where(
                        objects.c.project_id == project,
                        paper_revisions.c.project_id == project,
                        paper_revisions.c.run_id == identity,
                        object_lifecycle.c.project_id == project,
                        object_lifecycle.c.state == "reclaiming",
                        objects.c.id.in_([obj for _, obj in pending]),
                        ~used(object_build_pins, "object_id", objects.c.id),
                        ~used(version_object_pins, "object_id", objects.c.id),
                        ~used(version_paper_pins, "paper_revision_id", objects.c.paper_revision_id),
                    )
                    .order_by(objects.c.id)
                    .with_for_update(of=object_lifecycle)
                ).all()
                if set(verified) != set(pending) or len(verified) != len(pending):
                    raise ValueError("cleanup scope or protection changed")
            orphans = [
                (UUID(attempt), UUID(obj)) for attempt, obj in run.get("cleanup_orphan_files", [])
            ]
            if not set(orphans) <= staging_paths(run) or (
                orphans
                and conn.scalar(
                    sa.select(objects.c.id)
                    .where(objects.c.id.in_([obj for _, obj in orphans]))
                    .limit(1)
                )
            ):
                raise ValueError("unregistered staging scope changed")
            for attempt_id, object_id in pending + orphans:
                files.discard(project, attempt_id, object_id)
        except ValueError, TypeError, KeyError, OSError:
            job.update(state="failed", error="STORAGE_FILE_UNAVAILABLE")
        else:
            removed = [UUID(obj) for _, obj in run.pop("cleanup_pending_objects")]
            conn.execute(
                objects.delete().where(objects.c.project_id == project, objects.c.id.in_(removed))
            )
            conn.execute(
                paper_revisions.delete().where(
                    paper_revisions.c.project_id == project,
                    paper_revisions.c.run_id == identity,
                    ~used(objects, "paper_revision_id", paper_revisions.c.id),
                    ~used(version_paper_pins, "paper_revision_id", paper_revisions.c.id),
                )
            )
            orphan_files = run.pop("cleanup_orphan_files", [])
            job.update(
                state="completed",
                reclaimed_objects=job["reclaimed_objects"] + len(removed) + len(orphan_files),
                error=None,
            )
        save(conn, run)
