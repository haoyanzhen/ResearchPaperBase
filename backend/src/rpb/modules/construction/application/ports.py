"""Construction-owned initialization within the caller's transaction."""

from typing import Protocol
from uuid import UUID


class ConstructionInitializer(Protocol):
    def initialize(self, project_id: UUID, workspace_id: UUID) -> None: ...
