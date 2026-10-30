"""Unpublished, Run-owned immutable file/text objects; never knowledge members."""

import sqlalchemy as sa

from rpb.adapters.account import metadata

objects = sa.Table(
    "construction_processing_objects",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "run_id", sa.Uuid, sa.ForeignKey("construction_runs.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("candidate_id", sa.Uuid, nullable=False),
    sa.Column("project_id", sa.Uuid, nullable=False),
    sa.Column("file_bytes", sa.LargeBinary, nullable=True),
    sa.Column("text", sa.Text, nullable=True),
    sa.Column("digest", sa.Text, nullable=False),
)
