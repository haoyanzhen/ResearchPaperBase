"""Read reusable vector members from the exact published, pinned paper baseline."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import (
    chunks,
    embeddings,
    publication_events,
    vector_members,
    vector_views,
)
from rpb.adapters.knowledge_paper_tables import objects, version_object_pins
from rpb.adapters.knowledge_tables import versions
from rpb.adapters.knowledge_vector_seal import verify_vector_view
from rpb.modules.account_config.application.ports import AccountError


@dataclass
class BaselineVectors:
    profile: dict[str, Any]
    members: dict[UUID, UUID]  # chunk -> embedding
    source_revisions: dict[str, str]
    dependency_digest: str
    view_id: UUID
    view_digest: str
    texts: dict[UUID, tuple[UUID, str]]

    def verify_artifacts(self, conn: Any, files: ImmutableFileStore, project: UUID) -> None:
        try:
            for text_id, (attempt, digest) in self.texts.items():
                files.read(project, attempt, text_id, digest)
            digest = verify_vector_view(conn, project, self.view_id, set(self.members))
        except OSError, ValueError:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
        if digest != self.view_digest:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)


def read_baseline_vectors(
    conn: Any,
    project: UUID,
    version: UUID,
    retained: list[Any],
) -> BaselineVectors:
    unavailable = AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    # The permanent publication event pins the exact version/view/profile binding.
    row = conn.execute(
        sa.select(
            versions.c.manifest,
            versions.c.manifest_digest,
            versions.c.ready_proof,
            versions.c.source_run_id,
            vector_views.c.run_id,
            vector_views.c.attempt_id,
            vector_views.c.id,
            vector_views.c.build_profile_id,
            vector_views.c.dependency_digest,
        )
        .select_from(
            versions.join(
                publication_events,
                sa.and_(
                    publication_events.c.project_id == versions.c.project_id,
                    publication_events.c.version_id == versions.c.id,
                ),
            ).join(
                vector_views,
                sa.and_(
                    vector_views.c.project_id == publication_events.c.project_id,
                    vector_views.c.id == publication_events.c.vector_view_id,
                    vector_views.c.profile_id == publication_events.c.embedding_profile_id,
                ),
            )
        )
        .where(versions.c.project_id == project, versions.c.id == version, versions.c.sealed)
    ).one_or_none()
    if row is None:
        raise unavailable
    manifest, proof = row.manifest, row.ready_proof
    if (
        content_digest(manifest) != row.manifest_digest
        or row.run_id != row.source_run_id
        or proof["project_id"] != str(project)
        or proof["run_id"] != str(row.run_id)
        or proof["attempt_id"] != str(row.attempt_id)
        or proof["manifest_digest"] != row.manifest_digest
        or manifest["vector_view_id"] != str(row.id)
        or proof["vector_view_id"] != str(row.id)
        or content_digest(manifest["build_profile"]) != row.build_profile_id
        or row.build_profile_id != proof["build_profile_id"]
    ):
        raise unavailable
    targets = {
        (p["project_paper_id"], p["paper_revision_id"]): p["objects"]["text"]
        for p in manifest["papers"]
    }
    if set(targets) != {(p["project_paper_id"], p["paper_revision_id"]) for p in retained}:
        raise unavailable
    rows = conn.execute(
        sa.select(chunks, embeddings.c.id.label("embedding_id"))
        .select_from(
            vector_members.join(embeddings, vector_members.c.embedding_id == embeddings.c.id).join(
                chunks, embeddings.c.chunk_id == chunks.c.id
            )
        )
        .where(vector_members.c.project_id == project, vector_members.c.view_id == row.id)
    ).mappings()
    members = {}
    texts = {}
    source_revisions: dict[str, str] = {}
    objects_by_id = {
        obj["id"]: obj
        for obj in conn.execute(
            sa.select(objects)
            .join(version_object_pins, version_object_pins.c.object_id == objects.c.id)
            .where(
                version_object_pins.c.project_id == project,
                version_object_pins.c.version_id == version,
                objects.c.project_id == project,
                objects.c.kind == "text",
            )
        ).mappings()
    }
    for chunk in rows:
        text_id = chunk["text_revision_id"]
        obj = objects_by_id.get(text_id)
        if (
            obj is None
            or obj["paper_revision_id"] != chunk["asset_revision"]
            or targets.get((str(chunk["asset_id"]), str(chunk["asset_revision"]))) != str(text_id)
            or obj["dependencies"] != chunk["dependencies"]
            or proof["object_digests"].get(str(text_id)) != obj["sha256"]
        ):
            raise unavailable
        if text_id not in texts:
            lineage = obj["dependencies"]
            if not lineage["source_ids"] or set(lineage["source_ids"]) != set(
                lineage["source_revisions"]
            ):
                raise unavailable
            for sid, revision in lineage["source_revisions"].items():
                if source_revisions.setdefault(sid, revision) != revision:
                    raise unavailable
            texts[text_id] = (obj["attempt_id"], obj["sha256"])
        members[chunk["id"]] = chunk["embedding_id"]
    if (
        {str(t) for t in texts} != set(targets.values())
        or len(members) != proof["counts"]["chunks"]
        or len(members) != proof["counts"]["vectors"]
    ):
        raise unavailable
    return BaselineVectors(
        manifest["build_profile"],
        members,
        source_revisions,
        row.dependency_digest,
        row.id,
        manifest["vector_digest"],
        texts,
    )
