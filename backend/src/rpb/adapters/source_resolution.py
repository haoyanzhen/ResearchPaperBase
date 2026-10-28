"""Read-only source resolution seam; real Run consumers must freeze this result at start."""

from typing import Any

import sqlalchemy as sa
from cryptography.fernet import InvalidToken

from rpb.adapters import source_tables, system_source_tables
from rpb.adapters.sources import SourceStore
from rpb.modules.account_config.application.ports import AccountError


class SourceResolver:
    def __init__(self, store: SourceStore) -> None:
        self.store = store

    def resolve(
        self, token: str, policy: dict[str, Any] | None = None, expected_actor: str | None = None
    ) -> dict[str, Any]:
        policy = {"mode": "all_resolvable"} if policy is None else policy
        if not isinstance(policy, dict) or set(policy) - {"mode", "source_refs"}:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        mode = policy.get("mode")
        refs = policy.get("source_refs")
        if (
            not isinstance(mode, str)
            or mode not in {"all_resolvable", "selected"}
            or (mode == "all_resolvable" and "source_refs" in policy)
        ):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        chosen: set[tuple[str, str]] = set()
        if mode == "selected":
            if not isinstance(refs, list) or not refs:
                raise AccountError("VALIDATION_FIELD_INVALID", 422)
            for ref in refs:
                if (
                    not isinstance(ref, dict)
                    or set(ref) != {"source", "config_id"}
                    or not isinstance(ref.get("source"), str)
                    or ref.get("source") not in {"user", "system"}
                    or not isinstance(ref.get("config_id"), str)
                ):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                chosen.add((ref["source"], ref["config_id"]))
        with self.store.account.authorized_connection(token, None) as (conn, actor):
            if expected_actor is not None and str(actor) != expected_actor:
                raise AccountError("AUTH_SESSION_INVALID", 401)
            personal = list(
                conn.execute(
                    sa.select(source_tables.configs)
                    .where(
                        source_tables.configs.c.owner_id == actor,
                        source_tables.configs.c.deleted.is_(False),
                    )
                    .order_by(source_tables.configs.c.id)
                ).mappings()
            )
            providers = {row["data"]["provider"] for row in personal}
            system = list(
                conn.execute(
                    sa.select(system_source_tables.configs)
                    .where(system_source_tables.configs.c.deleted.is_(False))
                    .order_by(system_source_tables.configs.c.id)
                ).mappings()
            )
            candidates = [("user", row) for row in personal] + [
                ("system", row) for row in system if row["data"]["provider"] not in providers
            ]
            identities = {(scope, str(row["id"])) for scope, row in candidates}
            if mode == "selected" and not chosen <= identities:
                # Do not expose private foreign IDs or silently replace an explicit selection.
                raise AccountError("CONFIG_CONNECTION_FAILED", 409)
            resolved, rejected = [], []
            for scope, row in candidates:
                if mode == "selected" and (scope, str(row["id"])) not in chosen:
                    continue
                data = row["data"]
                reason = None
                if not data["enabled"]:
                    reason = "CONFIG_SOURCE_DISABLED"
                elif data["access_mode"] == "api_key":
                    try:
                        if not self.store.cipher or not row["secret_ciphertext"]:
                            raise ValueError("missing")
                        self.store.cipher.decrypt(row["secret_ciphertext"]).decode()
                    except InvalidToken, UnicodeError, ValueError:
                        reason = "CONFIG_SECRET_UNAVAILABLE"
                table = source_tables.tasks if scope == "user" else system_source_tables.tasks
                last = (
                    conn.execute(
                        sa.select(table)
                        .where(
                            table.c.config_id == row["id"],
                            table.c.config_revision == row["revision"],
                            table.c.credential_revision == row["credential_revision"],
                            table.c.state.in_(["succeeded", "failed"]),
                            sa.or_(
                                table.c.error.is_(None),
                                table.c.error != "PERMISSION_RESOURCE_UNAVAILABLE",
                            ),
                        )
                        .order_by(table.c.created_at.desc(), table.c.id.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if not reason and last and last["state"] == "failed":
                    reason = last["error"] or "CONFIG_CONNECTION_FAILED"
                item = {
                    "source": scope,
                    "config_id": str(row["id"]),
                    "provider": data["provider"],
                    "config_revision": str(row["revision"]),
                    "credential_revision": str(row["credential_revision"]),
                    "enabled": data["enabled"],
                    "access_mode": data["access_mode"],
                    "rate_limit_per_minute": data["rate_limit_per_minute"],
                }
                if reason:
                    rejected.append({**item, "reason_code": reason})
                else:
                    resolved.append(item)
            return {
                "reason_code": "CONFIG_MISSING" if not candidates else None,
                "sources": resolved,
                "rejected": rejected,
                "valid": bool(resolved) and not (mode == "selected" and rejected),
            }
