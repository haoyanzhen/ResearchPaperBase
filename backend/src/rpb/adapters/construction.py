"""Construction's own storage writer, with no independent commit."""

from uuid import UUID

from sqlalchemy.engine import Connection

from rpb.adapters.project import construction_workspaces


class ConstructionInitializer:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def initialize(self, project_id: UUID, workspace_id: UUID) -> None:
        self.connection.execute(
            construction_workspaces.insert().values(id=workspace_id, project_id=project_id)
        )
