"""Nullable account display name; preserve identity and authentication facts."""

import sqlalchemy as sa
from alembic import op

revision = "0006_account_profile"
down_revision = "0005_project_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("accounts", sa.Column("display_name", sa.Text))
    op.create_check_constraint(
        "ck_accounts_display_name",
        "accounts",
        "display_name IS NULL OR length(display_name) <= 200",
    )


def downgrade():
    op.execute("LOCK TABLE accounts IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM accounts WHERE display_name IS NOT NULL)")
    ):
        raise RuntimeError("Profile downgrade refused: display names contain data")
    op.drop_constraint("ck_accounts_display_name", "accounts", type_="check")
    op.drop_column("accounts", "display_name")
