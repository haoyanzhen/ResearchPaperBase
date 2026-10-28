"""Only consume the per-run unprivileged descriptor; never read DATABASE_URL."""

import json
import stat
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def storage(request):
    path = request.config.getoption("--storage-target")
    if not path:
        pytest.fail("Explicit disposable storage target required; no connection attempted")
    path = Path(path).resolve(strict=True)
    data = json.loads(path.read_text())
    run_id = data["run_id"]
    assert run_id.startswith("rpb_test_") and len(run_id) == 41
    assert data["database"] == data["username"] == run_id
    assert Path(data["host"]).resolve() == path.parent
    assert path.parent.name.startswith("rpb-db-")
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    engine = sa.create_engine(
        sa.URL.create(
            "postgresql+psycopg",
            username=run_id,
            password=data["password"],
            database=run_id,
            query={"host": data["host"], "port": "5432"},
        ),
        hide_parameters=True,
    )
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["test_run_id"] = run_id
    try:
        with engine.begin() as conn:
            assert conn.scalar(sa.text("SHOW server_version_num"))[:2] == "17"
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")  # env validates DB, role, marker, privilege before DDL
        yield engine, cfg
    finally:
        engine.dispose()


@pytest.fixture
def db(storage):
    engine, cfg = storage
    with engine.begin() as conn:
        for table in (
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
            "system_llm_tasks",
            "system_llm_commands",
            "system_llm_configs",
            "account_action_previews",
            "account_governance_audit",
            "account_reset_commands",
            "account_cleanup_records",
        ):
            conn.execute(sa.text(f"DELETE FROM {table}"))
        conn.execute(sa.text("DELETE FROM project_lifecycle_records"))
        conn.execute(sa.text("DELETE FROM project_create_commands"))
        conn.execute(sa.text("DELETE FROM auth_sessions"))
        conn.execute(sa.text("DELETE FROM construction_workspaces"))
        conn.execute(sa.text("DELETE FROM projects"))
        conn.execute(sa.text("DELETE FROM accounts"))
        conn.execute(sa.text("DELETE FROM source_dispatch_limits"))
    yield engine, cfg
    with engine.begin() as conn:
        for table in (
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
            "system_llm_tasks",
            "system_llm_commands",
            "system_llm_configs",
            "account_action_previews",
            "account_governance_audit",
            "account_reset_commands",
            "account_cleanup_records",
        ):
            conn.execute(sa.text(f"DELETE FROM {table}"))
        conn.execute(sa.text("DELETE FROM project_lifecycle_records"))
        conn.execute(sa.text("DELETE FROM project_create_commands"))
        conn.execute(sa.text("DELETE FROM auth_sessions"))
        conn.execute(sa.text("DELETE FROM construction_workspaces"))
        conn.execute(sa.text("DELETE FROM projects"))
        conn.execute(sa.text("DELETE FROM accounts"))
        conn.execute(sa.text("DELETE FROM source_dispatch_limits"))
