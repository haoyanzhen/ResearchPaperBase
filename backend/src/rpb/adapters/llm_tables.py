"""Config-owned persistence; migrations alone create tables."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.project_commands import metadata

configs = sa.Table(
    "llm_configs",
    metadata,
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
commands = sa.Table(
    "llm_commands",
    metadata,
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
selections = sa.Table(
    "llm_selections",
    metadata,
    sa.Column(
        "owner_id", sa.Uuid, sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("revision", sa.Uuid, nullable=False),
    sa.Column("selection", JSONB),
)
tasks = sa.Table(
    "llm_tasks",
    metadata,
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
sa.Index("ix_llm_tasks_queue", tasks.c.state, tasks.c.created_at)

audit = sa.Table(
    "llm_audit",
    metadata,
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
