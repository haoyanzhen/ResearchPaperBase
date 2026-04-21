"""initial schema — 12 tables from schema.sql v1.0

Revision ID: 0001
Revises:
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── pgcrypto 扩展 ─────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ── 1. users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",            sa.String(50),  nullable=False),
        sa.Column("username",      sa.String(50),  nullable=False),
        sa.Column("email",         sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at",    sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",    sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email",    name="uq_users_email"),
    )
    op.create_index("idx_users_created_at", "users", ["created_at"])

    # ── 2. user_configs ───────────────────────────────────────────────────────
    op.create_table(
        "user_configs",
        sa.Column("id",                sa.String(50),  nullable=False),
        sa.Column("user_id",           sa.String(50),  nullable=False),
        sa.Column("config_name",       sa.String(100), nullable=False),
        sa.Column("config_value",      sa.Text(),      nullable=False),
        sa.Column("is_system_default", sa.Boolean(),   nullable=False,
                  server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_user_configs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_user_configs_user", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "config_name",
                            name="uq_user_configs_user_config"),
    )
    op.create_index("idx_user_configs_user_id", "user_configs", ["user_id"])

    # ── 3. projects ───────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id",            sa.String(50),  nullable=False),
        sa.Column("user_id",       sa.String(50),  nullable=False),
        sa.Column("name",          sa.String(255), nullable=False),
        sa.Column("description",   sa.Text(),      nullable=True),
        sa.Column("mode",          sa.String(20),  nullable=False,
                  server_default=sa.text("'construction'")),
        sa.Column("status",        sa.String(20),  nullable=False,
                  server_default=sa.text("'idle'")),
        sa.Column("total_papers",  sa.Integer(),   nullable=False,
                  server_default=sa.text("0")),
        sa.Column("valid_papers",  sa.Integer(),   nullable=False,
                  server_default=sa.text("0")),
        sa.Column("auto_push",     sa.Boolean(),   nullable=False,
                  server_default=sa.text("FALSE")),
        sa.Column("push_interval", sa.SmallInteger(), nullable=True),
        sa.Column("last_push_at",  sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("next_push_at",  sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",    sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",    sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_projects_user", ondelete="CASCADE"),
        sa.CheckConstraint(
            "mode IN ('construction','deep_research','review')",
            name="chk_projects_mode",
        ),
        sa.CheckConstraint(
            "status IN ('idle','running','paused','error','archived')",
            name="chk_projects_status",
        ),
    )
    op.create_index("idx_projects_user_id",    "projects", ["user_id"])
    op.create_index("idx_projects_status",     "projects", ["status"])
    op.create_index("idx_projects_mode",       "projects", ["mode"])
    op.create_index("idx_projects_next_push",  "projects", ["next_push_at"])
    op.create_index("idx_projects_created_at", "projects", ["created_at"])

    # ── 4. keywords ───────────────────────────────────────────────────────────
    op.create_table(
        "keywords",
        sa.Column("id",                              sa.String(50),   nullable=False),
        sa.Column("project_id",                      sa.String(50),   nullable=False),
        sa.Column("search_word",                     sa.String(500),  nullable=False),
        sa.Column("boolean_expressions",             postgresql.JSONB(), nullable=True),
        sa.Column("searched_papers_arxiv",           sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("searched_papers_openalex",        sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("searched_papers_semanticscholar", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("searched_papers_ads",             sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("searched_papers_total",           sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("is_searched",  sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("is_selected",  sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_search_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_keywords"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_keywords_project", ondelete="CASCADE"),
    )
    op.create_index("idx_keywords_project_id",  "keywords", ["project_id"])
    op.create_index("idx_keywords_is_selected", "keywords", ["project_id", "is_selected"])

    # ── 5. papers ─────────────────────────────────────────────────────────────
    op.create_table(
        "papers",
        sa.Column("id",                  sa.String(50),  nullable=False),
        sa.Column("doi",                 sa.String(100), nullable=True),
        sa.Column("arxiv_id",            sa.String(50),  nullable=True),
        sa.Column("title",               sa.Text(),      nullable=False),
        sa.Column("authors",             postgresql.JSONB(), nullable=True),
        sa.Column("pub_date",            sa.Date(),      nullable=True),
        sa.Column("venue",               sa.String(200), nullable=True),
        sa.Column("abstract",            sa.Text(),      nullable=True),
        sa.Column("source",              sa.String(50),  nullable=True),
        sa.Column("retrieved_at",        sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("download_status",     sa.String(20),  nullable=False,
                  server_default=sa.text("'not_downloaded'")),
        sa.Column("pdf_path",            sa.String(500), nullable=True),
        sa.Column("text_path",           sa.String(500), nullable=True),
        sa.Column("download_error",      sa.Text(),      nullable=True),
        sa.Column("ai_analysis_status",  sa.String(20),  nullable=False,
                  server_default=sa.text("'not_analyzed'")),
        sa.Column("ai_analysis",         postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_papers"),
        sa.UniqueConstraint("doi",      name="uq_papers_doi"),
        sa.UniqueConstraint("arxiv_id", name="uq_papers_arxiv_id"),
        sa.UniqueConstraint("title",    name="uq_papers_title"),
        sa.CheckConstraint(
            "download_status IN ('not_downloaded','success','failed')",
            name="chk_papers_download_status",
        ),
        sa.CheckConstraint(
            "ai_analysis_status IN ('not_analyzed','success','failed')",
            name="chk_papers_ai_analysis_status",
        ),
    )
    op.create_index("idx_papers_pub_date", "papers", ["pub_date"])
    op.create_index("idx_papers_source",   "papers", ["source"])

    # ── 6. project_paper_relations ────────────────────────────────────────────
    op.create_table(
        "project_paper_relations",
        sa.Column("id",              sa.String(50),   nullable=False),
        sa.Column("project_id",      sa.String(50),   nullable=False),
        sa.Column("paper_id",        sa.String(50),   nullable=False),
        sa.Column("reference_score", sa.SmallInteger(), nullable=True),
        sa.Column("technical_score", sa.SmallInteger(), nullable=True),
        sa.Column("total_score",     sa.SmallInteger(), nullable=True),
        sa.Column("scoring_reason",  sa.Text(),       nullable=True),
        sa.Column("is_valid",   sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("push_status",sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("pushed_at",  sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_project_paper_relations"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_ppr_project", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"],
                                name="fk_ppr_paper", ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "paper_id", name="uq_ppr_project_paper"),
        sa.CheckConstraint(
            "reference_score IS NULL OR (reference_score >= 0 AND reference_score <= 5)",
            name="chk_ppr_reference_score",
        ),
        sa.CheckConstraint(
            "technical_score IS NULL OR (technical_score >= 0 AND technical_score <= 5)",
            name="chk_ppr_technical_score",
        ),
        sa.CheckConstraint(
            "total_score IS NULL OR (total_score >= 0 AND total_score <= 10)",
            name="chk_ppr_total_score",
        ),
    )
    op.create_index("idx_ppr_project_paper", "project_paper_relations",
                    ["project_id", "paper_id"], unique=True)
    op.create_index("idx_ppr_project_id",    "project_paper_relations", ["project_id"])
    op.create_index("idx_ppr_paper_id",      "project_paper_relations", ["paper_id"])
    op.create_index("idx_ppr_is_valid",      "project_paper_relations",
                    ["project_id", "is_valid"])
    op.create_index("idx_ppr_push_status",   "project_paper_relations",
                    ["project_id", "push_status"])

    # ── 7. stage_records ──────────────────────────────────────────────────────
    op.create_table(
        "stage_records",
        sa.Column("id",           sa.String(50),    nullable=False),
        sa.Column("project_id",   sa.String(50),    nullable=False),
        sa.Column("mode",         sa.String(20),    nullable=False),
        sa.Column("stage",        sa.SmallInteger(), nullable=False),
        sa.Column("status",       sa.String(20),    nullable=False),
        sa.Column("started_at",   sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paused_at",    sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resumed_at",   sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failed_at",    sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("result",       postgresql.JSONB(), nullable=True),
        sa.Column("error",        sa.Text(),         nullable=True),
        sa.Column("user_actions", postgresql.JSONB(), nullable=True),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_stage_records"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_stage_records_project", ondelete="CASCADE"),
        sa.CheckConstraint(
            "mode IN ('construction','review')",
            name="chk_stage_records_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running','paused','completed','failed')",
            name="chk_stage_records_status",
        ),
        sa.CheckConstraint(
            "NOT (mode = 'construction' AND (stage < 1 OR stage > 7))",
            name="chk_stage_records_stage_construction",
        ),
        sa.CheckConstraint(
            "NOT (mode = 'review' AND (stage < 1 OR stage > 5))",
            name="chk_stage_records_stage_review",
        ),
    )
    op.create_index("idx_stage_records_project_id", "stage_records", ["project_id"])
    op.create_index("idx_stage_records_mode",       "stage_records", ["project_id", "mode"])
    op.create_index("idx_stage_records_stage",      "stage_records",
                    ["project_id", "mode", "stage"])
    op.create_index("idx_stage_records_status",     "stage_records", ["status"])

    # ── 8. research_dialogues ─────────────────────────────────────────────────
    op.create_table(
        "research_dialogues",
        sa.Column("id",             sa.String(50),  nullable=False),
        sa.Column("project_id",     sa.String(50),  nullable=False),
        sa.Column("title",          sa.String(255), nullable=True),
        sa.Column("status",         sa.String(20),  nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("turn_count",     sa.Integer(),   nullable=False,
                  server_default=sa.text("0")),
        sa.Column("summary",        sa.Text(),      nullable=True),
        sa.Column("tags",           postgresql.JSONB(), nullable=True),
        sa.Column("created_at",     sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",     sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_active_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_research_dialogues"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_research_dialogues_project", ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('active','archived')",
            name="chk_research_dialogues_status",
        ),
    )
    op.create_index("idx_research_dialogues_project_id",  "research_dialogues", ["project_id"])
    op.create_index("idx_research_dialogues_status",      "research_dialogues",
                    ["project_id", "status"])
    op.create_index("idx_research_dialogues_last_active", "research_dialogues",
                    ["last_active_at"])

    # ── 9. dialogue_turns ─────────────────────────────────────────────────────
    op.create_table(
        "dialogue_turns",
        sa.Column("id",                sa.String(50), nullable=False),
        sa.Column("dialogue_id",       sa.String(50), nullable=False),
        sa.Column("project_id",        sa.String(50), nullable=False),
        sa.Column("turn_index",        sa.Integer(),  nullable=False),
        sa.Column("sub_mode",          sa.String(20), nullable=False),
        sa.Column("user_content",      sa.Text(),     nullable=False),
        sa.Column("assistant_content", sa.Text(),     nullable=False),
        sa.Column("referenced_papers", postgresql.JSONB(), nullable=True),
        sa.Column("graph_nodes_used",  postgresql.JSONB(), nullable=True),
        sa.Column("input_tokens",      sa.Integer(),  nullable=True),
        sa.Column("output_tokens",     sa.Integer(),  nullable=True),
        sa.Column("created_at",        sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_dialogue_turns"),
        sa.ForeignKeyConstraint(["dialogue_id"], ["research_dialogues.id"],
                                name="fk_dialogue_turns_dialogue", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_dialogue_turns_project", ondelete="CASCADE"),
        sa.UniqueConstraint("dialogue_id", "turn_index",
                            name="uq_dialogue_turns_index"),
        sa.CheckConstraint(
            "sub_mode IN ('theory','technical','experiment')",
            name="chk_dialogue_turns_sub_mode",
        ),
    )
    op.create_index("idx_dialogue_turns_index",      "dialogue_turns",
                    ["dialogue_id", "turn_index"], unique=True)
    op.create_index("idx_dialogue_turns_dialogue",   "dialogue_turns", ["dialogue_id"])
    op.create_index("idx_dialogue_turns_project",    "dialogue_turns", ["project_id"])
    op.create_index("idx_dialogue_turns_created_at", "dialogue_turns", ["created_at"])

    # ── 10. review_outlines ───────────────────────────────────────────────────
    op.create_table(
        "review_outlines",
        sa.Column("id",              sa.String(50), nullable=False),
        sa.Column("project_id",      sa.String(50), nullable=False),
        sa.Column("version",         sa.Integer(),  nullable=False,
                  server_default=sa.text("1")),
        sa.Column("topic_expansion", sa.Text(),     nullable=True),
        sa.Column("outline",         postgresql.JSONB(), nullable=True),
        sa.Column("status",          sa.String(20), nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("confirmed_at",    sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",      sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_review_outlines"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_review_outlines_project", ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "version",
                            name="uq_review_outlines_version"),
        sa.CheckConstraint(
            "status IN ('draft','confirmed','archived')",
            name="chk_review_outlines_status",
        ),
    )
    op.create_index("idx_review_outlines_version",    "review_outlines",
                    ["project_id", "version"], unique=True)
    op.create_index("idx_review_outlines_project_id", "review_outlines", ["project_id"])
    op.create_index("idx_review_outlines_status",     "review_outlines",
                    ["project_id", "status"])

    # ── 11. review_chapters ───────────────────────────────────────────────────
    op.create_table(
        "review_chapters",
        sa.Column("id",              sa.String(50),    nullable=False),
        sa.Column("outline_id",      sa.String(50),    nullable=False),
        sa.Column("project_id",      sa.String(50),    nullable=False),
        sa.Column("chapter_index",   sa.SmallInteger(), nullable=False),
        sa.Column("title",           sa.String(255),   nullable=False),
        sa.Column("content",         sa.Text(),        nullable=True),
        sa.Column("citations",       postgresql.JSONB(), nullable=True),
        sa.Column("iteration_count", sa.SmallInteger(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("review_history",  postgresql.JSONB(), nullable=True),
        sa.Column("status",          sa.String(20),    nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("completed_at",    sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",      sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_review_chapters"),
        sa.ForeignKeyConstraint(["outline_id"], ["review_outlines.id"],
                                name="fk_review_chapters_outline", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_review_chapters_project", ondelete="CASCADE"),
        sa.UniqueConstraint("outline_id", "chapter_index",
                            name="uq_review_chapters_index"),
        sa.CheckConstraint(
            "status IN ('pending','writing','reviewing','completed')",
            name="chk_review_chapters_status",
        ),
    )
    op.create_index("idx_review_chapters_index",      "review_chapters",
                    ["outline_id", "chapter_index"], unique=True)
    op.create_index("idx_review_chapters_outline_id", "review_chapters", ["outline_id"])
    op.create_index("idx_review_chapters_project_id", "review_chapters", ["project_id"])
    op.create_index("idx_review_chapters_status",     "review_chapters",
                    ["project_id", "status"])

    # ── 12. recommendations ───────────────────────────────────────────────────
    op.create_table(
        "recommendations",
        sa.Column("id",           sa.String(50),  nullable=False),
        sa.Column("user_id",      sa.String(50),  nullable=False),
        sa.Column("dialogue_id",  sa.String(50),  nullable=True),
        sa.Column("content_type", sa.String(50),  nullable=False),
        sa.Column("title",        sa.String(255), nullable=False),
        sa.Column("content",      sa.Text(),      nullable=False),
        sa.Column("tags",         postgresql.JSONB(), nullable=True),
        sa.Column("contact_info", sa.String(255), nullable=True),
        sa.Column("view_count",   sa.Integer(),   nullable=False,
                  server_default=sa.text("0")),
        sa.Column("like_count",   sa.Integer(),   nullable=False,
                  server_default=sa.text("0")),
        sa.Column("is_visible",   sa.Boolean(),   nullable=False,
                  server_default=sa.text("TRUE")),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",   sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id", name="pk_recommendations"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_recommendations_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dialogue_id"], ["research_dialogues.id"],
                                name="fk_recommendations_dialogue", ondelete="SET NULL"),
    )
    op.create_index("idx_recommendations_user_id",    "recommendations", ["user_id"])
    op.create_index("idx_recommendations_dialogue",   "recommendations", ["dialogue_id"])
    op.create_index("idx_recommendations_type",       "recommendations", ["content_type"])
    op.create_index("idx_recommendations_created_at", "recommendations",
                    ["created_at"], postgresql_ops={"created_at": "DESC"})
    op.create_index("idx_recommendations_like_count", "recommendations",
                    ["like_count"], postgresql_ops={"like_count": "DESC"})


def downgrade() -> None:
    # 按照外键依赖的逆序删除
    op.drop_table("recommendations")
    op.drop_table("review_chapters")
    op.drop_table("review_outlines")
    op.drop_table("dialogue_turns")
    op.drop_table("research_dialogues")
    op.drop_table("stage_records")
    op.drop_table("project_paper_relations")
    op.drop_table("papers")
    op.drop_table("keywords")
    op.drop_table("projects")
    op.drop_table("user_configs")
    op.drop_table("users")
