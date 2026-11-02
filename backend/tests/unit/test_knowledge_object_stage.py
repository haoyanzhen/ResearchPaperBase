"""Text locators must cover the original revision without invented offsets."""

import pytest

from rpb.adapters.knowledge_object_stage import validated_locators
from rpb.modules.account_config.application.ports import AccountError


def test_complete_unicode_offsets_and_unknown_page_are_preserved():
    segments = [{"start_offset": 0, "end_offset": 3, "page": None}]
    assert validated_locators(segments, "文🙂字", "abstract_fallback") == segments


@pytest.mark.parametrize(
    "segments",
    [
        [],
        [{"start_offset": 0, "end_offset": 2, "page": 1}],
        [{"start_offset": 1, "end_offset": 3, "page": 1}],
        [
            {"start_offset": 0, "end_offset": 2, "page": 2},
            {"start_offset": 2, "end_offset": 3, "page": 1},
        ],
        [{"start_offset": 0, "end_offset": 3, "page": 0}],
    ],
)
def test_incomplete_or_invalid_locator_is_rejected(segments):
    with pytest.raises(AccountError):
        validated_locators(segments, "文🙂字", "full_text")


def test_multiple_segments_from_same_page_are_valid():
    segments = [
        {"start_offset": 0, "end_offset": 2, "page": 1},
        {"start_offset": 2, "end_offset": 3, "page": 1},
    ]
    assert validated_locators(segments, "文🙂字", "full_text") == segments


def test_abstract_fallback_cannot_claim_pdf_pages():
    with pytest.raises(AccountError):
        validated_locators(
            [{"start_offset": 0, "end_offset": 3, "page": 1}], "文🙂字", "abstract_fallback"
        )
