"""Persist the Project writer slot and its revocation epoch."""

import sqlalchemy as sa
from alembic import op

revision = "0016_construction_slots"
down_revision = "0015_processing_objects"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE construction_runs IN ACCESS EXCLUSIVE MODE")
    op.create_unique_constraint(
        "uq_construction_project_run", "construction_runs", ["project_id", "id"]
    )
    op.create_table(
        "construction_project_slots",
        sa.Column(
            "project_id",
            sa.Uuid,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("occupant_run_id", sa.Uuid),
        sa.Column("epoch", sa.BigInteger, nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["project_id", "occupant_run_id"],
            ["construction_runs.project_id", "construction_runs.id"],
            name="fk_slot_project_run",
        ),
        sa.CheckConstraint("epoch >= 0", name="ck_construction_slot_epoch"),
    )
    # Existing live P0 runs retain their slot and attempt; unique index ensures at most one.
    op.execute("""INSERT INTO construction_project_slots(project_id, occupant_run_id, epoch)
                  SELECT project_id, id, 1 FROM construction_runs
                  WHERE status IN ('running', 'waiting_user')""")
    op.execute("""UPDATE construction_runs SET payload = jsonb_set(payload, '{slot_epoch}', '1'::jsonb)
                  WHERE status IN ('running', 'waiting_user')""")


def downgrade():
    op.execute("LOCK TABLE construction_project_slots IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM construction_project_slots WHERE occupant_run_id IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("cannot downgrade while a Construction slot is occupied")
    op.drop_table("construction_project_slots")
    op.drop_constraint("uq_construction_project_run", "construction_runs", type_="unique")
