"""Run facts and the database-enforced single Project writer."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.account import metadata

runs = sa.Table(
    "construction_runs",
    metadata,
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
        "status IN ('queued','running','waiting_user','failed','cancelled','succeeded')",
        name="ck_retrieval_run_status",
    ),
    sa.UniqueConstraint("project_id", "id", name="uq_construction_project_run"),
)
sa.Index(
    "uq_construction_writer",
    runs.c.project_id,
    unique=True,
    postgresql_where=runs.c.status.in_(["running", "waiting_user"]),
)
slots = sa.Table(
    "construction_project_slots",
    metadata,
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("occupant_run_id", sa.Uuid, nullable=True),
    sa.Column("epoch", sa.BigInteger, nullable=False, server_default="0"),
    sa.ForeignKeyConstraint(
        ["project_id", "occupant_run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        name="fk_slot_project_run",
    ),
    sa.CheckConstraint("epoch >= 0", name="ck_construction_slot_epoch"),
)
commands = sa.Table(
    "construction_run_commands",
    metadata,
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("actor_id", sa.Uuid, primary_key=True),
    sa.Column("operation", sa.Text, primary_key=True),
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("fingerprint", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
)
