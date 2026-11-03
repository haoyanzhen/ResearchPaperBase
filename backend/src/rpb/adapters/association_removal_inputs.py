"""Read just the evidence that will remain in the newly published version."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest, pinned_revisions
from rpb.adapters.knowledge_build_tables import (
    chunks,
    embeddings,
    graph_labels,
    graph_views,
    profiles,
    publication_events,
    vector_members,
    vector_views,
)
from rpb.adapters.knowledge_chunk_integrity import verify_chunk_closure
from rpb.adapters.knowledge_graph_baseline import current_text_dependencies, metadata_dependency
from rpb.adapters.knowledge_paper_tables import objects, paper_revisions, version_object_pins
from rpb.adapters.knowledge_tables import versions
from rpb.modules.account_config.application.ports import AccountError


def pinned_manifest(conn: Any, project: UUID, base: UUID) -> Any:
    """Verify membership by immutable IDs without opening the papers."""
    row = (
        conn.execute(
            sa.select(versions).where(
                versions.c.project_id == project, versions.c.id == base, versions.c.sealed
            )
        )
        .mappings()
        .one()
    )
    manifest = row["manifest"]
    pins = set(
        conn.execute(
            pinned_revisions(project, base).with_only_columns(
                paper_revisions.c.project_paper_id, paper_revisions.c.id
            )
        )
    )
    members = {
        (UUID(p["project_paper_id"]), UUID(p["paper_revision_id"])) for p in manifest["papers"]
    }
    if (
        manifest.get("materials") != []
        or pins != members
        or len(members) != len(manifest["papers"])
        or len({p for p, r in members}) != len(members)
        or content_digest(manifest) != row["manifest_digest"]
        or row["manifest_digest"] != row["ready_proof"]["manifest_digest"]
    ):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    return row


@dataclass
class RemainingEvidence:
    papers: list[Any]
    profile: Any
    graph: UUID
    members: dict[UUID, UUID] = field(default_factory=dict)
    fragments: dict[UUID, str] = field(default_factory=dict)
    digests: dict[str, str] = field(default_factory=dict)
    stamps: dict[str, Any] = field(default_factory=dict)
    text_dependencies: dict[str, Any] = field(default_factory=dict)
    metadata_dependencies: dict[str, Any] = field(default_factory=dict)


def read_remaining(
    conn: Any,
    files: ImmutableFileStore,
    project: Any,
    actor: UUID,
    state: Any,
    record: Any,
    removed: set[tuple[str, str]],
) -> RemainingEvidence:
    pid = project["id"]
    manifest, proof = record["manifest"], record["ready_proof"]
    fail = AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    # The event and sealed, immutable view headers attest the source views. Verify the
    # selected subset from its evidence below, without opening any excluded paper bytes.
    vid, gid = UUID(manifest["vector_view_id"]), UUID(manifest["graph_view_id"])
    profile = manifest["build_profile"]
    binding = (
        conn.execute(
            sa.select(publication_events).where(
                publication_events.c.project_id == pid,
                publication_events.c.version_id == record["id"],
            )
        )
        .mappings()
        .one()
    )
    if (
        binding["vector_view_id"] != vid
        or binding["graph_view_id"] != gid
        or binding["embedding_profile_id"] != profile["embedding_profile_id"]
        or conn.scalar(
            sa.select(profiles.c.body).where(profiles.c.id == binding["embedding_profile_id"])
        )
        != profile["embedding"]
    ):
        raise fail
    for table, view, digest in (
        (graph_views, gid, manifest["graph_digest"]),
        (vector_views, vid, manifest["vector_digest"]),
    ):
        if not conn.scalar(
            sa.select(table.c.id).where(
                table.c.project_id == pid,
                table.c.id == view,
                table.c.sealed,
                table.c.run_id == record["source_run_id"],
                table.c.digest == digest,
                table.c.build_profile_id == content_digest(profile),
            )
        ):
            raise fail
    witnessed = proof.get("source_dependency_digests")

    def require_witness(kind: str, key: str, dependency: Any, legacy: Any) -> None:
        if witnessed is None:
            if dependency != legacy:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
        elif witnessed[kind].get(key) != content_digest(dependency):
            raise AccountError("STATE_REVISION_CONFLICT", 409)

    keep = [
        p
        for p in manifest["papers"]
        if (p["project_paper_id"], p["paper_revision_id"]) not in removed
    ]
    result = RemainingEvidence(keep, profile, gid)
    revisions = {UUID(p["paper_revision_id"]): p for p in keep}
    chunk_rows: dict[UUID, list[Any]] = defaultdict(list)
    for chunk in conn.execute(
        sa.select(chunks, embeddings.c.id.label("embedding_id"))
        .select_from(
            vector_members.join(embeddings, vector_members.c.embedding_id == embeddings.c.id).join(
                chunks, chunks.c.id == embeddings.c.chunk_id
            )
        )
        .where(
            vector_members.c.project_id == pid,
            vector_members.c.view_id == vid,
            chunks.c.asset_revision.in_(revisions),
        )
    ).mappings():
        if str(chunk["asset_id"]) != revisions[chunk["asset_revision"]]["project_paper_id"]:
            raise fail
        result.members[chunk["id"]] = chunk["embedding_id"]
        chunk_rows[chunk["text_revision_id"]].append(chunk)
    for rid, member in revisions.items():
        # Determine current permission before reading metadata or protected files.
        candidate_id = conn.scalar(
            sa.select(paper_revisions.c.candidate_id).where(
                paper_revisions.c.project_id == pid, paper_revisions.c.id == rid
            )
        )
        cid = str(candidate_id)
        result.metadata_dependencies[cid] = metadata_dependency(state, actor, project, cid)
        legacy_metadata = None
        if witnessed is None:
            legacy_metadata = conn.scalar(
                sa.select(graph_labels.c.dependencies)
                .where(
                    graph_labels.c.project_id == pid,
                    graph_labels.c.view_id == gid,
                    graph_labels.c.source["asset_revision"].astext == str(rid),
                    graph_labels.c.source["field"].astext == "title",
                )
                .limit(1)
            )
        require_witness("metadata", cid, result.metadata_dependencies[cid], legacy_metadata)
        content = conn.scalar(
            sa.select(paper_revisions.c.content).where(
                paper_revisions.c.project_id == pid, paper_revisions.c.id == rid
            )
        )
        if content_digest(content) != member["digest"]:
            raise fail
        source_kind = content["processing"]["text_source_kind"]
        if set(member["objects"]) != ({"file", "text"} if source_kind == "full_text" else {"text"}):
            raise fail
        for kind, oid in member["objects"].items():
            obj = (
                conn.execute(
                    sa.select(objects)
                    .join(version_object_pins, objects.c.id == version_object_pins.c.object_id)
                    .where(
                        version_object_pins.c.project_id == pid,
                        version_object_pins.c.version_id == record["id"],
                        objects.c.id == UUID(oid),
                        objects.c.paper_revision_id == rid,
                        objects.c.kind == kind,
                        objects.c.project_id == pid,
                    )
                )
                .mappings()
                .one()
            )
            lineage = obj["dependencies"]
            if (
                not lineage["source_ids"]
                or set(lineage["source_ids"]) != set(lineage["source_revisions"])
                or obj["sha256"] != proof["object_digests"][oid]
            ):
                raise fail
            dependencies = current_text_dependencies(
                state, actor, project, lineage["source_revisions"]
            )
            for sid, dependency in dependencies.items():
                # Older versions have no per-source witness. Matching the immutable analysis
                # commit audit proves its monotonically revised permissions have not changed.
                legacy = None
                if witnessed is None:
                    for entry in lineage.get("material_audit", []):
                        if (
                            entry["boundary"] == "commit"
                            and entry["source"]["source_id"] == sid
                            and entry.get("permitted") is True
                        ):
                            legacy = {
                                k: entry[k]
                                for k in ("source", "classification_revision", "policy_revision")
                            }
                require_witness("text", sid, dependency, legacy)
            result.text_dependencies.update(dependencies)
            stamp = files.stamp(pid, obj["attempt_id"], obj["id"])
            data = files.read(pid, obj["attempt_id"], obj["id"], obj["sha256"])
            if (
                len(data) != obj["size_bytes"]
                or files.stamp(pid, obj["attempt_id"], obj["id"]) != stamp
            ):
                raise fail
            result.stamps[oid] = (obj["attempt_id"], stamp)
            result.digests[oid] = obj["sha256"]
            if kind == "text":
                text = data.decode()
                group = chunk_rows[obj["id"]]
                verify_chunk_closure(text, obj, source_kind, group)
                result.fragments.update(
                    {c["id"]: text[c["start_offset"] : c["end_offset"]] for c in group}
                )
    if result.members.keys() != result.fragments.keys():
        raise fail
    return result
