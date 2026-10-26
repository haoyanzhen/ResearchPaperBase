"""Account storage metadata; only Alembic creates tables. No authentication service."""

import sqlalchemy as sa

metadata = sa.MetaData()
accounts = sa.Table(
    "accounts",
    metadata,
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
