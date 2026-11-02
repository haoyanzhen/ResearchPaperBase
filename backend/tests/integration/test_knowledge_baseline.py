# ruff: noqa: F811
"""Schema constraints and baseline freezing; inserts are isolated test fixtures, not publication."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_construction_runs import Papers, setup
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_tables import runs
from rpb.adapters.run_worker import RunWorker


def test_project_baseline_freezes_at_slot_and_version_is_immutable(subject):
    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    first = post(c, h, path, body, "knowledge-fixture-start-1").json()["data"]["run"]
    second = post(c, h, path, body, "knowledge-fixture-start-2").json()["data"]["run"]
    assert RunWorker(app.state.run_store, Papers()).run_once()
    current = c.get(path + "/" + first["id"]).json()["data"]
    assert current["base_knowledge_version_id"] is None
    assert (
        post(
            c,
            h,
            path + "/" + first["id"] + "/cancel",
            {"expected_revision": current["revision"], "attempt_id": current["task"]["attempt_id"]},
            "knowledge-fixture-cancel-1",
        ).status_code
        == 200
    )
    with engine.connect() as conn:
        project_id = conn.scalar(sa.select(runs.c.project_id).where(runs.c.id == UUID(first["id"])))
    version_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            versions.insert().values(
                id=version_id,
                project_id=project_id,
                source_run_id=UUID(first["id"]),
                base_version_id=None,
                manifest={},
                manifest_digest="test-only",
                ready_proof={},
                published_at=datetime.now(UTC),
            )
        )
        conn.execute(heads.insert().values(project_id=project_id, version_id=version_id))
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                versions.update()
                .where(versions.c.id == version_id)
                .values(manifest={"changed": True})
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(versions.delete().where(versions.c.id == version_id))
    from rpb.adapters.source_tables import dispatch_limits

    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(app.state.run_store, Papers()).run_once()
    result = c.get(path + "/" + second["id"]).json()["data"]
    assert result["base_knowledge_version_id"] == str(version_id)
    assert result["input_snapshot"]["base_knowledge_version_id"] == str(version_id)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                versions.insert().values(
                    id=uuid4(),
                    project_id=project_id,
                    source_run_id=UUID(first["id"]),
                    base_version_id=None,
                    manifest={},
                    manifest_digest="duplicate",
                    ready_proof={},
                    published_at=datetime.now(UTC),
                )
            )
