"""Copy confirmed Run objects into Project-scoped immutable staging files."""

import copy
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_paper_stage import stage_paper
from rpb.adapters.knowledge_paper_tables import object_build_pins, object_lifecycle
from rpb.adapters.knowledge_paper_tables import objects as staged_objects
from rpb.adapters.processing_tables import objects as processing_objects
from rpb.adapters.run_tables import runs
from rpb.modules.account_config.application.ports import AccountError


def validated_locators(segments: Any, text: str, source_kind: str) -> list[dict[str, Any]]:
    if (
        source_kind not in {"full_text", "abstract_fallback"}
        or not isinstance(segments, list)
        or not segments
    ):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    offset, last_page = 0, 0
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {"start_offset", "end_offset", "page"}:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        start, end, page = segment["start_offset"], segment["end_offset"], segment["page"]
        if (
            type(start) is not int
            or type(end) is not int
            or start != offset
            or not start < end <= len(text)
            or (page is not None and (type(page) is not int or page <= 0 or page < last_page))
            or (source_kind == "abstract_fallback" and page is not None)
        ):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        offset = end
        if page is not None:
            last_page = page
    if offset != len(text):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    return copy.deepcopy(segments)


def require_build_protection(
    conn: Any,
    project_id: UUID,
    object_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    epoch: int,
    lease_until: str,
) -> None:
    """Lock the lifecycle record and require this exact construction's durable pin."""
    state = conn.scalar(
        sa.select(object_lifecycle.c.state)
        .where(
            object_lifecycle.c.project_id == project_id,
            object_lifecycle.c.object_id == object_id,
        )
        .with_for_update()
    )
    pin_epoch = conn.scalar(
        sa.select(object_build_pins.c.slot_epoch).where(
            object_build_pins.c.project_id == project_id,
            object_build_pins.c.object_id == object_id,
            object_build_pins.c.run_id == run_id,
            object_build_pins.c.attempt_id == attempt_id,
        )
    )
    if (
        state != "ready"
        or pin_epoch != epoch
        or datetime.fromisoformat(lease_until) <= datetime.now(UTC)
    ):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)


def stage_objects(
    store: Any,
    file_root: Path,
    actor: UUID,
    project_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    candidate_id: UUID,
) -> list[dict[str, str]]:
    """Stage then revalidate before registering; this is not a version pin or proof."""
    files = ImmutableFileStore(file_root)

    def read_inputs(conn: Any) -> tuple[dict[str, str], list[dict[str, Any]]]:
        staged = stage_paper(conn, store, actor, project_id, run_id, attempt_id, candidate_id)
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
        candidate = next(c for c in run["candidates"] if c["id"] == str(candidate_id))
        processing = candidate["processing"]
        basis = processing["basis"]
        if (
            processing["text_source_kind"] == "full_text" and basis["document_asset_id"] is None
        ) or (
            processing["text_source_kind"] == "abstract_fallback"
            and basis["document_asset_id"] is not None
        ):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        source_text = (
            conn.execute(
                sa.select(processing_objects).where(
                    processing_objects.c.id == UUID(basis["text_revision_id"]),
                    processing_objects.c.project_id == project_id,
                    processing_objects.c.run_id == run_id,
                    processing_objects.c.candidate_id == candidate_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if source_text is None or not isinstance(source_text["text"], str):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        text_bytes = source_text["text"].encode()
        if hashlib.sha256(text_bytes).hexdigest() != processing["text_digest"]:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        revision = candidate["analysis_basis"]["analysis_revision"]
        dependencies = copy.deepcopy(run["analysis_lineage"][revision]["dependencies"])
        inputs = [
            {
                "kind": "text",
                "source_revision_id": basis["text_revision_id"],
                "data": text_bytes,
                "locators": validated_locators(
                    processing["segments"], source_text["text"], processing["text_source_kind"]
                ),
                "dependencies": dependencies,
            }
        ]
        if basis["document_asset_id"] is not None:
            source_file = (
                conn.execute(
                    sa.select(processing_objects).where(
                        processing_objects.c.id == UUID(basis["document_asset_id"]),
                        processing_objects.c.project_id == project_id,
                        processing_objects.c.run_id == run_id,
                        processing_objects.c.candidate_id == candidate_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if source_file is None or source_file["file_bytes"] is None:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            file_bytes = bytes(source_file["file_bytes"])
            if hashlib.sha256(file_bytes).hexdigest() != source_file["digest"]:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            inputs.append(
                {
                    "kind": "file",
                    "source_revision_id": basis["file_revision"],
                    "data": file_bytes,
                    "locators": [],
                    "dependencies": dependencies,
                }
            )
        return staged, inputs

    with store.account.engine.begin() as conn:
        staged, inputs = read_inputs(conn)
    prepared = [
        {
            **item,
            "id": uuid5(attempt_id, f"{candidate_id}:{item['kind']}"),
            "sha256": hashlib.sha256(item["data"]).hexdigest(),
        }
        for item in inputs
    ]
    with store.account.engine.begin() as conn:
        current, fresh = read_inputs(conn)
        if current != staged or fresh != inputs:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        result = []
        for item in prepared:
            values = {
                "id": item["id"],
                "project_id": project_id,
                "paper_revision_id": UUID(staged["paper_revision_id"]),
                "attempt_id": attempt_id,
                "kind": item["kind"],
                "source_revision_id": UUID(item["source_revision_id"]),
                "sha256": item["sha256"],
                "size_bytes": len(item["data"]),
                "locators": item["locators"],
                "dependencies": item["dependencies"],
            }
            existing = (
                conn.execute(
                    sa.select(staged_objects).where(
                        staged_objects.c.project_id == project_id, staged_objects.c.id == item["id"]
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is None:
                conn.execute(staged_objects.insert().values(**values))
            elif dict(existing) != values:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            life = (
                conn.execute(
                    sa.select(object_lifecycle)
                    .where(
                        object_lifecycle.c.project_id == project_id,
                        object_lifecycle.c.object_id == item["id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if life is None:
                conn.execute(
                    object_lifecycle.insert().values(project_id=project_id, object_id=item["id"])
                )
            elif life["state"] != "ready":
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
            if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            try:
                if (
                    existing is None
                    and files.write(project_id, attempt_id, item["id"], item["data"])
                    != item["sha256"]
                ):
                    raise ValueError("object mismatch")
                for _ in range(2):
                    if (
                        files.read(project_id, attempt_id, item["id"], item["sha256"])
                        != item["data"]
                    ):
                        raise ValueError("object mismatch")
            except OSError, ValueError:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
            run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
            pin = (
                conn.execute(
                    sa.select(object_build_pins).where(
                        object_build_pins.c.project_id == project_id,
                        object_build_pins.c.object_id == item["id"],
                        object_build_pins.c.run_id == run_id,
                        object_build_pins.c.attempt_id == attempt_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if pin is None:
                conn.execute(
                    object_build_pins.insert().values(
                        project_id=project_id,
                        object_id=item["id"],
                        run_id=run_id,
                        attempt_id=attempt_id,
                        slot_epoch=run["slot_epoch"],
                    )
                )
            elif pin["slot_epoch"] != run["slot_epoch"]:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            result.append(
                {"object_id": str(item["id"]), "kind": item["kind"], "sha256": item["sha256"]}
            )
        if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        return result
