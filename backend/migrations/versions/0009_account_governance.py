"""Confirmed administrator account governance and durable cleanup receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_account_governance"
down_revision = "0008_source_configuration"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_action_previews",
        sa.Column("token_hash", sa.Text, primary_key=True),
        sa.Column("actor_id", sa.Uuid, nullable=False),
        sa.Column("target_id", sa.Uuid, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("view", JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean, nullable=False),
    )
    op.create_table(
        "account_governance_audit",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("actor_id", sa.Uuid, nullable=False),
        sa.Column("target_id", sa.Uuid, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.Text, nullable=False),
    )
    op.create_table(
        "account_reset_commands",
        sa.Column("actor_id", sa.Uuid, primary_key=True),
        sa.Column("target_id", sa.Uuid, primary_key=True),
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("operation_id", sa.Uuid, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "account_cleanup_records",
        sa.Column("target_id", sa.Uuid, primary_key=True),
        sa.Column("actor_id", sa.Uuid, nullable=False),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("operation_id", sa.Uuid, nullable=False),
    )


def downgrade():
    for name in (
        "account_action_previews",
        "account_governance_audit",
        "account_reset_commands",
        "account_cleanup_records",
    ):
        op.execute(f"LOCK TABLE {name} IN ACCESS EXCLUSIVE MODE")
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {name})")):
            raise RuntimeError("Account governance downgrade refused: durable facts exist")
    for name in (
        "account_cleanup_records",
        "account_reset_commands",
        "account_governance_audit",
        "account_action_previews",
    ):
        op.drop_table(name)
