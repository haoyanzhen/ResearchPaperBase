"""Requirements for source-complete text slices and their page locators."""

import copy
import hashlib
from uuid import uuid4

import pytest

from rpb.adapters.knowledge_chunk_integrity import verify_chunk_closure
from rpb.modules.account_config.application.ports import AccountError


def fixture():
    text = "甲乙丙丁戊己"
    identity, revision = uuid4(), uuid4()
    obj = {
        "id": identity,
        "paper_revision_id": revision,
        "dependencies": {"source_ids": ["x"]},
        "locators": [
            {"start_offset": 0, "end_offset": 3, "page": 1},
            {"start_offset": 3, "end_offset": 6, "page": 2},
        ],
    }
    rows = []
    for start, end in [(0, 4), (3, 6)]:
        rows.append(
            {
                "start_offset": start,
                "end_offset": end,
                "text_revision_id": identity,
                "asset_revision": revision,
                "source_kind": "full_text",
                "chunker_revision": "paragraph-token-v1",
                "dependencies": obj["dependencies"],
                "text_digest": hashlib.sha256(text[start:end].encode()).hexdigest(),
                "locators": [
                    {
                        "start_offset": max(start, x["start_offset"]),
                        "end_offset": min(end, x["end_offset"]),
                        "page": x["page"],
                    }
                    for x in obj["locators"]
                    if x["start_offset"] < end and x["end_offset"] > start
                ],
            }
        )
    return text, obj, rows


def test_unicode_chunks_and_page_spans_cover_original_text():
    text, obj, rows = fixture()
    verify_chunk_closure(text, obj, "full_text", rows)


@pytest.mark.parametrize(
    "defect", ["gap", "missing_tail", "digest", "page", "wrong_revision", "dependency", "chunker"]
)
def test_incomplete_or_untraceable_chunk_is_rejected(defect):
    text, obj, rows = fixture()
    rows = copy.deepcopy(rows)
    if defect == "gap":
        rows[0]["end_offset"] = 2
        rows[0]["text_digest"] = hashlib.sha256(text[:2].encode()).hexdigest()
        rows[0]["locators"] = [{"start_offset": 0, "end_offset": 2, "page": 1}]
    elif defect == "missing_tail":
        rows.pop()
    elif defect == "digest":
        rows[0]["text_digest"] = "bad"
    elif defect == "page":
        rows[0]["locators"][0]["page"] = 99
    elif defect == "wrong_revision":
        rows[0]["text_revision_id"] = uuid4()
    elif defect == "dependency":
        rows[0]["dependencies"] = {"source_ids": ["other"]}
    else:
        rows[0]["chunker_revision"] = "other"
    with pytest.raises(AccountError):
        verify_chunk_closure(text, obj, "full_text", rows)
