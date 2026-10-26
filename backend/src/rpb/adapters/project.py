"""Project identity and unique Construction container; no public write/authorization API."""

import sqlalchemy as sa

from rpb.adapters.account import metadata as metadata

projects = sa.Table(
    "projects",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column(
        "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", name="fk_projects_owner"), nullable=False
    ),
    sa.Column("construction_workspace_id", sa.Uuid, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=False, server_default=""),
    sa.Column("research_scope", sa.Text, nullable=False, server_default=""),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("authority_epoch", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("revision", sa.Uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.CheckConstraint("char_length(name) BETWEEN 1 AND 200", name="ck_projects_name"),
    sa.CheckConstraint("char_length(description) <= 10000", name="ck_projects_description"),
    sa.CheckConstraint("char_length(research_scope) <= 10000", name="ck_projects_research_scope"),
    sa.CheckConstraint("status IN ('active', 'archived', 'deleted')", name="ck_projects_status"),
    sa.CheckConstraint("authority_epoch >= 0", name="ck_projects_authority_epoch"),
    sa.ForeignKeyConstraint(
        ["id", "construction_workspace_id"],
        ["construction_workspaces.project_id", "construction_workspaces.id"],
        name="fk_projects_own_cw",
        deferrable=True,
        initially="DEFERRED",
        use_alter=True,
    ),
)
construction_workspaces = sa.Table(
    "construction_workspaces",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", name="fk_cw_project"), nullable=False
    ),
    sa.Column("revision", sa.Uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.UniqueConstraint("project_id", name="uq_cw_project"),
    sa.UniqueConstraint("project_id", "id", name="uq_cw_project_id"),
)
sa.Index("ix_projects_owner_created_id", projects.c.owner_id, projects.c.created_at, projects.c.id)
