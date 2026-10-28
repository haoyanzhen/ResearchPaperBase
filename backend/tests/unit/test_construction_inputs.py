"""Approved policy boundaries, not prompt-output snapshots."""

from uuid import uuid4

import pytest

from rpb.modules.construction.domain.runs import RunInputError, initial_screening, start_input


@pytest.mark.parametrize("score,valid", [(0, False), (6.99, False), (7, True), (10, True)])
def test_cw02_default_boundary(score, valid):
    result = initial_screening(score)
    assert result == {
        "score": score,
        "score_scale": {"min": 0, "max": 10},
        "threshold": 7,
        "threshold_source": "system_default",
        "valid": valid,
    }


@pytest.mark.parametrize("score", [None, True, "7", -1, 11, float("nan"), float("inf")])
def test_cw02_invalid_is_not_zero_or_valid(score):
    with pytest.raises(RunInputError):
        initial_screening(score)


def valid_input():
    return {
        "selected_terms": [{"term_id": str(uuid4()), "confirmed_revision": str(uuid4())}],
        "retrieval_range": {"published_from": None, "published_until": None},
        "result_limit_per_source": 100,
        "model_selection": {},
    }


def test_cr01_defaults_and_rejections():
    value = valid_input()
    assert start_input(value)["mode"] == "retrieval"
    for patch in (
        {"selected_terms": []},
        {"selected_terms": value["selected_terms"] * 2},
        {"result_limit_per_source": True},
        {"result_limit_per_source": 1001},
        {"mode": "revision_only"},
        {"unknown": 1},
        {"retrieval_range": {"published_from": "2026-01-01", "published_until": None}},
        {
            "retrieval_range": {
                "published_from": "2026-01-01T00:00:00Z",
                "published_until": "2026-01-01T00:00:00Z",
            }
        },
    ):
        with pytest.raises(RunInputError):
            start_input(value | patch)


def test_cursor_expiry_and_revision_binding(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters import runs
    from rpb.modules.account_config.application.ports import AccountError

    items = [{"id": "a"}, {"id": "b"}]
    cursor = runs.page(items, {"page_size": 1}, "secret", ["actor", "project", "run", "rev"])[
        "next_cursor"
    ]
    with pytest.raises(AccountError) as exc:
        runs.page(items, {"cursor": cursor}, "secret", ["actor", "project", "run", "changed"])
    assert exc.value.code == "VALIDATION_CURSOR_MISMATCH"

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(hours=2)

    monkeypatch.setattr(runs, "datetime", Later)
    with pytest.raises(AccountError) as exc:
        runs.page(items, {"cursor": cursor}, "secret", ["actor", "project", "run", "rev"])
    assert exc.value.code == "VALIDATION_CURSOR_EXPIRED"
