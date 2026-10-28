"""ST03 and D-CW-01 A requirements, independent of persistence implementation."""

import pytest

from rpb.modules.construction.domain.terms import TermError, resolve_terms, term_write


def test_defaults_and_manual_selection_independent_of_auto_update():
    value = term_write({"query": " graph retrieval "})
    assert value["query"] == "graph retrieval"
    assert value["auto_update_enabled"] is True
    assert value["source_policy"] == {"mode": "all_resolvable"}
    assert term_write({"auto_update_enabled": False}, partial=True) == {
        "auto_update_enabled": False
    }


@pytest.mark.parametrize(
    "value",
    [
        {"query": " "},
        {"query": "q", "enabled": True},
        {"query": "q", "auto_update_enabled": 1},
        {"query": "q", "source_policy": {"mode": "selected", "source_refs": []}},
        {"query": "q", "keywords": [" "]},
    ],
)
def test_invalid_terms_rejected(value):
    with pytest.raises(TermError):
        term_write(value)


def test_selected_failure_is_whole_term_but_all_resolvable_preserves_success():
    resolution = {"sources": ["available"], "rejected": [{"reason": "disabled"}], "valid": False}
    result = resolve_terms(
        [
            {
                "term_id": "selected",
                "source_policy": {"mode": "selected"},
                "resolution": resolution,
            },
            {
                "term_id": "all",
                "source_policy": {"mode": "all_resolvable"},
                "resolution": {**resolution, "valid": True},
            },
        ]
    )
    assert result["valid"]
    assert [v["term_id"] for v in result["executable"]] == ["all"]
    assert result["executable"][0]["rejected"] == resolution["rejected"]
    assert [v["term_id"] for v in result["failed"]] == ["selected"]
    assert not resolve_terms(
        [{"term_id": "selected", "source_policy": {"mode": "selected"}, "resolution": resolution}]
    )["valid"]
