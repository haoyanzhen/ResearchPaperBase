"""PS01–07: committed pairs, rejected ownership, upgrade preservation and lock races."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import IntegrityError
from test_account_storage import migrate, values

from rpb.adapters.account import accounts
from rpb.adapters.project import construction_workspaces as cw
from rpb.adapters.project import metadata, projects


def owner(conn):
    return conn.scalar(accounts.insert().values(**values()).returning(accounts.c.id))


def pair(conn, owner_id, **overrides):
    pid, wid = uuid4(), uuid4()
    conn.execute(
        projects.insert().values(
            id=pid, owner_id=owner_id, construction_workspace_id=wid, name="Research", **overrides
        )
    )
    conn.execute(cw.insert().values(id=wid, project_id=pid))
    return pid, wid


def test_ps01_upgrade_existing_account_and_metadata(db):
    engine, cfg = db
    old_columns = [column for column in accounts.c if column.name != "display_name"]
    migrate(engine, cfg, "downgrade", "0001_account")
    with engine.begin() as conn:
        oid = owner(conn)
        before = conn.execute(sa.select(*old_columns)).one()
    migrate(engine, cfg, "upgrade", "head")
    migrate(engine, cfg, "upgrade", "head")
    with engine.connect() as conn:
        assert conn.execute(sa.select(*old_columns)).one() == before
        assert conn.scalar(sa.select(accounts.c.display_name)) is None
        assert conn.scalar(sa.select(accounts.c.id)) == oid
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0018_knowledge_build_views"
        )


def test_ps02_pair_commits_defaults_and_independent_read(db):
    engine, _ = db
    with engine.begin() as conn:
        pid, wid = pair(conn, owner(conn))
    with engine.connect() as conn:
        p = conn.execute(sa.select(projects)).mappings().one()
        w = conn.execute(sa.select(cw)).mappings().one()
        assert (p["id"], p["construction_workspace_id"], w["project_id"], w["id"]) == (
            pid,
            wid,
            pid,
            wid,
        )
        assert p["status"] == "active" and p["authority_epoch"] == 0
        assert p["description"] == p["research_scope"] == ""
        for row in (p, w):
            assert isinstance(row["revision"], UUID)
            assert row["created_at"].utcoffset().total_seconds() == 0
            assert row["updated_at"] == row["created_at"]
        assert set(sa.inspect(conn).get_table_names()) == {
            "accounts",
            "projects",
            "construction_workspaces",
            "construction_term_states",
            "construction_runs",
            "construction_processing_objects",
            "construction_project_slots",
            "knowledge_versions",
            "knowledge_project_heads",
            "paper_identities",
            "paper_identity_titles",
            "knowledge_project_papers",
            "knowledge_paper_revisions",
            "knowledge_version_paper_pins",
            "knowledge_paper_objects",
            "knowledge_object_lifecycle",
            "knowledge_object_build_pins",
            "knowledge_publication_events",
            "knowledge_version_object_pins",
            "knowledge_embedding_profiles",
            "knowledge_chunks",
            "knowledge_embeddings",
            "knowledge_vector_views",
            "knowledge_vector_view_members",
            "knowledge_graph_views",
            "knowledge_graph_extractions",
            "knowledge_graph_nodes",
            "knowledge_graph_labels",
            "knowledge_graph_edges",
            "knowledge_graph_supports",
            "construction_run_commands",
            "alembic_version",
            "auth_sessions",
            "project_create_commands",
            "project_lifecycle_records",
            "system_llm_configs",
            "system_llm_commands",
            "system_llm_tasks",
            "security_diagnostics",
            "security_audit",
            "security_configs",
            "smtp_oauth_handshakes",
            "smtp_audit",
            "smtp_tasks",
            "smtp_commands",
            "smtp_configs",
            "system_source_audit",
            "system_source_tasks",
            "system_source_commands",
            "system_source_configs",
            "system_llm_audit",
            "llm_configs",
            "llm_commands",
            "llm_selections",
            "llm_tasks",
            "llm_audit",
            "source_configs",
            "source_commands",
            "source_tasks",
            "source_audit",
            "source_dispatch_limits",
            "account_action_previews",
            "account_governance_audit",
            "account_reset_commands",
            "account_cleanup_records",
        }


@pytest.mark.parametrize(
    "case",
    [
        "missing_owner",
        "project_only",
        "cw_only",
        "cross_project",
        "second_cw",
        "delete_cw",
        "delete_owner",
    ],
)
def test_ps03_reject_invalid_pair_and_rollback(db, case):
    engine, _ = db
    with engine.begin() as conn:
        oid = owner(conn)
        pid, wid = pair(conn, oid)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        if case == "missing_owner":
            pair(conn, uuid4())
        elif case == "project_only":
            conn.execute(
                projects.insert().values(
                    owner_id=oid, construction_workspace_id=uuid4(), name="orphan"
                )
            )
        elif case == "cw_only":
            conn.execute(cw.insert().values(project_id=uuid4()))
        elif case == "cross_project":
            other, _ = pair(conn, oid)
            conn.execute(
                projects.update()
                .where(projects.c.id == other)
                .values(construction_workspace_id=wid)
            )
        elif case == "second_cw":
            conn.execute(cw.insert().values(project_id=pid))
        elif case == "delete_cw":
            conn.execute(cw.delete().where(cw.c.id == wid))
        else:
            conn.execute(accounts.delete())
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(cw)) == 1
        assert conn.scalar(sa.select(cw.c.id)) == wid
        assert conn.scalar(sa.select(accounts.c.id)) == oid


@pytest.mark.parametrize(
    "field,bad",
    [
        ("name", ""),
        ("name", "x" * 201),
        ("description", "x" * 10001),
        ("research_scope", "x" * 10001),
        ("status", "paused"),
        ("authority_epoch", -1),
    ]
    + [
        (f, None)
        for f in [
            "owner_id",
            "construction_workspace_id",
            "name",
            "description",
            "research_scope",
            "status",
            "authority_epoch",
            "revision",
            "created_at",
            "updated_at",
        ]
    ],
)
def test_ps04_fields_rejected_without_partial_pair(db, field, bad):
    engine, _ = db
    with engine.begin() as conn:
        oid = owner(conn)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        pair(conn, oid)
        conn.execute(projects.update().values({field: bad}))
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(cw)) == 0


@pytest.mark.parametrize("status", ["active", "archived", "deleted"])
def test_ps04_valid_limits_and_status_facts(db, status):
    engine, _ = db
    with engine.begin() as conn:
        pair(conn, owner(conn), description="x" * 10000, research_scope="x" * 10000, status=status)
        conn.execute(projects.update().values(name="x" * 200))
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.status)) == status


def test_ps05_populated_downgrade_refused_empty_preserves_account(db):
    engine, cfg = db
    with engine.begin() as conn:
        oid = owner(conn)
        pid, _ = pair(conn, oid)
    with pytest.raises(RuntimeError, match="contains data"):
        migrate(engine, cfg, "downgrade", "0001_account")
    with engine.begin() as conn:
        assert conn.scalar(sa.select(projects.c.id)) == pid
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0018_knowledge_build_views"
        )
        conn.execute(cw.delete())
        conn.execute(projects.delete())
    migrate(engine, cfg, "downgrade", "0001_account")
    with engine.connect() as conn:
        assert conn.scalar(sa.select(accounts.c.id)) == oid
        assert not sa.inspect(conn).has_table("projects")
    migrate(engine, cfg, "upgrade", "head")


@pytest.mark.parametrize("created", ["projects", "construction_workspaces"])
def test_ps05_upgrade_failure_rolls_back_to_account(db, created):
    engine, cfg = db
    migrate(engine, cfg, "downgrade", "0001_account")
    with engine.begin() as conn:
        oid = owner(conn)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if f"CREATE TABLE {created} " in statement:
            raise RuntimeError("injected Project migration failure")

    sa.event.listen(engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            migrate(engine, cfg, "upgrade", "head")
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail)
    with engine.connect() as conn:
        assert set(sa.inspect(conn).get_table_names()) == {"accounts", "alembic_version"}
        assert conn.scalar(sa.select(accounts.c.id)) == oid
        assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0001_account"
    migrate(engine, cfg, "upgrade", "head")


def test_ps06_committing_writer_blocks_destructive_downgrade(db):
    engine, cfg = db
    with engine.begin() as conn:
        oid = owner(conn)
    ready, pids = Event(), []
    with engine.connect() as writer:
        transaction = writer.begin()
        pid, _ = pair(writer, oid)
        writer_pid = writer.scalar(sa.text("SELECT pg_backend_pid()"))

        def downgrade():
            from alembic import command

            with engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL lock_timeout='8s'"))
                pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
                cfg.attributes["connection"] = conn
                ready.set()
                command.downgrade(cfg, "0001_account")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(downgrade)
            try:
                assert ready.wait(5)
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if writer_pid in observer.scalar(
                            sa.text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[0]}
                        ):
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("writer/downgrade lock interleaving not observed")
                transaction.commit()
                with pytest.raises(RuntimeError, match="contains data"):
                    future.result(timeout=10)
            finally:
                if transaction.is_active:
                    transaction.rollback()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(projects.c.id)) == pid
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0018_knowledge_build_views"
        )


@pytest.mark.parametrize(
    "table,field",
    [(projects, "id")]
    + [(cw, f) for f in ["id", "project_id", "revision", "created_at", "updated_at"]],
)
def test_ps04_all_container_identity_and_facts_nonnull(db, table, field):
    engine, _ = db
    with engine.begin() as conn:
        oid = owner(conn)
    with pytest.raises(IntegrityError) as error, engine.begin() as conn:
        pair(conn, oid)
        conn.execute(table.update().values({field: None}))
    assert error.value.orig.sqlstate == "23502"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(projects)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(cw)) == 0
        assert conn.scalar(sa.select(accounts.c.id)) == oid
