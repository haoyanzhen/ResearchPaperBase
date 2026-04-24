"""add admin columns to users and create system_configs

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users: add is_admin, is_active ────────────────────────────────────────
    op.add_column("users", sa.Column(
        "is_admin", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")
    ))
    op.add_column("users", sa.Column(
        "is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")
    ))
    op.create_index("idx_users_is_admin", "users", ["is_admin"])

    # ── 13. system_configs ────────────────────────────────────────────────────
    op.create_table(
        "system_configs",
        sa.Column("id",           sa.String(50),  nullable=False),
        sa.Column("config_name",  sa.String(100), nullable=False),
        sa.Column("config_value", sa.Text(),       nullable=False),
        sa.Column("description",  sa.String(255),  nullable=True),
        sa.Column("updated_by",   sa.String(50),   nullable=True),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",   sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_system_configs"),
        sa.UniqueConstraint("config_name", name="uq_system_configs_name"),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"],
            name="fk_system_configs_updater", ondelete="SET NULL"
        ),
    )
    op.create_index("idx_system_configs_config_name", "system_configs", ["config_name"])


def downgrade() -> None:
    op.drop_table("system_configs")
    op.drop_index("idx_users_is_admin", table_name="users")
    op.drop_column("users", "is_active")
    op.drop_column("users", "is_admin")
