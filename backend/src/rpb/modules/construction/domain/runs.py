"""Pure validation for manual retrieval inputs and the approved scoring policy."""

import math
from datetime import datetime
from typing import Any
from uuid import UUID


class RunInputError(ValueError):
    pass


def instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RunInputError("time")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RunInputError("time") from None
    if result.tzinfo is None:
        raise RunInputError("timezone")
    return result


def start_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {
        "mode",
        "selected_terms",
        "supplement_ids",
        "retrieval_range",
        "result_limit_per_source",
        "model_selection",
        "graph_mode",
    }:
        raise RunInputError("fields")
    if value.get("mode", "retrieval") != "retrieval" or value.get("supplement_ids", []) != []:
        raise RunInputError("unsupported input")
    terms = value.get("selected_terms")
    if not isinstance(terms, list) or not 1 <= len(terms) <= 100:
        raise RunInputError("terms")
    ids = set()
    for term in terms:
        if not isinstance(term, dict) or set(term) != {"term_id", "confirmed_revision"}:
            raise RunInputError("term")
        try:
            identity = str(UUID(term["term_id"]))
            UUID(term["confirmed_revision"])
        except ValueError, TypeError, AttributeError:
            raise RunInputError("identity") from None
        if identity in ids:
            raise RunInputError("duplicate")
        ids.add(identity)
    limit = value.get("result_limit_per_source")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise RunInputError("limit")
    window = value.get("retrieval_range")
    if not isinstance(window, dict) or set(window) != {"published_from", "published_until"}:
        raise RunInputError("window")
    first, last = instant(window["published_from"]), instant(window["published_until"])
    if first and last and first >= last:
        raise RunInputError("window")
    if not isinstance(value.get("graph_mode", "incremental"), str) or value.get(
        "graph_mode", "incremental"
    ) not in {"incremental", "rebuild"}:
        raise RunInputError("graph")
    if "model_selection" not in value:
        raise RunInputError("model")
    return {"mode": "retrieval", "supplement_ids": [], "graph_mode": "incremental", **value}


def initial_screening(score: Any) -> dict[str, Any]:
    """D-CW-02 A: invalid model output never becomes a fabricated zero score."""
    if type(score) not in {float, int} or not math.isfinite(score) or not 0 <= score <= 10:
        raise RunInputError("score")
    return {
        "score": score,
        "score_scale": {"min": 0, "max": 10},
        "threshold": 7,
        "threshold_source": "system_default",
        "valid": score >= 7,
    }
