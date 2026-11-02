"""Reuse a complete published paper graph inside a new, project-scoped graph view."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest, pinned_revisions
from rpb.adapters.knowledge_build_tables import (
    chunks,
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_supports,
    graph_views,
    publication_events,
)
from rpb.adapters.knowledge_chunk_integrity import verify_chunk_closure
from rpb.adapters.knowledge_graph_seal import verify_graph_view
from rpb.adapters.knowledge_paper_tables import objects, paper_revisions
from rpb.adapters.knowledge_tables import versions
from rpb.adapters.knowledge_vector_baseline import read_baseline_vectors
from rpb.adapters.search_terms import allowed, classification, policy_view
from rpb.modules.account_config.application.ports import AccountError


def metadata_dependency(state: Any, actor: UUID, project: Any, source_id: str) -> dict[str, Any]:
    if not allowed(state, actor, project, source_id):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    source = classification(state, project, source_id)
    return {
        "source_ids": [source_id],
        "source_revisions": {source_id: source["source"]["content_revision"]},
        "classification_revisions": {source_id: source["revision"]},
        "policy_revision": policy_view(state, actor, project)["revision"],
    }


def current_text_dependencies(
    state: Any, actor: UUID, project: Any, source_revisions: dict[str, str]
) -> dict[str, Any]:
    dependencies = {}
    for sid, expected in source_revisions.items():
        source = classification(state, project, sid)
        if source["source"]["content_revision"] != expected or not allowed(
            state, actor, project, sid
        ):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        dependencies[sid] = {
            "source": source["source"],
            "classification_revision": source["revision"],
            "policy_revision": policy_view(state, actor, project)["revision"],
        }
    return dependencies


@dataclass
class BaselineGraph:
    view: UUID
    fragments: dict[UUID, str]
    text_dependencies: dict[str, Any]
    metadata_dependencies: dict[str, Any]


def read_baseline_graph(
    conn: Any,
    files: ImmutableFileStore,
    project: Any,
    actor: UUID,
    state: Any,
    run: Any,
    profile_id: str,
    verified: BaselineGraph | None = None,
    *,
    verify_locators: bool = False,
) -> BaselineGraph:
    project_id = project["id"]
    version = UUID(run["input_snapshot"]["base_knowledge_version_id"])
    base = read_baseline_vectors(
        conn, project_id, version, run["ingestion_confirmation"]["retained_papers"]
    )
    row = (
        conn.execute(
            sa.select(versions.c.manifest, versions.c.ready_proof, graph_views)
            .select_from(
                versions.join(
                    publication_events,
                    sa.and_(
                        publication_events.c.version_id == versions.c.id,
                        publication_events.c.project_id == versions.c.project_id,
                    ),
                ).join(
                    graph_views,
                    sa.and_(
                        graph_views.c.project_id == versions.c.project_id,
                        graph_views.c.id == publication_events.c.graph_view_id,
                        graph_views.c.run_id == versions.c.source_run_id,
                    ),
                )
            )
            .where(
                versions.c.project_id == project_id, versions.c.id == version, graph_views.c.sealed
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or not isinstance(row["ready_proof"].get("counts"), dict)
        or row["manifest"]["graph_view_id"] != str(row["id"])
        or row["ready_proof"]["graph_view_id"] != str(row["id"])
        or row["ready_proof"]["attempt_id"] != str(row["attempt_id"])
        or row["ready_proof"].get("candidate_revision") != str(row["candidate_revision"])
        or row["ready_proof"].get("dependency_set_digest") != row["dependency_digest"]
        or row["build_profile_id"] != profile_id
        or profile_id != content_digest(base.profile)
    ):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    metadata = {
        str(cid): metadata_dependency(state, actor, project, str(cid))
        for cid in conn.scalars(
            pinned_revisions(project_id, version).with_only_columns(paper_revisions.c.candidate_id)
        )
    }
    dependencies = current_text_dependencies(state, actor, project, base.source_revisions)
    if (
        content_digest(dependencies) != base.dependency_digest
        or content_digest({"text": dependencies, "metadata": metadata}) != row["dependency_digest"]
    ):
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    if verified is not None:
        # Sealed rows cannot change. Dispatch rechecks authority; commit rereads the artifacts.
        if (
            verified.view != row["id"]
            or verified.fragments.keys() != base.members.keys()
            or verified.text_dependencies != dependencies
            or verified.metadata_dependencies != metadata
        ):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        return verified
    # Both metadata and text dependencies are authorized before opening protected content.
    try:
        texts = {
            tid: files.read(project_id, attempt, tid, digest).decode("utf-8")
            for tid, (attempt, digest) in base.texts.items()
        }
        fragments = {
            chunk.id: texts[chunk.text_revision_id][chunk.start_offset : chunk.end_offset]
            for chunk in conn.execute(
                sa.select(
                    chunks.c.id,
                    chunks.c.text_revision_id,
                    chunks.c.start_offset,
                    chunks.c.end_offset,
                ).where(chunks.c.project_id == project_id, chunks.c.id.in_(base.members))
            )
        }
        if verify_locators:
            grouped: dict[UUID, list[Any]] = {}
            for chunk in conn.execute(
                sa.select(chunks).where(
                    chunks.c.project_id == project_id, chunks.c.id.in_(base.members)
                )
            ).mappings():
                grouped.setdefault(chunk["text_revision_id"], []).append(chunk)
            for obj in conn.execute(
                sa.select(
                    objects,
                    paper_revisions.c.content["processing"]["text_source_kind"].astext.label(
                        "source_kind"
                    ),
                )
                .join(
                    paper_revisions,
                    sa.and_(
                        objects.c.project_id == paper_revisions.c.project_id,
                        objects.c.paper_revision_id == paper_revisions.c.id,
                    ),
                )
                .where(objects.c.project_id == project_id, objects.c.id.in_(texts))
            ).mappings():
                rows = grouped[obj["id"]]
                verify_chunk_closure(texts[obj["id"]], obj, obj["source_kind"], rows)
        digest = verify_graph_view(
            conn,
            project_id,
            row["id"],
            set(base.members),
            fragments,
            expected_counts=row["ready_proof"]["counts"],
        )
    except OSError, ValueError, KeyError:
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
    if digest != row["manifest"]["graph_digest"]:
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    return BaselineGraph(row["id"], fragments, dependencies, metadata)


def copy_graph_members(
    conn: Any, project: UUID, source: UUID, target: UUID
) -> dict[tuple[str, str], UUID]:
    # IDs are view-scoped. Keeping them preserves every edge, support and label reference.
    for table in (graph_nodes, graph_labels, graph_edges, graph_supports, graph_extractions):
        columns = [sa.literal(target) if c.name == "view_id" else c for c in table.c]
        conn.execute(
            table.insert().from_select(
                table.c.keys(),
                sa.select(*columns).where(table.c.project_id == project, table.c.view_id == source),
            )
        )
    return {
        (r.kind, r.identity_key): r.id
        for r in conn.execute(
            sa.select(graph_nodes.c.kind, graph_nodes.c.identity_key, graph_nodes.c.id).where(
                graph_nodes.c.project_id == project, graph_nodes.c.view_id == target
            )
        )
    }
