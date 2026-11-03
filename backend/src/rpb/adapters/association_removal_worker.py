"""Publish a confirmed subtraction from a pinned version without provider calls."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.association_removal_inputs import pinned_manifest, read_remaining
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.construction_slots import acquire
from rpb.adapters.first_publication import persist_version
from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import (
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_supports,
    graph_views,
    vector_members,
    vector_views,
)
from rpb.adapters.knowledge_graph_seal import seal_graph_view
from rpb.adapters.knowledge_tables import heads
from rpb.adapters.knowledge_vector_seal import seal_vector_view
from rpb.adapters.project import projects
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.runs import persist, transition
from rpb.adapters.search_terms import load, now
from rpb.modules.account_config.application.ports import AccountError


def _copy_graph(
    conn: Any, project: UUID, original: UUID, view: UUID, kept: set[UUID], revisions: set[UUID]
) -> dict[str, int]:
    def rows(table: Any, condition: Any) -> list[Any]:
        return list(
            conn.execute(
                sa.select(table).where(
                    table.c.project_id == project, table.c.view_id == original, condition
                )
            ).mappings()
        )

    def insert(table: Any, records: list[Any]) -> None:
        if records:
            conn.execute(table.insert(), [dict(row) | {"view_id": view} for row in records])

    labels = rows(
        graph_labels,
        sa.or_(
            graph_labels.c.source["chunk_id"].astext.in_([str(k) for k in kept]),
            graph_labels.c.source["asset_revision"].astext.in_([str(r) for r in revisions]),
        ),
    )
    supports = rows(
        graph_supports,
        sa.or_(graph_supports.c.chunk_id.in_(kept), graph_supports.c.asset_revision.in_(revisions)),
    )
    edges = rows(graph_edges, graph_edges.c.id.in_({r["edge_id"] for r in supports}))
    node_ids = {r["node_id"] for r in labels} | {
        r[k] for r in edges for k in ("source_id", "target_id")
    }
    nodes = rows(graph_nodes, graph_nodes.c.id.in_(node_ids))
    extractions = rows(graph_extractions, graph_extractions.c.chunk_id.in_(kept))
    for table, records in (
        (graph_nodes, nodes),
        (graph_labels, labels),
        (graph_edges, edges),
        (graph_supports, supports),
        (graph_extractions, extractions),
    ):
        insert(table, records)
    return {
        "nodes": len(nodes),
        "assertions": len(edges),
        "supports": len(supports),
        "extractions": len(extractions),
    }


def _publish(conn: Any, root: Path, project: Any, run: Any) -> None:
    pid, actor, identity, attempt = (
        UUID(run[k]) for k in ("project_id", "owner_id", "id", "attempt_id")
    )
    base = conn.scalar(
        sa.select(heads.c.version_id).where(heads.c.project_id == pid).with_for_update()
    )
    intent = run["removal"]
    if (
        str(base) != intent["base_version"]
        or content_digest([str(base), intent["targets"]]) != intent["member_scope"]
        or [
            (r["target_kind"], r["target_id"], r["base_asset_revision"])
            for r in intent["revisions"]
        ]
        != [(t["kind"], t["id"], t["asset_revision"]) for t in intent["targets"]]
    ):
        raise AccountError("STATE_CONFIRMATION_STALE", 409)
    rev = str(uuid4())
    run.update(
        effective_input_revision=str(uuid4()),
        candidate_revision=rev,
        candidate_version={
            "revision": rev,
            "state": "preparing",
            "content_locked": True,
            "closing_reason": None,
        },
        input_snapshot={
            "mode": "revision_only",
            "pending_revision_ids": [r["id"] for r in intent["revisions"]],
            "supplement_ids": [],
            "base_knowledge_version_id": str(base),
            "frozen_at": now(),
        },
        lease_until=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    )
    acquire(conn, run)
    transition(run, "running")
    persist(conn, run)
    record = pinned_manifest(conn, pid, base)
    baseline = record["manifest"]["papers"]
    pairs = {(p["project_paper_id"], p["paper_revision_id"]) for p in baseline}
    removed = {(t["id"], t["asset_revision"]) for t in intent["targets"] if t["kind"] == "paper"}
    if not removed or len(removed) != len(intent["targets"]) or not removed <= pairs:
        raise AccountError("STATE_CONFIRMATION_STALE", 409)
    files = ImmutableFileStore(root)
    kept_inputs = read_remaining(conn, files, project, actor, load(conn, project), record, removed)
    papers = kept_inputs.papers
    revisions = {UUID(p["paper_revision_id"]) for p in papers}
    kept = set(kept_inputs.members)
    text_deps = kept_inputs.text_dependencies
    graph_dep = content_digest({"text": text_deps, "metadata": kept_inputs.metadata_dependencies})
    profile_id = content_digest(kept_inputs.profile)
    vi, gi = uuid4(), uuid4()
    binding = {
        "project_id": pid,
        "run_id": identity,
        "attempt_id": attempt,
        "slot_epoch": run["slot_epoch"],
        "input_revision": UUID(run["effective_input_revision"]),
        "candidate_revision": UUID(rev),
        "build_profile_id": profile_id,
    }
    eid = kept_inputs.profile["embedding_profile_id"]
    conn.execute(
        vector_views.insert().values(
            **binding, id=vi, profile_id=eid, dependency_digest=content_digest(text_deps)
        )
    )
    if kept:
        conn.execute(
            vector_members.insert(),
            [
                {
                    "project_id": pid,
                    "view_id": vi,
                    "embedding_id": kept_inputs.members[k],
                    "profile_id": eid,
                }
                for k in kept
            ],
        )
    vector_digest = seal_vector_view(conn, pid, vi, kept)
    conn.execute(graph_views.insert().values(**binding, id=gi, dependency_digest=graph_dep))
    counts = _copy_graph(conn, pid, kept_inputs.graph, gi, kept, revisions)
    graph_digest = seal_graph_view(conn, pid, gi, kept, kept_inputs.fragments)
    counts.update(papers=len(papers), texts=len(papers), chunks=len(kept), vectors=len(kept))
    manifest = {
        "papers": papers,
        "materials": [],
        "vector_view_id": str(vi),
        "graph_view_id": str(gi),
        "build_profile": kept_inputs.profile,
        "vector_digest": vector_digest,
        "graph_digest": graph_digest,
    }
    proof = {
        "project_id": str(pid),
        "base_version_id": str(base),
        "run_id": str(identity),
        "attempt_id": str(attempt),
        "candidate_revision": rev,
        "manifest_digest": content_digest(manifest),
        "build_profile_id": profile_id,
        "vector_view_id": str(vi),
        "graph_view_id": str(gi),
        "counts": counts,
        "object_digests": kept_inputs.digests,
        "dependency_set_digest": graph_dep,
        "validated_at": now(),
        "read_barrier_id": str(uuid4()),
    }
    for oid, (file_attempt, expected) in kept_inputs.stamps.items():
        if files.stamp(pid, file_attempt, UUID(oid)) != expected:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    result = persist_version(
        conn,
        run,
        pid,
        identity,
        attempt,
        base,
        manifest,
        proof,
        kept_inputs.text_dependencies,
        kept_inputs.metadata_dependencies,
    )
    for revision in intent["revisions"]:
        revision.update(inclusion_status="published", published_version_id=result, updated_at=now())
    conn.execute(runs.update().where(runs.c.id == identity).values(payload=run))


class AssociationRemovalWorker:
    """A local projection of sealed assets, independent of model runtimes."""

    def __init__(self, store: Any, root: Path) -> None:
        self.store, self.root = store, root
        store.association_removal_enabled = True

    def run_once(self) -> bool:
        return process_one(self.store, self.root)


def process_one(store: Any, root: Path) -> bool:
    with store.account.engine.begin() as conn:
        conn.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )
        run = conn.scalar(
            sa.select(runs.c.payload)
            .where(
                runs.c.status == "queued",
                runs.c.payload["phase"].astext == "association_removal",
                ~sa.exists(
                    sa.select(slots.c.project_id).where(
                        slots.c.project_id == runs.c.project_id,
                        slots.c.occupant_run_id.is_not(None),
                    )
                ),
            )
            .order_by(runs.c.created_at, runs.c.id)
            .limit(1)
            .with_for_update()
        )
        if run is None:
            return False
        project = (
            conn.execute(
                sa.select(projects)
                .where(projects.c.id == UUID(run["project_id"]))
                .with_for_update()
            )
            .mappings()
            .one()
        )
        store.revoke(conn, project, run)
        if run["status"] != "queued":
            return True
        try:
            with conn.begin_nested():
                actor = UUID(run["owner_id"])
                if not store.terms.llm.permitted_actor(conn, actor):
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                store.terms.project(conn, actor, project["id"], write=True)
                _publish(conn, root, project, run)
        except Exception as exc:
            original = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(run["id"])))
            transition(
                original,
                "failed",
                exc.code if isinstance(exc, AccountError) else "STORAGE_FILE_UNAVAILABLE",
            )
            persist(conn, original)
        return True
