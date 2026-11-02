"""Published version identities and Project-scoped default pointers."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.run_tables import runs

metadata = runs.metadata

versions = sa.Table(
    "knowledge_versions",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("source_run_id", sa.Uuid, nullable=False, unique=True),
    sa.Column("base_version_id", sa.Uuid),
    sa.Column("manifest", JSONB, nullable=False),
    sa.Column("manifest_digest", sa.Text, nullable=False),
    sa.Column("ready_proof", JSONB, nullable=False),
    sa.Column("sealed", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("project_id", "id", name="uq_knowledge_project_version"),
    sa.ForeignKeyConstraint(
        ["project_id", "source_run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        name="fk_knowledge_project_run",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "base_version_id"],
        ["knowledge_versions.project_id", "knowledge_versions.id"],
        name="fk_knowledge_project_base",
    ),
)
heads = sa.Table(
    "knowledge_project_heads",
    metadata,
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("version_id", sa.Uuid, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "version_id"],
        ["knowledge_versions.project_id", "knowledge_versions.id"],
        name="fk_knowledge_head_project_version",
    ),
)
