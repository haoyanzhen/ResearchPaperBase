"""Requirements of the user-approved title-only paper identity rule."""

import pytest

from rpb.modules.construction.domain.paper_identity import (
    normalized_paper_title,
    paper_title_groups,
)
from rpb.modules.construction.domain.runs import RunInputError


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Attention: Is All You Need!", "attention is all you need"),
        ("A—B", "ab"),
        ("《研究》：方法，结果。", "研究方法结果"),
        ("A_B", "ab"),
        ("Don't", "dont"),
        ("ÉTUDE", "étude"),
    ],
)
def test_pi01_punctuation_and_lowercase_are_sufficient(left, right):
    assert normalized_paper_title(left) == normalized_paper_title(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [("A B", "AB"), ("A  B", "A B"), ("C++", "C"), ("x=y", "xy"), ("ß", "ss")],
)
def test_pi02_no_undeclared_fuzzy_or_symbol_normalization(left, right):
    assert normalized_paper_title(left) != normalized_paper_title(right)


@pytest.mark.parametrize("title", [None, 1, True, "", " \t", "—。!?", " . "])
def test_pi03_missing_identity_is_rejected_not_merged(title):
    with pytest.raises(RunInputError):
        normalized_paper_title(title)


def test_pi04_grouping_retains_every_source_and_does_not_mutate_input():
    titles = ["FIRST!", "Second", "first", "FIRST", "Third"]
    before = titles.copy()
    assert paper_title_groups(titles) == [[0, 2, 3], [1], [4]]
    assert titles == before
    assert paper_title_groups([]) == []
    assert paper_title_groups(iter(titles)) == [[0, 2, 3], [1], [4]]


def test_pi05_doi_and_arxiv_are_not_required_or_used_for_matching():
    papers = [
        {"title": "A: Result", "doi": "10.1/one", "arxiv_id": None},
        {"title": "a result", "doi": None, "arxiv_id": "2601.00001"},
        {"title": "Different", "doi": "10.1/one", "arxiv_id": "2601.00001"},
    ]
    assert paper_title_groups(p["title"] for p in papers) == [[0, 1], [2]]


def test_pi06_normalization_is_idempotent():
    for title in ["《A》: Research!", "C++", "İSTANBUL", "α—β"]:
        value = normalized_paper_title(title)
        assert normalized_paper_title(value) == value
