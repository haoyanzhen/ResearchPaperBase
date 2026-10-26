"""Atomic Project.Create command receipt; no generic Task/outbox."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_project_commands"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_projects_id_owner", "projects", ["id", "owner_id"])
    op.create_table(
        "project_create_commands",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "actor_id",
            sa.Uuid,
            sa.ForeignKey("accounts.id", name="fk_create_actor"),
            nullable=False,
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
        sa.UniqueConstraint(
            "actor_id", "operation", "scope", "key", name="uq_project_create_command"
        ),
        sa.CheckConstraint("operation = 'Project.Create'", name="ck_create_operation"),
        sa.CheckConstraint("scope = 'projects:create'", name="ck_create_scope"),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 16 AND 128 AND key !~ '[^ -~]'", name="ck_create_key"
        ),
        sa.CheckConstraint(
            "char_length(fingerprint) = 64 AND fingerprint !~ '[^0-9a-f]'",
            name="ck_create_fingerprint",
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


def downgrade():
    op.execute("LOCK TABLE project_create_commands IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM project_create_commands)")):
        raise RuntimeError("Project command downgrade refused: commands contains data")
    op.drop_table("project_create_commands")
    op.drop_constraint("uq_projects_id_owner", "projects", type_="unique")
