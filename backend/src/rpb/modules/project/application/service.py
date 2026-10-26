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
