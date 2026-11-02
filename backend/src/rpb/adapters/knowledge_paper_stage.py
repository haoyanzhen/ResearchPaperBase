"""Stage one confirmed Project paper under the current Construction write fence."""

import copy
import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.analysis_lineage import currently_usable
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.construction_slots import is_current
from rpb.adapters.knowledge_baseline_papers import content_digest, pinned_revisions
from rpb.adapters.knowledge_paper_tables import (
    paper_identities,
    paper_identity_titles,
    paper_revisions,
    project_papers,
    version_paper_pins,
)
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.processing_tables import objects
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.search_terms import load
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.domain.paper_identity import normalized_paper_title
from rpb.modules.construction.domain.runs import RunInputError


def stage_paper(
    conn: Any,
    store: Any,
    actor: UUID,
    project_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    candidate_id: UUID,
) -> dict[str, str]:
    """Caller supplies an authenticated transaction; this does not publish a version."""
    from rpb.adapters.runs import persist

    conn.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK})
    project = store.terms.project(conn, actor, project_id, write=True)
    conn.execute(sa.select(slots).where(slots.c.project_id == project_id).with_for_update()).first()
    row = (
        conn.execute(
            sa.select(runs)
            .where(
                runs.c.id == run_id,
                runs.c.project_id == project_id,
                runs.c.owner_id == actor,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    run = copy.deepcopy(row["payload"])
    confirmation = run.get("ingestion_confirmation") or {}
    if (
        not store.terms.llm.permitted_actor(conn, actor)
        or project["authority_epoch"] != run["authority_epoch"]
        or run["status"] != "running"
        or run.get("phase") != "knowledge_build"
        or run["attempt_id"] != str(attempt_id)
        or datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC)
        or confirmation.get("attempt_id") != str(attempt_id)
        or confirmation.get("candidate_revision") != run["candidate_revision"]
        or confirmation.get("input_revision") != run["effective_input_revision"]
        or confirmation.get("input_snapshot") != run["input_snapshot"]
        or confirmation.get("config_snapshot") != run["config_snapshot"]
        or confirmation.get("model_config") != run["model_config"]
        or confirmation.get("source_configs") != run["source_configs"]
        or confirmation.get("candidate_snapshot") != run["candidates"]
        or (run.get("candidate_version") or {}).get("content_locked") is not True
        or not is_current(conn, run)
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    latest = conn.scalar(sa.select(heads.c.version_id).where(heads.c.project_id == project_id))
    if (run["input_snapshot"].get("base_knowledge_version_id")) != (
        str(latest) if latest else None
    ):
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    candidate = next((c for c in run["candidates"] if c["id"] == str(candidate_id)), None)
    if candidate is None or str(candidate_id) not in confirmation["preview"]["valid_papers"]:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if not currently_usable(run, candidate, load(conn, project), project, actor):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    processing = candidate["processing"]
    text = (
        conn.execute(
            sa.select(objects).where(
                objects.c.id == UUID(processing["basis"]["text_revision_id"]),
                objects.c.project_id == project_id,
                objects.c.run_id == run_id,
                objects.c.candidate_id == candidate_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        not text
        or not text["text"]
        or hashlib.sha256(text["text"].encode()).hexdigest() != processing["text_digest"]
    ):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    try:
        title_key = normalized_paper_title(candidate["metadata"]["title"])
    except KeyError, RunInputError:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409) from None
    existing = (
        conn.execute(
            sa.select(paper_revisions).where(
                paper_revisions.c.project_id == project_id,
                paper_revisions.c.run_id == run_id,
                paper_revisions.c.candidate_id == candidate_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    content = {
        "metadata": copy.deepcopy(candidate["metadata"]),
        "screening": copy.deepcopy(candidate["screening"]),
        "analysis": copy.deepcopy(candidate["analysis"]),
        "analysis_revision": candidate["analysis_basis"]["analysis_revision"],
        "analysis_lineage": copy.deepcopy(
            run["analysis_lineage"][candidate["analysis_basis"]["analysis_revision"]]
        ),
        "processing": copy.deepcopy(processing),
        "source": copy.deepcopy(candidate["source"]),
    }
    digest = content_digest(content)
    published_identities = (
        sa.select(paper_identity_titles.c.identity_id)
        .distinct()
        .select_from(
            paper_identity_titles.join(
                paper_identities, paper_identities.c.id == paper_identity_titles.c.identity_id
            )
            .join(
                project_papers,
                project_papers.c.identity_id == paper_identity_titles.c.identity_id,
            )
            .join(
                paper_revisions,
                sa.and_(
                    paper_revisions.c.project_id == project_papers.c.project_id,
                    paper_revisions.c.project_paper_id == project_papers.c.id,
                ),
            )
            .join(
                version_paper_pins,
                sa.and_(
                    version_paper_pins.c.project_id == paper_revisions.c.project_id,
                    version_paper_pins.c.paper_revision_id == paper_revisions.c.id,
                ),
            )
            .join(
                versions,
                sa.and_(
                    versions.c.project_id == version_paper_pins.c.project_id,
                    versions.c.id == version_paper_pins.c.version_id,
                ),
            )
        )
        .where(
            paper_identity_titles.c.normalized_title == title_key,
            versions.c.sealed.is_(True),
        )
    )
    identities = list(
        conn.scalars(published_identities.where(paper_identities.c.unresolved_project_id.is_(None)))
    )
    own_identities = list(
        conn.scalars(published_identities.where(project_papers.c.project_id == project_id))
    )
    distinct = candidate["deduplication"].get("baseline_resolution") == "distinct"
    # A current-Run distinct decision does not decide against removed history.
    # Reimport needs separate confirmation, which this command cannot yet supply.
    own_papers = (
        set(
            conn.scalars(
                sa.select(project_papers.c.id).where(
                    project_papers.c.project_id == project_id,
                    project_papers.c.identity_id.in_(own_identities),
                )
            )
        )
        if own_identities
        else set()
    )
    # The baseline is immutable. Staging needs its pinned IDs, not the full paper contents.
    retained = []
    if latest is not None:
        pinned = (
            pinned_revisions(project_id, latest)
            .with_only_columns(paper_revisions.c.project_paper_id, paper_revisions.c.id)
            .order_by(paper_revisions.c.project_paper_id)
        )
        retained = [
            {"project_paper_id": str(asset), "paper_revision_id": str(revision)}
            for asset, revision in conn.execute(pinned)
        ]
    # First-version attempts accepted before retained membership was recorded have no base.
    if retained != confirmation.get("retained_papers", [] if latest is None else None):
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    active_papers = {UUID(item["project_paper_id"]) for item in retained}
    if own_papers - active_papers or (own_papers and not distinct):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    unresolved = not distinct and not own_identities and len(identities) > 1
    if existing:
        if existing["digest"] != digest or existing["content"] != content:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        saved = conn.execute(
            sa.select(project_papers.c.identity_id, paper_identities.c.unresolved_project_id)
            .join(paper_identities, paper_identities.c.id == project_papers.c.identity_id)
            .where(
                project_papers.c.project_id == project_id,
                project_papers.c.id == existing["project_paper_id"],
            )
        ).one()
        if bool(saved.unresolved_project_id) != unresolved or (
            not distinct and len(identities) == 1 and saved.identity_id != identities[0]
        ):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        return {
            "project_paper_id": str(existing["project_paper_id"]),
            "paper_revision_id": str(existing["id"]),
        }
    create_identity = distinct or (not own_identities and (not identities or unresolved))
    identity = (
        uuid4() if create_identity else own_identities[0] if own_identities else identities[0]
    )
    if create_identity:
        conn.execute(
            paper_identities.insert().values(
                id=identity, unresolved_project_id=project_id if unresolved else None
            )
        )
        conn.execute(
            paper_identity_titles.insert().values(identity_id=identity, normalized_title=title_key)
        )
    project_paper = conn.scalar(
        sa.select(project_papers.c.id).where(
            project_papers.c.project_id == project_id,
            project_papers.c.identity_id == identity,
        )
    )
    if project_paper in active_papers:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    if project_paper is None:
        project_paper = uuid4()
        conn.execute(
            project_papers.insert().values(
                id=project_paper, project_id=project_id, identity_id=identity
            )
        )
    revision = uuid4()
    conn.execute(
        paper_revisions.insert().values(
            id=revision,
            project_id=project_id,
            project_paper_id=project_paper,
            run_id=run_id,
            candidate_id=candidate_id,
            content=content,
            digest=digest,
        )
    )
    result = {"project_paper_id": str(project_paper), "paper_revision_id": str(revision)}
    run.setdefault("paper_stage", {})[str(candidate_id)] = result
    persist(conn, run)
    return result
