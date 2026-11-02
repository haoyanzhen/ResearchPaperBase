"""Build an isolated vector view for confirmed papers and compatible retained members."""

import copy
import hashlib
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_failure import (
    BuildClaimChanged,
    record_failure,
    require_publication_claim,
)
from rpb.adapters.knowledge_build_tables import (
    chunks,
    embeddings,
    profiles,
    vector_members,
    vector_views,
)
from rpb.adapters.knowledge_object_stage import require_build_protection, stage_objects
from rpb.adapters.knowledge_paper_stage import stage_paper
from rpb.adapters.knowledge_paper_tables import objects as paper_objects
from rpb.adapters.knowledge_vector_baseline import BaselineVectors, read_baseline_vectors
from rpb.adapters.knowledge_vector_seal import seal_vector_view, verify_vector_view
from rpb.adapters.local_embeddings import valid_profile
from rpb.adapters.run_tables import runs
from rpb.adapters.search_terms import allowed, classification, load, policy_view
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.knowledge.domain.chunking import split_text


def _build_profile(run: Any, embedding: Any) -> dict[str, Any]:
    snapshot = run["config_snapshot"]
    return {
        "embedding": copy.deepcopy(embedding),
        "embedding_profile_id": embedding["profile_id"],
        "chunker_revision": "paragraph-token-v1",
        "extractor_schema_revision": "single-slice-v1",
        "extractor_prompt_revision": "single-slice-prompt-v1",
        "extractor_config_digest": content_digest(
            {
                "model": snapshot["model_selection"],
                "revision": snapshot["config_revision"],
                "config": run["model_config"],
            }
        ),
        "graph_rules_revision": "paper-chunk-support-v1",
        "lexical_revision": "initial-lexical-v1",
    }


def build_vector_view(
    store: Any,
    file_root: Path,
    actor: UUID,
    project_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    port_factory: Callable[..., Any],
    *,
    publication_claim_id: str | None = None,
) -> dict[str, Any]:
    """Construct only isolated artifacts, with rechecks at every dispatch and commit."""
    files = ImmutableFileStore(file_root)
    with store.account.engine.connect() as conn:
        initial = conn.scalar(
            sa.select(runs.c.payload).where(
                runs.c.id == run_id, runs.c.project_id == project_id, runs.c.owner_id == actor
            )
        )
    snapshot = initial.get("input_snapshot") if initial else None
    if (
        not isinstance(snapshot, dict)
        or "base_knowledge_version_id" not in snapshot
        or (
            snapshot["base_knowledge_version_id"] is not None
            and snapshot.get("graph_mode") != "incremental"
        )
    ):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    selected = (
        (initial.get("ingestion_confirmation") or {}).get("preview", {}).get("valid_papers", [])
    )
    if not selected:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    for candidate in selected:
        stage_objects(
            store,
            file_root,
            actor,
            project_id,
            run_id,
            attempt_id,
            UUID(candidate),
            publication_claim_id=publication_claim_id,
        )

    base_id = snapshot["base_knowledge_version_id"]
    baseline: BaselineVectors | None = None

    def current(conn: Any, *, verify_baseline: bool = False) -> tuple[Any, list[Any], str]:
        nonlocal baseline
        identities = []
        for candidate in selected:
            identities.append(
                stage_paper(conn, store, actor, project_id, run_id, attempt_id, UUID(candidate))
            )
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
        if publication_claim_id is not None:
            require_publication_claim(run, publication_claim_id)
        if run["ingestion_confirmation"]["preview"]["valid_papers"] != selected:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        project = store.terms.project(conn, actor, project_id, write=True)
        state = load(conn, project)
        materials = []
        dependencies = {}
        if run["input_snapshot"]["base_knowledge_version_id"] != base_id:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        if base_id is not None and verify_baseline:
            checked = read_baseline_vectors(
                conn,
                project_id,
                UUID(base_id),
                run["ingestion_confirmation"]["retained_papers"],
            )
            if baseline is not None and baseline != checked:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            baseline = checked
        if baseline is not None:
            for sid, revision in baseline.source_revisions.items():
                source = classification(state, project, sid)
                if source["source"]["content_revision"] != revision or not allowed(
                    state, actor, project, sid
                ):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                dependencies[sid] = {
                    "source": source["source"],
                    "classification_revision": source["revision"],
                    "policy_revision": policy_view(state, actor, project)["revision"],
                }
            if content_digest(dependencies) != baseline.dependency_digest:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            if verify_baseline:
                baseline.verify_artifacts(conn, files, project_id)
        for candidate_id, identity in zip(selected, identities, strict=True):
            candidate = next(c for c in run["candidates"] if c["id"] == candidate_id)
            obj = (
                conn.execute(
                    sa.select(paper_objects).where(
                        paper_objects.c.project_id == project_id,
                        paper_objects.c.paper_revision_id == UUID(identity["paper_revision_id"]),
                        paper_objects.c.kind == "text",
                        paper_objects.c.attempt_id == attempt_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if obj is None:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            require_build_protection(
                conn,
                project_id,
                obj["id"],
                run_id,
                attempt_id,
                run["slot_epoch"],
                run["lease_until"],
            )
            try:
                raw = files.read(project_id, attempt_id, obj["id"], obj["sha256"])
                text = raw.decode("utf-8")
            except OSError, ValueError, UnicodeError:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
            if (
                len(raw) != obj["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != candidate["processing"]["text_digest"]
                or not text.strip()
            ):
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            lineage = obj["dependencies"]
            for sid in lineage["source_ids"]:
                source = classification(state, project, sid)
                dependencies[sid] = {
                    "source": source["source"],
                    "classification_revision": source["revision"],
                    "policy_revision": policy_view(state, actor, project)["revision"],
                }
            materials.append(
                {
                    "candidate": copy.deepcopy(candidate),
                    "identity": identity,
                    "object": dict(obj),
                    "text": text,
                }
            )
        if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        return run, materials, content_digest(dependencies)

    with store.account.engine.begin() as conn:
        frozen_run, materials, dependency_digest = current(conn, verify_baseline=True)
        material_digest = content_digest(
            [
                {
                    "candidate_id": item["candidate"]["id"],
                    "candidate_revision": item["candidate"]["revision"],
                    "paper_revision_id": item["identity"]["paper_revision_id"],
                    "text_object_id": str(item["object"]["id"]),
                    "text_digest": item["object"]["sha256"],
                    "locators": item["object"]["locators"],
                    "dependencies": item["object"]["dependencies"],
                }
                for item in materials
            ]
        )
        previous = frozen_run.get("vector_build")
        if previous:
            saved_profile = previous["profile"]
            expected_build_profile = _build_profile(frozen_run, saved_profile["embedding"])
            view_id = UUID(previous["view_id"])
            view = (
                conn.execute(
                    sa.select(vector_views).where(
                        vector_views.c.project_id == project_id, vector_views.c.id == view_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            expected = {UUID(identity) for identity in previous["chunks"]}
            if (
                view is None
                or view["run_id"] != run_id
                or view["attempt_id"] != attempt_id
                or view["slot_epoch"] != frozen_run["slot_epoch"]
                or view["input_revision"] != UUID(frozen_run["effective_input_revision"])
                or view["candidate_revision"] != UUID(frozen_run["candidate_revision"])
                or not valid_profile(saved_profile["embedding"])
                or (
                    baseline is not None
                    and (
                        saved_profile != baseline.profile or not baseline.members.keys() <= expected
                    )
                )
                or saved_profile != expected_build_profile
                or view["build_profile_id"] != content_digest(previous["profile"])
                or previous["profile_id"] != view["build_profile_id"]
                or view["profile_id"] != saved_profile["embedding"]["profile_id"]
                or view["dependency_digest"] != dependency_digest
                or previous["dependency_digest"] != dependency_digest
                or previous.get("material_digest") != material_digest
                or conn.scalar(
                    sa.select(profiles.c.body).where(profiles.c.id == view["profile_id"])
                )
                != previous["profile"]["embedding"]
                or verify_vector_view(conn, project_id, view_id, expected) != previous["digest"]
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            return copy.deepcopy(previous)
        if frozen_run.get("vector_build_claim"):
            raise AccountError("LOCK_CONTENT_BUSY", 409)
        claim_id = str(uuid4())
        expected_claim: dict[str, Any] = {
            "id": claim_id,
            "attempt_id": str(attempt_id),
            "state": "running",
            "material_digest": material_digest,
            "dependency_digest": dependency_digest,
        }
        from rpb.adapters.runs import persist

        frozen_run["vector_build_claim"] = expected_claim
        persist(conn, frozen_run)

    @contextmanager
    def permit() -> Any:
        with store.account.engine.begin() as conn:
            live_run, live_materials, live_digest = current(conn)
            if (
                live_digest != dependency_digest
                or live_materials != materials
                or live_run["attempt_id"] != str(attempt_id)
                or live_run.get("vector_build_claim") != expected_claim
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            yield

    try:
        with port_factory(permit) as port:
            profile = copy.deepcopy(port.profile)
            if not valid_profile(profile):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            build_profile = _build_profile(frozen_run, profile)
            if baseline is not None and build_profile != baseline.profile:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            profile_id = content_digest(build_profile)
            with store.account.engine.begin() as conn:
                live, actual, digest = current(conn)
                if (
                    live.get("vector_build_claim") != expected_claim
                    or actual != materials
                    or digest != dependency_digest
                ):
                    raise AccountError("STATE_REVISION_CONFLICT", 409)
                frozen_claim = dict(
                    expected_claim, build_profile_id=profile_id, build_profile=build_profile
                )
                live["vector_build_claim"] = frozen_claim
                persist(conn, live)
            expected_claim = frozen_claim
            prepared = []
            for material in materials:
                for piece in split_text(material["text"], port):
                    text = material["text"][piece.start : piece.end]
                    vector = port.embed(text)
                    locators = [
                        {
                            "start_offset": max(piece.start, part["start_offset"]),
                            "end_offset": min(piece.end, part["end_offset"]),
                            "page": part["page"],
                        }
                        for part in material["object"]["locators"]
                        if part["start_offset"] < piece.end and part["end_offset"] > piece.start
                    ]
                    prepared.append((material, piece, text, vector, locators))
            if not prepared:
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        with store.account.engine.begin() as conn:
            run, live_materials, live_digest = current(conn, verify_baseline=True)
            if live_materials != materials or live_digest != dependency_digest:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            if run.get("vector_build") or run.get("vector_build_claim") != expected_claim:
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            conn.execute(
                insert(profiles)
                .values(id=profile["profile_id"], body=profile)
                .on_conflict_do_nothing()
            )
            if (
                conn.scalar(
                    sa.select(profiles.c.body).where(profiles.c.id == profile["profile_id"])
                )
                != profile
            ):
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            view_id = uuid4()
            conn.execute(
                vector_views.insert().values(
                    id=view_id,
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    slot_epoch=run["slot_epoch"],
                    input_revision=UUID(run["effective_input_revision"]),
                    candidate_revision=UUID(run["candidate_revision"]),
                    build_profile_id=profile_id,
                    dependency_digest=dependency_digest,
                    profile_id=profile["profile_id"],
                )
            )
            expected_chunks = set(baseline.members) if baseline is not None else set()
            if baseline is not None and baseline.members:
                conn.execute(
                    vector_members.insert(),
                    [
                        dict(
                            project_id=project_id,
                            view_id=view_id,
                            embedding_id=embedding,
                            profile_id=profile["profile_id"],
                        )
                        for embedding in baseline.members.values()
                    ],
                )
            for material, piece, text, vector, locators in prepared:
                chunk_id, embedding_id = uuid4(), uuid4()
                expected_chunks.add(chunk_id)
                conn.execute(
                    chunks.insert().values(
                        id=chunk_id,
                        project_id=project_id,
                        run_id=run_id,
                        asset_id=UUID(material["identity"]["project_paper_id"]),
                        asset_revision=UUID(material["identity"]["paper_revision_id"]),
                        text_revision_id=material["object"]["id"],
                        start_offset=piece.start,
                        end_offset=piece.end,
                        text_digest=hashlib.sha256(text.encode()).hexdigest(),
                        source_kind=material["candidate"]["processing"]["text_source_kind"],
                        chunker_revision="paragraph-token-v1",
                        locators=locators,
                        dependencies=material["object"]["dependencies"],
                    )
                )
                conn.execute(
                    embeddings.insert().values(
                        id=embedding_id,
                        project_id=project_id,
                        chunk_id=chunk_id,
                        profile_id=profile["profile_id"],
                        embedding=vector,
                    )
                )
                conn.execute(
                    vector_members.insert().values(
                        project_id=project_id,
                        view_id=view_id,
                        embedding_id=embedding_id,
                        profile_id=profile["profile_id"],
                    )
                )
            digest = seal_vector_view(conn, project_id, view_id, expected_chunks)
            run["vector_build"] = {
                "view_id": str(view_id),
                "digest": digest,
                "profile": build_profile,
                "profile_id": profile_id,
                "dependency_digest": dependency_digest,
                "material_digest": material_digest,
                "chunks": [str(x) for x in sorted(expected_chunks)],
            }
            if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            run["vector_build_claim"]["state"] = "succeeded"
            from rpb.adapters.runs import persist

            persist(conn, run)
            return copy.deepcopy(run["vector_build"])
    except BaseException as failure:
        try:
            record_failure(
                store,
                actor,
                project_id,
                run_id,
                attempt_id,
                "vector_build_claim",
                claim_id,
                failure,
                expected_claim=expected_claim,
                publication_claim_id=publication_claim_id,
            )
        except BuildClaimChanged:
            raise
        except Exception:
            # A revoked write fence may prevent any diagnostic update.
            pass
        raise
