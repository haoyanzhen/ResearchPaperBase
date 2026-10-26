"""Coordinate Project creation, Construction initialization and durable replay."""

import hashlib
import json
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
