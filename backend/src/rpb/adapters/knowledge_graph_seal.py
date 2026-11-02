"""Seal graph membership with a stable digest; callers still owe source validation."""

import hashlib
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.knowledge_build_tables import (
    chunks,
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_supports,
    graph_views,
)
from rpb.adapters.knowledge_paper_tables import paper_revisions


class GraphViewIncomplete(ValueError):
    pass


def seal_graph_view(
    conn: Any,
    project_id: UUID,
    view_id: UUID,
    expected_chunks: set[UUID],
    chunk_texts: dict[UUID, str] | None = None,
) -> str:
    view = (
        conn.execute(
            sa.select(graph_views)
            .where(graph_views.c.project_id == project_id, graph_views.c.id == view_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if view is None or view["sealed"]:
        raise GraphViewIncomplete("view unavailable")
    digest = _digest(conn, project_id, view_id, expected_chunks, view, chunk_texts)
    conn.execute(
        graph_views.update().where(graph_views.c.id == view_id).values(sealed=True, digest=digest)
    )
    return digest


def verify_graph_view(
    conn: Any,
    project_id: UUID,
    view_id: UUID,
    expected_chunks: set[UUID],
    chunk_texts: dict[UUID, str] | None = None,
    *,
    expected_counts: dict[str, int] | None = None,
) -> str:
    view = (
        conn.execute(
            sa.select(graph_views)
            .where(graph_views.c.project_id == project_id, graph_views.c.id == view_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if view is None or not view["sealed"]:
        raise GraphViewIncomplete("sealed view unavailable")
    digest = _digest(conn, project_id, view_id, expected_chunks, view, chunk_texts, expected_counts)
    if digest != view["digest"]:
        raise GraphViewIncomplete("sealed view digest mismatch")
    return digest


def _digest(
    conn: Any,
    project_id: UUID,
    view_id: UUID,
    expected_chunks: set[UUID],
    view: Any,
    chunk_texts: dict[UUID, str] | None,
    expected_counts: dict[str, int] | None = None,
) -> str:
    tables = (graph_extractions, graph_nodes, graph_labels, graph_edges, graph_supports)
    records = {}
    for table in tables:
        records[table.name] = list(
            conn.execute(
                sa.select(table)
                .where(table.c.project_id == project_id, table.c.view_id == view_id)
                .order_by(*table.primary_key.columns)
            ).mappings()
        )
    if expected_counts is not None:
        for key, table in (
            ("nodes", graph_nodes),
            ("assertions", graph_edges),
            ("supports", graph_supports),
            ("extractions", graph_extractions),
        ):
            if type(expected_counts.get(key)) is not int or expected_counts[key] != len(
                records[table.name]
            ):
                raise GraphViewIncomplete("graph counts differ from published proof")
    extraction_rows = records[graph_extractions.name]
    if {row["chunk_id"] for row in extraction_rows} != expected_chunks:
        raise GraphViewIncomplete("extractions differ from frozen chunks")
    chunk_rows = {
        row["id"]: row
        for row in conn.execute(
            sa.select(chunks).where(
                chunks.c.project_id == project_id, chunks.c.id.in_(expected_chunks)
            )
        ).mappings()
    }
    if set(chunk_rows) != expected_chunks:
        raise GraphViewIncomplete("chunk unavailable")
    if chunk_texts is not None:
        if set(chunk_texts) != expected_chunks or any(
            len(chunk_texts[cid]) != chunk["end_offset"] - chunk["start_offset"]
            or hashlib.sha256(chunk_texts[cid].encode()).hexdigest() != chunk["text_digest"]
            for cid, chunk in chunk_rows.items()
        ):
            raise GraphViewIncomplete("readback text differs from frozen chunks")
    nodes = {row["id"] for row in records[graph_nodes.name]}
    edges = records[graph_edges.name]
    edge_ids = {row["id"] for row in edges}
    supports = records[graph_supports.name]
    supported_edges = {row["edge_id"] for row in supports}
    if (
        any(row["node_id"] not in nodes for row in records[graph_labels.name])
        or any(row["source_id"] not in nodes or row["target_id"] not in nodes for row in edges)
        or any(row["edge_id"] not in edge_ids for row in supports)
        or not edge_ids <= supported_edges
    ):
        raise GraphViewIncomplete("unresolved graph membership")
    members = {(row["asset_id"], row["asset_revision"]) for row in chunk_rows.values()}
    metadata = {
        (row["project_paper_id"], row["id"]): row["content"].get("metadata", {})
        for row in conn.execute(
            sa.select(paper_revisions).where(
                paper_revisions.c.project_id == project_id,
                paper_revisions.c.id.in_({revision for _, revision in members}),
            )
        ).mappings()
    }

    def check_source(source: Any, label: str | None = None) -> None:
        try:
            if source["kind"] == "text":
                chunk = chunk_rows[UUID(str(source["chunk_id"]))]
                start, end = source["start_offset"], source["end_offset"]
                if (
                    type(start) is int
                    and type(end) is int
                    and chunk["start_offset"] <= start < end <= chunk["end_offset"]
                    and str(chunk["text_revision_id"]) == str(source["text_revision_id"])
                ):
                    if label is not None:
                        fragment = (chunk_texts or {})[chunk["id"]]
                        offset = chunk["start_offset"]
                        if fragment[start - offset : end - offset] != label:
                            raise GraphViewIncomplete("graph label differs from frozen text")
                    return
            elif source["kind"] == "metadata":
                member = UUID(str(source["asset_id"])), UUID(str(source["asset_revision"]))
                if member in members and str(member[1]) == str(source["metadata_revision"]):
                    field = source["field"]
                    value = metadata[member][field]
                    if (
                        field == "title"
                        and isinstance(value, str)
                        and value
                        and label in (None, value)
                    ):
                        return
                    if (
                        field == "authors"
                        and isinstance(value, list)
                        and value
                        and (label is None or label in value)
                    ):
                        return
        except KeyError, ValueError, TypeError:
            pass
        raise GraphViewIncomplete("graph evidence outside frozen source")

    for support in supports:
        check_source(support)
    for row in records[graph_labels.name]:
        check_source(row["source"], row["label"])
    binding = {
        key: str(view[key])
        for key in (
            "project_id",
            "id",
            "run_id",
            "attempt_id",
            "slot_epoch",
            "input_revision",
            "candidate_revision",
            "build_profile_id",
            "dependency_digest",
        )
    }
    encoded = json.dumps(
        {
            "view": binding,
            "records": {key: [dict(row) for row in value] for key, value in records.items()},
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
