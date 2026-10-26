"""Private encrypted source configurations and durable connection tasks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_source_configuration"
down_revision = "0007_llm_configuration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_dispatch_limits",
        sa.Column("scope", sa.Text, primary_key=True),
        sa.Column("next_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_configs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("credential_revision", sa.Uuid, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary),
        sa.Column("deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_commands",
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("operation", sa.Text, primary_key=True),
        sa.Column("target", sa.Text, primary_key=True),
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("config_id", sa.Uuid, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_tasks",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("source_configs.id"), nullable=False),
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
            "state IN ('queued','running','succeeded','failed')", name="ck_source_tasks_state"
        ),
    )
    op.create_table(
        "source_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("source_configs.id"), nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("secret_operation", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_tasks_queue", "source_tasks", ["state", "created_at"])


def downgrade():
    op.execute(
        "LOCK TABLE source_configs, source_commands, source_tasks, source_audit "
        "IN ACCESS EXCLUSIVE MODE"
    )
    for name in ("source_configs", "source_commands", "source_tasks", "source_audit"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name})")):
            raise RuntimeError("Source downgrade refused: configuration or task data exists")
    op.drop_table("source_dispatch_limits")
    op.drop_table("source_audit")
    op.drop_table("source_tasks")
    op.drop_table("source_commands")
    op.drop_table("source_configs")
