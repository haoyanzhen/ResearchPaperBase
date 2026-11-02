"""A missing frozen baseline must never masquerade as a first construction."""

import pytest

from rpb.adapters.knowledge_baseline_papers import baseline_papers
from rpb.adapters.paper_screening import baseline_ready
from rpb.modules.account_config.application.ports import AccountError


@pytest.mark.parametrize("snapshot", [None, {}, "invalid"])
def test_missing_baseline_fact_is_not_an_empty_project(snapshot):
    with pytest.raises(AccountError) as error:
        baseline_papers(None, {"input_snapshot": snapshot})
    assert error.value.code == "STORAGE_FILE_UNAVAILABLE"


def test_explicit_no_version_is_a_valid_first_baseline():
    assert baseline_papers(None, {"input_snapshot": {"base_knowledge_version_id": None}}) == []


def test_missing_or_mismatched_loaded_baseline_is_not_ready():
    assert not baseline_ready({"input_snapshot": {"base_knowledge_version_id": None}})
    assert not baseline_ready(
        {
            "input_snapshot": {"base_knowledge_version_id": "version-a"},
            "baseline_loaded_version_id": "version-b",
            "baseline_papers": [],
        }
    )
    assert baseline_ready(
        {
            "input_snapshot": {"base_knowledge_version_id": None},
            "baseline_loaded_version_id": None,
            "baseline_papers": [],
        }
    )
