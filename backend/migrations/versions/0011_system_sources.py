"""Platform source assets independent of the administering account lifecycle."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_system_sources"
down_revision = "0010_system_llm"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_source_configs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("credential_revision", sa.Uuid, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary),
        sa.Column("deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "system_source_commands",
        sa.Column("owner_id", sa.Uuid, primary_key=True),
        sa.Column("operation", sa.Text, primary_key=True),
        sa.Column("target", sa.Text, primary_key=True),
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("config_id", sa.Uuid, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "system_source_tasks",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("system_source_configs.id"), nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("credential_revision", sa.Uuid, nullable=False),
        sa.Column("config_revision", sa.Uuid, nullable=False),
        sa.Column("attempt_id", sa.Uuid, nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("input", JSONB, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("result", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("events", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('queued','running','succeeded','failed')",
            name="ck_system_source_tasks_state",
        ),
    )
    op.create_table(
        "system_source_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("system_source_configs.id"), nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("config_type", sa.Text, nullable=False, server_default="system_source"),
        sa.Column("result", sa.Text, nullable=False, server_default="succeeded"),
        sa.Column("secret_operation", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_system_source_tasks_queue", "system_source_tasks", ["state", "created_at"])


def downgrade():
    op.execute(
        "LOCK TABLE system_source_configs, system_source_commands, "
        "system_source_tasks, system_source_audit "
        "IN ACCESS EXCLUSIVE MODE"
    )
    for name in (
        "system_source_configs",
        "system_source_commands",
        "system_source_tasks",
        "system_source_audit",
    ):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name})")):
            raise RuntimeError("Source downgrade refused: configuration or task data exists")
    op.drop_table("system_source_audit")
    op.drop_table("system_source_tasks")
    op.drop_table("system_source_commands")
    op.drop_table("system_source_configs")
