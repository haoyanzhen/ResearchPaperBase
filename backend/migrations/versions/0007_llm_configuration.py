"""Private encrypted LLM configurations and durable connection tasks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_llm_configuration"
down_revision = "0006_account_profile"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "llm_configs",
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
        "llm_commands",
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
        "llm_selections",
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("selection", JSONB),
    )
    op.create_table(
        "llm_tasks",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("llm_configs.id"), nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("credential_revision", sa.Uuid, nullable=False),
        sa.Column("config_revision", sa.Uuid, nullable=False),
        sa.Column("attempt_id", sa.Uuid, nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text),
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
            "state IN ('queued','running','succeeded','failed')", name="ck_llm_tasks_state"
        ),
    )
    op.create_table(
        "llm_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("llm_configs.id"), nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("secret_operation", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_tasks_queue", "llm_tasks", ["state", "created_at"])


def downgrade():
    op.execute(
        "LOCK TABLE llm_configs, llm_commands, llm_selections, llm_tasks, llm_audit "
        "IN ACCESS EXCLUSIVE MODE"
    )
    for name in ("llm_configs", "llm_commands", "llm_selections", "llm_tasks", "llm_audit"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name})")):
            raise RuntimeError("LLM downgrade refused: configuration or task data exists")
    op.drop_table("llm_audit")
    op.drop_table("llm_tasks")
    op.drop_table("llm_selections")
    op.drop_table("llm_commands")
    op.drop_table("llm_configs")
