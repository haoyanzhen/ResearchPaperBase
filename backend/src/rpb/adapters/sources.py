"""Private research source configurations and durable diagnostic tasks."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from rpb.adapters.llm import LLMStore, event_record, public_error, require_revision, uuid_value
from rpb.adapters.source_tables import audit, commands, configs, tasks
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.domain.sources import SourceError, validate_source


class SourceStore(LLMStore):
    def config(self, conn: Connection, actor: UUID, identity: str) -> dict[str, Any]:
        row = (
            conn.execute(
                sa.select(configs).where(
                    configs.c.id == uuid_value(identity),
                    configs.c.owner_id == actor,
                    configs.c.deleted.is_(False),
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        return dict(row)

    def task(self, conn: Connection, actor: UUID, identity: str) -> dict[str, Any]:
        row = (
            conn.execute(
                sa.select(tasks).where(
                    tasks.c.id == uuid_value(identity), tasks.c.owner_id == actor
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        self.config(conn, actor, str(row["config_id"]))
        return dict(row)

    def view(self, conn: Connection, actor: UUID, row: dict[str, Any]) -> dict[str, Any]:
        tested = (
            conn.execute(
                sa.select(tasks)
                .where(
                    tasks.c.config_id == row["id"],
                    tasks.c.config_revision == row["revision"],
                    tasks.c.credential_revision == row["credential_revision"],
                    tasks.c.operation == "test",
                    tasks.c.state.in_(["succeeded", "failed"]),
                )
                .order_by(tasks.c.created_at.desc(), tasks.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return {
            "id": str(row["id"]),
            "revision": str(row["revision"]),
            "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
            "updated_at": row["updated_at"].isoformat().replace("+00:00", "Z"),
            **row["data"],
            "secret": {"configured": row["secret_ciphertext"] is not None, "hint": None},
            "connection_status": "available"
            if tested and tested["state"] == "succeeded"
            else "unavailable"
            if tested
            else "untested",
            "last_test_at": tested["finished_at"].isoformat().replace("+00:00", "Z")
            if tested and tested["finished_at"]
            else None,
        }

    def task_view(self, row: dict[str, Any]) -> dict[str, Any]:
        identity = str(row["id"])
        base = "/api/v1/tasks/" + identity
        result = (
            []
            if row["result"] is None
            else [{"type": "connection_test", "id": identity, "url": base + "/result"}]
        )
        return {
            "task_id": identity,
            "attempt_id": str(row["attempt_id"]),
            "operation_id": "Config.TestSource",
            "target": {"type": "user_data_source_config", "id": str(row["config_id"])},
            "project_id": None,
            "knowledge_version_id": None,
            "execution_status": row["state"],
            "status_url": base,
            "events_url": base + "/events",
            "cancel_url": None,
            "result_refs": result,
            "revision": str(row["revision"]),
            "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
            "updated_at": (row["finished_at"] or row["started_at"] or row["created_at"])
            .isoformat()
            .replace("+00:00", "Z"),
            "started_at": row["started_at"].isoformat().replace("+00:00", "Z")
            if row["started_at"]
            else None,
            "finished_at": row["finished_at"].isoformat().replace("+00:00", "Z")
            if row["finished_at"]
            else None,
            "stage": row["operation"],
            "business_state": None,
            "waiting_items": [],
            "cancel_requested_at": None,
            "error": public_error(row["error"]) if row["error"] else None,
            "warnings": [],
            "event_cursor": row["events"][-1]["cursor"],
            "partial_result_ref": None,
            "target_location": {
                "parent_type": None,
                "parent_id": None,
                "read_url": "/api/v1/me/data-source-configs/" + str(row["config_id"]),
            },
            "material_use_notices": [],
        }

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            return validate_source(data)
        except SourceError as exc:
            raise AccountError(exc.code, 422) from None

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
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and expected_actor != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
            row = (
                self.config(conn, actor, target)
                if target and operation not in {"task", "result", "events"}
                else None
            )
            if operation == "list":
                items = [
                    self.view(conn, actor, dict(x))
                    for x in conn.execute(
                        sa.select(configs)
                        .where(configs.c.owner_id == actor, configs.c.deleted.is_(False))
                        .order_by(configs.c.created_at.desc(), configs.c.id.desc())
                    ).mappings()
                ]
                cursor = data.get("cursor")
                start = 0
                if cursor:
                    identities = [item["id"] for item in items]
                    if cursor not in identities:
                        raise AccountError("VALIDATION_BAD_REQUEST", 400)
                    start = identities.index(cursor) + 1
                page = items[start : start + data["page_size"]]
                more = start + len(page) < len(items)
                return {
                    "items": page,
                    "next_cursor": page[-1]["id"] if more else None,
                    "has_more": more,
                }
            if operation == "read":
                assert row is not None
                return self.view(conn, actor, row)
            if operation in {"task", "result", "events"}:
                job = self.task(conn, actor, target or "")
                if operation == "events":
                    return {"events": job["events"], "view": self.task_view(job)}
                if operation == "task":
                    return self.task_view(job)
                if job["state"] not in {"succeeded", "failed"}:
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                if not job["result"]:
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                return {"result_type": "connection_test", "payload": job["result"]}
            now = datetime.now(UTC)
            fingerprint = hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if operation in {"create", "test"}:
                if (
                    not key
                    or not 16 <= len(key) <= 128
                    or not all(32 <= ord(c) <= 126 for c in key)
                ):
                    raise AccountError("VALIDATION_BAD_REQUEST", 400)
                lookup = sa.and_(
                    commands.c.owner_id == actor,
                    commands.c.operation == operation,
                    commands.c.target == (target or ""),
                    commands.c.key == key,
                )
                previous = conn.execute(sa.select(commands).where(lookup)).mappings().first()
                if previous:
                    self.config(conn, actor, str(previous["config_id"]))
                    if previous["fingerprint"] != fingerprint:
                        raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                    if operation != "create":
                        return self.task_view(self.task(conn, actor, previous["result"]["task_id"]))
                    return previous["result"]
            if operation in {"create", "update"}:
                if row:
                    require_revision(row["revision"], data.get("expected_revision"))
                values = self._validate({**(row["data"] if row else {}), **data})
                secret, secret_changed = self._secret(
                    data.get("secret"), row["secret_ciphertext"] if row else None
                )
                if row and values == row["data"] and not secret_changed:
                    return self.view(conn, actor, row)
                identity = row["id"] if row else uuid4()
                updates = {
                    "revision": uuid4(),
                    "credential_revision": uuid4()
                    if secret_changed or not row
                    else row["credential_revision"],
                    "data": values,
                    "secret_ciphertext": secret,
                    "updated_at": now,
                }
                if row:
                    conn.execute(configs.update().where(configs.c.id == identity).values(**updates))
                else:
                    conn.execute(
                        configs.insert().values(
                            id=identity, owner_id=actor, created_at=now, **updates
                        )
                    )
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        owner_id=actor,
                        config_id=identity,
                        operation=operation,
                        secret_operation=data.get("secret", {}).get("operation", "keep"),
                        revision=updates["revision"],
                        occurred_at=now,
                    )
                )
                result = self.view(conn, actor, self.config(conn, actor, str(identity)))
            elif operation == "delete":
                assert row is not None
                require_revision(row["revision"], data.get("expected_revision"))
                deletion_revision = uuid4()
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        owner_id=actor,
                        config_id=row["id"],
                        operation="delete",
                        secret_operation="clear",
                        revision=deletion_revision,
                        occurred_at=now,
                    )
                )
                conn.execute(
                    configs.update()
                    .where(configs.c.id == row["id"])
                    .values(
                        deleted=True,
                        secret_ciphertext=None,
                        revision=deletion_revision,
                        updated_at=now,
                    )
                )
                return None
            elif operation in {"test"}:
                assert row is not None
                identity = row["id"]
                job_id = uuid4()
                task_revision = uuid4()
                conn.execute(
                    tasks.insert().values(
                        id=job_id,
                        owner_id=actor,
                        config_id=identity,
                        revision=task_revision,
                        credential_revision=row["credential_revision"],
                        config_revision=row["revision"],
                        attempt_id=uuid4(),
                        operation=operation,
                        input=row["data"],
                        state="queued",
                        created_at=now,
                        events=[event_record("queued", task_revision, now)],
                    )
                )
                result = self.task_view(self.task(conn, actor, str(job_id)))
            else:
                raise AccountError("VALIDATION_FIELD_INVALID", 422)
            if operation in {"create", "test"}:
                conn.execute(
                    commands.insert().values(
                        owner_id=actor,
                        operation=operation,
                        target=target or "",
                        key=key,
                        fingerprint=fingerprint,
                        config_id=identity,
                        result=result,
                        expires_at=now + timedelta(hours=48),
                    )
                )
            return result
