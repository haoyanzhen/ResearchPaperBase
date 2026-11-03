"""Load authorized immutable paper inputs, independently of a published index or graph."""

from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest, pinned_revisions
from rpb.adapters.knowledge_paper_tables import objects
from rpb.adapters.knowledge_publication_baseline import retained_inputs
from rpb.adapters.search_term_worker import TermWorker
from rpb.modules.account_config.application.ports import AccountError


def rebuild_requested(run: Any) -> bool:
    snapshot = run.get("input_snapshot") or {}
    return (
        bool(snapshot.get("base_knowledge_version_id")) and snapshot.get("graph_mode") == "rebuild"
    )


def preview_dependency_digest(conn: Any, project: Any, actor: UUID, run: Any) -> str:
    from rpb.adapters.search_terms import load

    confirmation = {"retained_papers": run["baseline_papers"]}
    retained = retained_inputs(
        conn,
        project,
        actor,
        load(conn, project),
        UUID(run["input_snapshot"]["base_knowledge_version_id"]),
        run | {"ingestion_confirmation": confirmation},
    )
    return retained.dependency_digest


def verify_retained_service(
    conn: Any, store: Any, project: Any, state: Any, run: Any, dependencies: dict[str, Any]
) -> None:
    guard = TermWorker(store.terms, None)
    for sid in dependencies:
        guard.check(
            conn,
            project,
            state,
            {
                "owner_id": run["owner_id"],
                "authority_epoch": run["authority_epoch"],
                "source_id": sid,
                "model_selection": run["config_snapshot"]["model_selection"],
                "config": run["model_config"],
            },
        )


def retained_materials(
    conn: Any,
    store: Any,
    files: ImmutableFileStore,
    project: Any,
    actor: UUID,
    state: Any,
    run: Any,
) -> tuple[list[Any], dict[str, Any]]:
    version = UUID(run["input_snapshot"]["base_knowledge_version_id"])
    retained = retained_inputs(conn, project, actor, state, version, run)
    if run["ingestion_confirmation"].get("rebuild_dependency_digest") != retained.dependency_digest:
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    verify_retained_service(conn, store, project, state, run, retained.text_dependencies)
    papers = {
        str(row["id"]): row
        for row in conn.execute(pinned_revisions(project["id"], version)).mappings()
    }
    materials = []
    for member in retained.papers:
        paper = papers[member["paper_revision_id"]]
        if content_digest(paper["content"]) != member["digest"]:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        obj = (
            conn.execute(
                sa.select(objects).where(
                    objects.c.project_id == project["id"],
                    objects.c.id == UUID(member["objects"]["text"]),
                )
            )
            .mappings()
            .one()
        )
        try:
            data = files.read(project["id"], obj["attempt_id"], obj["id"], obj["sha256"])
            text = data.decode("utf-8")
        except OSError, ValueError:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
        if len(data) != obj["size_bytes"] or not text.strip():
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        candidate = {
            "id": str(paper["candidate_id"]),
            "revision": str(paper["id"]),
            "metadata": paper["content"]["metadata"],
            "processing": paper["content"]["processing"],
        }
        materials.append(
            {"candidate": candidate, "identity": member, "object": dict(obj), "text": text}
        )
    return materials, retained.text_dependencies
