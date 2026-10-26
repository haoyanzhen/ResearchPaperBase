"""Coordinate Project creation, Construction initialization and durable replay."""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.project.application.ports import ProjectTransaction


class ProjectService:
    def __init__(
        self,
        uow: Callable[[str, str | None], AbstractContextManager[ProjectTransaction]],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.uow, self.clock = uow, clock
        self._cursor_key = secrets.token_bytes(32)

    def create(
        self, token: str, csrf: str, key: str, data: dict[str, str]
    ) -> tuple[dict[str, Any], datetime]:
        fingerprint = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        with self.uow(token, csrf) as tx:
            previous = tx.find_command(key)
            if previous:
                tx.read_project(previous["project_id"])
                if previous["schema_version"] != 1:
                    raise AccountError("STORAGE_INTERNAL_FAILURE", 500)
                if previous["fingerprint"] != fingerprint:
                    raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                return previous["result"], previous["expires_at"]
            identity, workspace = uuid4(), uuid4()
            tx.insert_project(identity, workspace, data)
            tx.construction.initialize(identity, workspace)
            result = tx.read_project(identity)
            now = self.clock()
            expires = now + timedelta(hours=48)
            tx.save_command(key, fingerprint, identity, result, now, expires)
        return result, expires

    def read(self, token: str, identity: UUID) -> dict[str, Any]:
        with self.uow(token, None) as tx:
            return tx.read_project(identity)

    def list_projects(
        self, token: str, page_size: int, cursor: str | None, expected_actor: UUID | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        with self.uow(token, None) as tx:
            if expected_actor is not None and expected_actor != tx.actor_id:
                raise AccountError("AUTH_SESSION_INVALID", 401)
            boundary = None
            expires = int(self.clock().timestamp()) + 1800
            if cursor is not None:
                try:
                    payload, signature = cursor.split(".")
                    expected = hmac.new(self._cursor_key, payload.encode(), "sha256").hexdigest()
                    if not hmac.compare_digest(signature, expected):
                        raise ValueError("signature")
                    decoded = json.loads(base64.urlsafe_b64decode(payload))
                    if decoded[
                        "scope"
                    ] != "Project.List:nondeleted:created_at,id:desc:v1" or decoded["actor"] != str(
                        tx.actor_id
                    ):
                        raise ValueError("scope")
                    expires = decoded["expires"]
                    at = datetime.fromisoformat(decoded["at"])
                    if at.tzinfo is None:
                        raise ValueError("timezone")
                    boundary = (at, UUID(decoded["id"]))
                except ValueError, KeyError, TypeError, binascii.Error, UnicodeError:
                    raise AccountError("VALIDATION_CURSOR_MISMATCH", 400) from None
                if expires <= self.clock().timestamp():
                    raise AccountError("VALIDATION_CURSOR_EXPIRED", 400)
            rows = tx.list_projects(page_size + 1, boundary)
            items = rows[:page_size]
            next_cursor = None
            if len(rows) > page_size:
                last = items[-1]
                payload = base64.urlsafe_b64encode(
                    json.dumps(
                        {
                            "scope": "Project.List:nondeleted:created_at,id:desc:v1",
                            "actor": str(tx.actor_id),
                            "expires": expires,
                            "at": last["created_at"].isoformat(),
                            "id": str(last["id"]),
                        },
                        separators=(",", ":"),
                    ).encode()
                ).decode()
                signature = hmac.new(self._cursor_key, payload.encode(), "sha256").hexdigest()
                next_cursor = payload + "." + signature
            return items, next_cursor

    @staticmethod
    def require_revision(current: dict[str, Any], revision: str | None) -> None:
        if revision is None:
            raise AccountError("STATE_REVISION_REQUIRED", 428)
        if str(current["revision"]) != revision:
            raise AccountError("STATE_REVISION_CONFLICT", 412)

    @staticmethod
    def require_active(current: dict[str, Any]) -> None:
        if current["status"] != "active":
            raise AccountError("STATE_PROJECT_READ_ONLY", 409)

    def update(
        self, token: str, csrf: str, identity: UUID, revision: str | None, data: dict[str, str]
    ) -> dict[str, Any]:
        with self.uow(token, csrf) as tx:
            current = tx.read_project(identity)
            self.require_active(current)
            self.require_revision(current, revision)
            changed = {k: v for k, v in data.items() if v != current[k]}
            return tx.update_metadata(identity, changed, self.clock()) if changed else current

    @staticmethod
    def confirmation_view(payload: dict[str, Any], signed: str) -> dict[str, Any]:
        action = payload["action"]
        risk = "archive_readonly" if action == "archive" else "delete_unavailable"
        message = (
            "归档后只读保留，不能解除归档。"
            if action == "archive"
            else "软删除后不能进入此项目，也不再出现在项目列表中。"
        )
        return {
            "confirmation_id": payload["id"],
            "action": action,
            "target": {"type": "project", "id": payload["project"]},
            "subject_revision": payload["revision"],
            "impact_revision": payload["revision"],
            "knowledge_version_id": None,
            "candidate_revision": None,
            "risks": [{"id": risk, "message": message}],
            "expires_at": datetime.fromtimestamp(payload["expires"], UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "confirmation_token": signed,
            "affected_items": [],
            "retained_items": [
                {
                    "kind": "protected_scope",
                    "scope": "existing_content",
                    "reason": "保留项目已有记录，本操作不物理清理资产。",
                },
                {
                    "kind": "protected_scope",
                    "scope": "shared_identity",
                    "reason": "不删除共享论文身份。",
                },
                {
                    "kind": "protected_scope",
                    "scope": "other_projects",
                    "reason": "不修改其他项目或用户数据。",
                },
                {
                    "kind": "protected_scope",
                    "scope": "completed_exports",
                    "reason": "不删除已完成导出。",
                },
            ],
            "blocked_reasons": [],
        }

    def preview(
        self, token: str, csrf: str, identity: UUID, revision: str | None, action: str
    ) -> dict[str, Any]:
        with self.uow(token, csrf) as tx:
            current = tx.read_project(identity)
            self.require_active(current)
            self.require_revision(current, revision)
            payload = {
                "scope": "project-lifecycle-v1",
                "id": str(uuid4()),
                "actor": str(tx.actor_id),
                "project": str(identity),
                "revision": revision,
                "action": action,
                "expires": int(self.clock().timestamp()) + 600,
            }
            raw = base64.urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":")).encode()
            ).decode()
            signed = raw + "." + hmac.new(self._cursor_key, raw.encode(), "sha256").hexdigest()
            return self.confirmation_view(payload, signed)

    def change_state(
        self,
        token: str,
        csrf: str,
        identity: UUID,
        action: str,
        revision: str | None,
        confirmation: str | None,
        risks: list[str],
        key: str | None = None,
    ) -> tuple[dict[str, Any], datetime | None]:
        fingerprint = hashlib.sha256(
            json.dumps(
                [action, revision, confirmation, sorted(risks)], separators=(",", ":")
            ).encode()
        ).hexdigest()
        with self.uow(token, csrf) as tx:
            current = tx.read_project(identity)
            if key is not None:
                old = tx.find_lifecycle(identity, key)
                if old:
                    if old["schema_version"] != 1:
                        raise AccountError("STORAGE_INTERNAL_FAILURE", 500)
                    if old["fingerprint"] != fingerprint:
                        raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                    return old["result"], old["expires_at"]
            self.require_active(current)
            self.require_revision(current, revision)
            if not confirmation:
                raise AccountError("STATE_CONFIRMATION_REQUIRED", 409)
            try:
                raw, signature = confirmation.split(".")
                if not hmac.compare_digest(
                    signature, hmac.new(self._cursor_key, raw.encode(), "sha256").hexdigest()
                ):
                    raise ValueError("signature")
                payload = json.loads(base64.urlsafe_b64decode(raw))
                if (
                    payload["scope"],
                    payload["actor"],
                    payload["project"],
                    payload["revision"],
                    payload["action"],
                ) != ("project-lifecycle-v1", str(tx.actor_id), str(identity), revision, action):
                    raise ValueError("binding")
                if payload["expires"] <= self.clock().timestamp():
                    raise ValueError("expired")
            except ValueError, TypeError, KeyError, binascii.Error, UnicodeError:
                raise AccountError("STATE_CONFIRMATION_STALE", 409) from None
            preview = self.confirmation_view(payload, confirmation)
            if sorted(risks) != sorted(r["id"] for r in preview["risks"]):
                raise AccountError("STATE_CONFIRMATION_REQUIRED", 409)
            now = self.clock()
            result = tx.transition(identity, "archived" if action == "archive" else "deleted", now)
            expires = now + timedelta(hours=48) if key is not None else None
            preview.pop("confirmation_token")
            preview["token_digest"] = hashlib.sha256(confirmation.encode()).hexdigest()

            def wire(value: Any) -> str:
                return (
                    value.isoformat().replace("+00:00", "Z")
                    if isinstance(value, datetime)
                    else str(value)
                )

            tx.save_lifecycle(
                {
                    "id": uuid4(),
                    "actor_id": tx.actor_id,
                    "project_id": identity,
                    "action": action,
                    "key": key,
                    "fingerprint": fingerprint,
                    "schema_version": 1,
                    "subject_revision": UUID(str(revision)),
                    "confirmation": preview,
                    "result": json.loads(json.dumps(result, default=wire)),
                    "accepted_at": now,
                    "expires_at": expires,
                }
            )
            return result, expires
