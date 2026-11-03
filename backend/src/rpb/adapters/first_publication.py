"""Commit a Project paper version from verified, sealed construction artifacts."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_failure import BuildClaimChanged, require_publication_claim
from rpb.adapters.knowledge_build_tables import (
    graph_edges,
    graph_extractions,
    graph_nodes,
    graph_supports,
    publication_events,
    vector_members,
)
from rpb.adapters.knowledge_object_stage import require_build_protection
from rpb.adapters.knowledge_paper_tables import (
    object_build_pins,
    objects,
    paper_revisions,
    version_object_pins,
    version_paper_pins,
)
from rpb.adapters.knowledge_publication_baseline import checked_base, retained_inputs
from rpb.adapters.knowledge_rebuild import rebuild_requested, verify_retained_service
from rpb.adapters.knowledge_tables import heads, versions
from rpb.modules.account_config.application.ports import AccountError


def prepare_verified(
    conn: Any,
    root: Path,
    run: Any,
    material: list[Any],
    vector: Any,
    graph: Any,
    project_record: Any,
    state: Any,
    claim_id: str | None,
) -> dict[str, Any]:
    """Called under the graph read barrier, after the committed views are verified."""
    from rpb.adapters.runs import persist

    project, identity, attempt = (UUID(run[key]) for key in ("project_id", "id", "attempt_id"))
    require_publication_claim(run, claim_id)
    base = checked_base(conn, project, run)
    files = ImmutableFileStore(root)
    inherited = retained_inputs(
        conn,
        project_record,
        UUID(run["owner_id"]),
        state,
        base,
        run,
        files,
        capture_stamps=rebuild_requested(run),
    )
    papers, digests = list(inherited.papers), dict(inherited.digests)
    members = {item["chunk"]["asset_revision"]: item for item in material}
    retained_revisions = {UUID(p["paper_revision_id"]) for p in inherited.papers}
    for revision, item in sorted(members.items()):
        if revision in retained_revisions:
            continue
        candidate, asset = item["candidate"], item["chunk"]["asset_id"]
        paper = (
            conn.execute(
                sa.select(paper_revisions).where(
                    paper_revisions.c.project_id == project,
                    paper_revisions.c.id == revision,
                    paper_revisions.c.project_paper_id == asset,
                    paper_revisions.c.run_id == identity,
                    paper_revisions.c.candidate_id == UUID(candidate["id"]),
                )
            )
            .mappings()
            .one()
        )
        if paper["digest"] != content_digest(paper["content"]):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        rows = list(
            conn.execute(
                sa.select(objects)
                .where(
                    objects.c.project_id == project,
                    objects.c.paper_revision_id == revision,
                    objects.c.attempt_id == attempt,
                )
                .order_by(objects.c.id)
            ).mappings()
        )
        expected = (
            {"text", "file"}
            if candidate["processing"]["text_source_kind"] == "full_text"
            else {"text"}
        )
        if {row["kind"] for row in rows} != expected:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        for row in rows:
            require_build_protection(
                conn, project, row["id"], identity, attempt, run["slot_epoch"], run["lease_until"]
            )
            data = files.read(project, attempt, row["id"], row["sha256"])
            if len(data) != row["size_bytes"]:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            digests[str(row["id"])] = row["sha256"]
        papers.append(
            {
                "project_paper_id": str(asset),
                "paper_revision_id": str(revision),
                "digest": paper["digest"],
                "objects": {r["kind"]: str(r["id"]) for r in rows},
            }
        )
    manifest = {
        "papers": papers,
        "materials": [],
        "vector_view_id": vector["view_id"],
        "graph_view_id": graph["view_id"],
        "build_profile": vector["profile"],
        "vector_digest": vector["digest"],
        "graph_digest": graph["digest"],
    }
    counts = {"papers": len(papers), "texts": len(papers), "chunks": len(vector["chunks"])}
    for name, table, view in (
        ("vectors", vector_members, vector),
        ("nodes", graph_nodes, graph),
        ("assertions", graph_edges, graph),
        ("supports", graph_supports, graph),
        ("extractions", graph_extractions, graph),
    ):
        counts[name] = conn.scalar(
            sa.select(sa.func.count())
            .select_from(table)
            .where(table.c.project_id == project, table.c.view_id == UUID(view["view_id"]))
        )
    if counts["chunks"] != counts["vectors"] or counts["chunks"] != counts["extractions"]:
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    at = datetime.now(UTC)
    proof = {
        "project_id": str(project),
        "base_version_id": str(base) if base else None,
        "run_id": str(identity),
        "attempt_id": str(attempt),
        "candidate_revision": run["candidate_revision"],
        "manifest_digest": content_digest(manifest),
        "build_profile_id": vector["profile_id"],
        "vector_view_id": vector["view_id"],
        "graph_view_id": graph["view_id"],
        "counts": counts,
        "object_digests": digests,
        "dependency_set_digest": graph["dependency_digest"],
        "validated_at": at.isoformat().replace("+00:00", "Z"),
        "read_barrier_id": str(uuid4()),
    }
    if rebuild_requested(run):
        proof["retained_file_stamps"] = inherited.file_stamps
        if not run["ingestion_confirmation"]["preview"]["valid_papers"]:
            old = conn.execute(
                sa.select(versions.c.manifest, versions.c.ready_proof).where(
                    versions.c.project_id == project, versions.c.id == base, versions.c.sealed
                )
            ).one()
            if (
                old.manifest["build_profile"] == vector["profile"]
                and old.ready_proof["dependency_set_digest"] == inherited.dependency_digest
            ):
                # The runtime changed between the equivalence check and actual rebuilding.
                raise AccountError("STATE_REVISION_CONFLICT", 409)
    run["publication_ready"] = {
        "manifest": manifest,
        "proof": proof,
        "publication_claim_id": claim_id,
        "readback_digest": content_digest(proof),
        "input_revision": run["effective_input_revision"],
        "slot_epoch": run["slot_epoch"],
        "vector": vector,
        "graph": graph,
    }
    run["candidate_version"]["state"] = "ready_to_publish"
    persist(conn, run)
    return {"read_barrier_id": proof["read_barrier_id"], "readback_digest": content_digest(proof)}


def commit_ready(
    store: Any,
    actor: UUID,
    project: UUID,
    identity: UUID,
    attempt: UUID,
    barrier: str,
    claim_id: str | None = None,
    expected_readback_digest: str | None = None,
    file_root: Path | None = None,
) -> str:
    from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
    from rpb.adapters.knowledge_paper_stage import locked_build_run, stage_paper
    from rpb.adapters.run_tables import runs
    from rpb.adapters.search_term_worker import TermWorker
    from rpb.adapters.search_terms import allowed, classification, load, policy_view

    with store.account.engine.begin() as conn:
        conn.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )
        if not store.terms.llm.permitted_actor(conn, actor):
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        proj = store.terms.project(conn, actor, project, write=True)
        run = conn.scalar(
            sa.select(runs.c.payload).where(
                runs.c.id == identity, runs.c.project_id == project, runs.c.owner_id == actor
            )
        )
        if not run or run["attempt_id"] != str(attempt):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        ready = run.get("publication_ready") or {}
        proof = ready.get("proof") or {}
        if proof.get("read_barrier_id") != barrier:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        if run["status"] == "succeeded":
            decision = conn.scalar(
                sa.select(versions.c.id)
                .join(publication_events, publication_events.c.version_id == versions.c.id)
                .where(
                    versions.c.project_id == project,
                    versions.c.source_run_id == identity,
                    versions.c.sealed,
                    versions.c.ready_proof["read_barrier_id"].astext == barrier,
                )
            )
            if not decision or str(decision) != run["published_knowledge_version_id"]:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            return str(decision)
        require_publication_claim(run, claim_id)
        if claim_id and expected_readback_digest != content_digest(proof):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        if ready.get("publication_claim_id") != claim_id:
            raise BuildClaimChanged()
        manifest = ready["manifest"]
        if (
            (
                (
                    "readback_digest" in ready
                    or run["input_snapshot"]["base_knowledge_version_id"] is not None
                )
                and ready.get("readback_digest") != content_digest(proof)
            )
            or proof["project_id"] != str(project)
            or proof["run_id"] != str(identity)
            or proof["attempt_id"] != str(attempt)
            or proof["vector_view_id"] != manifest["vector_view_id"]
            or proof["graph_view_id"] != manifest["graph_view_id"]
            or proof["vector_view_id"] != ready["vector"]["view_id"]
            or proof["graph_view_id"] != ready["graph"]["view_id"]
            or proof["build_profile_id"] != ready["vector"]["profile_id"]
            or proof["build_profile_id"] != ready["graph"]["profile_id"]
            or proof["dependency_set_digest"] != ready["graph"]["dependency_digest"]
            or manifest["build_profile"] != ready["vector"]["profile"]
            or manifest["graph_digest"] != ready["graph"]["digest"]
            or manifest["vector_digest"] != ready["vector"]["digest"]
            or content_digest(manifest) != proof["manifest_digest"]
            or run["candidate_revision"] != proof["candidate_revision"]
            or run["effective_input_revision"] != ready["input_revision"]
            or run["slot_epoch"] != ready["slot_epoch"]
            or ready["vector"] != run["vector_build"]
            or ready["graph"] != run["graph_build"]
            or run["candidate_version"]["state"] != "ready_to_publish"
        ):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        base = checked_base(conn, project, run)
        if proof.get("base_version_id") != (str(base) if base else None):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        state = load(conn, proj)
        policy = policy_view(state, actor, proj)["revision"]
        text_deps, meta_deps = {}, {}
        selected = run["ingestion_confirmation"]["preview"]["valid_papers"]
        members = set()
        for cid in selected:
            staged = stage_paper(conn, store, actor, project, identity, attempt, UUID(cid))
            members.add(UUID(staged["paper_revision_id"]))
            c = next(c for c in run["candidates"] if c["id"] == cid)
            src = classification(state, proj, cid)
            if not allowed(state, actor, proj, cid):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            meta_deps[cid] = {
                "source_ids": [cid],
                "source_revisions": {cid: src["source"]["content_revision"]},
                "classification_revisions": {cid: src["revision"]},
                "policy_revision": policy,
            }
            for sid in run["analysis_lineage"][c["analysis_basis"]["analysis_revision"]][
                "dependencies"
            ]["source_ids"]:
                source = classification(state, proj, sid)
                text_deps[sid] = {
                    "source": source["source"],
                    "classification_revision": source["revision"],
                    "policy_revision": policy,
                }
                TermWorker(store.terms, None).check(
                    conn,
                    proj,
                    state,
                    {
                        "owner_id": str(actor),
                        "authority_epoch": run["authority_epoch"],
                        "source_id": sid,
                        "model_selection": run["config_snapshot"]["model_selection"],
                        "config": run["model_config"],
                    },
                )
        if rebuild_requested(run):
            locked_build_run(conn, store, actor, project, identity, attempt)
        elif not members:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        inherited = retained_inputs(conn, proj, actor, state, base, run)
        if rebuild_requested(run):
            stamps = proof.get("retained_file_stamps", {})
            if (
                file_root is None
                or stamps.keys() != inherited.digests.keys()
                or inherited.dependency_digest
                != run["ingestion_confirmation"].get("rebuild_dependency_digest")
            ):
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            files = ImmutableFileStore(file_root)
            try:
                for object_id, (file_attempt, stamp) in stamps.items():
                    if files.stamp(project, UUID(file_attempt), UUID(object_id)) != stamp:
                        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            except OSError, ValueError:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
            verify_retained_service(conn, store, proj, state, run, inherited.text_dependencies)
        text_deps.update(inherited.text_dependencies)
        meta_deps.update(inherited.metadata_dependencies)
        members.update(UUID(p["paper_revision_id"]) for p in inherited.papers)
        by_revision = {p["paper_revision_id"]: p for p in manifest["papers"]}
        if (
            any(by_revision.get(p["paper_revision_id"]) != p for p in inherited.papers)
            or len(by_revision) != len(manifest["papers"])
            or members != {UUID(x["paper_revision_id"]) for x in manifest["papers"]}
            or content_digest({"text": text_deps, "metadata": meta_deps})
            != proof["dependency_set_digest"]
        ):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        digests = proof["object_digests"]
        object_ids = {oid for paper in manifest["papers"] for oid in paper["objects"].values()}
        if set(digests) != object_ids or any(
            digests.get(oid) != sha for oid, sha in inherited.digests.items()
        ):
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        for oid in sorted(digests.keys() - inherited.digests.keys()):
            require_build_protection(
                conn, project, UUID(oid), identity, attempt, run["slot_epoch"], run["lease_until"]
            )
        return persist_version(
            conn, run, project, identity, attempt, base, manifest, proof, text_deps, meta_deps
        )


def persist_version(
    conn: Any,
    run: Any,
    project: UUID,
    identity: UUID,
    attempt: UUID,
    base: UUID | None,
    manifest: Any,
    proof: Any,
    text_dependencies: Any,
    metadata_dependencies: Any,
) -> str:
    """Insert the verified snapshot, pins, publication event and default atomically."""
    from rpb.adapters.runs import persist, transition

    # A later subtraction can validate each retained source without accessing excluded evidence.
    proof = proof | {
        "source_dependency_digests": {
            kind: {sid: content_digest(dependency) for sid, dependency in deps.items()}
            for kind, deps in (("text", text_dependencies), ("metadata", metadata_dependencies))
        }
    }
    members = {UUID(p["paper_revision_id"]) for p in manifest["papers"]}
    digests = proof["object_digests"]
    version = uuid4()
    at = datetime.now(UTC)
    conn.execute(
        versions.insert().values(
            id=version,
            project_id=project,
            source_run_id=identity,
            base_version_id=base,
            manifest=manifest,
            manifest_digest=proof["manifest_digest"],
            ready_proof=proof,
            sealed=False,
            published_at=at,
        )
    )
    for revision in members:
        conn.execute(
            version_paper_pins.insert().values(
                project_id=project, version_id=version, paper_revision_id=revision
            )
        )
    for object_id in digests:
        conn.execute(
            version_object_pins.insert().values(
                project_id=project, version_id=version, object_id=UUID(object_id)
            )
        )
        conn.execute(
            object_build_pins.delete().where(
                object_build_pins.c.project_id == project,
                object_build_pins.c.object_id == UUID(object_id),
                object_build_pins.c.run_id == identity,
                object_build_pins.c.attempt_id == attempt,
                object_build_pins.c.slot_epoch == run["slot_epoch"],
            )
        )
    conn.execute(versions.update().where(versions.c.id == version).values(sealed=True))
    if base is None:
        conn.execute(heads.insert().values(project_id=project, version_id=version))
    elif (
        conn.execute(
            heads.update()
            .where(heads.c.project_id == project, heads.c.version_id == base)
            .values(version_id=version)
        ).rowcount
        != 1
    ):
        raise AccountError("STATE_REVISION_CONFLICT", 409)
    if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
    run["published_knowledge_version_id"] = str(version)
    conn.execute(
        publication_events.insert().values(
            version_id=version,
            project_id=project,
            graph_view_id=UUID(proof["graph_view_id"]),
            vector_view_id=UUID(proof["vector_view_id"]),
            embedding_profile_id=manifest["build_profile"]["embedding_profile_id"],
            created_at=at,
            state="pending",
        )
    )
    run["completion"] = {
        "outcome": "published",
        "verified_knowledge_version_id": None,
        "checked_at": at.isoformat().replace("+00:00", "Z"),
        "checked_scope": run["input_snapshot"],
    }
    run["candidate_version"]["state"] = "published"
    run["finished_at"] = at.isoformat().replace("+00:00", "Z")
    transition(run, "succeeded")
    persist(conn, run)
    return str(version)
