"""Account governance, confirmed under the same lock as authentication and dispatch."""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import sqlalchemy as sa
from fastapi.encoders import jsonable_encoder
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from rpb.adapters.account import accounts
from rpb.adapters.auth import (
    ACCOUNT_GOVERNANCE_LOCK,
    AccountStore,
    digest,
    hash_password,
    metadata,
    sessions,
)
from rpb.adapters.llm import event_record
from rpb.adapters.smtp_tables import handshakes as smtp_handshakes
from rpb.adapters.smtp_tables import tasks as smtp_tasks  # noqa: F401
from rpb.adapters.source_tables import configs as source_configs
from rpb.adapters.source_tables import dispatch_limits
from rpb.adapters.source_tables import tasks as source_tasks
from rpb.adapters.source_worker import SourceWorker
from rpb.modules.account_config.application.ports import AccountError

previews = sa.Table(
    "account_action_previews",
    metadata,
    sa.Column("token_hash", sa.Text, primary_key=True),
    sa.Column("actor_id", sa.Uuid, nullable=False),
    sa.Column("target_id", sa.Uuid, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("revision", sa.Uuid, nullable=False),
    sa.Column("parameters", JSONB, nullable=False),
    sa.Column("view", JSONB, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("consumed", sa.Boolean, nullable=False),
)
audit = sa.Table(
    "account_governance_audit",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("actor_id", sa.Uuid, nullable=False),
    sa.Column("target_id", sa.Uuid, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("result", sa.Text, nullable=False),
)
commands = sa.Table(
    "account_reset_commands",
    metadata,
    sa.Column("actor_id", sa.Uuid, primary_key=True),
    sa.Column("target_id", sa.Uuid, primary_key=True),
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("fingerprint", sa.Text, nullable=False),
    sa.Column("operation_id", sa.Uuid, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
)

cleanups = sa.Table(
    "account_cleanup_records",
    metadata,
    sa.Column("target_id", sa.Uuid, primary_key=True),
    sa.Column("actor_id", sa.Uuid, nullable=False),
    sa.Column("fingerprint", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("operation_id", sa.Uuid, nullable=False),
)


def identity(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError, TypeError:
        raise AccountError("VALIDATION_BAD_REQUEST", 400) from None


def revision(row: Any, value: str | None) -> None:
    if not value:
        raise AccountError("STATE_REVISION_REQUIRED", 428)
    if str(row["revision"]) != value:
        raise AccountError("STATE_REVISION_CONFLICT", 412)


class AdminAccountStore:
    def __init__(self, account: AccountStore) -> None:
        self.account = account

    def view(self, conn: Any, row: Any) -> dict[str, Any]:
        result = {
            k: row[k]
            for k in (
                "id",
                "revision",
                "username",
                "email",
                "display_name",
                "enabled",
                "is_admin",
                "created_at",
                "updated_at",
            )
        }
        result["last_login_at"] = conn.scalar(
            sa.select(sa.func.max(sessions.c.created_at)).where(sessions.c.account_id == row["id"])
        )
        return dict(
            jsonable_encoder(
                result,
                custom_encoder={
                    datetime: lambda value: value.astimezone(UTC).isoformat().replace("+00:00", "Z")
                },
            )
        )

    def impact(self, conn: Any, target: UUID, action: str) -> str:
        facts: dict[str, Any] = {}
        if action in {"delete", "disable", "reset_password"}:
            for name in (
                "projects",
                "llm_configs",
                "llm_tasks",
                "source_configs",
                "source_tasks",
                "llm_selections",
            ):
                table = metadata.tables[name]
                columns = [
                    c
                    for c in table.c
                    if c.name
                    in {
                        "id",
                        "owner_id",
                        "revision",
                        "state",
                        "status",
                        "deleted",
                        "credential_revision",
                        "authority_epoch",
                    }
                ]
                facts[name] = sorted(
                    [
                        dict(row)
                        for row in conn.execute(
                            sa.select(*columns).where(table.c.owner_id == target)
                        ).mappings()
                    ],
                    key=str,
                )
            facts["sessions"] = sorted(
                [
                    dict(row)
                    for row in conn.execute(
                        sa.select(sessions.c.token_hash, sessions.c.revoked).where(
                            sessions.c.account_id == target
                        )
                    ).mappings()
                ],
                key=str,
            )
        if action in {"delete", "disable", "revoke_admin"}:
            for name in ("system_llm_tasks", "system_source_tasks", "smtp_tasks"):
                table = metadata.tables[name]
                facts[name] = [
                    dict(row)
                    for row in conn.execute(
                        sa.select(table.c.id, table.c.revision, table.c.state)
                        .where(table.c.owner_id == target, table.c.state.in_(["queued", "running"]))
                        .order_by(table.c.id)
                    ).mappings()
                ]
        if action in {"delete", "disable", "revoke_admin", "reset_password"}:
            facts["smtp_oauth_handshakes"] = [
                dict(row)
                for row in conn.execute(
                    sa.select(smtp_handshakes.c.state_hash, smtp_handshakes.c.expires_at)
                    .where(smtp_handshakes.c.owner_id == target, smtp_handshakes.c.used.is_(False))
                    .order_by(smtp_handshakes.c.state_hash)
                ).mappings()
            ]
        encoded = json.dumps(jsonable_encoder(facts), sort_keys=True)
        return str(uuid5(NAMESPACE_URL, digest(encoded)))

    def allowed(self, conn: Any, actor: UUID, row: Any, action: str) -> None:
        if action in {"enable", "disable", "delete"} and row["is_admin"]:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        if action in {"grant_admin", "revoke_admin"} and row["id"] == actor:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
        if action in {"disable", "delete", "revoke_admin"} and row["is_admin"] and row["enabled"]:
            count = conn.scalar(
                sa.select(sa.func.count())
                .select_from(accounts)
                .where(accounts.c.enabled.is_(True), accounts.c.is_admin.is_(True))
            )
            if count <= 1:
                raise AccountError("STATE_LAST_ADMIN_REQUIRED", 409)

    def invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None = None,
    ) -> Any:
        try:
            result = self._invoke(operation, token, csrf, target, data, key, expected_actor)
            if isinstance(result, dict) and "cleanup_target" in result:
                return self.cleanup(identity(result["cleanup_target"]))
            return result
        except IntegrityError:
            raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409) from None

    def _invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None,
    ) -> Any:
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and str(actor) != expected_actor:
                raise AccountError("AUTH_SESSION_INVALID", 401)
            if not conn.scalar(sa.select(accounts.c.is_admin).where(accounts.c.id == actor)):
                raise AccountError("PERMISSION_ADMIN_REQUIRED", 403)
            if operation == "list":
                rows = list(
                    conn.execute(
                        sa.select(accounts).order_by(
                            accounts.c.created_at.desc(), accounts.c.id.desc()
                        )
                    ).mappings()
                )
                start = 0
                if data.get("cursor"):
                    ids = [str(r["id"]) for r in rows]
                    if data["cursor"] not in ids:
                        raise AccountError("VALIDATION_BAD_REQUEST", 400)
                    start = ids.index(data["cursor"]) + 1
                page = rows[start : start + data["page_size"]]
                more = start + len(page) < len(rows)
                return {
                    "items": [self.view(conn, r) for r in page],
                    "next_cursor": str(page[-1]["id"]) if more else None,
                    "has_more": more,
                }
            target_id = identity(target or "")
            receipt = (
                conn.execute(sa.select(cleanups).where(cleanups.c.target_id == target_id))
                .mappings()
                .first()
            )
            fp = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            if receipt:
                if (
                    operation == "delete"
                    and receipt["actor_id"] == actor
                    and receipt["fingerprint"] == fp
                ):
                    return {"cleanup_target": str(target_id)}
                if data.get("action") != "delete" or receipt["state"] == "completed":
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            row = (
                conn.execute(sa.select(accounts).where(accounts.c.id == target_id))
                .mappings()
                .first()
            )
            if not row:
                raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
            action = data["action"]
            now = datetime.now(UTC)
            fp = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            if operation == "reset":
                if (
                    not key
                    or not 16 <= len(key) <= 128
                    or any(ord(c) < 32 or ord(c) > 126 for c in key)
                ):
                    raise AccountError("VALIDATION_BAD_REQUEST", 400)
                old = (
                    conn.execute(
                        sa.select(commands).where(
                            commands.c.actor_id == actor,
                            commands.c.target_id == target_id,
                            commands.c.key == key,
                        )
                    )
                    .mappings()
                    .first()
                )
                if old:
                    if old["fingerprint"] != fp:
                        raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                    if old["expires_at"] <= now:
                        raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                    return {
                        "reset_completed": True,
                        "password_disclosed": False,
                        "operation_id": str(old["operation_id"]),
                        "_expires": old["expires_at"].isoformat().replace("+00:00", "Z"),
                    }
            revision(row, data.get("expected_revision"))
            self.allowed(conn, actor, row, action)
            parameters = {"email": data["email"].strip()} if action == "change_email" else {}
            if operation == "preview":
                raw = secrets.token_urlsafe(32)
                expires = now + timedelta(minutes=10)
                risks = [
                    {
                        "id": "account_change",
                        "message": {
                            "delete": "将删除此普通账号及其Project和私人数据，不能撤销。",
                            "reset_password": (
                                "将生成新密码并撤销此账号已有会话；新密码仅本次响应显示。"
                            ),
                            "disable": "将禁用此普通账号并撤销已有会话。",
                        }.get(action, "将修改此账号的基础信息或访问权限，请核对目标账号。"),
                    }
                ]
                if receipt:
                    risks[0]["message"] = (
                        "此前删除清理尚未完成，账号已失效；确认后继续清理私人数据。"
                    )
                view = {
                    "confirmation_id": str(uuid4()),
                    "action": action,
                    "target": {"type": "account", "id": str(target_id)},
                    "subject_revision": str(row["revision"]),
                    "impact_revision": self.impact(conn, target_id, action),
                    "knowledge_version_id": None,
                    "candidate_revision": None,
                    "risks": risks,
                    "expires_at": expires.isoformat().replace("+00:00", "Z"),
                    "affected_items": [
                        {
                            "kind": "account_governance",
                            "account_id": str(target_id),
                            "account_revision": str(row["revision"]),
                            "operation": action,
                            "summary": "变更所选账号；不授予私人内容读取权。",
                        }
                    ],
                    "retained_items": [
                        {
                            "kind": "protected_scope",
                            "scope": scope,
                            "reason": "保留共享身份、其他用户数据及必要治理审计。",
                        }
                        for scope in ["shared_identity", "other_projects", "historical_evidence"]
                    ],
                    "blocked_reasons": [],
                }
                conn.execute(
                    previews.insert().values(
                        token_hash=digest(raw),
                        actor_id=actor,
                        target_id=target_id,
                        action=action,
                        revision=row["revision"],
                        parameters=parameters,
                        view=view,
                        expires_at=expires,
                        consumed=False,
                    )
                )
                return {**view, "confirmation_token": raw}
            confirmation = (
                conn.execute(
                    sa.select(previews).where(
                        previews.c.token_hash == digest(data.get("confirmation_token") or "")
                    )
                )
                .mappings()
                .first()
            )
            if not data.get("confirmation_token"):
                raise AccountError("STATE_CONFIRMATION_REQUIRED", 409)
            if (
                not confirmation
                or confirmation["actor_id"] != actor
                or confirmation["target_id"] != target_id
                or confirmation["action"] != action
                or confirmation["revision"] != row["revision"]
                or confirmation["parameters"] != parameters
                or confirmation["view"]["impact_revision"] != self.impact(conn, target_id, action)
                or confirmation["consumed"]
                or confirmation["expires_at"] <= now
            ):
                raise AccountError("STATE_CONFIRMATION_STALE", 409)
            if data.get("acknowledged_risk_ids") != ["account_change"]:
                raise AccountError("STATE_CONFIRMATION_REQUIRED", 409)
            values: dict[str, Any] = {"revision": uuid4(), "updated_at": now}
            password = None
            operation_id = uuid4()
            if action == "change_email":
                normalized = parameters["email"].casefold()
                if conn.scalar(
                    sa.select(accounts.c.id).where(
                        accounts.c.id != target_id,
                        sa.or_(
                            accounts.c.email_key == normalized,
                            accounts.c.username_key == normalized,
                        ),
                    )
                ):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                values.update(email=parameters["email"], email_key=parameters["email"].casefold())
            elif action in {"enable", "disable"}:
                values["enabled"] = action == "enable"
            elif action in {"grant_admin", "revoke_admin"}:
                values["is_admin"] = action == "grant_admin"
            elif action == "reset_password":
                password = secrets.token_urlsafe(24)
                values["password_hash"] = hash_password(password)
            if action in {"disable", "delete"}:
                # A later re-enable must never revive previously authorized work.
                from rpb.adapters.project import projects

                conn.execute(
                    projects.update()
                    .where(projects.c.owner_id == target_id)
                    .values(authority_epoch=projects.c.authority_epoch + 1)
                )
            if action in {"disable", "delete", "revoke_admin"}:
                for name in (
                    ("system_llm_tasks", "system_source_tasks", "smtp_tasks")
                    if action == "revoke_admin"
                    else (
                        "llm_tasks",
                        "source_tasks",
                        "system_llm_tasks",
                        "system_source_tasks",
                        "smtp_tasks",
                    )
                ):
                    table = metadata.tables[name]
                    for job in (
                        conn.execute(
                            sa.select(table).where(
                                table.c.owner_id == target_id,
                                table.c.state.in_(["queued", "running"]),
                            )
                        )
                        .mappings()
                        .all()
                    ):
                        rev = uuid4()
                        conn.execute(
                            table.update()
                            .where(table.c.id == job["id"])
                            .values(
                                state="failed",
                                error="PERMISSION_RESOURCE_UNAVAILABLE",
                                revision=rev,
                                finished_at=now,
                                lease_until=None,
                                events=job["events"] + [event_record("failed", rev, now)],
                            )
                        )
            if action in {"disable", "reset_password", "delete", "revoke_admin"}:
                conn.execute(
                    smtp_handshakes.update()
                    .where(smtp_handshakes.c.owner_id == target_id)
                    .values(used=True)
                )
            if action in {"disable", "reset_password", "delete"}:
                conn.execute(
                    sessions.update().where(sessions.c.account_id == target_id).values(revoked=True)
                )
            if action == "delete" and receipt:
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        actor_id=actor,
                        target_id=target_id,
                        action="delete_cleanup",
                        occurred_at=now,
                        result="resumed",
                    )
                )
                conn.execute(
                    cleanups.update()
                    .where(cleanups.c.target_id == target_id)
                    .values(actor_id=actor, fingerprint=fp, state="pending")
                )
                conn.execute(
                    previews.update()
                    .where(previews.c.token_hash == confirmation["token_hash"])
                    .values(consumed=True)
                )
                return {"cleanup_target": str(target_id)}
            if action == "delete":
                values["enabled"] = False
                conn.execute(accounts.update().where(accounts.c.id == target_id).values(**values))
                conn.execute(
                    cleanups.insert().values(
                        target_id=target_id,
                        actor_id=actor,
                        fingerprint=fp,
                        state="pending",
                        operation_id=operation_id,
                    )
                )
            else:
                conn.execute(accounts.update().where(accounts.c.id == target_id).values(**values))
            conn.execute(
                previews.update()
                .where(previews.c.token_hash == confirmation["token_hash"])
                .values(consumed=True)
            )
            conn.execute(
                audit.insert().values(
                    id=operation_id,
                    actor_id=actor,
                    target_id=target_id,
                    action=action,
                    occurred_at=now,
                    result="succeeded",
                )
            )
            if action == "reset_password":
                conn.execute(
                    commands.insert().values(
                        actor_id=actor,
                        target_id=target_id,
                        key=key,
                        fingerprint=fp,
                        operation_id=operation_id,
                        expires_at=now + timedelta(hours=48),
                    )
                )
                return {
                    "reset_completed": True,
                    "password_disclosed": True,
                    "operation_id": str(operation_id),
                    "new_password": password,
                    "_expires": (now + timedelta(hours=48)).isoformat().replace("+00:00", "Z"),
                }
            if action == "delete":
                return {"cleanup_target": str(target_id)}
            updated = (
                conn.execute(sa.select(accounts).where(accounts.c.id == target_id)).mappings().one()
            )
            return self.view(conn, updated)

    def cleanup(self, target_id: UUID) -> Any:
        try:
            with self.account.engine.begin() as conn:
                conn.execute(
                    sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
                )
                record = (
                    conn.execute(sa.select(cleanups).where(cleanups.c.target_id == target_id))
                    .mappings()
                    .one()
                )
                if record["state"] == "completed":
                    return {
                        "resource_id": str(target_id),
                        "revision": str(record["operation_id"]),
                        "task": None,
                    }
                # Governance was committed before cleanup. A failed cleanup can never
                # re-enable this account or make its tokens usable.
                for table in ("project_lifecycle_records", "project_create_commands"):
                    conn.execute(
                        sa.text(f"DELETE FROM {table} WHERE actor_id=:id"), {"id": target_id}
                    )
                conn.execute(
                    sa.text(
                        "DELETE FROM construction_workspaces WHERE project_id IN "
                        "(SELECT id FROM projects WHERE owner_id=:id)"
                    ),
                    {"id": target_id},
                )
                conn.execute(sa.text("DELETE FROM projects WHERE owner_id=:id"), {"id": target_id})
                conn.execute(sessions.delete().where(sessions.c.account_id == target_id))
                inputs = list(
                    conn.scalars(
                        sa.select(source_configs.c.data).where(
                            source_configs.c.owner_id == target_id
                        )
                    )
                )
                inputs += list(
                    conn.scalars(
                        sa.select(source_tasks.c.input).where(source_tasks.c.owner_id == target_id)
                    )
                )
                scopes = {
                    SourceWorker.pacing_scope({"owner_id": target_id, "input": data})
                    for data in inputs
                }
                scopes.add("arxiv-user:" + str(target_id))
                conn.execute(dispatch_limits.delete().where(dispatch_limits.c.scope.in_(scopes)))
                conn.execute(accounts.delete().where(accounts.c.id == target_id))
                conn.execute(
                    previews.delete().where(
                        sa.or_(previews.c.actor_id == target_id, previews.c.target_id == target_id)
                    )
                )
                conn.execute(
                    commands.delete().where(
                        sa.or_(commands.c.actor_id == target_id, commands.c.target_id == target_id)
                    )
                )
                conn.execute(
                    cleanups.update()
                    .where(cleanups.c.target_id == target_id)
                    .values(state="completed")
                )
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        actor_id=record["actor_id"],
                        target_id=target_id,
                        action="delete_cleanup",
                        occurred_at=datetime.now(UTC),
                        result="completed",
                    )
                )
                return {
                    "resource_id": str(target_id),
                    "revision": str(record["operation_id"]),
                    "task": None,
                }
        except Exception:
            with self.account.engine.begin() as conn:
                conn.execute(
                    sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
                )
                receipt = (
                    conn.execute(sa.select(cleanups).where(cleanups.c.target_id == target_id))
                    .mappings()
                    .one()
                )
                if receipt["state"] == "completed":
                    return {
                        "resource_id": str(target_id),
                        "revision": str(receipt["operation_id"]),
                        "task": None,
                    }
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        actor_id=receipt["actor_id"],
                        target_id=target_id,
                        action="delete_cleanup",
                        occurred_at=datetime.now(UTC),
                        result="failed",
                    )
                )
                conn.execute(
                    cleanups.update()
                    .where(cleanups.c.target_id == target_id)
                    .values(state="failed")
                )
            raise AccountError("STORAGE_INTERNAL_FAILURE", 500) from None
