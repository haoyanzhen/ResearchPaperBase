"""Durable claim/dispatch/result phases; expired in-flight jobs fail without resending."""

import hashlib
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import sqlalchemy as sa
from cryptography.fernet import InvalidToken

from rpb.adapters.account import accounts
from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.llm import event_record
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.source_tables import configs, dispatch_limits, tasks
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

    def pacing_scope(self, job: dict[str, Any]) -> str:
        data = job["input"]
        if data["provider"] == "arxiv":
            return "arxiv-user:" + str(job["owner_id"])
        url = urlsplit(data["base_url"])
        endpoint = f"{url.hostname}:{url.port or (443 if url.scheme == 'https' else 80)}"
        return hashlib.sha256(
            (str(job["owner_id"]) + ":" + data["provider"] + ":" + endpoint).encode()
        ).hexdigest()

    @contextmanager
    def outbound_slot(self, job: dict[str, Any]) -> Iterator[None]:
        key = int.from_bytes(
            hashlib.sha256(
                (
                    "arxiv-public"
                    if job["input"]["provider"] == "arxiv"
                    else self.pacing_scope(job)
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
            actor = conn.execute(
                sa.select(accounts.c.enabled).where(accounts.c.id == job["owner_id"])
            ).scalar()
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
            if not actor or not config or config["deleted"]:
                raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
            if config["revision"] != job["config_revision"]:
                raise ProviderFailure("CONFIG_CONNECTION_FAILED")
            with self.store.account.engine.begin() as pacing:
                now = datetime.now(UTC)
                data = job["input"]
                rate = data["rate_limit_per_minute"] or PROVIDERS[data["provider"]]["rpm"]
                limits = [(self.pacing_scope(job), rate)]
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
                return bool(expired)
            job = dict(row)
            config = (
                conn.execute(sa.select(configs).where(configs.c.id == job["config_id"]))
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
            if not actor or not actor["enabled"] or not config or config["deleted"]:
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
            transition_revision = uuid4()
            conn.execute(
                tasks.update()
                .where(tasks.c.id == job["id"])
                .values(
                    state="running",
                    revision=transition_revision,
                    started_at=now,
                    lease_until=now + timedelta(seconds=30 + 30),
                    events=job["events"] + [event_record("running", transition_revision, now)],
                )
            )
        result = None
        if error is None:
            try:
                with self.outbound_slot(job):
                    result = self.provider.execute(
                        job["input"], job["operation"], None, secret, lambda: self.dispatch(job)
                    )
            except ProviderFailure as exc:
                error = exc.code
            except ParameterError:
                error = "VALIDATION_FIELD_INVALID"
            except Exception:
                # An unknown provider/transport exception is never automatically retried.
                error = "PROVIDER_RESULT_UNKNOWN"
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
            actor = (
                conn.execute(sa.select(accounts).where(accounts.c.id == job["owner_id"]))
                .mappings()
                .first()
            )
            if not actor or not actor["enabled"] or not config or config["deleted"]:
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
