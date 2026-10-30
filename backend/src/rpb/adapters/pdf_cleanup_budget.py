"""Serializable call budgets; callers must lock and commit reservations before I/O.

These functions never dispatch. An unsettled reservation survives restart and
blocks another call, since its external outcome cannot safely be assumed.
"""

import math
from typing import Any
from uuid import uuid4

SOURCE_SECONDS = 120.0
GROUP_SECONDS = 240.0
CALL_SECONDS = 30.0
SOURCE_CALLS = 32
GROUP_CALLS = 64


class BudgetBlocked(ValueError):
    pass


def new_budget(limits: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "revision": 1,
        "limits": dict(limits)
        if limits is not None
        else {
            "source_seconds": SOURCE_SECONDS,
            "group_seconds": GROUP_SECONDS,
            "call_seconds": CALL_SECONDS,
            "source_calls": SOURCE_CALLS,
            "group_calls": GROUP_CALLS,
        },
        "calls": 0,
        "seconds": 0.0,
        "sources": {},
        "pending": None,
    }


def reserve(budget: dict[str, Any], source_id: str, timeout: float) -> dict[str, Any]:
    """Charge a whole timeout first. Commit before send, under the Run lock."""
    if budget["pending"] is not None:
        raise BudgetBlocked("outcome_unknown")
    if not source_id or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise BudgetBlocked("invalid_request")
    source = budget["sources"].get(source_id, {"calls": 0, "seconds": 0.0})
    limits = budget["limits"]
    if budget["calls"] >= limits["group_calls"] or budget["seconds"] >= limits["group_seconds"]:
        raise BudgetBlocked("group_exhausted")
    if source["calls"] >= limits["source_calls"] or source["seconds"] >= limits["source_seconds"]:
        raise BudgetBlocked("source_exhausted")
    limit = min(
        timeout,
        limits["call_seconds"],
        limits["source_seconds"] - source["seconds"],
        limits["group_seconds"] - budget["seconds"],
    )
    reservation = {"id": str(uuid4()), "source_id": source_id, "timeout": limit}
    budget["calls"] += 1
    budget["seconds"] += limit
    source["calls"] += 1
    source["seconds"] += limit
    budget["sources"][source_id] = source
    budget["pending"] = reservation
    return dict(reservation)


def settle(budget: dict[str, Any], reservation_id: str, elapsed: float) -> None:
    """Known outcome only; duplicate/late settlements cannot refund a new call.

    The caller measures elapsed time monotonically and validates the attempt,
    source, authority and input dependencies before committing this mutation.
    A crash before commit keeps the entire reservation charged.
    """
    pending = budget["pending"]
    if pending is None or pending["id"] != reservation_id:
        raise BudgetBlocked("stale_reservation")
    if isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0:
        raise BudgetBlocked("invalid_elapsed")
    # An unexpectedly slow adapter must not earn a refund. Excess elapsed time
    # is charged too; subsequent calls cannot escape by changing source.
    adjustment = elapsed - pending["timeout"]
    budget["seconds"] = max(0.0, budget["seconds"] + adjustment)
    source = budget["sources"][pending["source_id"]]
    source["seconds"] = max(0.0, source["seconds"] + adjustment)
    budget["pending"] = None
