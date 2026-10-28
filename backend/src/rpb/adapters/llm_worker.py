"""Durable claim/dispatch/result phases; expired in-flight jobs fail without resending."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Protocol
from uuid import uuid4

import sqlalchemy as sa
from cryptography.fernet import InvalidToken

from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.llm import LLMStore, event_record
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.security import (
    execute_test,
    prune_diagnostics,
    read_policy,
    record_diagnostic,
    test_config,
)
from rpb.modules.account_config.domain.parameters import ParameterError


class Provider(Protocol):
    def execute(
        self,
        config: dict[str, Any],
        operation: str,
        model: str | None,
        secret: str,
        authorize: Callable[[], AbstractContextManager[None]],
    ) -> dict[str, Any]: ...


class LLMWorker:
    def __init__(self, store: LLMStore, provider: Provider) -> None:
        self.store, self.provider = store, provider

    @contextmanager
    def dispatch(self, job: dict[str, Any]) -> Iterator[None]:
        configs, tasks = self.store.configs, self.store.tasks
        # Order revocation against the actual outbound request, not just queue claim.
        with self.store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            config = (
                conn.execute(sa.select(configs).where(configs.c.id == job["config_id"]))
                .mappings()
                .first()
            )
            current = (
                conn.execute(sa.select(tasks).where(tasks.c.id == job["id"])).mappings().first()
            )
            if (
                not current
                or current["state"] != "running"
                or current["attempt_id"] != job["attempt_id"]
                or current["lease_until"] <= datetime.now(UTC)
            ):
                raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
            if (
                not self.store.permitted_actor(conn, job["owner_id"])
                or not config
                or config["deleted"]
            ):
                raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
            if config["revision"] != job["config_revision"]:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            yield

    def run_once(self) -> bool:
        configs, tasks = self.store.configs, self.store.tasks
        now = datetime.now(UTC)
        with self.store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            expired = (
                conn.execute(
                    sa.select(tasks)
                    .where(tasks.c.state == "running", tasks.c.lease_until < now)
                    .with_for_update()
                )
                .mappings()
                .all()
            )
            for stale in expired:
                transition_revision = uuid4()
                conn.execute(
                    tasks.update()
                    .where(tasks.c.id == stale["id"])
                    .values(
                        state="failed",
                        revision=transition_revision,
                        finished_at=now,
                        error="PROVIDER_RESULT_UNKNOWN",
                        events=stale["events"] + [event_record("failed", transition_revision, now)],
                    )
                )
            row = (
                conn.execute(
                    sa.select(tasks)
                    .where(tasks.c.state == "queued")
                    .order_by(tasks.c.created_at, tasks.c.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                prune_diagnostics(conn, read_policy(conn))
                return bool(expired)
            job = dict(row)
            config = (
                conn.execute(sa.select(configs).where(configs.c.id == job["config_id"]))
                .mappings()
                .first()
            )
            error = None
            secret = ""
            if (
                not self.store.permitted_actor(conn, job["owner_id"])
                or not config
                or config["deleted"]
            ):
                error = "PERMISSION_RESOURCE_UNAVAILABLE"
            elif config["revision"] != job["config_revision"]:
                error = "CONFIG_CONNECTION_FAILED"
            elif not config["secret_ciphertext"] or not self.store.cipher:
                error = "CONFIG_SECRET_UNAVAILABLE"
            else:
                try:
                    secret = self.store.cipher.decrypt(config["secret_ciphertext"]).decode()
                except InvalidToken, UnicodeError:
                    error = "CONFIG_SECRET_UNAVAILABLE"
            policy = read_policy(conn)
            budget = test_config(job["input"], policy)["timeout_seconds"]
            job["input"] = {**job["input"], "_test_policy": policy}
            transition_revision = uuid4()
            conn.execute(
                tasks.update()
                .where(tasks.c.id == job["id"])
                .values(
                    state="running",
                    revision=transition_revision,
                    started_at=now,
                    lease_until=now + timedelta(seconds=budget + 30),
                    input=job["input"],
                    events=job["events"] + [event_record("running", transition_revision, now)],
                )
            )
        result = None
        started = monotonic()
        attempts = 0
        if error is None:
            try:
                result, attempts = execute_test(
                    self.provider,
                    job["input"],
                    job["operation"],
                    job["model_id"],
                    secret,
                    lambda: self.dispatch(job),
                    policy,
                )
            except ProviderFailure as exc:
                error = exc.code
                attempts = exc.attempts
            except ParameterError:
                error = "VALIDATION_FIELD_INVALID"
            except Exception:
                # An unknown provider/transport exception is never automatically retried.
                error = "PROVIDER_RESULT_UNKNOWN"
                attempts = max(attempts, 1)
        with self.store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            current = (
                conn.execute(sa.select(tasks).where(tasks.c.id == job["id"]).with_for_update())
                .mappings()
                .first()
            )
            if (
                not current
                or current["state"] != "running"
                or current["attempt_id"] != job["attempt_id"]
            ):
                return True
            config = (
                conn.execute(sa.select(configs).where(configs.c.id == job["config_id"]))
                .mappings()
                .first()
            )
            if (
                not self.store.permitted_actor(conn, job["owner_id"])
                or not config
                or config["deleted"]
            ):
                error = "PERMISSION_RESOURCE_UNAVAILABLE"
                result = None
            now = datetime.now(UTC)
            if current["lease_until"] < now:
                error = "PROVIDER_RESULT_UNKNOWN"
                result = None
            payload = {
                "status": "failed" if error else "succeeded",
                "checked_at": now.isoformat().replace("+00:00", "Z"),
                "reason_code": error,
                "models": [],
                "model_id": job["model_id"],
                "config_revision": str(job["config_revision"]),
                "credential_revision": str(job["credential_revision"]),
                "test_kind": job["operation"],
                **(
                    result
                    or {"discovered_models": [], "tested_parameters": None, "test_overrides": {}}
                ),
            }
            state = "failed" if error else "succeeded"
            record_diagnostic(
                conn,
                job["id"],
                policy,
                stage=job["operation"],
                status=state,
                error=error,
                elapsed_ms=int((monotonic() - started) * 1000),
                attempts=attempts,
                protocol="http",
            )
            transition_revision = uuid4()
            conn.execute(
                tasks.update()
                .where(tasks.c.id == job["id"])
                .values(
                    state=state,
                    revision=transition_revision,
                    finished_at=now,
                    result=payload,
                    error=error,
                    events=current["events"] + [event_record(state, transition_revision, now)],
                )
            )
        return True
