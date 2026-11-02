"""Project-local writer ownership, fenced by a monotonically increasing epoch."""

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from rpb.adapters.run_tables import slots
from rpb.modules.account_config.application.ports import AccountError


def acquire(conn: Any, run: Any) -> None:
    project_id, run_id = UUID(run["project_id"]), UUID(run["id"])
    conn.execute(insert(slots).values(project_id=project_id).on_conflict_do_nothing())
    current = (
        conn.execute(sa.select(slots).where(slots.c.project_id == project_id).with_for_update())
        .mappings()
        .one()
    )
    if current["occupant_run_id"] is not None:
        raise AccountError("LOCK_CONSTRUCTION_OCCUPIED", 409)
    epoch = current["epoch"] + 1
    conn.execute(
        slots.update()
        .where(slots.c.project_id == project_id)
        .values(occupant_run_id=run_id, epoch=epoch)
    )
    run["slot_epoch"] = epoch


def is_current(conn: Any, run: Any) -> bool:
    if not isinstance(run.get("slot_epoch"), int):
        return False
    return (
        conn.execute(
            sa.select(slots.c.epoch)
            .where(
                slots.c.project_id == UUID(run["project_id"]),
                slots.c.occupant_run_id == UUID(run["id"]),
                slots.c.epoch == run["slot_epoch"],
            )
            .with_for_update()
        ).scalar_one_or_none()
        is not None
    )


def release(conn: Any, run: Any) -> None:
    if not isinstance(run.get("slot_epoch"), int):
        return
    conn.execute(
        slots.update()
        .where(
            slots.c.project_id == UUID(run["project_id"]),
            slots.c.occupant_run_id == UUID(run["id"]),
            slots.c.epoch == run["slot_epoch"],
        )
        .values(occupant_run_id=None, epoch=slots.c.epoch + 1)
    )
