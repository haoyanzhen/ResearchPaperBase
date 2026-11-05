"""Project-scoped Research sessions and atomic creation receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0020_research_sessions"
down_revision = "0019_run_temporary_cleanup"
branch_labels = None
depends_on = None


def upgrade():
    from rpb.adapters.research_tables import catalogs, commands, sessions

    catalogs.create(op.get_bind())
    sessions.create(op.get_bind())
    commands.create(op.get_bind())


def downgrade():
    tables = ("research_create_commands", "research_sessions", "research_catalogs")
    for table in tables:
        op.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Research downgrade refused: table contains data")
    for table in tables:
        op.drop_table(table)
