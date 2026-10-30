"""Closed candidate analysis structures from FR-025 / 04-01, without transport state."""

from typing import Any


def paper_analysis(value: Any) -> dict[str, Any]:
    fields = {"one_sentence_summary", "highlights", "relevance_points", "methods", "innovations"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("analysis_fields")
    result: dict[str, Any] = {}
    for name in fields:
        item = value[name]
        if name in {"one_sentence_summary", "methods"}:
            if not isinstance(item, str) or not item.strip() or len(item) > 10000 or "\x00" in item:
                raise ValueError("analysis_text")
            item.encode("utf-8")
            result[name] = item
        else:
            if not isinstance(item, list) or len(item) > 100:
                raise ValueError("analysis_array")
            if any(
                not isinstance(x, str) or not x.strip() or len(x) > 2000 or "\x00" in x
                for x in item
            ):
                raise ValueError("analysis_array_item")
            for text in item:
                text.encode("utf-8")
            result[name] = list(item)
    return result
