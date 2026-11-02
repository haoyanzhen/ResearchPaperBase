# ruff: noqa: E501
"""Isolated vector and graph build artifacts; publication is a separate protocol."""

import sqlalchemy as sa
from alembic import op

revision = "0018_knowledge_build_views"
down_revision = "0017_knowledge_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE construction_runs DROP CONSTRAINT ck_retrieval_run_status")
    op.execute(
        "ALTER TABLE construction_runs ADD CONSTRAINT ck_retrieval_run_status CHECK (status IN ('queued','running','waiting_user','failed','cancelled','succeeded'))"
    )
    extension = op.get_bind().scalar(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    )
    if not extension or not extension.startswith("0.8."):
        raise RuntimeError("pgvector 0.8 must be provisioned before migration")
    op.execute(
        """CREATE TABLE paper_identities (id UUID PRIMARY KEY, unresolved_project_id UUID)"""
    )
    op.execute("""CREATE TABLE paper_identity_titles (
        identity_id UUID NOT NULL REFERENCES paper_identities(id),
        normalized_title TEXT NOT NULL,
        CONSTRAINT ck_identity_nonempty_title CHECK (length(trim(normalized_title)) > 0),
        PRIMARY KEY (identity_id, normalized_title)
    )""")
    op.execute("CREATE INDEX ix_identity_title ON paper_identity_titles (normalized_title)")
    op.execute("""CREATE TABLE knowledge_project_papers (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        identity_id UUID NOT NULL REFERENCES paper_identities(id),
        CONSTRAINT uq_project_paper_scope UNIQUE (project_id, id),
        CONSTRAINT uq_project_paper_identity UNIQUE (project_id, identity_id)
    )""")
    op.execute("""CREATE FUNCTION rpb_guard_unresolved_paper_identity() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM paper_identities WHERE id = NEW.identity_id
                       AND unresolved_project_id IS NOT NULL
                       AND unresolved_project_id <> NEW.project_id) THEN
                RAISE EXCEPTION 'unresolved identity belongs to another Project';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER guard_unresolved_paper_identity BEFORE INSERT OR UPDATE
        ON knowledge_project_papers FOR EACH ROW EXECUTE FUNCTION rpb_guard_unresolved_paper_identity()""")
    op.execute("""CREATE TABLE knowledge_paper_revisions (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        project_paper_id UUID NOT NULL,
        run_id UUID NOT NULL,
        candidate_id UUID NOT NULL,
        content JSONB NOT NULL,
        digest TEXT NOT NULL,
        CONSTRAINT uq_project_paper_revision_scope UNIQUE (project_id, id),
        CONSTRAINT uq_candidate_paper_revision UNIQUE (project_id, run_id, candidate_id),
        CONSTRAINT fk_paper_revision_project_paper FOREIGN KEY (project_id, project_paper_id)
            REFERENCES knowledge_project_papers(project_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_paper_revision_project_run FOREIGN KEY (project_id, run_id)
            REFERENCES construction_runs(project_id, id) DEFERRABLE INITIALLY DEFERRED
    )""")
    op.execute("""CREATE TABLE knowledge_version_paper_pins (
        project_id UUID NOT NULL,
        version_id UUID NOT NULL,
        paper_revision_id UUID NOT NULL,
        PRIMARY KEY (project_id, version_id, paper_revision_id),
        CONSTRAINT fk_paper_pin_version FOREIGN KEY (project_id, version_id)
            REFERENCES knowledge_versions(project_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_paper_pin_revision FOREIGN KEY (project_id, paper_revision_id)
            REFERENCES knowledge_paper_revisions(project_id, id) DEFERRABLE INITIALLY DEFERRED
    )""")
    op.execute("""CREATE TABLE knowledge_paper_objects (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        paper_revision_id UUID NOT NULL,
        attempt_id UUID NOT NULL,
        kind TEXT NOT NULL,
        source_revision_id UUID NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes BIGINT NOT NULL,
        locators JSONB NOT NULL,
        dependencies JSONB NOT NULL,
        CONSTRAINT uq_paper_object_scope UNIQUE (project_id, id),
        CONSTRAINT uq_paper_object_kind UNIQUE (project_id, paper_revision_id, kind),
        CONSTRAINT fk_paper_object_revision FOREIGN KEY (project_id, paper_revision_id)
            REFERENCES knowledge_paper_revisions(project_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT ck_paper_object_kind CHECK (kind IN ('text','file')),
        CONSTRAINT ck_paper_object_size CHECK (size_bytes >= 0 AND size_bytes <= 52428800)
    )""")
    op.execute("""CREATE TABLE knowledge_object_lifecycle (
        project_id UUID NOT NULL, object_id UUID NOT NULL,
        state TEXT NOT NULL DEFAULT 'ready', PRIMARY KEY (project_id, object_id),
        FOREIGN KEY (project_id, object_id) REFERENCES knowledge_paper_objects(project_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_object_lifecycle_state CHECK (state IN ('ready','reclaiming'))
    )""")
    op.execute("""CREATE TABLE knowledge_object_build_pins (
        project_id UUID NOT NULL, object_id UUID NOT NULL, run_id UUID NOT NULL,
        attempt_id UUID NOT NULL, slot_epoch BIGINT NOT NULL,
        PRIMARY KEY (project_id, object_id, run_id, attempt_id),
        FOREIGN KEY (project_id, object_id) REFERENCES knowledge_object_lifecycle(project_id, object_id) ON DELETE CASCADE,
        FOREIGN KEY (project_id, run_id) REFERENCES construction_runs(project_id, id) ON DELETE CASCADE
    )""")
    op.execute("""CREATE TABLE knowledge_version_object_pins (
        project_id UUID NOT NULL,
        version_id UUID NOT NULL,
        object_id UUID NOT NULL,
        PRIMARY KEY (project_id, version_id, object_id),
        CONSTRAINT fk_object_pin_version FOREIGN KEY (project_id, version_id)
            REFERENCES knowledge_versions(project_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_object_pin_object FOREIGN KEY (project_id, object_id)
            REFERENCES knowledge_paper_objects(project_id, id) DEFERRABLE INITIALLY DEFERRED
    )""")
    op.execute(
        "\nCREATE TABLE knowledge_embedding_profiles (\n\tid TEXT NOT NULL, \n\tbody JSONB NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_chunks (\n\tid UUID NOT NULL, \n\tproject_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\tasset_id UUID NOT NULL, \n\tasset_revision UUID NOT NULL, \n\ttext_revision_id UUID NOT NULL, \n\tstart_offset INTEGER NOT NULL, \n\tend_offset INTEGER NOT NULL, \n\ttext_digest TEXT NOT NULL, \n\tsource_kind TEXT NOT NULL, \n\tchunker_revision TEXT NOT NULL, \n\tlocators JSONB NOT NULL, \n\tdependencies JSONB NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_chunk_project_id UNIQUE (project_id, id), \n\tCONSTRAINT uq_chunk_identity UNIQUE (project_id, asset_id, asset_revision, text_revision_id, start_offset, end_offset, chunker_revision), \n\tCONSTRAINT fk_chunk_project_run FOREIGN KEY(project_id, run_id) REFERENCES construction_runs (project_id, id) DEFERRABLE INITIALLY DEFERRED, \n\tCONSTRAINT ck_chunk_offsets CHECK (start_offset >= 0 AND end_offset > start_offset), \n\tCONSTRAINT ck_chunk_source CHECK (source_kind IN ('full_text','abstract_fallback')), \n\tFOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_embeddings (\n\tid UUID NOT NULL, \n\tproject_id UUID NOT NULL, \n\tchunk_id UUID NOT NULL, \n\tprofile_id TEXT NOT NULL, \n\tembedding VECTOR(768) NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_embedding_project_profile UNIQUE (project_id, id, profile_id), \n\tCONSTRAINT uq_embedding_identity UNIQUE (project_id, chunk_id, profile_id), \n\tCONSTRAINT fk_embedding_project_chunk FOREIGN KEY(project_id, chunk_id) REFERENCES knowledge_chunks (project_id, id) DEFERRABLE INITIALLY DEFERRED, \n\tCONSTRAINT ck_embedding_normalized CHECK (abs(vector_norm(embedding) - 1.0) < 0.0001), \n\tFOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, \n\tFOREIGN KEY(profile_id) REFERENCES knowledge_embedding_profiles (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_vector_views (\n\tid UUID NOT NULL, \n\tproject_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\tattempt_id UUID NOT NULL, \n\tslot_epoch BIGINT NOT NULL, \n\tinput_revision UUID NOT NULL, \n\tcandidate_revision UUID NOT NULL, \n\tbuild_profile_id TEXT NOT NULL, \n\tdependency_digest TEXT NOT NULL, \n\tprofile_id TEXT NOT NULL, \n\tsealed BOOLEAN DEFAULT false NOT NULL, \n\tdigest TEXT, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_vector_view_project_profile UNIQUE (project_id, id, profile_id), \n\tCONSTRAINT fk_vector_view_project_run FOREIGN KEY(project_id, run_id) REFERENCES construction_runs (project_id, id) DEFERRABLE INITIALLY DEFERRED, \n\tCONSTRAINT ck_vector_view_seal CHECK ((sealed AND digest IS NOT NULL) OR (NOT sealed AND digest IS NULL)), \n\tFOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, \n\tFOREIGN KEY(profile_id) REFERENCES knowledge_embedding_profiles (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_vector_view_members (\n\tproject_id UUID NOT NULL, \n\tview_id UUID NOT NULL, \n\tembedding_id UUID NOT NULL, \n\tprofile_id TEXT NOT NULL, \n\tPRIMARY KEY (project_id, view_id, embedding_id), \n\tCONSTRAINT fk_vector_member_view FOREIGN KEY(project_id, view_id, profile_id) REFERENCES knowledge_vector_views (project_id, id, profile_id) ON DELETE CASCADE, \n\tCONSTRAINT fk_vector_member_embedding FOREIGN KEY(project_id, embedding_id, profile_id) REFERENCES knowledge_embeddings (project_id, id, profile_id) DEFERRABLE INITIALLY DEFERRED\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_graph_views (\n\tid UUID NOT NULL, \n\tproject_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\tattempt_id UUID NOT NULL, \n\tslot_epoch BIGINT NOT NULL, \n\tinput_revision UUID NOT NULL, \n\tcandidate_revision UUID NOT NULL, \n\tbuild_profile_id TEXT NOT NULL, \n\tdependency_digest TEXT NOT NULL, \n\tsealed BOOLEAN DEFAULT false NOT NULL, \n\tdigest TEXT, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_graph_view_project_id UNIQUE (project_id, id), \n\tCONSTRAINT fk_graph_view_project_run FOREIGN KEY(project_id, run_id) REFERENCES construction_runs (project_id, id) DEFERRABLE INITIALLY DEFERRED, \n\tCONSTRAINT ck_graph_view_seal CHECK ((sealed AND digest IS NOT NULL) OR (NOT sealed AND digest IS NULL)), \n\tFOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_graph_extractions (\n\tproject_id UUID NOT NULL, \n\tview_id UUID NOT NULL, \n\tchunk_id UUID NOT NULL, \n\textractor_revision TEXT NOT NULL, \n\tresult_digest TEXT NOT NULL, \n\tdependencies JSONB NOT NULL, \n\tPRIMARY KEY (project_id, view_id, chunk_id), \n\tCONSTRAINT fk_graph_extraction_view FOREIGN KEY(project_id, view_id) REFERENCES knowledge_graph_views (project_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_graph_extraction_chunk FOREIGN KEY(project_id, chunk_id) REFERENCES knowledge_chunks (project_id, id) DEFERRABLE INITIALLY DEFERRED\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_graph_nodes (\n\tproject_id UUID NOT NULL, \n\tview_id UUID NOT NULL, \n\tid UUID NOT NULL, \n\tkind TEXT NOT NULL, \n\tidentity_key TEXT NOT NULL, \n\tPRIMARY KEY (project_id, view_id, id), \n\tCONSTRAINT uq_graph_node_identity UNIQUE (project_id, view_id, kind, identity_key), \n\tCONSTRAINT fk_graph_node_view FOREIGN KEY(project_id, view_id) REFERENCES knowledge_graph_views (project_id, id) ON DELETE CASCADE, \n\tCONSTRAINT ck_graph_node_kind CHECK (kind IN ('paper','material','chunk','author','concept','method','dataset','keyword'))\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_graph_labels (\n\tproject_id UUID NOT NULL, \n\tview_id UUID NOT NULL, \n\tid UUID NOT NULL, \n\tnode_id UUID NOT NULL, \n\tlabel TEXT NOT NULL, \n\tsource JSONB NOT NULL, \n\tdependencies JSONB NOT NULL, \n\tPRIMARY KEY (project_id, view_id, id), \n\tCONSTRAINT fk_graph_label_node FOREIGN KEY(project_id, view_id, node_id) REFERENCES knowledge_graph_nodes (project_id, view_id, id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_graph_edges (\n\tproject_id UUID NOT NULL, \n\tview_id UUID NOT NULL, \n\tid UUID NOT NULL, \n\tsource_id UUID NOT NULL, \n\ttarget_id UUID NOT NULL, \n\tpredicate TEXT NOT NULL, \n\textractor_revision TEXT NOT NULL, \n\tconfidence FLOAT, \n\tdependencies JSONB NOT NULL, \n\tPRIMARY KEY (project_id, view_id, id), \n\tCONSTRAINT fk_graph_edge_source FOREIGN KEY(project_id, view_id, source_id) REFERENCES knowledge_graph_nodes (project_id, view_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_graph_edge_target FOREIGN KEY(project_id, view_id, target_id) REFERENCES knowledge_graph_nodes (project_id, view_id, id) DEFERRABLE INITIALLY DEFERRED, \n\tCONSTRAINT ck_graph_edge_predicate CHECK (predicate IN ('belongs_to','authored_by','cites','mentions','uses_method','uses_dataset','related_to')), \n\tCONSTRAINT ck_graph_edge_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE knowledge_graph_supports (\n\tproject_id UUID NOT NULL, \n\tview_id UUID NOT NULL, \n\tid UUID NOT NULL, \n\tedge_id UUID NOT NULL, \n\tkind TEXT NOT NULL, \n\tchunk_id UUID, \n\ttext_revision_id UUID, \n\tstart_offset INTEGER, \n\tend_offset INTEGER, \n\tasset_id UUID, \n\tasset_revision UUID, \n\tmetadata_revision UUID, \n\tfield TEXT, \n\tdependencies JSONB NOT NULL, \n\tPRIMARY KEY (project_id, view_id, id), \n\tCONSTRAINT fk_graph_support_edge FOREIGN KEY(project_id, view_id, edge_id) REFERENCES knowledge_graph_edges (project_id, view_id, id) ON DELETE CASCADE, \n\tCONSTRAINT fk_graph_support_chunk FOREIGN KEY(project_id, chunk_id) REFERENCES knowledge_chunks (project_id, id) DEFERRABLE INITIALLY DEFERRED, \n\tCONSTRAINT ck_graph_support_shape CHECK ((kind = 'text' AND chunk_id IS NOT NULL AND text_revision_id IS NOT NULL AND start_offset IS NOT NULL AND end_offset IS NOT NULL AND start_offset >= 0 AND end_offset > start_offset AND asset_id IS NULL AND asset_revision IS NULL AND metadata_revision IS NULL AND field IS NULL) OR (kind = 'metadata' AND chunk_id IS NULL AND text_revision_id IS NULL AND start_offset IS NULL AND end_offset IS NULL AND asset_id IS NOT NULL AND asset_revision IS NOT NULL AND metadata_revision IS NOT NULL AND field IS NOT NULL))\n)\n\n"
    )
    op.execute("""CREATE TABLE knowledge_publication_events (
        version_id UUID PRIMARY KEY, project_id UUID NOT NULL, graph_view_id UUID NOT NULL,
        vector_view_id UUID NOT NULL, embedding_profile_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','sent')),
        FOREIGN KEY (project_id, version_id) REFERENCES knowledge_versions(project_id,id) ON DELETE CASCADE,
        FOREIGN KEY (project_id,graph_view_id) REFERENCES knowledge_graph_views(project_id,id) DEFERRABLE INITIALLY DEFERRED,
        FOREIGN KEY (project_id,vector_view_id,embedding_profile_id) REFERENCES knowledge_vector_views(project_id,id,profile_id) DEFERRABLE INITIALLY DEFERRED
    )""")
    op.execute("""CREATE FUNCTION rpb_guard_publication_event() RETURNS trigger AS $$
        BEGIN
            IF TG_OP='DELETE' AND pg_trigger_depth()>1 THEN RETURN OLD; END IF;
            IF TG_OP='UPDATE' AND OLD.state='pending' AND NEW.state='sent'
               AND (to_jsonb(OLD)-'state')=(to_jsonb(NEW)-'state') THEN RETURN NEW; END IF;
            RAISE EXCEPTION 'published view references are permanent';
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER publication_event_immutable BEFORE UPDATE OR DELETE
        ON knowledge_publication_events FOR EACH ROW EXECUTE FUNCTION rpb_guard_publication_event()""")
    op.execute("""CREATE FUNCTION rpb_no_artifact_update() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'immutable knowledge artifact'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE FUNCTION rpb_guard_sealed_view() RETURNS trigger AS $$
        BEGIN
            IF OLD.sealed AND NOT (TG_OP = 'DELETE' AND pg_trigger_depth() > 1) THEN
                RAISE EXCEPTION 'sealed knowledge view is immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE FUNCTION rpb_guard_view_member() RETURNS trigger AS $$
        DECLARE view_sealed boolean; pid uuid; vid uuid;
        BEGIN
            IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'view members are immutable'; END IF;
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
            IF TG_OP = 'DELETE' THEN pid := OLD.project_id; vid := OLD.view_id;
            ELSE pid := NEW.project_id; vid := NEW.view_id; END IF;
            IF TG_ARGV[0] = 'vector' THEN
                SELECT sealed INTO view_sealed FROM knowledge_vector_views
                WHERE project_id = pid AND id = vid FOR UPDATE;
            ELSE
                SELECT sealed INTO view_sealed FROM knowledge_graph_views
                WHERE project_id = pid AND id = vid FOR UPDATE;
            END IF;
            IF view_sealed IS DISTINCT FROM false THEN
                RAISE EXCEPTION 'view is unavailable or sealed';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE FUNCTION rpb_guard_paper_pin() RETURNS trigger AS $$
        DECLARE version_sealed boolean;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                SELECT sealed INTO version_sealed FROM knowledge_versions
                    WHERE project_id = NEW.project_id AND id = NEW.version_id FOR UPDATE;
                IF version_sealed IS DISTINCT FROM false THEN
                    RAISE EXCEPTION 'paper pins require an unsealed version draft';
                END IF;
                RETURN NEW;
            END IF;
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
            RAISE EXCEPTION 'published paper pin is immutable';
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE FUNCTION rpb_guard_object_protection() RETURNS trigger AS $$
        DECLARE object_state text;
        BEGIN
            SELECT state INTO object_state FROM knowledge_object_lifecycle
                WHERE project_id = NEW.project_id AND object_id = NEW.object_id FOR UPDATE;
            IF object_state IS DISTINCT FROM 'ready' THEN
                RAISE EXCEPTION 'object unavailable for protection';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE FUNCTION rpb_guard_object_lifecycle() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
                RAISE EXCEPTION 'object lifecycle deletion requires governed cleanup';
            END IF;
            IF NEW.project_id <> OLD.project_id OR NEW.object_id <> OLD.object_id OR
               OLD.state <> 'ready' OR NEW.state <> 'reclaiming' OR
               EXISTS (SELECT 1 FROM knowledge_object_build_pins p WHERE p.project_id = OLD.project_id AND p.object_id = OLD.object_id) OR
               EXISTS (SELECT 1 FROM knowledge_version_object_pins p WHERE p.project_id = OLD.project_id AND p.object_id = OLD.object_id) THEN
                RAISE EXCEPTION 'protected object cannot be reclaimed';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER guard_object_lifecycle BEFORE UPDATE OR DELETE ON knowledge_object_lifecycle
        FOR EACH ROW EXECUTE FUNCTION rpb_guard_object_lifecycle()""")
    op.execute("""CREATE FUNCTION rpb_guard_build_pin_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN RETURN OLD; END IF;
            IF TG_OP = 'DELETE' AND EXISTS (
                SELECT 1 FROM knowledge_version_object_pins p JOIN knowledge_versions v
                ON v.project_id=p.project_id AND v.id=p.version_id
                WHERE p.object_id=OLD.object_id AND p.project_id=OLD.project_id
                AND v.source_run_id=OLD.run_id AND NOT v.sealed
                AND v.ready_proof->>'attempt_id'=OLD.attempt_id::text
            ) THEN RETURN OLD; END IF;
            RAISE EXCEPTION 'build protection needs controlled release';
        END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER guard_build_pin_mutation BEFORE UPDATE OR DELETE ON knowledge_object_build_pins
        FOR EACH ROW EXECUTE FUNCTION rpb_guard_build_pin_mutation()""")
    op.execute("""CREATE TRIGGER guard_build_object_pin BEFORE INSERT ON knowledge_object_build_pins
        FOR EACH ROW EXECUTE FUNCTION rpb_guard_object_protection()""")
    op.execute("""CREATE TRIGGER z_guard_version_object_pin BEFORE INSERT ON knowledge_version_object_pins
        FOR EACH ROW EXECUTE FUNCTION rpb_guard_object_protection()""")
    op.execute("""CREATE TRIGGER immutable_paper_pin BEFORE INSERT OR UPDATE OR DELETE
        ON knowledge_version_paper_pins FOR EACH ROW EXECUTE FUNCTION rpb_guard_paper_pin()""")
    op.execute("""CREATE TRIGGER immutable_object_pin BEFORE INSERT OR UPDATE OR DELETE
        ON knowledge_version_object_pins FOR EACH ROW EXECUTE FUNCTION rpb_guard_paper_pin()""")
    for table in (
        "paper_identities",
        "knowledge_embedding_profiles",
        "knowledge_chunks",
        "knowledge_embeddings",
        "knowledge_project_papers",
        "knowledge_paper_revisions",
        "knowledge_paper_objects",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_update BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION rpb_no_artifact_update()"
        )
    for table in ("knowledge_vector_views", "knowledge_graph_views"):
        op.execute(
            f"CREATE TRIGGER sealed_view_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION rpb_guard_sealed_view()"
        )
    for table, kind in (
        ("knowledge_vector_view_members", "vector"),
        ("knowledge_graph_extractions", "graph"),
        ("knowledge_graph_nodes", "graph"),
        ("knowledge_graph_labels", "graph"),
        ("knowledge_graph_edges", "graph"),
        ("knowledge_graph_supports", "graph"),
    ):
        op.execute(
            f"CREATE TRIGGER sealed_member_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION rpb_guard_view_member('{kind}')"
        )


def downgrade():
    op.execute("ALTER TABLE construction_runs DROP CONSTRAINT ck_retrieval_run_status")
    op.execute(
        "ALTER TABLE construction_runs ADD CONSTRAINT ck_retrieval_run_status CHECK (status IN ('queued','running','waiting_user','failed','cancelled'))"
    )
    tables = (
        "knowledge_publication_events",
        "knowledge_version_object_pins",
        "knowledge_object_build_pins",
        "knowledge_object_lifecycle",
        "knowledge_paper_objects",
        "knowledge_version_paper_pins",
        "knowledge_paper_revisions",
        "knowledge_project_papers",
        "paper_identity_titles",
        "paper_identities",
        "knowledge_graph_supports",
        "knowledge_graph_edges",
        "knowledge_graph_labels",
        "knowledge_graph_nodes",
        "knowledge_graph_extractions",
        "knowledge_graph_views",
        "knowledge_vector_view_members",
        "knowledge_vector_views",
        "knowledge_embeddings",
        "knowledge_chunks",
        "knowledge_embedding_profiles",
    )
    for table in tables:
        op.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Refusing to discard knowledge build artifacts")
    for table in tables:
        op.drop_table(table)
    for function in (
        "rpb_guard_publication_event",
        "rpb_guard_build_pin_mutation",
        "rpb_guard_object_lifecycle",
        "rpb_guard_object_protection",
        "rpb_guard_unresolved_paper_identity",
        "rpb_guard_paper_pin",
        "rpb_guard_view_member",
        "rpb_guard_sealed_view",
        "rpb_no_artifact_update",
    ):
        op.execute(f"DROP FUNCTION {function}()")
