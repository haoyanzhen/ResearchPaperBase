"""Global paper identity and Project-scoped immutable paper revisions.

Rows are staging facts until referenced by a published version manifest.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.knowledge_tables import metadata

paper_identities = sa.Table(
    "paper_identities",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("unresolved_project_id", sa.Uuid),
)
paper_identity_titles = sa.Table(
    "paper_identity_titles",
    metadata,
    sa.Column("identity_id", sa.Uuid, sa.ForeignKey("paper_identities.id"), primary_key=True),
    sa.Column("normalized_title", sa.Text, primary_key=True),
    sa.CheckConstraint("length(trim(normalized_title)) > 0", name="ck_identity_nonempty_title"),
)
sa.Index("ix_identity_title", paper_identity_titles.c.normalized_title)
project_papers = sa.Table(
    "knowledge_project_papers",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("identity_id", sa.Uuid, sa.ForeignKey("paper_identities.id"), nullable=False),
    sa.UniqueConstraint("project_id", "id", name="uq_project_paper_scope"),
    sa.UniqueConstraint("project_id", "identity_id", name="uq_project_paper_identity"),
)
paper_revisions = sa.Table(
    "knowledge_paper_revisions",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("project_paper_id", sa.Uuid, nullable=False),
    sa.Column("run_id", sa.Uuid, nullable=False),
    sa.Column("candidate_id", sa.Uuid, nullable=False),
    sa.Column("content", JSONB, nullable=False),
    sa.Column("digest", sa.Text, nullable=False),
    sa.UniqueConstraint("project_id", "id", name="uq_project_paper_revision_scope"),
    sa.UniqueConstraint("project_id", "run_id", "candidate_id", name="uq_candidate_paper_revision"),
    sa.ForeignKeyConstraint(
        ["project_id", "project_paper_id"],
        ["knowledge_project_papers.project_id", "knowledge_project_papers.id"],
        name="fk_paper_revision_project_paper",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        name="fk_paper_revision_project_run",
        deferrable=True,
        initially="DEFERRED",
    ),
)
version_paper_pins = sa.Table(
    "knowledge_version_paper_pins",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("version_id", sa.Uuid, primary_key=True),
    sa.Column("paper_revision_id", sa.Uuid, primary_key=True),
    sa.ForeignKeyConstraint(
        ["project_id", "version_id"],
        ["knowledge_versions.project_id", "knowledge_versions.id"],
        name="fk_paper_pin_version",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "paper_revision_id"],
        ["knowledge_paper_revisions.project_id", "knowledge_paper_revisions.id"],
        name="fk_paper_pin_revision",
        deferrable=True,
        initially="DEFERRED",
    ),
)
objects = sa.Table(
    "knowledge_paper_objects",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("paper_revision_id", sa.Uuid, nullable=False),
    sa.Column("attempt_id", sa.Uuid, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("source_revision_id", sa.Uuid, nullable=False),
    sa.Column("sha256", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.Column("locators", JSONB, nullable=False),
    sa.Column("dependencies", JSONB, nullable=False),
    sa.UniqueConstraint("project_id", "id", name="uq_paper_object_scope"),
    sa.UniqueConstraint("project_id", "paper_revision_id", "kind", name="uq_paper_object_kind"),
    sa.ForeignKeyConstraint(
        ["project_id", "paper_revision_id"],
        ["knowledge_paper_revisions.project_id", "knowledge_paper_revisions.id"],
        name="fk_paper_object_revision",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint("kind IN ('text','file')", name="ck_paper_object_kind"),
    sa.CheckConstraint("size_bytes >= 0 AND size_bytes <= 52428800", name="ck_paper_object_size"),
)
object_lifecycle = sa.Table(
    "knowledge_object_lifecycle",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("object_id", sa.Uuid, primary_key=True),
    sa.Column("state", sa.Text, nullable=False, server_default="ready"),
    sa.ForeignKeyConstraint(
        ["project_id", "object_id"],
        ["knowledge_paper_objects.project_id", "knowledge_paper_objects.id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("state IN ('ready','reclaiming')", name="ck_object_lifecycle_state"),
)
object_build_pins = sa.Table(
    "knowledge_object_build_pins",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("object_id", sa.Uuid, primary_key=True),
    sa.Column("run_id", sa.Uuid, primary_key=True),
    sa.Column("attempt_id", sa.Uuid, primary_key=True),
    sa.Column("slot_epoch", sa.BigInteger, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "object_id"],
        ["knowledge_object_lifecycle.project_id", "knowledge_object_lifecycle.object_id"],
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        ondelete="CASCADE",
    ),
)
version_object_pins = sa.Table(
    "knowledge_version_object_pins",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("version_id", sa.Uuid, primary_key=True),
    sa.Column("object_id", sa.Uuid, primary_key=True),
    sa.ForeignKeyConstraint(
        ["project_id", "version_id"],
        ["knowledge_versions.project_id", "knowledge_versions.id"],
        name="fk_object_pin_version",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "object_id"],
        ["knowledge_paper_objects.project_id", "knowledge_paper_objects.id"],
        name="fk_object_pin_object",
        deferrable=True,
        initially="DEFERRED",
    ),
)
