"""Durable claim/dispatch/result phases; expired in-flight jobs fail without resending."""

import hashlib
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import sqlalchemy as sa
from cryptography.fernet import InvalidToken

from rpb.adapters.account import accounts
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.llm import event_record
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.security import (
    execute_test,
    prune_diagnostics,
    read_policy,
    record_diagnostic,
    test_config,
)
from rpb.adapters.source_tables import dispatch_limits
from rpb.adapters.sources import SourceStore
from rpb.modules.account_config.domain.parameters import ParameterError
from rpb.modules.account_config.domain.sources import PROVIDERS


class Provider(Protocol):
    def execute(
        self,
        config: dict[str, Any],
        operation: str,
        model: str | None,
        secret: str,
        authorize: Callable[[], AbstractContextManager[None]],
    ) -> dict[str, Any]: ...


class SourceWorker:
    def __init__(self, store: SourceStore, provider: Provider) -> None:
        self.store, self.provider = store, provider

    @staticmethod
    def pacing_scope(job: dict[str, Any], *, system: bool = False) -> str:
        data = job["input"]
        owner = "system" if system else str(job["owner_id"])
        if data["provider"] == "arxiv":
            return "arxiv-user:" + owner
        url = urlsplit(data["base_url"])
        endpoint = f"{url.hostname}:{url.port or (443 if url.scheme == 'https' else 80)}"
        return hashlib.sha256(
            (owner + ":" + data["provider"] + ":" + endpoint).encode()
        ).hexdigest()

    @contextmanager
    def outbound_slot(self, job: dict[str, Any]) -> Iterator[None]:
        key = int.from_bytes(
            hashlib.sha256(
                (
                    "arxiv-public"
                    if job["input"]["provider"] == "arxiv"
                    else self.pacing_scope(job, system=self.store.system)
                ).encode()
            ).digest()[:8],
            signed=True,
        )
        with self.store.account.engine.connect() as conn:
            held = bool(conn.scalar(sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
            try:
                if not held:
                    raise ProviderFailure("PROVIDER_RATE_LIMITED")
                yield
            finally:
                if held:
                    conn.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": key})

    @contextmanager
    def dispatch(self, job: dict[str, Any]) -> Iterator[None]:
        # Order revocation against the actual outbound request, not just queue claim.
        with self.store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            actor = self.store.permitted_actor(conn, job["owner_id"])
            config = (
                conn.execute(
                    sa.select(self.store.configs).where(self.store.configs.c.id == job["config_id"])
                )
                .mappings()
                .first()
            )
            current = (
                conn.execute(sa.select(self.store.tasks).where(self.store.tasks.c.id == job["id"]))
                .mappings()
                .first()
            )
            if (
                not current
                or current["state"] != "running"
                or current["attempt_id"] != job["attempt_id"]
                or current["lease_until"] <= datetime.now(UTC)
            ):
                raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
            if not actor or not config or config["deleted"]:
                raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
            if config["revision"] != job["config_revision"]:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            with self.store.account.engine.begin() as pacing:
                now = datetime.now(UTC)
                data = job["input"]
                rate = data["rate_limit_per_minute"] or PROVIDERS[data["provider"]]["rpm"]
                limits = [(self.pacing_scope(job, system=self.store.system), rate)]
                if data["provider"] == "arxiv":
                    limits.append(("arxiv-public", 20))
                for scope, budget in limits:
                    next_at = pacing.scalar(
                        sa.select(dispatch_limits.c.next_at).where(dispatch_limits.c.scope == scope)
                    )
                    if next_at and next_at > now:
                        raise ProviderFailure("PROVIDER_RATE_LIMITED")
                    values = {"next_at": now + timedelta(seconds=60 / budget)}
                    if next_at:
                        pacing.execute(
                            dispatch_limits.update()
                            .where(dispatch_limits.c.scope == scope)
                            .values(**values)
                        )
                    else:
                        pacing.execute(dispatch_limits.insert().values(scope=scope, **values))
            yield

    def run_once(self) -> bool:
        now = datetime.now(UTC)
        with self.store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            expired = (
                conn.execute(
                    sa.select(self.store.tasks)
                    .where(
                        self.store.tasks.c.state == "running", self.store.tasks.c.lease_until < now
                    )
                    .with_for_update()
                )
                .mappings()
                .all()
            )
            for stale in expired:
                transition_revision = uuid4()
                conn.execute(
                    self.store.tasks.update()
                    .where(self.store.tasks.c.id == stale["id"])
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
                    sa.select(self.store.tasks)
                    .where(self.store.tasks.c.state == "queued")
                    .order_by(self.store.tasks.c.created_at, self.store.tasks.c.id)
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
                conn.execute(
                    sa.select(self.store.configs).where(self.store.configs.c.id == job["config_id"])
                )
                .mappings()
                .first()
            )
            actor = (
                conn.execute(sa.select(accounts).where(accounts.c.id == job["owner_id"]))
                .mappings()
                .first()
            )
            error = None
            secret = ""
            if (
                not actor
                or not actor["enabled"]
                or (self.store.system and not actor["is_admin"])
                or not config
                or config["deleted"]
            ):
                error = "PERMISSION_RESOURCE_UNAVAILABLE"
            elif config["revision"] != job["config_revision"]:
                error = "CONFIG_CONNECTION_FAILED"
            elif config["data"]["access_mode"] == "anonymous":
                pass
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
                self.store.tasks.update()
                .where(self.store.tasks.c.id == job["id"])
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
                with self.outbound_slot(job):
                    result, attempts = execute_test(
                        self.provider,
                        job["input"],
                        job["operation"],
                        None,
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
                conn.execute(
                    sa.select(self.store.tasks)
                    .where(self.store.tasks.c.id == job["id"])
                    .with_for_update()
                )
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
                conn.execute(
                    sa.select(self.store.configs).where(self.store.configs.c.id == job["config_id"])
                )
                .mappings()
                .first()
            )
            actor = (
                conn.execute(sa.select(accounts).where(accounts.c.id == job["owner_id"]))
                .mappings()
                .first()
            )
            if (
                not actor
                or not actor["enabled"]
                or (self.store.system and not actor["is_admin"])
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
                "config_revision": str(job["config_revision"]),
                "credential_revision": str(job["credential_revision"]),
                "access_mode": job["input"]["access_mode"],
                **(result or {}),
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
                self.store.tasks.update()
                .where(self.store.tasks.c.id == job["id"])
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
