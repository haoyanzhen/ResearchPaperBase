"""Migrate only a caller-supplied, verified disposable test connection."""

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

from rpb.adapters import knowledge_build_tables, knowledge_paper_tables, knowledge_tables  # noqa: F401
from rpb.adapters.llm_tables import metadata

ERROR = "Migration execution unavailable: verified isolated test connection required"
try:
    config = context.config
except AttributeError:
    raise RuntimeError(ERROR) from None
connection = config.attributes.get("connection")
run_id = config.attributes.get("test_run_id")
if not isinstance(connection, Connection) or not isinstance(run_id, str):
    raise RuntimeError(ERROR)
if connection.dialect.name != "postgresql" or not run_id.startswith("rpb_test_"):
    raise RuntimeError(ERROR)
identity = connection.execute(
    text(
        "SELECT current_database(), current_user, "
        "current_setting('rpb.test_run_id', true), "
        "(SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname=current_user)"
    )
).one()
if tuple(identity) != (run_id, run_id, run_id, False):
    raise RuntimeError(ERROR)
context.configure(connection=connection, target_metadata=metadata, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
