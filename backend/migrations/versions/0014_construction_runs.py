"""Durable retrieval Run and scoped idempotency receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014_construction_runs"
down_revision = "0013_search_terms"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "construction_runs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("revision", sa.Uuid, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting_user','failed','cancelled')",
            name="ck_retrieval_run_status",
        ),
    )
    op.create_index(
        "uq_construction_writer",
        "construction_runs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('running','waiting_user')"),
    )
    op.create_table(
        "construction_run_commands",
        sa.Column(
            "project_id",
            sa.Uuid,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("actor_id", sa.Uuid, primary_key=True),
        sa.Column("operation", sa.Text, primary_key=True),
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )


def downgrade():
    op.execute("LOCK TABLE construction_runs, construction_run_commands IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM construction_runs) "
            "OR EXISTS(SELECT 1 FROM construction_run_commands)"
        )
    ):
        raise RuntimeError("Refusing to discard durable Run facts")
    op.drop_table("construction_run_commands")
    op.drop_table("construction_runs")
