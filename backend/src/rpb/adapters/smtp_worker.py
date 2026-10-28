"""Durable SMTP tests; expired/unknown executions never resend requests."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

import sqlalchemy as sa

from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.llm import event_record
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.security import execute_test, read_policy, record_diagnostic, test_config
from rpb.adapters.smtp import SMTP_ID, SMTPStore
from rpb.adapters.smtp_provider import SMTPProvider


class SMTPWorker:
    def __init__(self, store: SMTPStore, provider: SMTPProvider | None = None) -> None:
        self.store, self.provider = store, provider or SMTPProvider()

    def run_once(self) -> bool:
        store, now = self.store, datetime.now(UTC)
        tasks = store.tasks
        with store.account.engine.begin() as conn:
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
                conn.execute(
                    store.configs.update()
                    .where(
                        store.configs.c.id == SMTP_ID,
                        store.configs.c.revision == stale["config_revision"],
                        store.configs.c.refresh_task_id == stale["id"],
                        store.configs.c.refresh_attempt_id == stale["attempt_id"],
                        store.configs.c.oauth_status == "refreshing",
                    )
                    .values(oauth_status="reauthorization_required")
                )
                rev = uuid4()
                conn.execute(
                    tasks.update()
                    .where(tasks.c.id == stale["id"])
                    .values(
                        state="failed",
                        error="PROVIDER_RESULT_UNKNOWN",
                        revision=rev,
                        finished_at=now,
                        events=stale["events"] + [event_record("failed", rev, now)],
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
            policy = read_policy(conn)
            values = test_config(job["input"], policy)
            values["_test_policy"] = policy
            config = store.config(conn, job["owner_id"], str(SMTP_ID))
            values["_refresh"] = False
            if (
                config["data"].get("auth_type") == "token"
                and config["oauth_status"] == "connected"
                and config["revision"] == job["config_revision"]
                and config["credential_revision"] == job["credential_revision"]
                and store.permitted_actor(conn, job["owner_id"])
            ):
                try:
                    grant = store.decrypt(config["oauth_ciphertext"])
                    if datetime.fromisoformat(grant["expires_at"]) <= now + timedelta(seconds=30):
                        # Commit intent before rotating a remote credential. A crash requires
                        # reauthorization rather than replaying an indeterminate refresh.
                        values["_refresh"] = True
                        conn.execute(
                            store.configs.update()
                            .where(store.configs.c.id == SMTP_ID)
                            .values(
                                oauth_status="refreshing",
                                refresh_task_id=job["id"],
                                refresh_attempt_id=job["attempt_id"],
                            )
                        )
                except ProviderFailure, ValueError, KeyError:
                    pass
            rev = uuid4()
            conn.execute(
                tasks.update()
                .where(tasks.c.id == job["id"])
                .values(
                    state="running",
                    revision=rev,
                    input=values,
                    started_at=now,
                    lease_until=now + timedelta(seconds=values["timeout_seconds"] + 30),
                    events=job["events"] + [event_record("running", rev, now)],
                )
            )
        error = None
        attempts = 0
        result: dict[str, Any] = {}
        start = monotonic()
        credential_revision = job["credential_revision"]
        try:
            # The common governance lock orders revocation before the actual request.
            with store.account.engine.begin() as conn:
                conn.execute(
                    sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
                )
                row = (
                    conn.execute(sa.select(tasks).where(tasks.c.id == job["id"]).with_for_update())
                    .mappings()
                    .one()
                )
                config = store.config(conn, job["owner_id"], str(SMTP_ID))
                if row["lease_until"] <= datetime.now(UTC):
                    raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
                if (
                    not store.permitted_actor(conn, job["owner_id"])
                    or row["state"] != "running"
                    or row["attempt_id"] != job["attempt_id"]
                ):
                    raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
                if (
                    config["revision"] != job["config_revision"]
                    or config["credential_revision"] != job["credential_revision"]
                ):
                    raise ProviderFailure("CONFIG_CONNECTION_FAILED")
                secret = store.secret(config)
                if config["data"]["auth_type"] == "token":
                    if config["oauth_status"] != "connected" and not (
                        config["oauth_status"] == "refreshing"
                        and values["_refresh"]
                        and config["refresh_task_id"] == job["id"]
                        and config["refresh_attempt_id"] == job["attempt_id"]
                    ):
                        raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
                    grant = store.decrypt(config["oauth_ciphertext"])
                    if datetime.fromisoformat(grant["expires_at"]) <= datetime.now(UTC) + timedelta(
                        seconds=30
                    ):
                        try:
                            refreshed = store.oauth.exchange(
                                config["data"],
                                secret,
                                {
                                    "grant_type": "refresh_token",
                                    "refresh_token": grant["refresh_token"],
                                },
                                max(0.001, values["timeout_seconds"] - (monotonic() - start)),
                            )
                            store.save_grant(conn, job["owner_id"], config, refreshed, grant)
                            config = store.config(conn, job["owner_id"], str(SMTP_ID))
                            grant = store.decrypt(config["oauth_ciphertext"])
                            credential_revision = config["credential_revision"]
                            conn.execute(
                                tasks.update()
                                .where(tasks.c.id == job["id"])
                                .values(credential_revision=credential_revision)
                            )
                        except ProviderFailure as exc:
                            conn.execute(
                                store.configs.update()
                                .where(store.configs.c.id == SMTP_ID)
                                .values(oauth_status="reauthorization_required")
                            )
                            error = exc.code
                    secret = grant["access_token"]
                if error is None:
                    remaining = values["timeout_seconds"] - (monotonic() - start)
                    if remaining <= 0:
                        raise ProviderFailure("PROVIDER_TIMEOUT")
                    adapter = self.provider

                    class Execution:
                        def execute(
                            self,
                            data: dict[str, Any],
                            operation: str,
                            model: str | None,
                            credential: str,
                            authorize: Any,
                        ) -> dict[str, Any]:
                            with authorize():
                                return adapter.execute(data, credential, data["timeout_seconds"])

                    lease_until = row["lease_until"]

                    @contextmanager
                    def authorize() -> Any:
                        if datetime.now(UTC) >= lease_until:
                            raise ProviderFailure("PROVIDER_RESULT_UNKNOWN")
                        yield

                    try:
                        result, attempts = execute_test(
                            Execution(),
                            {**values, "timeout_seconds": remaining},
                            "test",
                            None,
                            secret,
                            authorize,
                            policy,
                        )
                    except ProviderFailure as exc:
                        error = exc.code
                    except Exception:
                        error = "PROVIDER_RESULT_UNKNOWN"

        except ProviderFailure as exc:
            error = exc.code
        except Exception:
            error = "PROVIDER_RESULT_UNKNOWN"
        with store.account.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            row = (
                conn.execute(sa.select(tasks).where(tasks.c.id == job["id"]).with_for_update())
                .mappings()
                .one()
            )
            if row["state"] != "running" or row["attempt_id"] != job["attempt_id"]:
                if values.get("_refresh"):
                    conn.execute(
                        store.configs.update()
                        .where(
                            store.configs.c.id == SMTP_ID,
                            store.configs.c.revision == job["config_revision"],
                            store.configs.c.refresh_task_id == job["id"],
                            store.configs.c.refresh_attempt_id == job["attempt_id"],
                            store.configs.c.oauth_status == "refreshing",
                        )
                        .values(oauth_status="reauthorization_required")
                    )
                return True
            config = store.config(conn, job["owner_id"], str(SMTP_ID))
            if not store.permitted_actor(conn, job["owner_id"]):
                error = "PERMISSION_RESOURCE_UNAVAILABLE"
            elif (
                config["revision"] != job["config_revision"]
                or config["credential_revision"] != credential_revision
            ):
                error = "CONFIG_CONNECTION_FAILED"
            if row["lease_until"] < datetime.now(UTC):
                error = "PROVIDER_RESULT_UNKNOWN"
            if (
                config["oauth_status"] == "refreshing"
                and config["revision"] == job["config_revision"]
                and config["refresh_task_id"] == job["id"]
                and config["refresh_attempt_id"] == job["attempt_id"]
            ):
                conn.execute(
                    store.configs.update()
                    .where(store.configs.c.id == SMTP_ID)
                    .values(oauth_status="reauthorization_required")
                )
            status, rev, now = "failed" if error else "succeeded", uuid4(), datetime.now(UTC)
            payload = {
                "status": status,
                "checked_at": now.isoformat().replace("+00:00", "Z"),
                "reason_code": error,
                "config_revision": str(job["config_revision"]),
                "credential_revision": str(credential_revision),
                "authenticated": bool(result.get("authenticated")) if not error else False,
            }
            conn.execute(
                tasks.update()
                .where(tasks.c.id == job["id"])
                .values(
                    state=status,
                    error=error,
                    result=payload,
                    revision=rev,
                    finished_at=now,
                    events=row["events"] + [event_record(status, rev, now)],
                )
            )
            record_diagnostic(
                conn,
                job["id"],
                policy,
                stage="test",
                status=status,
                error=error,
                elapsed_ms=int((monotonic() - start) * 1000),
                attempts=attempts,
                protocol="smtp",
            )
        return True
