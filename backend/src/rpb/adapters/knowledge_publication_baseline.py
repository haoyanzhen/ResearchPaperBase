"""Validate the retained manifest and its permanent references before extending it."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import baseline_papers, content_digest, pinned_revisions
from rpb.adapters.knowledge_graph_baseline import current_text_dependencies, metadata_dependency
from rpb.adapters.knowledge_paper_tables import objects, paper_revisions, version_object_pins
from rpb.adapters.knowledge_tables import heads, versions
from rpb.modules.account_config.application.ports import AccountError


@dataclass
class RetainedInputs:
    file_stamps: dict[str, Any] = field(default_factory=dict)
    papers: list[Any] = field(default_factory=list)
    digests: dict[str, str] = field(default_factory=dict)
    text_dependencies: dict[str, Any] = field(default_factory=dict)
    metadata_dependencies: dict[str, Any] = field(default_factory=dict)

    @property
    def dependency_digest(self) -> str:
        return content_digest(
            {"text": self.text_dependencies, "metadata": self.metadata_dependencies}
        )


def checked_base(conn: Any, project: UUID, run: Any) -> UUID | None:
    version: UUID | None = conn.scalar(
        sa.select(heads.c.version_id).where(heads.c.project_id == project)
    )
    if run["input_snapshot"]["base_knowledge_version_id"] != (str(version) if version else None):
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    return version


def retained_inputs(
    conn: Any,
    project: Any,
    actor: UUID,
    state: Any,
    version: UUID | None,
    run: Any,
    files: ImmutableFileStore | None = None,
    *,
    capture_stamps: bool = False,
) -> RetainedInputs:
    retained = RetainedInputs()
    if version is None:
        return retained
    project_id = project["id"]
    record = conn.execute(
        sa.select(versions.c.manifest, versions.c.manifest_digest, versions.c.ready_proof).where(
            versions.c.project_id == project_id, versions.c.id == version, versions.c.sealed
        )
    ).one()
    unavailable = AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    if (
        content_digest(record.manifest) != record.manifest_digest
        or record.ready_proof["manifest_digest"] != record.manifest_digest
    ):
        raise unavailable
    retained.papers = record.manifest["papers"]
    pinned = {
        str(row.id): row
        for row in conn.execute(
            pinned_revisions(project_id, version).with_only_columns(
                paper_revisions.c.id,
                paper_revisions.c.project_paper_id,
                paper_revisions.c.candidate_id,
                paper_revisions.c.digest,
                paper_revisions.c.content["processing"]["text_source_kind"].astext.label("kind"),
            )
        )
    }
    actual = {
        row["id"]: row
        for row in conn.execute(
            sa.select(objects)
            .join(version_object_pins, version_object_pins.c.object_id == objects.c.id)
            .where(
                objects.c.project_id == project_id,
                version_object_pins.c.project_id == project_id,
                version_object_pins.c.version_id == version,
            )
        ).mappings()
    }
    confirmed = run["ingestion_confirmation"]["retained_papers"]
    pairs = {(p["project_paper_id"], p["paper_revision_id"]) for p in retained.papers}
    if (
        pairs != {(str(r.project_paper_id), str(r.id)) for r in pinned.values()}
        or pairs != {(p["project_paper_id"], p["paper_revision_id"]) for p in confirmed}
        or len(pairs) != len(retained.papers)
    ):
        raise unavailable
    source_revisions: dict[str, str] = {}
    for member in retained.papers:
        paper = pinned[member["paper_revision_id"]]
        cid = str(paper.candidate_id)
        retained.metadata_dependencies[cid] = metadata_dependency(state, actor, project, cid)
        expected = {"text", "file"} if paper.kind == "full_text" else {"text"}
        refs = member["objects"]
        if (
            paper.kind not in {"full_text", "abstract_fallback"}
            or member["digest"] != paper.digest
            or set(refs) != expected
        ):
            raise unavailable
        for kind, oid in refs.items():
            row = actual.get(UUID(oid))
            if (
                row is None
                or row["kind"] != kind
                or row["paper_revision_id"] != paper.id
                or oid in retained.digests
            ):
                raise unavailable
            lineage = row["dependencies"]
            if not lineage["source_ids"] or set(lineage["source_ids"]) != set(
                lineage["source_revisions"]
            ):
                raise unavailable
            for sid, revision in lineage["source_revisions"].items():
                if source_revisions.setdefault(sid, revision) != revision:
                    raise unavailable
            retained.digests[oid] = row["sha256"]
    retained.text_dependencies = current_text_dependencies(state, actor, project, source_revisions)
    if retained.digests != record.ready_proof["object_digests"] or len(actual) != len(
        retained.digests
    ):
        raise unavailable
    digest = retained.dependency_digest
    if run["input_snapshot"].get("graph_mode") == "rebuild":
        confirmed_digest = run["ingestion_confirmation"].get("rebuild_dependency_digest")
        if confirmed_digest is not None and digest != confirmed_digest:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
    elif digest != record.ready_proof["dependency_set_digest"]:
        raise unavailable
    if files is not None:
        # Rehash the persisted paper contents after validating all source permissions.
        baseline_papers(conn, run, papers_only=True)
        for oid, row in actual.items():
            try:
                stamp = files.stamp(project_id, row["attempt_id"], oid) if capture_stamps else None
                data = files.read(project_id, row["attempt_id"], oid, row["sha256"])
                if stamp is not None:
                    if files.stamp(project_id, row["attempt_id"], oid) != stamp:
                        raise unavailable
                    retained.file_stamps[str(oid)] = [str(row["attempt_id"]), stamp]
            except OSError, ValueError:
                raise unavailable from None
            if len(data) != row["size_bytes"]:
                raise unavailable
    return retained
