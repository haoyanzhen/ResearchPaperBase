"""Project and exactly one same-Project Construction container; frozen DDL."""

import sqlalchemy as sa
from alembic import op

revision = "0002_project"
down_revision = "0001_account"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_id",
            sa.Uuid,
            sa.ForeignKey("accounts.id", name="fk_projects_owner"),
            nullable=False,
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
        sa.CheckConstraint(
            "char_length(research_scope) <= 10000", name="ck_projects_research_scope"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'deleted')", name="ck_projects_status"
        ),
        sa.CheckConstraint("authority_epoch >= 0", name="ck_projects_authority_epoch"),
    )
    op.create_table(
        "construction_workspaces",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            sa.Uuid,
            sa.ForeignKey("projects.id", name="fk_cw_project"),
            nullable=False,
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
    op.create_foreign_key(
        "fk_projects_own_cw",
        "projects",
        "construction_workspaces",
        ["id", "construction_workspace_id"],
        ["project_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_index("ix_projects_owner_created_id", "projects", ["owner_id", "created_at", "id"])


def downgrade():
    op.execute("LOCK TABLE projects, construction_workspaces IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM projects) "
            "OR EXISTS (SELECT 1 FROM construction_workspaces)"
        )
    ):
        raise RuntimeError("Project downgrade refused: projects contains data")
    op.drop_constraint("fk_projects_own_cw", "projects", type_="foreignkey")
    op.drop_table("construction_workspaces")
    op.drop_table("projects")
