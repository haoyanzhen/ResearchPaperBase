"""Hashed server sessions; account and Project data remain untouched."""

import sqlalchemy as sa
from alembic import op

revision = "0003_auth_sessions"
down_revision = "0002_project"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("account_id", sa.Uuid, sa.ForeignKey("accounts.id", name="fk_sessions_account")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),
    )
    op.create_index("ix_sessions_account", "auth_sessions", ["account_id"])


def downgrade():
    op.execute("LOCK TABLE auth_sessions IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM auth_sessions)")):
        raise RuntimeError("Session downgrade refused: sessions contains data")
    op.drop_table("auth_sessions")
