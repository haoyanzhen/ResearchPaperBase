"""Build an isolated, evidence-bearing graph from a sealed first-version vector view."""

import copy
import hashlib
import unicodedata
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_failure import record_failure
from rpb.adapters.knowledge_build_tables import (
    chunks,
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_supports,
    graph_views,
)
from rpb.adapters.knowledge_chunk_integrity import verify_chunk_closure
from rpb.adapters.knowledge_graph_seal import seal_graph_view, verify_graph_view
from rpb.adapters.knowledge_object_stage import require_build_protection
from rpb.adapters.knowledge_paper_stage import stage_paper
from rpb.adapters.knowledge_paper_tables import objects as paper_objects
from rpb.adapters.knowledge_vector_builder import build_vector_view
from rpb.adapters.knowledge_vector_seal import verify_vector_view
from rpb.adapters.run_tables import runs
from rpb.adapters.search_term_worker import TermWorker
from rpb.adapters.search_terms import allowed, classification, load, policy_view
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.knowledge.domain.graph_validation import validate_extraction


def build_graph_view(
    store: Any,
    file_root: Path,
    actor: UUID,
    project_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    provider: Any,
    *,
    publish: bool = False,
    tokenizer_factory: Any = None,
) -> dict[str, Any]:
    """Run validated extraction per chunk; graph and vector remain unpublished."""

    def no_model(_permit: Any) -> Any:
        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)

    vector = build_vector_view(store, file_root, actor, project_id, run_id, attempt_id, no_model)
    files, guard = ImmutableFileStore(file_root), TermWorker(store.terms, None)
    chunk_ids = {UUID(x) for x in vector["chunks"]}

    def current(conn: Any) -> tuple[Any, list[Any], str, str]:
        initial = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
        if not initial or initial.get("vector_build") != vector:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        selected = initial["ingestion_confirmation"]["preview"]["valid_papers"]
        identities = {
            candidate: stage_paper(
                conn, store, actor, project_id, run_id, attempt_id, UUID(candidate)
            )
            for candidate in selected
        }
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == run_id))
        if run.get("vector_build") != vector:
            raise AccountError("STATE_REVISION_CONFLICT", 409)
        verify_vector_view(conn, project_id, UUID(vector["view_id"]), chunk_ids)
        project = store.terms.project(conn, actor, project_id, write=True)
        state = load(conn, project)
        by_asset = {item["project_paper_id"]: cid for cid, item in identities.items()}
        material, dependencies, metadata_dependencies, secret = [], {}, {}, None
        closures: dict[UUID, dict[str, Any]] = {}
        rows = list(
            conn.execute(
                sa.select(chunks)
                .where(chunks.c.project_id == project_id, chunks.c.id.in_(chunk_ids))
                .order_by(chunks.c.id)
            ).mappings()
        )
        if len(rows) != len(chunk_ids) or {str(row["asset_id"]) for row in rows} != set(by_asset):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        for row in rows:
            candidate_id = by_asset.get(str(row["asset_id"]))
            if (
                candidate_id is None
                or str(row["asset_revision"]) != identities[candidate_id]["paper_revision_id"]
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            candidate = next(c for c in run["candidates"] if c["id"] == candidate_id)
            if not allowed(state, actor, project, candidate_id):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            metadata_source = classification(state, project, candidate_id)
            metadata_dependency = {
                "source_ids": [candidate_id],
                "source_revisions": {candidate_id: metadata_source["source"]["content_revision"]},
                "classification_revisions": {candidate_id: metadata_source["revision"]},
                "policy_revision": policy_view(state, actor, project)["revision"],
            }
            metadata_dependencies[candidate_id] = metadata_dependency
            obj = (
                conn.execute(
                    sa.select(paper_objects).where(
                        paper_objects.c.project_id == project_id,
                        paper_objects.c.id == row["text_revision_id"],
                        paper_objects.c.paper_revision_id == row["asset_revision"],
                        paper_objects.c.kind == "text",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if obj is None or obj["dependencies"] != row["dependencies"]:
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
                text = files.read(project_id, obj["attempt_id"], obj["id"], obj["sha256"]).decode(
                    "utf-8"
                )
            except OSError, ValueError, UnicodeError:
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410) from None
            closure = closures.setdefault(
                obj["id"],
                {
                    "text": text,
                    "object": dict(obj),
                    "source_kind": candidate["processing"]["text_source_kind"],
                    "chunks": [],
                },
            )
            if closure["text"] != text or closure["object"] != dict(obj):
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            closure["chunks"].append(dict(row))
            fragment = text[row["start_offset"] : row["end_offset"]]
            if (
                not fragment
                or row["end_offset"] > len(text)
                or hashlib.sha256(fragment.encode()).hexdigest() != row["text_digest"]
            ):
                raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
            for sid in obj["dependencies"]["source_ids"]:
                source = classification(state, project, sid)
                dependencies[sid] = {
                    "source": source["source"],
                    "classification_revision": source["revision"],
                    "policy_revision": policy_view(state, actor, project)["revision"],
                }
                job = {
                    "owner_id": str(actor),
                    "authority_epoch": run["authority_epoch"],
                    "source_id": sid,
                    "model_selection": run["config_snapshot"]["model_selection"],
                    "config": run["model_config"],
                }
                _, credential = guard.check(conn, project, state, job)
                if secret is not None and secret != credential:
                    raise AccountError("CONFIG_SECRET_UNAVAILABLE", 409)
                secret = credential
            material.append(
                {
                    "chunk": dict(row),
                    "candidate": copy.deepcopy(candidate),
                    "text": fragment,
                    "metadata_dependencies": metadata_dependency,
                }
            )
        for closure in closures.values():
            verify_chunk_closure(
                closure["text"], closure["object"], closure["source_kind"], closure["chunks"]
            )
        dep_digest = content_digest(dependencies)
        if dep_digest != vector["dependency_digest"] or secret is None:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        return (
            run,
            material,
            content_digest({"text": dependencies, "metadata": metadata_dependencies}),
            secret,
        )

    if publish:
        from rpb.modules.knowledge.domain.chunking import split_text

        with store.account.engine.begin() as conn:
            initial, frozen, frozen_digest, _ = current(conn)
            if not initial.get("graph_build") or not tokenizer_factory:
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)

        @contextmanager
        def tokenizer_permit() -> Any:
            with store.account.engine.begin() as conn:
                _, actual, digest, _ = current(conn)
                if actual != frozen or digest != frozen_digest:
                    raise AccountError("STATE_REVISION_CONFLICT", 409)
                yield

        grouped: dict[UUID, list[Any]] = {}
        for item in frozen:
            grouped.setdefault(item["chunk"]["text_revision_id"], []).append(item)
        with tokenizer_factory(tokenizer_permit) as tokenizer:
            if tokenizer.profile != vector["profile"]["embedding"]:
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            for items in grouped.values():
                items.sort(key=lambda item: item["chunk"]["start_offset"])
                covered = 0
                parts = []
                ranges = []
                for item in items:
                    start, end = item["chunk"]["start_offset"], item["chunk"]["end_offset"]
                    if start > covered or end <= covered:
                        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
                    parts.append(item["text"][covered - start :])
                    ranges.append((start, end))
                    covered = end
                if ranges != [
                    (part.start, part.end) for part in split_text("".join(parts), tokenizer)
                ]:
                    raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    with store.account.engine.begin() as conn:
        run, material, dependency_digest, secret = current(conn)
        previous = run.get("graph_build")
        if previous:
            view = (
                conn.execute(
                    sa.select(graph_views).where(
                        graph_views.c.project_id == project_id,
                        graph_views.c.id == UUID(previous["view_id"]),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                view is None
                or view["run_id"] != run_id
                or view["attempt_id"] != attempt_id
                or view["slot_epoch"] != run["slot_epoch"]
                or view["input_revision"] != UUID(run["effective_input_revision"])
                or view["candidate_revision"] != UUID(run["candidate_revision"])
                or view["build_profile_id"] != vector["profile_id"]
                or view["dependency_digest"] != dependency_digest
                or previous["vector_view_id"] != vector["view_id"]
                or previous["profile_id"] != vector["profile_id"]
                or previous["dependency_digest"] != dependency_digest
                or verify_graph_view(
                    conn,
                    project_id,
                    UUID(previous["view_id"]),
                    chunk_ids,
                    {item["chunk"]["id"]: item["text"] for item in material},
                )
                != previous["digest"]
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            if publish:
                from rpb.adapters.first_publication import prepare_verified

                return prepare_verified(conn, file_root, run, material, vector, previous)
            return copy.deepcopy(previous)
        if publish:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        if run.get("graph_build_claim"):
            raise AccountError("LOCK_CONTENT_BUSY", 409)
        claim_id = str(uuid4())
        run["graph_build_claim"] = {
            "id": claim_id,
            "attempt_id": str(attempt_id),
            "state": "running",
        }
        from rpb.adapters.runs import persist

        persist(conn, run)

    @contextmanager
    def permit() -> Any:
        with store.account.engine.begin() as conn:
            live, actual, digest, credential = current(conn)
            if (
                actual != material
                or digest != dependency_digest
                or credential != secret
                or (live.get("graph_build_claim") or {}).get("id") != claim_id
                or (live.get("graph_build_claim") or {}).get("state") != "running"
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            yield

    try:
        proposals = []
        for item in material:
            entities, claims = provider.extract(
                run["model_config"],
                run["config_snapshot"]["model_selection"]["model_id"],
                secret,
                item["text"],
                {},
                permit,
            )
            proposal = {
                "entities": [asdict(entity) for entity in entities],
                "claims": [
                    {**asdict(claim), "quote": item["text"][claim.start : claim.end]}
                    for claim in claims
                ],
            }
            checked = validate_extraction(item["text"], proposal)
            proposals.append((item, checked[0], checked[1], content_digest(proposal)))

        with store.account.engine.begin() as conn:
            live, actual, digest, _ = current(conn)
            if (
                actual != material
                or digest != dependency_digest
                or (live.get("graph_build_claim") or {}).get("id") != claim_id
            ):
                raise AccountError("STATE_REVISION_CONFLICT", 409)
            view_id = uuid4()
            conn.execute(
                graph_views.insert().values(
                    id=view_id,
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    slot_epoch=live["slot_epoch"],
                    input_revision=UUID(live["effective_input_revision"]),
                    candidate_revision=UUID(live["candidate_revision"]),
                    build_profile_id=vector["profile_id"],
                    dependency_digest=dependency_digest,
                )
            )
            node_ids: dict[tuple[str, str], UUID] = {}

            def node(kind: str, identity: str) -> UUID:
                key = (kind, identity)
                if key not in node_ids:
                    node_ids[key] = uuid4()
                    conn.execute(
                        graph_nodes.insert().values(
                            project_id=project_id,
                            view_id=view_id,
                            id=node_ids[key],
                            kind=kind,
                            identity_key=identity,
                        )
                    )
                return node_ids[key]

            def label(node_id: UUID, value: str, source: dict[str, Any], deps: Any) -> None:
                conn.execute(
                    graph_labels.insert().values(
                        project_id=project_id,
                        view_id=view_id,
                        id=uuid4(),
                        node_id=node_id,
                        label=value,
                        source=source,
                        dependencies=deps,
                    )
                )

            def edge(
                source: UUID, target: UUID, predicate: str, support: dict[str, Any], deps: Any
            ) -> None:
                identity = uuid4()
                conn.execute(
                    graph_edges.insert().values(
                        project_id=project_id,
                        view_id=view_id,
                        id=identity,
                        source_id=source,
                        target_id=target,
                        predicate=predicate,
                        extractor_revision="single-slice-v1",
                        confidence=None,
                        dependencies=deps,
                    )
                )
                conn.execute(
                    graph_supports.insert().values(
                        project_id=project_id,
                        view_id=view_id,
                        id=uuid4(),
                        edge_id=identity,
                        dependencies=deps,
                        **support,
                    )
                )

            for item, entities, claims, proposal_digest in proposals:
                chunk, candidate, text = item["chunk"], item["candidate"], item["text"]
                deps = chunk["dependencies"]
                aid, arev, tid, cid = (
                    chunk["asset_id"],
                    chunk["asset_revision"],
                    chunk["text_revision_id"],
                    chunk["id"],
                )
                paper = node("paper", f"{aid}:{arev}")
                chunk_node = node("chunk", str(cid))
                meta = {
                    "kind": "metadata",
                    "asset_id": aid,
                    "asset_revision": arev,
                    "metadata_revision": arev,
                    "field": "title",
                }
                label(
                    paper,
                    candidate["metadata"]["title"],
                    {k: str(v) if isinstance(v, UUID) else v for k, v in meta.items()},
                    item["metadata_dependencies"],
                )
                whole = {
                    "kind": "text",
                    "chunk_id": cid,
                    "text_revision_id": tid,
                    "start_offset": chunk["start_offset"],
                    "end_offset": chunk["end_offset"],
                }
                label(
                    chunk_node,
                    text,
                    {k: str(v) if isinstance(v, UUID) else v for k, v in whole.items()},
                    deps,
                )
                edge(chunk_node, paper, "belongs_to", whole, deps)
                for index, author in enumerate(candidate["metadata"].get("authors", [])):
                    author_node = node("author", f"{arev}:{index}")
                    author_support = {**meta, "field": "authors"}
                    label(
                        author_node,
                        author,
                        {
                            k: str(v) if isinstance(v, UUID) else v
                            for k, v in author_support.items()
                        },
                        item["metadata_dependencies"],
                    )
                    edge(
                        paper,
                        author_node,
                        "authored_by",
                        author_support,
                        item["metadata_dependencies"],
                    )
                entity_nodes = []
                for entity in entities:
                    normalized = " ".join(
                        unicodedata.normalize("NFKC", entity.label).casefold().split()
                    )
                    entity_node = node(entity.kind, normalized)
                    support = {
                        "kind": "text",
                        "chunk_id": cid,
                        "text_revision_id": tid,
                        "start_offset": chunk["start_offset"] + entity.start,
                        "end_offset": chunk["start_offset"] + entity.end,
                    }
                    label(
                        entity_node,
                        entity.label,
                        {k: str(v) if isinstance(v, UUID) else v for k, v in support.items()},
                        deps,
                    )
                    entity_nodes.append(entity_node)
                for claim in claims:
                    source = (
                        paper
                        if claim.source == "asset"
                        else chunk_node
                        if claim.source == "chunk"
                        else entity_nodes[int(claim.source)]
                    )
                    support = {
                        "kind": "text",
                        "chunk_id": cid,
                        "text_revision_id": tid,
                        "start_offset": chunk["start_offset"] + claim.start,
                        "end_offset": chunk["start_offset"] + claim.end,
                    }
                    edge(source, entity_nodes[claim.target], claim.predicate, support, deps)
                conn.execute(
                    graph_extractions.insert().values(
                        project_id=project_id,
                        view_id=view_id,
                        chunk_id=cid,
                        extractor_revision="single-slice-v1",
                        result_digest=proposal_digest,
                        dependencies=deps,
                    )
                )
            graph_digest = seal_graph_view(
                conn,
                project_id,
                view_id,
                chunk_ids,
                {item["chunk"]["id"]: item["text"] for item in actual},
            )
            live["graph_build"] = {
                "view_id": str(view_id),
                "digest": graph_digest,
                "vector_view_id": vector["view_id"],
                "profile_id": vector["profile_id"],
                "dependency_digest": dependency_digest,
            }
            if datetime.fromisoformat(live["lease_until"]) <= datetime.now(UTC):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            live["graph_build_claim"]["state"] = "succeeded"
            from rpb.adapters.runs import persist

            persist(conn, live)
            return copy.deepcopy(live["graph_build"])
    except BaseException as failure:
        try:
            record_failure(
                store, actor, project_id, run_id, attempt_id, "graph_build_claim", claim_id, failure
            )
        except Exception:
            # A revoked write fence may prevent any diagnostic update.
            pass
        raise
