"""Platform test policy and bounded, separately disposable diagnostics."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from threading import TIMEOUT_MAX
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Connection

from rpb.adapters.account import accounts
from rpb.adapters.auth import AccountStore
from rpb.adapters.llm import require_revision
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.project_commands import metadata
from rpb.modules.account_config.application.ports import AccountError

DEFAULTS: dict[str, Any] = {
    "connection_timeout_seconds": 30,
    "connection_retry_count": 0,
    "config_snapshot_retention_days": 30,
    "diagnostic_scope": "minimal",
}
configs = sa.Table(
    "security_configs",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Uuid, nullable=False),
    sa.Column("data", JSONB(none_as_null=True)),
)
audit = sa.Table(
    "security_audit",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("owner_id", sa.Uuid, nullable=False),
    sa.Column("revision", sa.Uuid, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("operation", sa.Text, nullable=False, server_default="save"),
    sa.Column("config_type", sa.Text, nullable=False, server_default="security"),
    sa.Column("result", sa.Text, nullable=False, server_default="succeeded"),
)
diagnostics = sa.Table(
    "security_diagnostics",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("task_id", sa.Uuid, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("data", JSONB, nullable=False),
)


def read_policy(conn: Connection) -> dict[str, Any]:
    """Read current policy without creating configuration or touching private assets."""
    row = conn.execute(sa.select(configs).where(configs.c.id == "system")).mappings().first()
    return {
        **DEFAULTS,
        **((row["data"] or {}) if row else {}),
        "_revision": str(row["revision"]) if row else "deployment-default",
    }


def validate(values: dict[str, Any]) -> dict[str, Any]:
    if set(values) != set(DEFAULTS):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    for name in ("connection_timeout_seconds", "config_snapshot_retention_days"):
        if type(values[name]) is not int or values[name] < 1:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
    if (
        type(values["connection_retry_count"]) is not int
        or not 0 <= values["connection_retry_count"] <= 5
    ):
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    if values["diagnostic_scope"] not in {"minimal", "standard"}:
        raise AccountError("VALIDATION_FIELD_INVALID", 422)
    return dict(values)


class SecurityStore:
    def __init__(self, account: AccountStore) -> None:
        self.account = account

    @contextmanager
    def event_lease(self, token: str, expected_actor: str | None = None) -> Iterator[None]:
        self.invoke("read", token, None, None, {}, None, expected_actor)
        yield

    def invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None = None,
    ) -> dict[str, Any]:
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and expected_actor != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
            if not conn.scalar(sa.select(accounts.c.is_admin).where(accounts.c.id == actor)):
                raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
            conn.execute(
                insert(configs)
                .values(id="system", revision=uuid4(), data=None)
                .on_conflict_do_nothing(index_elements=[configs.c.id])
            )
            row = (
                conn.execute(sa.select(configs).where(configs.c.id == "system").with_for_update())
                .mappings()
                .one()
            )
            revision, value = row["revision"], row["data"]
            if operation == "save":
                require_revision(revision, data.get("expected_revision"))
                value = validate({k: v for k, v in data.items() if k != "expected_revision"})
                revision = uuid4()
                prune_diagnostics(conn, value)
                conn.execute(
                    configs.update()
                    .where(configs.c.id == "system")
                    .values(revision=revision, data=value)
                )
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        owner_id=actor,
                        revision=revision,
                        occurred_at=datetime.now(UTC),
                    )
                )
            elif operation != "read":
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            return {
                "revision": str(revision),
                "configured": value is not None,
                "effective": {**DEFAULTS, **(value or {})},
            }


def test_config(config: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """A test-only copy: neither stored user configuration nor business inputs change."""
    return {
        **config,
        "timeout_seconds": min(
            config.get("timeout_seconds", policy["connection_timeout_seconds"]),
            policy["connection_timeout_seconds"],
            int(TIMEOUT_MAX) - 60,  # Keep runtime timers and lease arithmetic representable.
        ),
    }


def execute_test(
    provider: Any,
    config: dict[str, Any],
    operation: str,
    model: str | None,
    secret: str,
    authorize: Callable[[], AbstractContextManager[None]],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """One total budget; only adapter-proven pre-submit connection failures may retry."""
    bounded = test_config(config, policy)
    deadline = monotonic() + bounded["timeout_seconds"]
    for attempt in range(policy["connection_retry_count"] + 1):
        left = deadline - monotonic()
        if left <= 0:
            exhausted = ProviderFailure("PROVIDER_TIMEOUT")
            exhausted.attempts = attempt
            raise exhausted
        try:
            result = provider.execute(
                {**bounded, "timeout_seconds": left},
                operation,
                model,
                secret,
                authorize,
            )
            return result, attempt + 1
        except ProviderFailure as exc:
            exc.attempts = attempt + 1
            if (
                exc.submitted is not False
                or exc.code not in {"CONFIG_CONNECTION_FAILED", "PROVIDER_TIMEOUT"}
                or attempt >= policy["connection_retry_count"]
            ):
                raise
    raise AssertionError("Unreachable bounded retry exit")


def prune_diagnostics(conn: Connection, policy: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    # A very large allowed retention means nothing has expired, not datetime overflow.
    days = policy["config_snapshot_retention_days"]
    if days > (now - datetime.min.replace(tzinfo=UTC)).days:
        return
    cutoff = now - timedelta(days=days)
    conn.execute(diagnostics.delete().where(diagnostics.c.occurred_at < cutoff))


def record_diagnostic(
    conn: Connection,
    task_id: UUID,
    policy: dict[str, Any],
    *,
    stage: str,
    status: str,
    error: str | None,
    elapsed_ms: int,
    attempts: int,
    protocol: str,
) -> None:
    """Never derive diagnostics from raw provider responses, config or credentials."""
    now = datetime.now(UTC)
    prune_diagnostics(conn, policy)
    value: dict[str, Any] = {
        "task_id": str(task_id),
        "stage": stage if stage in {"test", "refresh"} else "test",
        "status": status if status in {"succeeded", "failed"} else "failed",
        "error": error
        if error
        in {
            "CONFIG_CONNECTION_FAILED",
            "CONFIG_SECRET_UNAVAILABLE",
            "PROVIDER_UNAVAILABLE",
            "PROVIDER_TIMEOUT",
            "PROVIDER_RATE_LIMITED",
            "PROVIDER_RESPONSE_INVALID",
            "PROVIDER_RESULT_UNKNOWN",
            "PERMISSION_RESOURCE_UNAVAILABLE",
            "VALIDATION_FIELD_INVALID",
        }
        else None,
    }
    if policy["diagnostic_scope"] == "standard":
        value.update(
            elapsed_ms=max(0, elapsed_ms),
            attempts=max(0, attempts),
            protocol=protocol if protocol in {"http", "smtp", "oauth"} else "http",
        )
    conn.execute(
        diagnostics.insert().values(id=uuid4(), task_id=task_id, occurred_at=now, data=value)
    )
