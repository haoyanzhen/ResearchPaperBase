"""Resolve paper titles only from the Run's immutable Project baseline."""

import hashlib
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.knowledge_paper_tables import paper_revisions, version_paper_pins
from rpb.adapters.knowledge_tables import versions
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.paper_identity import normalized_paper_title
from rpb.modules.construction.domain.runs import RunInputError


def content_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def baseline_papers(conn: Any, run: Any) -> list[dict[str, str]]:
    snapshot = run.get("input_snapshot")
    if not isinstance(snapshot, dict) or "base_knowledge_version_id" not in snapshot:
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    baseline = snapshot["base_knowledge_version_id"]
    if baseline is None:
        return []
    try:
        project_id, version_id = UUID(run["project_id"]), UUID(baseline)
        version = (
            conn.execute(
                sa.select(versions).where(
                    versions.c.project_id == project_id,
                    versions.c.id == version_id,
                    versions.c.sealed.is_(True),
                )
            )
            .mappings()
            .one_or_none()
        )
        if version is None:
            raise ValueError("baseline unavailable")
        manifest = version["manifest"]
        if not isinstance(manifest, dict) or not isinstance(manifest.get("papers"), list):
            raise ValueError("baseline manifest unavailable")
        if content_digest(manifest) != version["manifest_digest"]:
            raise ValueError("baseline manifest digest mismatch")
        entries = manifest["papers"]
        expected = {(UUID(x["project_paper_id"]), UUID(x["paper_revision_id"])) for x in entries}
        if len(expected) != len(entries) or len({x[0] for x in expected}) != len(expected):
            raise ValueError("duplicate baseline membership")
        rows = list(
            conn.execute(
                sa.select(paper_revisions)
                .select_from(
                    version_paper_pins.join(
                        paper_revisions,
                        sa.and_(
                            version_paper_pins.c.project_id == paper_revisions.c.project_id,
                            version_paper_pins.c.paper_revision_id == paper_revisions.c.id,
                        ),
                    )
                )
                .where(
                    version_paper_pins.c.project_id == project_id,
                    version_paper_pins.c.version_id == version_id,
                )
            ).mappings()
        )
        count = conn.scalar(
            sa.select(sa.func.count())
            .select_from(version_paper_pins)
            .where(
                version_paper_pins.c.project_id == project_id,
                version_paper_pins.c.version_id == version_id,
            )
        )
        if len(rows) != count or {(x["project_paper_id"], x["id"]) for x in rows} != expected:
            raise ValueError("baseline membership mismatch")
        if any(content_digest(row["content"]) != row["digest"] for row in rows):
            raise ValueError("baseline paper digest mismatch")
        return sorted(
            [
                {
                    "project_paper_id": str(row["project_paper_id"]),
                    "paper_revision_id": str(row["id"]),
                    "normalized_title": normalized_paper_title(row["content"]["metadata"]["title"]),
                }
                for row in rows
            ],
            key=lambda item: item["project_paper_id"],
        )
    except AttributeError, KeyError, TypeError, ValueError, RunInputError:
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
