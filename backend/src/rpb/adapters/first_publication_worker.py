"""Dispatch a confirmed paper build once, including its final publication check."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.knowledge_build_failure import BuildClaimChanged, record_failure
from rpb.adapters.knowledge_graph_builder import build_graph_view
from rpb.adapters.knowledge_vector_builder import build_vector_view
from rpb.adapters.run_tables import runs
from rpb.adapters.runs import persist


class FirstPublicationWorker:
    def __init__(self, store: Any, root: Path, embedding: Any, graph: Any):
        self.store, self.root, self.embedding, self.graph = store, root, embedding, graph
        self.root.mkdir(parents=True, exist_ok=True)
        store.first_publication_enabled = True

    def run_once(self) -> bool:
        with self.store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            snapshot = runs.c.payload["input_snapshot"]
            selected = runs.c.payload["ingestion_confirmation"]["preview"]["valid_papers"]
            run = conn.scalar(
                sa.select(runs.c.payload)
                .where(
                    runs.c.status == "running",
                    runs.c.payload["phase"].astext == "knowledge_build",
                    sa.or_(
                        snapshot["base_knowledge_version_id"].astext.is_(None),
                        sa.and_(
                            snapshot["mode"].astext == "retrieval",
                            snapshot["graph_mode"].astext == "incremental",
                            snapshot["pending_revision_ids"] == [],
                            snapshot["supplement_ids"] == [],
                            sa.func.jsonb_typeof(selected) == "array",
                            selected != [],
                        ),
                    ),
                    sa.or_(
                        ~runs.c.payload.has_key("publication_claim"),
                        sa.and_(
                            runs.c.payload["publication_claim"]["state"].astext == "running",
                            sa.cast(
                                runs.c.payload["lease_until"].astext, sa.DateTime(timezone=True)
                            )
                            <= sa.func.now(),
                        ),
                    ),
                )
                .order_by(runs.c.created_at)
                .limit(1)
            )
            if not run:
                return False
            actor, project, identity, attempt = (
                UUID(run[k]) for k in ("owner_id", "project_id", "id", "attempt_id")
            )
            if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
                from rpb.adapters.runs import transition

                run.setdefault("publication_claim", {"id": str(uuid4())})["state"] = "unknown"
                transition(run, "running", "PROVIDER_RESULT_UNKNOWN")
                persist(conn, run)
                return True
            claim = str(uuid4())
            run["publication_claim"] = {"state": "running", "id": claim}
            persist(conn, run)
        args = (self.store, self.root, actor, project, identity, attempt)
        try:
            build_vector_view(*args, self.embedding, publication_claim_id=claim)
            build_graph_view(*args, self.graph, publication_claim_id=claim)
            ready = build_graph_view(
                *args,
                self.graph,
                publish=True,
                tokenizer_factory=self.embedding,
                publication_claim_id=claim,
            )
            from rpb.adapters.first_publication import commit_ready

            commit_ready(
                self.store,
                actor,
                project,
                identity,
                attempt,
                ready["read_barrier_id"],
                claim,
                ready["readback_digest"],
            )
        except BuildClaimChanged:
            return True
        except Exception as failure:
            record_failure(
                self.store, actor, project, identity, attempt, "publication_claim", claim, failure
            )
        return True
