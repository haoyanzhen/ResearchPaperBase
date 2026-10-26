"""Account identity storage only; no registration or governance behavior."""

import sqlalchemy as sa
from alembic import op

revision = "0001_account"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("username_key", sa.Text(collation="C"), nullable=False),
        sa.Column("email_key", sa.Text(collation="C"), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("is_admin", sa.Boolean, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("username_key", name="uq_accounts_username_key"),
        sa.UniqueConstraint("email_key", name="uq_accounts_email_key"),
        sa.CheckConstraint("username_key <> ''", name="ck_accounts_username_key"),
        sa.CheckConstraint("email_key <> ''", name="ck_accounts_email_key"),
        sa.CheckConstraint("password_hash <> ''", name="ck_accounts_password_hash"),
    )


def downgrade():
    # Hold the same lock through the emptiness check and DROP; concurrent inserts
    # must finish before the check or wait until this transaction finishes.
    op.execute("LOCK TABLE accounts IN ACCESS EXCLUSIVE MODE")
    # Explicitly refuse data loss. Empty disposable schemas may be rolled back.
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM accounts)")):
        raise RuntimeError("Account downgrade refused: accounts contains data")
    op.drop_table("accounts")
