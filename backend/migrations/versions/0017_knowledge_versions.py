"""Project-owned version identities and default pointers, without publishing data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017_knowledge_versions"
down_revision = "0016_construction_slots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_versions",
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
    op.create_table(
        "knowledge_project_heads",
        sa.Column(
            "project_id",
            sa.Uuid,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "version_id"],
            ["knowledge_versions.project_id", "knowledge_versions.id"],
            name="fk_knowledge_head_project_version",
        ),
    )
    # A version is append-only. Project deletion may cascade, but direct edits or deletes fail.
    op.execute("""CREATE FUNCTION rpb_knowledge_version_immutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
            IF TG_OP = 'UPDATE' AND NOT OLD.sealed AND NEW.sealed
                AND (to_jsonb(OLD) - 'sealed') = (to_jsonb(NEW) - 'sealed') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'published knowledge versions are immutable';
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER knowledge_version_immutable BEFORE UPDATE OR DELETE
                  ON knowledge_versions FOR EACH ROW EXECUTE FUNCTION rpb_knowledge_version_immutable()""")
    op.execute("""CREATE FUNCTION rpb_knowledge_version_must_seal() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM knowledge_versions WHERE id = NEW.id AND NOT sealed) THEN
                RAISE EXCEPTION 'knowledge version draft must be sealed before commit';
            END IF;
            RETURN NULL;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE CONSTRAINT TRIGGER knowledge_version_must_seal
        AFTER INSERT OR UPDATE ON knowledge_versions DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION rpb_knowledge_version_must_seal()""")
    op.execute("""CREATE FUNCTION rpb_head_requires_sealed_version() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM knowledge_versions
                WHERE project_id = NEW.project_id AND id = NEW.version_id AND sealed) THEN
                RAISE EXCEPTION 'default knowledge version must be sealed';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER knowledge_head_requires_sealed BEFORE INSERT OR UPDATE
        ON knowledge_project_heads FOR EACH ROW EXECUTE FUNCTION rpb_head_requires_sealed_version()""")


def downgrade():
    op.execute("LOCK TABLE knowledge_versions IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM knowledge_versions)")).scalar():
        raise RuntimeError("Refusing to discard published knowledge versions")
    op.drop_table("knowledge_project_heads")
    op.drop_table("knowledge_versions")
    op.execute("DROP FUNCTION rpb_head_requires_sealed_version()")
    op.execute("DROP FUNCTION rpb_knowledge_version_must_seal()")
    op.execute("DROP FUNCTION rpb_knowledge_version_immutable()")
