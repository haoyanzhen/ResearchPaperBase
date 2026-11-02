"""Record a build failure without rereading data whose policy may have changed."""

import copy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.auth import ACCOUNT_GOVERNANCE_LOCK
from rpb.adapters.construction_slots import is_current
from rpb.adapters.project import projects
from rpb.adapters.run_tables import runs, slots


def record_failure(
    store: Any,
    actor: UUID,
    project_id: UUID,
    run_id: UUID,
    attempt_id: UUID,
    claim_key: str,
    claim_id: str,
    failure: BaseException,
) -> None:
    from rpb.adapters.runs import persist, transition

    with store.account.engine.begin() as conn:
        conn.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
        )
        project = (
            conn.execute(sa.select(projects).where(projects.c.id == project_id).with_for_update())
            .mappings()
            .one_or_none()
        )
        conn.execute(
            sa.select(slots.c.project_id).where(slots.c.project_id == project_id).with_for_update()
        ).first()
        row = conn.execute(
            sa.select(runs.c.payload)
            .where(
                runs.c.id == run_id,
                runs.c.project_id == project_id,
            )
            .with_for_update()
        ).first()
        if row is None:
            return
        run = copy.deepcopy(row[0])
        claim = run.get(claim_key) or {}
        if not (
            run["status"] == "running"
            and run["owner_id"] == str(actor)
            and run["attempt_id"] == str(attempt_id)
            and claim.get("id") == claim_id
            and claim.get("state") == "running"
            and is_current(conn, run)
        ):
            return
        if (
            project is None
            or project["status"] != "active"
            or project["authority_epoch"] != run["authority_epoch"]
            or not store.terms.llm.permitted_actor(conn, actor)
        ):
            transition(run, "cancelled", "PERMISSION_RESOURCE_UNAVAILABLE")
        elif datetime.fromisoformat(run["lease_until"]) <= datetime.now(UTC):
            claim.update(state="unknown", error="PROVIDER_RESULT_UNKNOWN")
            transition(run, "running", "PROVIDER_RESULT_UNKNOWN")
        else:
            fallback = claim_key.removesuffix("_build_claim").upper() + "_BUILD_FAILED"
            claim.update(state="failed", error=getattr(failure, "code", fallback))
            transition(run, "failed", getattr(failure, "code", "PROVIDER_RESPONSE_INVALID"))
        persist(conn, run)
