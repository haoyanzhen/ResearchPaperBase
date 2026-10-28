"""Platform LLM assets independent of the administering account lifecycle."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010_system_llm"
down_revision = "0009_account_governance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_llm_configs",
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
        "system_llm_commands",
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
        "system_llm_tasks",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("system_llm_configs.id"), nullable=False),
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
            "state IN ('queued','running','succeeded','failed')", name="ck_system_llm_tasks_state"
        ),
    )
    op.create_table(
        "system_llm_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("system_llm_configs.id"), nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("config_type", sa.Text, nullable=False, server_default="system_llm"),
        sa.Column("result", sa.Text, nullable=False, server_default="succeeded"),
        sa.Column("secret_operation", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_system_llm_tasks_queue", "system_llm_tasks", ["state", "created_at"])


def downgrade():
    op.execute(
        "LOCK TABLE system_llm_configs, system_llm_commands, system_llm_tasks, system_llm_audit "
        "IN ACCESS EXCLUSIVE MODE"
    )
    for name in (
        "system_llm_configs",
        "system_llm_commands",
        "system_llm_tasks",
        "system_llm_audit",
    ):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name})")):
            raise RuntimeError("LLM downgrade refused: configuration or task data exists")
    op.drop_table("system_llm_audit")
    op.drop_table("system_llm_tasks")
    op.drop_table("system_llm_commands")
    op.drop_table("system_llm_configs")
