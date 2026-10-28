"""Durable Project-scoped search term aggregate; no Run or Knowledge Version."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_search_terms"
down_revision = "0012_platform_mail"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "construction_term_states",
        sa.Column(
            "project_id",
            sa.Uuid,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("payload", JSONB, nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'schema_version' "
            "AND payload->>'schema_version' = '1'",
            name="ck_term_state_schema",
        ),
    )


def downgrade():
    op.execute("LOCK TABLE construction_term_states IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM construction_term_states)")):
        raise RuntimeError("Refusing to discard durable search term facts")
    op.drop_table("construction_term_states")
