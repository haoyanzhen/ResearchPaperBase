"""Graph claims must reference real, same-slice text and closed predicate kinds."""

import copy

import pytest

from rpb.modules.knowledge.domain.graph_validation import validate_extraction


def test_claims_are_bound_to_real_text_and_supported_endpoint_types():
    text = "A transformer uses attention."
    value = {
        "entities": [{"kind": "method", "label": "attention", "start": 19, "end": 28}],
        "claims": [
            {
                "source": "asset",
                "target": 0,
                "predicate": "uses_method",
                "start": 0,
                "end": len(text),
                "quote": text,
            }
        ],
    }
    entities, claims = validate_extraction(text, value)
    assert entities[0].label == "attention" and claims[0].predicate == "uses_method"
    for change in ("invented_span", "wrong_target", "unsupported_predicate", "other_text"):
        wrong = copy.deepcopy(value)
        if change == "invented_span":
            wrong["claims"][0]["quote"] = "invented"
        elif change == "wrong_target":
            wrong["claims"][0]["target"] = 1
        elif change == "unsupported_predicate":
            wrong["claims"][0]["predicate"] = "causes"
        else:
            wrong["entities"][0]["label"] = "other"
        with pytest.raises(ValueError):
            validate_extraction(text, wrong)


def test_empty_extraction_is_not_an_error_and_unclosed_shapes_fail():
    assert validate_extraction("No named entities.", {"entities": [], "claims": []}) == ([], [])
    with pytest.raises(ValueError):
        validate_extraction("x", {"entities": [], "claims": [], "instruction": "publish"})
    with pytest.raises(ValueError):
        validate_extraction(
            "x", {"entities": [{"kind": [], "label": "x", "start": 0, "end": 1}], "claims": []}
        )


def test_repeated_label_cannot_retarget_support_to_another_occurrence():
    text = "attention. Other attention."
    proposal = {
        "entities": [{"kind": "method", "label": "attention", "start": 0, "end": 9}],
        "claims": [
            {
                "source": "asset",
                "target": 0,
                "predicate": "uses_method",
                "start": 11,
                "end": len(text),
                "quote": text[11:],
            }
        ],
    }
    with pytest.raises(ValueError):
        validate_extraction(text, proposal)
    other = "alpha. alpha beta."
    relation = {
        "entities": [
            {"kind": "concept", "label": "alpha", "start": 0, "end": 5},
            {"kind": "method", "label": "beta", "start": 13, "end": 17},
        ],
        "claims": [
            {
                "source": 0,
                "target": 1,
                "predicate": "related_to",
                "start": 7,
                "end": len(other),
                "quote": other[7:],
            }
        ],
    }
    with pytest.raises(ValueError):
        validate_extraction(other, relation)
