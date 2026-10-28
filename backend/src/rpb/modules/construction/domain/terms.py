"""Search term input and per-term resolution rules, independent of transports."""

from typing import Any
from uuid import UUID


class TermError(ValueError):
    pass


def source_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TermError("policy")
    if value == {"mode": "all_resolvable"}:
        return value
    if set(value) != {"mode", "source_refs"} or value["mode"] != "selected":
        raise TermError("policy")
    refs = value["source_refs"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 100:
        raise TermError("refs")
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"source", "config_id"}:
            raise TermError("ref")
        if (
            not isinstance(ref["source"], str)
            or ref["source"] not in {"user", "system"}
            or not isinstance(ref["config_id"], str)
        ):
            raise TermError("ref")
        try:
            UUID(ref["config_id"])
        except ValueError:
            raise TermError("ref") from None
        pair = (ref["source"], ref["config_id"])
        if pair in seen:
            raise TermError("duplicate")
        seen.add(pair)
    return value


def term_write(data: Any, partial: bool = False) -> dict[str, Any]:
    allowed = {
        "query",
        "keywords",
        "synonyms",
        "exclusions",
        "rationale",
        "coverage",
        "source_policy",
        "auto_update_enabled",
    }
    if not isinstance(data, dict) or set(data) - allowed or (not partial and "query" not in data):
        raise TermError("fields")
    result = (
        {}
        if partial
        else {
            "keywords": [],
            "synonyms": [],
            "exclusions": [],
            "rationale": "",
            "coverage": "",
            "source_policy": {"mode": "all_resolvable"},
            "auto_update_enabled": True,
        }
    )
    for name, value in data.items():
        if name in {"query", "rationale", "coverage"}:
            if (
                not isinstance(value, str)
                or not (1 if name == "query" else 0) <= len(value.strip()) <= 10000
            ):
                raise TermError(name)
            result[name] = value.strip()
        elif name in {"keywords", "synonyms", "exclusions"}:
            if (
                not isinstance(value, list)
                or len(value) > 100
                or any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 200 for x in value)
            ):
                raise TermError(name)
            result[name] = [x.strip() for x in value]
        elif name == "auto_update_enabled":
            if type(value) is not bool:
                raise TermError(name)
            result[name] = value
        else:
            result[name] = source_policy(value)
    return result


def resolve_terms(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Consume per-term resolver facts: selected is atomic, other terms may continue."""
    executable, failed = [], []
    for item in items:
        result = item["resolution"]
        selected = item["source_policy"]["mode"] == "selected"
        if not result["sources"] or (selected and (result["rejected"] or not result["valid"])):
            failed.append({"term_id": item["term_id"], "resolution": result})
        else:
            executable.append(
                {
                    "term_id": item["term_id"],
                    "sources": result["sources"],
                    "rejected": result["rejected"],
                }
            )
    return {"executable": executable, "failed": failed, "valid": bool(executable)}
