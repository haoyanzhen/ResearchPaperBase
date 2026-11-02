"""Claim once, freeze inside the slot transaction, reauthorize every external send."""

import copy
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from cryptography.fernet import InvalidToken

from rpb.adapters import source_tables, system_source_tables
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.construction_slots import acquire
from rpb.adapters.knowledge_tables import heads
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.project import projects
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.runs import ACTIVE, RunStore, persist, transition
from rpb.adapters.search_terms import now
from rpb.adapters.source_worker import SourceWorker
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.domain.parameters import ParameterError
from rpb.modules.account_config.domain.sources import PROVIDERS


class RunWorker:
    def __init__(self, store: RunStore, provider: Any) -> None:
        self.store, self.provider = store, provider

    @staticmethod
    def lock(conn: Any) -> None:
        conn.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )

    def source(self, conn: Any, run: Any, ref: Any) -> Any:
        table = source_tables.configs if ref["source"] == "user" else system_source_tables.configs
        row = (
            conn.execute(
                sa.select(table).where(
                    table.c.id == UUID(ref["config_id"]), table.c.deleted.is_(False)
                )
            )
            .mappings()
            .first()
        )
        if not row or (ref["source"] == "user" and str(row["owner_id"]) != run["owner_id"]):
            raise ProviderFailure("CONFIG_CONNECTION_FAILED")
        frozen = ref.get("config")
        data = row["data"]
        if not data["enabled"] or (
            frozen and any(data[k] != frozen[k] for k in ("provider", "base_url", "access_mode"))
        ):
            raise ProviderFailure("CONFIG_CONNECTION_FAILED")
        secret = ""
        if data["access_mode"] == "api_key":
            cipher = self.store.terms.sources.store.cipher
            try:
                if not cipher or not row["secret_ciphertext"]:
                    raise ValueError("secret")
                secret = cipher.decrypt(row["secret_ciphertext"]).decode()
            except InvalidToken, ValueError, UnicodeError:
                raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE") from None
        return dict(data), secret

    @contextmanager
    def dispatch(self, run_id: str, attempt: str, ref: Any, secret: str) -> Any:
        with self.store.account.engine.begin() as conn:
            self.lock(conn)
            row = (
                conn.execute(sa.select(runs).where(runs.c.id == UUID(run_id)).with_for_update())
                .mappings()
                .first()
            )
            if not row:
                raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
            run = copy.deepcopy(row["payload"])
            project = (
                conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                .mappings()
                .one()
            )
            if (
                run["status"] != "running"
                or run["attempt_id"] != attempt
                or project["status"] != "active"
                or project["authority_epoch"] != run["authority_epoch"]
                or not self.store.terms.llm.permitted_actor(conn, UUID(run["owner_id"]))
            ):
                raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
            if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
                raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
            _, current_secret = self.source(conn, run, ref)
            if current_secret != secret:
                raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
            # Shared provider pacing also covers configuration tests.
            with self.store.account.engine.begin() as pacing:
                stamp = datetime.now(UTC)
                config = ref["config"]
                rate = config["rate_limit_per_minute"] or PROVIDERS[config["provider"]]["rpm"]
                scope = SourceWorker.pacing_scope(
                    {"input": config, "owner_id": run["owner_id"]}, system=ref["source"] == "system"
                )
                limits = [(scope, rate)]
                if config["provider"] == "arxiv":
                    limits.append(("arxiv-public", 20))
                for scope, budget in limits:
                    next_at = pacing.scalar(
                        sa.select(source_tables.dispatch_limits.c.next_at).where(
                            source_tables.dispatch_limits.c.scope == scope
                        )
                    )
                    if next_at and next_at > stamp:
                        raise ProviderFailure("PROVIDER_RATE_LIMITED", submitted=False)
                    from sqlalchemy.dialects.postgresql import insert

                    pacing.execute(
                        insert(source_tables.dispatch_limits)
                        .values(scope=scope, next_at=stamp + timedelta(seconds=60 / budget))
                        .on_conflict_do_update(
                            index_elements=[source_tables.dispatch_limits.c.scope],
                            set_={"next_at": stamp + timedelta(seconds=60 / budget)},
                        )
                    )
            yield

    def run_once(self) -> bool:
        selected = None
        with self.store.account.engine.begin() as conn:
            self.lock(conn)
            rows = list(
                conn.execute(
                    sa.select(runs)
                    .where(runs.c.status.in_(ACTIVE))
                    .order_by(runs.c.created_at, runs.c.id)
                    .with_for_update()
                ).mappings()
            )
            occupied = set(
                conn.scalars(
                    sa.select(slots.c.project_id).where(slots.c.occupant_run_id.is_not(None))
                )
            )
            for row in rows:
                run = copy.deepcopy(row["payload"])
                project = (
                    conn.execute(sa.select(projects).where(projects.c.id == row["project_id"]))
                    .mappings()
                    .one()
                )
                self.store.revoke(conn, project, run)
                if run["status"] not in ACTIVE:
                    still_occupied = conn.scalar(
                        sa.select(slots.c.occupant_run_id).where(
                            slots.c.project_id == row["project_id"]
                        )
                    )
                    if still_occupied is None:
                        occupied.discard(row["project_id"])
                    continue
                if run.get("phase", "retrieval") != "retrieval":
                    continue
                if run["status"] == "running" and datetime.fromisoformat(
                    run["lease_until"]
                ) <= datetime.now(UTC):
                    if run.get("error") != "PROVIDER_RESULT_UNKNOWN":
                        transition(run, "running", "PROVIDER_RESULT_UNKNOWN")
                        persist(conn, run)
                    continue
                if selected or run["status"] != "queued" or row["project_id"] in occupied:
                    continue
                try:
                    terms, resolution, model = self.store.resolve(
                        conn, UUID(run["owner_id"]), project, run["request"]
                    )
                    source_configs = {}
                    for term in resolution["executable"]:
                        for ref in term["sources"]:
                            binding = ref["source"] + ":" + ref["config_id"]
                            config, _ = self.source(conn, run, ref)
                            source_configs[binding] = {**ref, "config": config}
                    run["resolution"] = resolution
                    run["source_configs"] = source_configs
                    run["model_config"] = copy.deepcopy(model["data"])
                    if run["request"].get("pdf_extraction_engine") == "llm_text_cleanup":
                        from rpb.adapters.pdf_cleanup_budget import new_budget
                        from rpb.adapters.pdf_cleanup_capacity import effective_config
                        from rpb.modules.account_config.domain.context_capacity import (
                            context_window,
                        )

                        selected_model = run["request"]["model_selection"]["model_id"]
                        cleanup_config, output, defaulted = effective_config(
                            model["data"], selected_model
                        )
                        capacity = context_window(model["data"], selected_model)
                        cleanup_config.setdefault("model_context_windows", {})[selected_model] = (
                            capacity
                        )
                        run["cleanup_model_config"] = cleanup_config
                        run["cleanup_settings"] = {
                            "engine_id": "llm_text_cleanup",
                            "engine_revision": "1",
                            "context_window_tokens": capacity,
                            "output_tokens": output,
                            "output_defaulted": defaulted,
                            "budget_limits": new_budget()["limits"],
                        }
                    stamp = now()
                    acquire(conn, run)
                    base_id = conn.scalar(
                        sa.select(heads.c.version_id).where(heads.c.project_id == project["id"])
                    )
                    run["input_snapshot"] = {
                        "mode": "retrieval",
                        "selected_terms": terms,
                        "supplement_ids": [],
                        "pending_revision_ids": [],
                        "retrieval_range": run["request"]["retrieval_range"],
                        "result_limit_per_source": run["request"]["result_limit_per_source"],
                        "resolved_sources": [
                            {
                                "source_kind": "provider",
                                "provider_config_ref": {
                                    "source": r["source"],
                                    "config_id": r["config_id"],
                                },
                                "url": None,
                                "supplement_id": None,
                                "search_term_id": None,
                                "retrieved_at": None,
                            }
                            for r in source_configs.values()
                        ],
                        "graph_mode": run["request"]["graph_mode"],
                        "base_knowledge_version_id": str(base_id) if base_id else None,
                        "frozen_at": stamp,
                    }
                    run["config_snapshot"] = {
                        "model_selection": run["request"]["model_selection"],
                        "parameters": copy.deepcopy(model["data"]["parameters"]),
                        "config_revision": str(model["revision"]),
                        "resolved_source_config_revisions": [
                            {"config_id": r["config_id"], "revision": r["config_revision"]}
                            for r in source_configs.values()
                        ],
                        "captured_at": stamp,
                    }
                    if run.get("cleanup_settings"):
                        run["config_snapshot"]["pdf_cleanup"] = run["cleanup_settings"]
                    run.update(
                        effective_input_revision=str(uuid4()),
                        started_at=stamp,
                        lease_until=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                    )
                    transition(run, "running")
                    persist(conn, run)
                    selected = copy.deepcopy(run)
                    occupied.add(row["project_id"])
                except ParameterError:
                    transition(run, "failed", "CONFIG_CONNECTION_FAILED")
                    persist(conn, run)
                except (AccountError, ProviderFailure) as exc:
                    if exc.code == "LOCK_CONSTRUCTION_OCCUPIED":
                        continue
                    transition(run, "failed", exc.code)
                    persist(conn, run)
        if not selected:
            return False
        candidates, results = [], []
        exhausted_sources = []
        budgets = {
            k: selected["request"]["result_limit_per_source"] for k in selected["source_configs"]
        }
        terms = {t["term_id"]: t["content"] for t in selected["input_snapshot"]["selected_terms"]}
        for term in selected["resolution"]["executable"]:
            for ref in term["sources"]:
                binding = ref["source"] + ":" + ref["config_id"]
                source = selected["source_configs"][binding]
                result = {
                    "term_id": term["term_id"],
                    "source": ref["source"],
                    "config_id": ref["config_id"],
                    "count": 0,
                    "status": "succeeded",
                    "error": None,
                }
                if budgets[binding] == 0:
                    result.update(status="skipped", error="budget_exhausted")
                    results.append(result)
                    continue
                try:

                    def credential() -> str:
                        with self.store.account.engine.connect() as current_connection:
                            return str(self.source(current_connection, selected, source)[1])

                    output = self.provider.search(
                        source["config"],
                        credential,
                        terms[term["term_id"]]["query"],
                        selected["request"]["retrieval_range"],
                        budgets[binding],
                        lambda current_secret: self.dispatch(
                            selected["id"], selected["attempt_id"], source, current_secret
                        ),
                    )
                    skipped = output.get("skipped_date", 0)
                    if (
                        not isinstance(output.get("items"), list)
                        or len(output["items"]) > budgets[binding]
                        or type(skipped) is not int
                        or skipped < 0
                    ):
                        raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
                    budgets[binding] -= len(output["items"])
                    result.update(
                        count=len(output["items"]),
                        skipped_date=skipped,
                        limited=output.get("limited", False),
                    )
                    if output.get("exhausted") is True:
                        exhausted_sources.append(
                            (term["term_id"], ref["source"], ref["config_id"], result["count"])
                        )
                    for metadata in output["items"]:
                        candidates.append(
                            {
                                "id": str(uuid4()),
                                "revision": str(uuid4()),
                                "kind": "paper",
                                "metadata": metadata,
                                "source": {
                                    "source_kind": "provider",
                                    "provider_config_ref": {
                                        "source": ref["source"],
                                        "config_id": ref["config_id"],
                                    },
                                    "url": metadata.get("url"),
                                    "supplement_id": None,
                                    "search_term_id": term["term_id"],
                                    "retrieved_at": now(),
                                },
                                "screening": {
                                    "score": None,
                                    "score_scale": None,
                                    "valid": None,
                                    "threshold_source": None,
                                    "reason": None,
                                },
                            }
                        )
                except ProviderFailure as exc:
                    result.update(status="failed", error=exc.code)
                results.append(result)
        with self.store.account.engine.begin() as conn:
            self.lock(conn)
            final_row = (
                conn.execute(
                    sa.select(runs).where(runs.c.id == UUID(selected["id"])).with_for_update()
                )
                .mappings()
                .first()
            )
            if not final_row:
                return True
            run = copy.deepcopy(final_row["payload"])
            project = (
                conn.execute(sa.select(projects).where(projects.c.id == final_row["project_id"]))
                .mappings()
                .one()
            )
            self.store.revoke(conn, project, run)
            if run["status"] != "running" or run["attempt_id"] != selected["attempt_id"]:
                return True
            if datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
                transition(run, "running", "PROVIDER_RESULT_UNKNOWN")
            else:
                rejected_bindings = set()
                for result in results:
                    binding = result["source"] + ":" + result["config_id"]
                    try:
                        self.source(conn, run, selected["source_configs"][binding])
                    except ProviderFailure as exc:
                        result.update(status="failed", error=exc.code, count=0)
                        rejected_bindings.add(binding)
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate["source"]["provider_config_ref"]["source"]
                    + ":"
                    + candidate["source"]["provider_config_ref"]["config_id"]
                    not in rejected_bindings
                ]
                run["candidates"], run["source_results"] = candidates, results
                run["exhausted_sources"] = exhausted_sources
                # Earlier workers did not check providers' partial-page/continuation markers.
                run["retrieval_proof_version"] = 2
                if any(r["status"] == "succeeded" for r in results):
                    revision = str(uuid4())
                    run["candidate_revision"] = revision
                    run["candidate_version"] = {
                        "state": "preparing",
                        "revision": revision,
                        "closing_reason": None,
                    }
                    run["waiting"] = {"id": str(uuid4()), "revision": str(uuid4())}
                    transition(run, "waiting_user")
                else:
                    transition(run, "failed", "CONFIG_CONNECTION_FAILED")
            persist(conn, run)
        return True
