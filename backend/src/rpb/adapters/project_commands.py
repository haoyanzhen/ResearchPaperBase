"""Project command persistence; caller-owned transaction includes owned initialization."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, RowMapping

from rpb.adapters.auth import AccountStore
from rpb.adapters.auth import metadata as metadata
from rpb.adapters.project import projects
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.application.ports import ConstructionInitializer
from rpb.modules.project.application.ports import ProjectTransaction

projects.append_constraint(sa.UniqueConstraint("id", "owner_id", name="uq_projects_id_owner"))

commands = sa.Table(
    "project_create_commands",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column(
        "actor_id", sa.Uuid, sa.ForeignKey("accounts.id", name="fk_create_actor"), nullable=False
    ),
    sa.Column("operation", sa.Text, nullable=False),
    sa.Column("scope", sa.Text, nullable=False),
    sa.Column("key", sa.String(128, collation="C"), nullable=False),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("schema_version", sa.Integer, nullable=False),
    sa.Column("project_id", sa.Uuid, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "actor_id"],
        ["projects.id", "projects.owner_id"],
        name="fk_create_owned_project",
    ),
    sa.Column("result", JSONB, nullable=False),
    sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("actor_id", "operation", "scope", "key", name="uq_project_create_command"),
    sa.CheckConstraint("operation = 'Project.Create'", name="ck_create_operation"),
    sa.CheckConstraint("scope = 'projects:create'", name="ck_create_scope"),
    sa.CheckConstraint(
        "char_length(key) BETWEEN 16 AND 128 AND key !~ '[^ -~]'", name="ck_create_key"
    ),
    sa.CheckConstraint(
        "char_length(fingerprint) = 64 AND fingerprint !~ '[^0-9a-f]'", name="ck_create_fingerprint"
    ),
    sa.CheckConstraint(
        "jsonb_typeof(result) = 'object' AND result ? 'id' "
        "AND jsonb_typeof(result->'id') = 'string' "
        "AND result->>'id' = project_id::text",
        name="ck_create_result_identity",
    ),
    sa.CheckConstraint(
        "expires_at >= accepted_at + interval '24 hours'", name="ck_create_retention"
    ),
)


class Transaction:
    def __init__(
        self, conn: Connection, actor_id: UUID, construction: ConstructionInitializer
    ) -> None:
        self.conn, self.actor_id, self.construction = conn, actor_id, construction

    def find_command(self, key: str) -> dict[str, Any] | None:
        row = (
            self.conn.execute(
                sa.select(commands).where(
                    commands.c.actor_id == self.actor_id,
                    commands.c.operation == "Project.Create",
                    commands.c.scope == "projects:create",
                    commands.c.key == key,
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def insert_project(self, identity: UUID, workspace: UUID, data: dict[str, str]) -> None:
        self.conn.execute(
            projects.insert().values(
                id=identity, owner_id=self.actor_id, construction_workspace_id=workspace, **data
            )
        )

    def read_project(self, identity: UUID) -> dict[str, Any]:
        row = (
            self.conn.execute(
                sa.select(projects)
                .where(projects.c.id == identity, projects.c.owner_id == self.actor_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not row or row["status"] == "deleted":
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        return self.project_view(row)

    def list_projects(
        self, limit: int, boundary: tuple[datetime, UUID] | None
    ) -> list[dict[str, Any]]:
        query = sa.select(projects).where(
            projects.c.owner_id == self.actor_id, projects.c.status != "deleted"
        )
        if boundary is not None:
            query = query.where(
                sa.tuple_(projects.c.created_at, projects.c.id)
                < sa.tuple_(sa.literal(boundary[0]), sa.literal(boundary[1]))
            )
        query = query.order_by(projects.c.created_at.desc(), projects.c.id.desc()).limit(limit)
        return [self.project_view(row) for row in self.conn.execute(query).mappings()]

    @staticmethod
    def project_view(row: RowMapping) -> dict[str, Any]:
        result = {
            n: row[n]
            for n in (
                "id",
                "revision",
                "created_at",
                "updated_at",
                "name",
                "description",
                "research_scope",
                "status",
            )
        }
        result.update(
            default_knowledge_version_id=None,
            last_construction_at=None,
            last_activity_at=None,
            permissions={"access": True, "use": True, "delete": True},
            available_actions=[],
        )
        return result

    def save_command(
        self,
        key: str,
        fingerprint: str,
        identity: UUID,
        data: dict[str, Any],
        now: datetime,
        expires: datetime,
    ) -> None:
        def encode(value: Any) -> str:
            return (
                value.isoformat().replace("+00:00", "Z")
                if isinstance(value, datetime)
                else str(value)
            )

        self.conn.execute(
            commands.insert().values(
                actor_id=self.actor_id,
                operation="Project.Create",
                scope="projects:create",
                key=key,
                fingerprint=fingerprint,
                schema_version=1,
                project_id=identity,
                result=json.loads(json.dumps(data, default=encode)),
                accepted_at=now,
                expires_at=expires,
            )
        )


class ProjectUnitOfWork:
    def __init__(
        self, account: AccountStore, initialize: Callable[[Connection], ConstructionInitializer]
    ) -> None:
        self.account, self.initialize = account, initialize

    @contextmanager
    def __call__(self, token: str, csrf: str | None) -> Iterator[ProjectTransaction]:
        with self.account.authorized_connection(token, csrf) as (conn, actor_id):
            yield Transaction(conn, actor_id, self.initialize(conn))
