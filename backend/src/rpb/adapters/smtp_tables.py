"""SMTP singleton, durable tests and OAuth handshakes; platform lifecycle."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.project_commands import metadata

configs = sa.Table(
    "smtp_configs",
    metadata,
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
commands = sa.Table(
    "smtp_commands",
    metadata,
    sa.Column("owner_id", sa.Uuid, primary_key=True),
    sa.Column("operation", sa.Text, primary_key=True),
    sa.Column("target", sa.Text, primary_key=True),
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("fingerprint", sa.Text, nullable=False),
    sa.Column("config_id", sa.Uuid, nullable=False),
    sa.Column("result", JSONB, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
)
tasks = sa.Table(
    "smtp_tasks",
    metadata,
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
        "state IN ('queued','running','succeeded','failed')", name="ck_smtp_tasks_state"
    ),
)
sa.Index("ix_smtp_tasks_queue", tasks.c.state, tasks.c.created_at)

audit = sa.Table(
    "smtp_audit",
    metadata,
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

handshakes = sa.Table(
    "smtp_oauth_handshakes",
    metadata,
    sa.Column("state_hash", sa.Text, primary_key=True),
    sa.Column("owner_id", sa.Uuid, nullable=False),
    sa.Column("session_hash", sa.Text, nullable=False),
    sa.Column("config_revision", sa.Uuid, nullable=False),
    sa.Column("credential_revision", sa.Uuid, nullable=False),
    sa.Column("verifier_ciphertext", sa.LargeBinary, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
)
