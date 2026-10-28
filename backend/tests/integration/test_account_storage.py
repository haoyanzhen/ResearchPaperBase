"""B02 storage requirements, real committed transactions and deterministic lock contention."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.exc import IntegrityError

from rpb.adapters.account import accounts, metadata


def values(suffix="one"):
    return dict(
        username=f"User {suffix}",
        email=f"{suffix}@example.invalid",
        username_key=f"user-{suffix}",
        email_key=f"{suffix}@example.invalid",
        password_hash="$test-only$irreversible-placeholder",
        enabled=True,
        is_admin=False,
    )


def migrate(engine, cfg, action, revision):
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        getattr(command, action)(cfg, revision)


def test_ac01_migration_metadata_and_rerun(db):
    engine, cfg = db
    with engine.begin() as conn:
        identity = conn.execute(
            accounts.insert().values(**values()).returning(accounts.c.id)
        ).scalar_one()
    migrate(engine, cfg, "upgrade", "head")
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), metadata) == []
        assert conn.scalar(sa.select(accounts.c.id)) == identity
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0014_construction_runs"
        )
        columns = sa.inspect(conn).get_columns("accounts")
        assert not {"password", "plaintext_password", "session_token"} & {
            c["name"] for c in columns
        }
        constraints = {c["name"] for c in sa.inspect(conn).get_check_constraints("accounts")}
        assert constraints == {
            "ck_accounts_username_key",
            "ck_accounts_email_key",
            "ck_accounts_password_hash",
            "ck_accounts_display_name",
        }


def test_ac02_committed_identity_status_revision_and_utc(db):
    engine, _ = db
    with engine.begin() as conn:
        row = (
            conn.execute(accounts.insert().values(**values()).returning(accounts)).mappings().one()
        )
    assert isinstance(row["id"], UUID) and isinstance(row["revision"], UUID)
    assert row["created_at"].utcoffset().total_seconds() == 0
    revision = uuid4()
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            accounts.update()
            .where(accounts.c.id == row["id"])
            .values(enabled=False, is_admin=True, revision=revision, updated_at=now)
        )
    with engine.connect() as conn:
        changed = conn.execute(sa.select(accounts)).mappings().one()
        assert changed["id"] == row["id"] and changed["created_at"] == row["created_at"]
        assert changed["revision"] == revision and changed["updated_at"] == now
        assert changed["enabled"] is False and changed["is_admin"] is True
        assert changed["password_hash"] == values()["password_hash"]


@pytest.mark.parametrize("field", ["username_key", "email_key"])
def test_ac03_unique_keys_rollback_whole_transaction(db, field):
    engine, _ = db
    with engine.begin() as conn:
        conn.execute(accounts.insert().values(**values()))
    with pytest.raises(IntegrityError) as error, engine.begin() as conn:
        conn.execute(accounts.insert().values(**values("would-rollback")))
        duplicate = values("two") | {field: values()[field]}
        conn.execute(accounts.insert().values(**duplicate))
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == f"uq_accounts_{field}"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1


@pytest.mark.parametrize("field", ["username_key", "email_key", "password_hash"])
@pytest.mark.parametrize("bad", [None, ""])
def test_ac04_required_storage_keys(db, field, bad):
    engine, _ = db
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(accounts.insert().values(**(values() | {field: bad})))
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 0


@pytest.mark.parametrize("field", ["username_key", "email_key"])
def test_ac05_concurrent_duplicate_blocks_then_rejects(db, field):
    engine, _ = db
    ready = Event()
    pids = []
    with engine.connect() as winner:
        transaction = winner.begin()
        winner.execute(accounts.insert().values(**values()))
        winner_pid = winner.scalar(sa.text("SELECT pg_backend_pid()"))

        def loser():
            with engine.begin() as conn:
                pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
                conn.execute(sa.text("SET LOCAL lock_timeout='8s'"))
                ready.set()
                conn.execute(accounts.insert().values(**(values("two") | {field: values()[field]})))

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(loser)
            try:
                assert ready.wait(5)
                deadline = time.monotonic() + 5
                with engine.connect() as observer:
                    while time.monotonic() < deadline:
                        blockers = observer.scalar(
                            sa.text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[0]}
                        )
                        if winner_pid in blockers:
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("Required unique-key lock interleaving not observed")
                transaction.commit()
                with pytest.raises(IntegrityError) as error:
                    future.result(timeout=10)
                assert error.value.orig.sqlstate == "23505"
            finally:
                if transaction.is_active:
                    transaction.rollback()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1


def test_ac06_downgrade_protects_committed_data_then_empty_roundtrip(db):
    engine, cfg = db
    with engine.begin() as conn:
        conn.execute(accounts.insert().values(**values()))
    with pytest.raises(RuntimeError, match="contains data"):
        migrate(engine, cfg, "downgrade", "base")
    with engine.begin() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0014_construction_runs"
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1
        conn.execute(accounts.delete())
    migrate(engine, cfg, "downgrade", "base")
    with engine.connect() as conn:
        assert not sa.inspect(conn).has_table("accounts")
    migrate(engine, cfg, "upgrade", "head")


def test_ac07_failed_upgrade_atomic_and_retryable(db):
    engine, cfg = db
    migrate(engine, cfg, "downgrade", "base")

    def fail_after_create(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE accounts" in statement:
            raise RuntimeError("injected failure after physical CREATE")

    sa.event.listen(engine, "after_cursor_execute", fail_after_create)
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            migrate(engine, cfg, "upgrade", "head")
    finally:
        sa.event.remove(engine, "after_cursor_execute", fail_after_create)
    with engine.connect() as conn:
        assert not sa.inspect(conn).has_table("accounts")
        assert conn.scalar(sa.text("SELECT count(*) FROM alembic_version")) == 0
    migrate(engine, cfg, "upgrade", "head")


def test_ac08_wrong_run_marker_refuses_ddl(db):
    engine, cfg = db
    original = cfg.attributes["test_run_id"]
    cfg.attributes["test_run_id"] = "rpb_test_wrong"
    try:
        with pytest.raises(RuntimeError, match="verified isolated"):
            migrate(engine, cfg, "downgrade", "base")
    finally:
        cfg.attributes["test_run_id"] = original
    with engine.connect() as conn:
        assert sa.inspect(conn).has_table("accounts")
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0014_construction_runs"
        )
        privileges = conn.execute(
            sa.text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname=current_user"
            )
        ).one()
        assert tuple(privileges) == (False, False, False)


@pytest.mark.parametrize(
    "field",
    ["id", "username", "email", "enabled", "is_admin", "revision", "created_at", "updated_at"],
)
def test_ac04_other_required_facts_reject_null(db, field):
    engine, _ = db
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(accounts.insert().values(**(values() | {field: None})))
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 0


def test_ac06_concurrent_committing_writer_prevents_downgrade(db):
    """R01: empty-check followed by DROP must not erase a racing committed account."""
    engine, cfg = db
    ready = Event()
    pids = []
    with engine.connect() as writer:
        transaction = writer.begin()
        writer.execute(accounts.insert().values(**values()))
        writer_pid = writer.scalar(sa.text("SELECT pg_backend_pid()"))

        def downgrade():
            with engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL lock_timeout='8s'"))
                pids.append(conn.scalar(sa.text("SELECT pg_backend_pid()")))
                cfg.attributes["connection"] = conn
                ready.set()
                command.downgrade(cfg, "base")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(downgrade)
            try:
                assert ready.wait(5)
                with engine.connect() as observer:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        blockers = observer.scalar(
                            sa.text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[0]}
                        )
                        if writer_pid in blockers:
                            break
                        time.sleep(0.01)
                    else:
                        pytest.fail("Required writer/downgrade interleaving not observed")
                transaction.commit()
                with pytest.raises(RuntimeError, match="contains data"):
                    future.result(timeout=10)
            finally:
                if transaction.is_active:
                    transaction.rollback()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(accounts)) == 1
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0014_construction_runs"
        )
