"""Verify a fully matched paper retrieval against its published version and close its Run."""

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters import ingestion_preview
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.baseline_match_preview import match_scope_digest, matched_baseline_scope
from rpb.adapters.construction_slots import is_current
from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_failure import require_publication_claim
from rpb.adapters.knowledge_build_tables import profiles
from rpb.adapters.knowledge_graph_baseline import read_baseline_graph
from rpb.adapters.knowledge_publication_baseline import retained_inputs
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.knowledge_vector_baseline import read_baseline_vectors
from rpb.adapters.knowledge_vector_builder import vector_build_profile
from rpb.adapters.knowledge_vector_seal import verify_vector_view
from rpb.adapters.local_embeddings import valid_profile
from rpb.adapters.run_tables import runs
from rpb.adapters.runs import persist, transition
from rpb.adapters.search_terms import load, now
from rpb.modules.account_config.application.ports import AccountError


def _locked_run(
    conn: Any, store: Any, actor: UUID, project: UUID, run_id: UUID, attempt: UUID
) -> tuple[Any, Any]:
    conn.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK})
    if not store.terms.llm.permitted_actor(conn, actor):
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    proj = store.terms.project(conn, actor, project)
    run = conn.scalar(
        sa.select(runs.c.payload)
        .where(runs.c.project_id == project, runs.c.id == run_id, runs.c.owner_id == actor)
        .with_for_update()
    )
    if not run or run["attempt_id"] != str(attempt):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    return proj, run


def _check(conn: Any, proj: Any, run: Any, claim: str, candidate_state: str) -> UUID:
    require_publication_claim(run, claim)
    confirmation = run["ingestion_confirmation"]
    decision = run["matched_screening"]
    candidate = run["candidate_version"]
    if (
        run["status"] != "running"
        or run["phase"] != "knowledge_build"
        or run["authority_epoch"] != proj["authority_epoch"]
        or proj["status"] != "active"
        or candidate.get("content_locked") is not True
        or candidate["state"] != candidate_state
        or candidate["revision"] != run["candidate_revision"]
        or confirmation["attempt_id"] != run["attempt_id"]
        or confirmation["actor_id"] != run["owner_id"]
        or confirmation["input_revision"] != run["effective_input_revision"]
        or confirmation["candidate_revision"] != run["candidate_revision"]
        or confirmation["input_snapshot"] != run["input_snapshot"]
        or confirmation["config_snapshot"] != run["config_snapshot"]
        or confirmation["model_config"] != run["model_config"]
        or confirmation["source_configs"] != run["source_configs"]
        or confirmation["candidate_snapshot"] != run["candidates"]
        or confirmation["acknowledged_risk_ids"] != []
        or confirmation["preview"]
        != ingestion_preview.preview(
            run | {"phase": "ingestion_preview", "status": "waiting_user"}, None
        )
        or confirmation["preview"]["valid_papers"]
        or confirmation["preview"]["failed"]
        or decision["actor_id"] != run["owner_id"]
        or decision["candidate_revision"] != run["candidate_revision"]
        or confirmation["verify_existing"] != decision["digest"]
        or decision["digest"] != match_scope_digest(run, decision["scope"])
        or decision["scope"] != matched_baseline_scope(conn, run)
        or not is_current(conn, run)
        or datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC)
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    base: UUID | None = conn.scalar(
        sa.select(heads.c.version_id).where(heads.c.project_id == proj["id"]).with_for_update()
    )
    if base is None or str(base) != run["input_snapshot"]["base_knowledge_version_id"]:
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    return base


def prepare_no_change(
    store: Any,
    root: Path,
    actor: UUID,
    project: UUID,
    identity: UUID,
    attempt: UUID,
    claim: str,
    embedding: Any,
) -> str:
    args = store, actor, project, identity, attempt

    @contextmanager
    def permit() -> Any:
        with store.account.engine.begin() as conn:
            proj, run = _locked_run(conn, *args)
            _check(conn, proj, run, claim, "preparing")
            yield

    with permit():
        pass
    with embedding(permit) as port:
        embedding_profile = port.profile
        if not valid_profile(embedding_profile):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
    files = ImmutableFileStore(root)
    with store.account.engine.begin() as conn:
        proj, run = _locked_run(conn, *args)
        base = _check(conn, proj, run, claim, "preparing")
        state = load(conn, proj)
        inherited = retained_inputs(conn, proj, actor, state, base, run, files, capture_stamps=True)
        vector = read_baseline_vectors(
            conn, project, base, run["ingestion_confirmation"]["retained_papers"]
        )
        if vector.profile != vector_build_profile(run, embedding_profile):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        if (
            conn.scalar(
                sa.select(profiles.c.body).where(profiles.c.id == embedding_profile["profile_id"])
            )
            != embedding_profile
        ):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        # retained_inputs has already read and hashed every permanently pinned file.
        if (
            verify_vector_view(conn, project, vector.view_id, set(vector.members))
            != vector.view_digest
        ):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        graph = read_baseline_graph(
            conn,
            files,
            proj,
            actor,
            state,
            run,
            content_digest(vector.profile),
            verify_locators=True,
        )
        record = conn.execute(
            sa.select(versions.c.manifest_digest, versions.c.ready_proof).where(
                versions.c.id == base, versions.c.project_id == project, versions.c.sealed
            )
        ).one()
        counts = record.ready_proof["counts"]
        expected = {
            "papers": len(inherited.papers),
            "texts": len(vector.texts),
            "chunks": len(vector.members),
            "vectors": len(vector.members),
        }
        if any(type(counts.get(k)) is not int or counts[k] != n for k, n in expected.items()):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        proof = {
            "id": str(uuid4()),
            "base": str(base),
            "attempt": str(attempt),
            "claim": claim,
            "epoch": run["slot_epoch"],
            "scope_digest": run["matched_screening"]["digest"],
            "confirmation_digest": content_digest(run["ingestion_confirmation"]),
            "manifest_digest": record.manifest_digest,
            "profile_id": content_digest(vector.profile),
            "object_digests": inherited.digests,
            "file_stamps": inherited.file_stamps,
            "vector_view_id": str(vector.view_id),
            "graph_view_id": str(graph.view),
            "counts": counts,
            "checked_at": now(),
        }
        run["no_change_ready"] = proof
        run["candidate_version"]["state"] = "ready_to_publish"
        _check(conn, proj, run, claim, "ready_to_publish")
        persist(conn, run)
        return content_digest(proof)


def commit_no_change(
    store: Any,
    root: Path,
    actor: UUID,
    project: UUID,
    identity: UUID,
    attempt: UUID,
    claim: str,
    proof_digest: str,
) -> str:
    with store.account.engine.begin() as conn:
        proj, run = _locked_run(conn, store, actor, project, identity, attempt)
        proof = run.get("no_change_ready")
        if not proof or content_digest(proof) != proof_digest or proof["claim"] != claim:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        if run["status"] == "succeeded":
            result = run["completion"]
            if (
                result["outcome"] != "no_change"
                or result["verified_knowledge_version_id"] != proof["base"]
            ):
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            return str(proof["base"])
        base = _check(conn, proj, run, claim, "ready_to_publish")
        inherited = retained_inputs(conn, proj, actor, load(conn, proj), base, run)
        if (
            proof["base"] != str(base)
            or proof["epoch"] != run["slot_epoch"]
            or proof["scope_digest"] != run["matched_screening"]["digest"]
            or proof["confirmation_digest"] != content_digest(run["ingestion_confirmation"])
            or proof["object_digests"] != inherited.digests
        ):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        files = ImmutableFileStore(root)
        if proof["file_stamps"].keys() != inherited.digests.keys():
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        try:
            for oid, (file_attempt, expected_stamp) in proof["file_stamps"].items():
                if files.stamp(project, UUID(file_attempt), UUID(oid)) != expected_stamp:
                    raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        except OSError, ValueError:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
        if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        run["completion"] = {
            "outcome": "no_change",
            "verified_knowledge_version_id": str(base),
            "checked_at": proof["checked_at"],
            "checked_scope": run["input_snapshot"],
        }
        run["candidate_version"].update(
            state="discarded", closing_reason={"code": "no_change", "message": "核验无变化"}
        )
        run["finished_at"] = now()
        transition(run, "succeeded")
        persist(conn, run)
        return str(base)
