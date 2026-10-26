"""Project transaction and command record ports; no writable ORM crosses this boundary."""

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from rpb.modules.construction.application.ports import ConstructionInitializer


class ProjectTransaction(Protocol):
    actor_id: UUID
    construction: ConstructionInitializer

    def find_command(self, key: str) -> dict[str, Any] | None: ...
    def insert_project(self, identity: UUID, workspace: UUID, data: dict[str, str]) -> None: ...
    def list_projects(
        self, limit: int, boundary: tuple[datetime, UUID] | None
    ) -> list[dict[str, Any]]: ...
    def read_project(self, identity: UUID) -> dict[str, Any]: ...
    def save_command(
        self,
        key: str,
        fingerprint: str,
        identity: UUID,
        data: dict[str, Any],
        now: datetime,
        expires: datetime,
    ) -> None: ...
