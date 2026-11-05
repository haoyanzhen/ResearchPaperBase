"""Research owns sessions and creation receipts; Knowledge remains read-only."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from rpb.adapters.knowledge_tables import metadata

sessions = sa.Table(
    "research_sessions",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("revision", sa.Uuid, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("project_id", "id", name="uq_research_project_session"),
    sa.CheckConstraint("status IN ('active','archived')", name="ck_research_session_status"),
    sa.CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_research_title"),
)
commands = sa.Table(
    "research_create_commands",
    metadata,
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("actor_id", sa.Uuid, nullable=False, primary_key=True),
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("fingerprint", sa.Text, nullable=False),
    sa.Column("result", JSONB, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
)

catalogs = sa.Table(
    "research_catalogs",
    metadata,
    sa.Column(
        "project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("cursor_secret", sa.Text, nullable=False),
)
