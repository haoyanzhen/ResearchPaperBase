"""Isolated construction artifacts; publication requires a separate ready proof."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.knowledge_tables import metadata

profiles = sa.Table(
    "knowledge_embedding_profiles",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("body", JSONB, nullable=False),
)
chunks = sa.Table(
    "knowledge_chunks",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("run_id", sa.Uuid, nullable=False),
    sa.Column("asset_id", sa.Uuid, nullable=False),
    sa.Column("asset_revision", sa.Uuid, nullable=False),
    sa.Column("text_revision_id", sa.Uuid, nullable=False),
    sa.Column("start_offset", sa.Integer, nullable=False),
    sa.Column("end_offset", sa.Integer, nullable=False),
    sa.Column("text_digest", sa.Text, nullable=False),
    sa.Column("source_kind", sa.Text, nullable=False),
    sa.Column("chunker_revision", sa.Text, nullable=False),
    sa.Column("locators", JSONB, nullable=False),
    sa.Column("dependencies", JSONB, nullable=False),
    sa.UniqueConstraint("project_id", "id", name="uq_chunk_project_id"),
    sa.UniqueConstraint(
        "project_id",
        "asset_id",
        "asset_revision",
        "text_revision_id",
        "start_offset",
        "end_offset",
        "chunker_revision",
        name="uq_chunk_identity",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        name="fk_chunk_project_run",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="ck_chunk_offsets"),
    sa.CheckConstraint("source_kind IN ('full_text','abstract_fallback')", name="ck_chunk_source"),
)
embeddings = sa.Table(
    "knowledge_embeddings",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("chunk_id", sa.Uuid, nullable=False),
    sa.Column(
        "profile_id", sa.Text, sa.ForeignKey("knowledge_embedding_profiles.id"), nullable=False
    ),
    sa.Column("embedding", Vector(768), nullable=False),
    sa.UniqueConstraint("project_id", "id", "profile_id", name="uq_embedding_project_profile"),
    sa.UniqueConstraint("project_id", "chunk_id", "profile_id", name="uq_embedding_identity"),
    sa.ForeignKeyConstraint(
        ["project_id", "chunk_id"],
        ["knowledge_chunks.project_id", "knowledge_chunks.id"],
        name="fk_embedding_project_chunk",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint(
        "abs(vector_norm(embedding) - 1.0) < 0.0001", name="ck_embedding_normalized"
    ),
)
vector_views = sa.Table(
    "knowledge_vector_views",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("run_id", sa.Uuid, nullable=False),
    sa.Column("attempt_id", sa.Uuid, nullable=False),
    sa.Column("slot_epoch", sa.BigInteger, nullable=False),
    sa.Column("input_revision", sa.Uuid, nullable=False),
    sa.Column("candidate_revision", sa.Uuid, nullable=False),
    sa.Column("build_profile_id", sa.Text, nullable=False),
    sa.Column("dependency_digest", sa.Text, nullable=False),
    sa.Column(
        "profile_id", sa.Text, sa.ForeignKey("knowledge_embedding_profiles.id"), nullable=False
    ),
    sa.Column("sealed", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("digest", sa.Text),
    sa.UniqueConstraint("project_id", "id", "profile_id", name="uq_vector_view_project_profile"),
    sa.ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        name="fk_vector_view_project_run",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint(
        "(sealed AND digest IS NOT NULL) OR (NOT sealed AND digest IS NULL)",
        name="ck_vector_view_seal",
    ),
)
vector_members = sa.Table(
    "knowledge_vector_view_members",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("view_id", sa.Uuid, primary_key=True),
    sa.Column("embedding_id", sa.Uuid, primary_key=True),
    sa.Column("profile_id", sa.Text, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id", "profile_id"],
        [
            "knowledge_vector_views.project_id",
            "knowledge_vector_views.id",
            "knowledge_vector_views.profile_id",
        ],
        name="fk_vector_member_view",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "embedding_id", "profile_id"],
        [
            "knowledge_embeddings.project_id",
            "knowledge_embeddings.id",
            "knowledge_embeddings.profile_id",
        ],
        name="fk_vector_member_embedding",
        deferrable=True,
        initially="DEFERRED",
    ),
)
graph_views = sa.Table(
    "knowledge_graph_views",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("run_id", sa.Uuid, nullable=False),
    sa.Column("attempt_id", sa.Uuid, nullable=False),
    sa.Column("slot_epoch", sa.BigInteger, nullable=False),
    sa.Column("input_revision", sa.Uuid, nullable=False),
    sa.Column("candidate_revision", sa.Uuid, nullable=False),
    sa.Column("build_profile_id", sa.Text, nullable=False),
    sa.Column("dependency_digest", sa.Text, nullable=False),
    sa.Column("sealed", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("digest", sa.Text),
    sa.UniqueConstraint("project_id", "id", name="uq_graph_view_project_id"),
    sa.ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["construction_runs.project_id", "construction_runs.id"],
        name="fk_graph_view_project_run",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint(
        "(sealed AND digest IS NOT NULL) OR (NOT sealed AND digest IS NULL)",
        name="ck_graph_view_seal",
    ),
)
graph_extractions = sa.Table(
    "knowledge_graph_extractions",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("view_id", sa.Uuid, primary_key=True),
    sa.Column("chunk_id", sa.Uuid, primary_key=True),
    sa.Column("extractor_revision", sa.Text, nullable=False),
    sa.Column("result_digest", sa.Text, nullable=False),
    sa.Column("dependencies", JSONB, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id"],
        ["knowledge_graph_views.project_id", "knowledge_graph_views.id"],
        name="fk_graph_extraction_view",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "chunk_id"],
        ["knowledge_chunks.project_id", "knowledge_chunks.id"],
        name="fk_graph_extraction_chunk",
        deferrable=True,
        initially="DEFERRED",
    ),
)
graph_nodes = sa.Table(
    "knowledge_graph_nodes",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("view_id", sa.Uuid, primary_key=True),
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("identity_key", sa.Text, nullable=False),
    sa.UniqueConstraint(
        "project_id", "view_id", "kind", "identity_key", name="uq_graph_node_identity"
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id"],
        ["knowledge_graph_views.project_id", "knowledge_graph_views.id"],
        name="fk_graph_node_view",
        ondelete="CASCADE",
    ),
    sa.CheckConstraint(
        "kind IN ('paper','material','chunk','author','concept','method','dataset','keyword')",
        name="ck_graph_node_kind",
    ),
)
graph_labels = sa.Table(
    "knowledge_graph_labels",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("view_id", sa.Uuid, primary_key=True),
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("node_id", sa.Uuid, nullable=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("source", JSONB, nullable=False),
    sa.Column("dependencies", JSONB, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id", "node_id"],
        [
            "knowledge_graph_nodes.project_id",
            "knowledge_graph_nodes.view_id",
            "knowledge_graph_nodes.id",
        ],
        name="fk_graph_label_node",
        ondelete="CASCADE",
    ),
)
graph_edges = sa.Table(
    "knowledge_graph_edges",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("view_id", sa.Uuid, primary_key=True),
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("source_id", sa.Uuid, nullable=False),
    sa.Column("target_id", sa.Uuid, nullable=False),
    sa.Column("predicate", sa.Text, nullable=False),
    sa.Column("extractor_revision", sa.Text, nullable=False),
    sa.Column("confidence", sa.Float),
    sa.Column("dependencies", JSONB, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id", "source_id"],
        [
            "knowledge_graph_nodes.project_id",
            "knowledge_graph_nodes.view_id",
            "knowledge_graph_nodes.id",
        ],
        name="fk_graph_edge_source",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id", "target_id"],
        [
            "knowledge_graph_nodes.project_id",
            "knowledge_graph_nodes.view_id",
            "knowledge_graph_nodes.id",
        ],
        name="fk_graph_edge_target",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint(
        "predicate IN ('belongs_to','authored_by','cites','mentions','uses_method','uses_dataset','related_to')",
        name="ck_graph_edge_predicate",
    ),
    sa.CheckConstraint(
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
        name="ck_graph_edge_confidence",
    ),
)
graph_supports = sa.Table(
    "knowledge_graph_supports",
    metadata,
    sa.Column("project_id", sa.Uuid, primary_key=True),
    sa.Column("view_id", sa.Uuid, primary_key=True),
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("edge_id", sa.Uuid, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("chunk_id", sa.Uuid),
    sa.Column("text_revision_id", sa.Uuid),
    sa.Column("start_offset", sa.Integer),
    sa.Column("end_offset", sa.Integer),
    sa.Column("asset_id", sa.Uuid),
    sa.Column("asset_revision", sa.Uuid),
    sa.Column("metadata_revision", sa.Uuid),
    sa.Column("field", sa.Text),
    sa.Column("dependencies", JSONB, nullable=False),
    sa.ForeignKeyConstraint(
        ["project_id", "view_id", "edge_id"],
        [
            "knowledge_graph_edges.project_id",
            "knowledge_graph_edges.view_id",
            "knowledge_graph_edges.id",
        ],
        name="fk_graph_support_edge",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "chunk_id"],
        ["knowledge_chunks.project_id", "knowledge_chunks.id"],
        name="fk_graph_support_chunk",
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.CheckConstraint(
        """(kind = 'text' AND chunk_id IS NOT NULL AND text_revision_id IS NOT NULL AND start_offset IS NOT NULL AND end_offset IS NOT NULL AND start_offset >= 0 AND end_offset > start_offset AND asset_id IS NULL AND asset_revision IS NULL AND metadata_revision IS NULL AND field IS NULL) OR (kind = 'metadata' AND chunk_id IS NULL AND text_revision_id IS NULL AND start_offset IS NULL AND end_offset IS NULL AND asset_id IS NOT NULL AND asset_revision IS NOT NULL AND metadata_revision IS NOT NULL AND field IS NOT NULL)""",
        name="ck_graph_support_shape",
    ),
)

publication_events = sa.Table(
    "knowledge_publication_events",
    metadata,
    sa.Column("version_id", sa.Uuid, primary_key=True),
    sa.Column("project_id", sa.Uuid, nullable=False),
    sa.Column("graph_view_id", sa.Uuid, nullable=False),
    sa.Column("vector_view_id", sa.Uuid, nullable=False),
    sa.Column("embedding_profile_id", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.CheckConstraint("state IN ('pending','sent')"),
    sa.ForeignKeyConstraint(
        ["project_id", "version_id"],
        ["knowledge_versions.project_id", "knowledge_versions.id"],
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "graph_view_id"],
        ["knowledge_graph_views.project_id", "knowledge_graph_views.id"],
        deferrable=True,
        initially="DEFERRED",
    ),
    sa.ForeignKeyConstraint(
        ["project_id", "vector_view_id", "embedding_profile_id"],
        [
            "knowledge_vector_views.project_id",
            "knowledge_vector_views.id",
            "knowledge_vector_views.profile_id",
        ],
        deferrable=True,
        initially="DEFERRED",
    ),
)
