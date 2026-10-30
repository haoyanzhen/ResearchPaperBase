"""PA01: requirement-derived shape, boundaries and rejection of partial success."""

import copy

import pytest

from rpb.modules.construction.domain.analysis import paper_analysis


def complete():
    return dict(
        one_sentence_summary="总结",
        highlights=["亮点"],
        relevance_points=["相关性"],
        methods="摘要未提供方法细节",
        innovations=[],
    )


def test_complete_and_empty_arrays_preserve_content_without_aliasing():
    value = complete()
    output = paper_analysis(value)
    assert output == value
    output["highlights"].append("new")
    assert value == complete()


@pytest.mark.parametrize("field", list(complete()))
def test_missing_field_is_not_partial_success(field):
    value = complete()
    del value[field]
    with pytest.raises(ValueError):
        paper_analysis(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "text",
        {},
        {**complete(), "business_type": "paper"},
        {**complete(), "important_summary": "material"},
    ],
)
def test_wrong_kind_or_shape_rejected(value):
    with pytest.raises(ValueError):
        paper_analysis(value)


@pytest.mark.parametrize("field", ["one_sentence_summary", "methods"])
@pytest.mark.parametrize(
    "value", ["", " \n", 1, True, None, [], "x" * 10001, "\ud800", "valid\x00text"]
)
def test_text_rejections(field, value):
    with pytest.raises(ValueError):
        paper_analysis({**complete(), field: value})


@pytest.mark.parametrize("field", ["highlights", "relevance_points", "innovations"])
@pytest.mark.parametrize(
    "value",
    [
        None,
        "x",
        {},
        [""],
        [" "],
        [True],
        [1],
        [None],
        ["x" * 2001],
        ["x"] * 101,
        ["\ud800"],
        ["valid\x00text"],
    ],
)
def test_array_rejections(field, value):
    with pytest.raises(ValueError):
        paper_analysis({**complete(), field: value})


def test_inclusive_maxima_unicode_and_no_silent_truncation():
    value = dict(
        one_sentence_summary="中" * 10000,
        methods="m" * 10000,
        highlights=["字" * 2000] * 100,
        relevance_points=[],
        innovations=[],
    )
    original = copy.deepcopy(value)
    assert paper_analysis(value) == original
    assert value == original
