"""Run-owned immutable processing objects, separate from published knowledge."""

import sqlalchemy as sa
from alembic import op

revision = "0015_processing_objects"
down_revision = "0014_construction_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "construction_processing_objects",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid,
            sa.ForeignKey("construction_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate_id", sa.Uuid, nullable=False),
        sa.Column("project_id", sa.Uuid, nullable=False),
        sa.Column("file_bytes", sa.LargeBinary, nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("digest", sa.Text, nullable=False),
    )


def downgrade():
    op.execute("LOCK TABLE construction_processing_objects IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM construction_processing_objects)")
    ):
        raise RuntimeError("Refusing to discard processing objects")
    op.drop_table("construction_processing_objects")
