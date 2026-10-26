"""Project lifecycle confirmation/audit and archive receipt, isolated from creation receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_project_lifecycle"
down_revision = "0004_project_commands"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_lifecycle_records",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("actor_id", sa.Uuid, nullable=False),
        sa.Column("project_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "actor_id"],
            ["projects.id", "projects.owner_id"],
            name="fk_lifecycle_owner",
        ),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("key", sa.String(128, collation="C"), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("subject_revision", sa.Uuid, nullable=False),
        sa.Column("confirmation", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("actor_id", "project_id", "action", "key", name="uq_lifecycle_key"),
        sa.UniqueConstraint("project_id", "subject_revision", name="uq_lifecycle_revision"),
        sa.CheckConstraint("action IN ('archive','delete')", name="ck_lifecycle_action"),
        sa.CheckConstraint(
            "(action = 'archive' AND key IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at >= accepted_at + interval '24 hours') "
            "OR (action = 'delete' AND key IS NULL AND expires_at IS NULL)",
            name="ck_lifecycle_receipt",
        ),
        sa.CheckConstraint(
            "key IS NULL OR (char_length(key) BETWEEN 16 AND 128 AND key !~ '[^ -~]')",
            name="ck_lifecycle_key",
        ),
        sa.CheckConstraint(
            "char_length(fingerprint) = 64 AND fingerprint !~ '[^0-9a-f]'",
            name="ck_lifecycle_fingerprint",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(confirmation) = 'object' AND jsonb_typeof(result) = 'object'",
            name="ck_lifecycle_objects",
        ),
    )


def downgrade():
    op.execute("LOCK TABLE project_lifecycle_records IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM project_lifecycle_records)")):
        raise RuntimeError("Lifecycle downgrade refused: records contains data")
    op.drop_table("project_lifecycle_records")
