"""Validate that stored chunks cover their protected text and keep source locators."""

import hashlib
from typing import Any

from rpb.adapters.knowledge_object_stage import validated_locators
from rpb.modules.account_config.application.ports import AccountError


def verify_chunk_closure(text: str, obj: Any, source_kind: str, rows: list[Any]) -> None:
    locations = validated_locators(obj["locators"], text, source_kind)
    if not rows or not text.strip():
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
    covered = 0
    for row in sorted(rows, key=lambda item: (item["start_offset"], item["end_offset"])):
        start, end = row["start_offset"], row["end_offset"]
        if (
            type(start) is not int
            or type(end) is not int
            or start < 0
            or start > covered
            or not start < end <= len(text)
            or row["text_revision_id"] != obj["id"]
            or row["asset_revision"] != obj["paper_revision_id"]
            or row["source_kind"] != source_kind
            or row["chunker_revision"] != "paragraph-token-v1"
            or row["dependencies"] != obj["dependencies"]
            or hashlib.sha256(text[start:end].encode()).hexdigest() != row["text_digest"]
        ):
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        expected = [
            {
                "start_offset": max(start, loc["start_offset"]),
                "end_offset": min(end, loc["end_offset"]),
                "page": loc["page"],
            }
            for loc in locations
            if loc["start_offset"] < end and loc["end_offset"] > start
        ]
        if row["locators"] != expected:
            raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
        covered = max(covered, end)
    if covered != len(text):
        raise AccountError("STORAGE_FILE_UNAVAILABLE", 410)
