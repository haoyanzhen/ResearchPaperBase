"""Allow terminal Construction Runs to release only their own staging protection."""

from alembic import op

revision = "0019_run_temporary_cleanup"
down_revision = "0018_knowledge_build_views"
branch_labels = None
depends_on = None


def guards(cleanup):
    release = (
        """IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1 FROM construction_runs r WHERE r.id=OLD.run_id AND r.project_id=OLD.project_id
        AND r.status IN ('failed','cancelled','succeeded')
        AND r.payload->'temporary_cleanup'->>'state'='queued'
    ) THEN RETURN OLD; END IF;"""
        if cleanup
        else ""
    )
    op.execute(f"""CREATE OR REPLACE FUNCTION rpb_guard_build_pin_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP='DELETE' AND pg_trigger_depth()>1 THEN RETURN OLD; END IF;
            {release}
            IF TG_OP='DELETE' AND EXISTS (
                SELECT 1 FROM knowledge_version_object_pins p JOIN knowledge_versions v
                ON v.project_id=p.project_id AND v.id=p.version_id
                WHERE p.object_id=OLD.object_id AND p.project_id=OLD.project_id
                AND v.source_run_id=OLD.run_id AND NOT v.sealed
                AND v.ready_proof->>'attempt_id'=OLD.attempt_id::text
            ) THEN RETURN OLD; END IF;
            RAISE EXCEPTION 'build protection needs controlled release';
        END; $$ LANGUAGE plpgsql""")
    release_view = (
        """IF TG_OP='DELETE' AND EXISTS (
        SELECT 1 FROM construction_runs r WHERE r.id=OLD.run_id AND r.project_id=OLD.project_id
        AND r.status IN ('failed','cancelled','succeeded')
        AND r.payload->'temporary_cleanup'->>'state'='queued'
    ) AND NOT EXISTS (
        SELECT 1 FROM knowledge_publication_events e WHERE e.project_id=OLD.project_id
        AND (e.vector_view_id=OLD.id OR e.graph_view_id=OLD.id)
    ) THEN RETURN OLD; END IF;"""
        if cleanup
        else ""
    )
    op.execute(f"""CREATE OR REPLACE FUNCTION rpb_guard_sealed_view() RETURNS trigger AS $$
        BEGIN
            {release_view}
            IF OLD.sealed AND NOT (TG_OP='DELETE' AND pg_trigger_depth()>1) THEN
                RAISE EXCEPTION 'sealed knowledge view is immutable';
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")


def upgrade():
    guards(True)
    # Adopt only pre-upgrade terminal runs with actual staging records. Failed
    # runs require the owner's explicit request, including legacy failures.
    op.execute("""WITH pending AS (
        SELECT r.id, gen_random_uuid() AS revision FROM construction_runs r
        WHERE r.status IN ('succeeded','cancelled') AND NOT r.payload ? 'temporary_cleanup'
        AND (r.payload ? 'ingestion_confirmation'
          OR EXISTS (SELECT 1 FROM construction_processing_objects p WHERE p.run_id=r.id)
          OR EXISTS (SELECT 1 FROM knowledge_paper_revisions p WHERE p.run_id=r.id)
          OR EXISTS (SELECT 1 FROM knowledge_object_build_pins p WHERE p.run_id=r.id)
          OR EXISTS (SELECT 1 FROM knowledge_vector_views v WHERE v.run_id=r.id)
          OR EXISTS (SELECT 1 FROM knowledge_graph_views v WHERE v.run_id=r.id))
    )
    UPDATE construction_runs r SET revision=p.revision, payload=r.payload || jsonb_build_object(
        'revision',p.revision::text,
        'updated_at',to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        'temporary_cleanup', jsonb_build_object('state','queued','attempts',0,'reclaimed_objects',0,
            'retained_objects',0,'error',null))
    FROM pending p WHERE r.id=p.id""")


def downgrade():
    guards(False)
