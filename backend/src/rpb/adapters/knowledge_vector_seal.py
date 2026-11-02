"""Seal a vector view against a caller-supplied, already frozen chunk set.

This is an integrity primitive, not publication authorization or a ready proof.
The caller must validate the frozen set and all permissions in its transaction.
"""

import hashlib
import json
import struct
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.knowledge_build_tables import chunks, embeddings, vector_members, vector_views


class VectorViewIncomplete(ValueError):
    pass


def seal_vector_view(conn: Any, project_id: UUID, view_id: UUID, expected_chunks: set[UUID]) -> str:
    view = (
        conn.execute(
            sa.select(vector_views)
            .where(vector_views.c.project_id == project_id, vector_views.c.id == view_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if view is None or view["sealed"]:
        raise VectorViewIncomplete("view unavailable")
    result = _digest(conn, project_id, view_id, expected_chunks, view)
    conn.execute(
        vector_views.update().where(vector_views.c.id == view_id).values(sealed=True, digest=result)
    )
    return result


def verify_vector_view(
    conn: Any, project_id: UUID, view_id: UUID, expected_chunks: set[UUID]
) -> str:
    view = (
        conn.execute(
            sa.select(vector_views)
            .where(vector_views.c.project_id == project_id, vector_views.c.id == view_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if view is None or not view["sealed"]:
        raise VectorViewIncomplete("sealed view unavailable")
    digest = _digest(conn, project_id, view_id, expected_chunks, view)
    if digest != view["digest"]:
        raise VectorViewIncomplete("sealed view digest mismatch")
    return digest


def _digest(
    conn: Any, project_id: UUID, view_id: UUID, expected_chunks: set[UUID], view: Any
) -> str:
    member_count = conn.scalar(
        sa.select(sa.func.count())
        .select_from(vector_members)
        .where(vector_members.c.project_id == project_id, vector_members.c.view_id == view_id)
    )
    rows = list(
        conn.execute(
            sa.select(
                embeddings.c.id, embeddings.c.chunk_id, embeddings.c.embedding, chunks.c.text_digest
            )
            .select_from(
                vector_members.join(
                    embeddings,
                    sa.and_(
                        vector_members.c.project_id == embeddings.c.project_id,
                        vector_members.c.embedding_id == embeddings.c.id,
                        vector_members.c.profile_id == embeddings.c.profile_id,
                    ),
                ).join(
                    chunks,
                    sa.and_(
                        chunks.c.project_id == embeddings.c.project_id,
                        chunks.c.id == embeddings.c.chunk_id,
                    ),
                )
            )
            .where(vector_members.c.project_id == project_id, vector_members.c.view_id == view_id)
            .order_by(embeddings.c.chunk_id)
        ).mappings()
    )
    if (
        len(rows) != member_count
        or len(rows) != len(expected_chunks)
        or {row["chunk_id"] for row in rows} != expected_chunks
    ):
        raise VectorViewIncomplete("vector membership differs from frozen chunks")
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
            "profile_id",
        )
    }
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode())
    for row in rows:
        digest.update(row["chunk_id"].bytes)
        digest.update(row["id"].bytes)
        digest.update(bytes.fromhex(row["text_digest"]))
        digest.update(struct.pack("!768f", *row["embedding"]))
    return digest.hexdigest()
