"""Platform source assets independent of the administering account lifecycle."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_platform_mail"
down_revision = "0011_system_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "smtp_configs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("credential_revision", sa.Uuid, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary),
        sa.Column("deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("configured", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("oauth_ciphertext", sa.LargeBinary),
        sa.Column("oauth_status", sa.Text, nullable=False, server_default="not_connected"),
        sa.Column("refresh_task_id", sa.Uuid),
        sa.Column("refresh_attempt_id", sa.Uuid),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "smtp_commands",
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
        "smtp_tasks",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("smtp_configs.id"), nullable=False),
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
            name="ck_smtp_tasks_state",
        ),
    )
    op.create_table(
        "smtp_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("config_id", sa.Uuid, sa.ForeignKey("smtp_configs.id"), nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("config_type", sa.Text, nullable=False, server_default="smtp"),
        sa.Column("result", sa.Text, nullable=False, server_default="succeeded"),
        sa.Column("secret_operation", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_smtp_tasks_queue", "smtp_tasks", ["state", "created_at"])

    op.create_table(
        "smtp_oauth_handshakes",
        sa.Column("state_hash", sa.Text, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("session_hash", sa.Text, nullable=False),
        sa.Column("config_revision", sa.Uuid, nullable=False),
        sa.Column("credential_revision", sa.Uuid, nullable=False),
        sa.Column("verifier_ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "security_configs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("data", JSONB),
    )
    op.create_table(
        "security_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation", sa.Text, nullable=False, server_default="save"),
        sa.Column("config_type", sa.Text, nullable=False, server_default="security"),
        sa.Column("result", sa.Text, nullable=False, server_default="succeeded"),
    )

    op.create_table(
        "security_diagnostics",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("task_id", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", JSONB, nullable=False),
    )


def downgrade():
    tables = (
        "smtp_configs",
        "smtp_tasks",
        "smtp_commands",
        "smtp_audit",
        "smtp_oauth_handshakes",
        "security_configs",
        "security_audit",
        "security_diagnostics",
    )
    op.execute("LOCK TABLE " + ", ".join(tables) + " IN ACCESS EXCLUSIVE MODE")
    for name in tables:
        where = (
            " WHERE configured"
            if name == "smtp_configs"
            else " WHERE data IS NOT NULL"
            if name == "security_configs"
            else ""
        )
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name}{where})")):
            raise RuntimeError("Platform mail downgrade refused: configuration or task data exists")
    for name in (
        "smtp_oauth_handshakes",
        "smtp_audit",
        "smtp_tasks",
        "smtp_commands",
        "smtp_configs",
        "security_audit",
        "security_configs",
        "security_diagnostics",
    ):
        op.drop_table(name)
