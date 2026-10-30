"""Approved per-source/group limits, including restart and stale outcomes."""

import copy
import json

import pytest

from rpb.adapters.pdf_cleanup_budget import BudgetBlocked, new_budget, reserve, settle


def call(budget, source, elapsed=0.0):
    reservation = reserve(budget, source, 30)
    settle(budget, reservation["id"], elapsed)
    return reservation


def test_budget01_shorter_source_and_group_remaining_timeout():
    budget = new_budget()
    for _ in range(3):
        call(budget, "a", 30)
    call(budget, "a", 20)
    reservation = reserve(budget, "a", 30)
    assert reservation["timeout"] == 10
    settle(budget, reservation["id"], 10)
    with pytest.raises(BudgetBlocked, match="source_exhausted"):
        reserve(budget, "a", 30)
    for _ in range(3):
        call(budget, "b", 30)
    call(budget, "b", 25)
    assert reserve(budget, "c", 30)["timeout"] == 5


def test_budget02_count_limits_cannot_reset_by_changing_sources():
    budget = new_budget()
    for _ in range(32):
        call(budget, "a")
    with pytest.raises(BudgetBlocked, match="source_exhausted"):
        reserve(budget, "a", 30)
    for _ in range(32):
        call(budget, "b")
    with pytest.raises(BudgetBlocked, match="group_exhausted"):
        reserve(budget, "c", 30)
    assert reserve(new_budget(), "a", 30)["timeout"] == 30


def test_budget03_restart_preserves_unknown_outcome_and_no_second_dispatch():
    budget = new_budget()
    reservation = reserve(budget, "a", 30)
    restored = json.loads(json.dumps(budget))
    before = copy.deepcopy(restored)
    with pytest.raises(BudgetBlocked, match="outcome_unknown"):
        reserve(restored, "b", 30)
    assert restored == before
    assert restored["calls"] == 1 and restored["seconds"] == 30
    settle(restored, reservation["id"], 4)
    assert restored["seconds"] == 4
    assert restored["sources"]["a"]["seconds"] == 4
    current = reserve(restored, "a", 30)
    with pytest.raises(BudgetBlocked, match="stale_reservation"):
        settle(restored, reservation["id"], 0)
    assert restored["pending"] == current


def test_budget04_timeout_minimum_and_adapter_overrun_are_charged():
    budget = new_budget()
    reservation = reserve(budget, "a", 7)
    assert reservation["timeout"] == 7
    settle(budget, reservation["id"], 250)
    with pytest.raises(BudgetBlocked, match="group_exhausted"):
        reserve(budget, "b", 30)


def test_budget07_restart_uses_frozen_limits(monkeypatch):
    budget = json.loads(json.dumps(new_budget()))
    monkeypatch.setattr("rpb.adapters.pdf_cleanup_budget.CALL_SECONDS", 90)
    monkeypatch.setattr("rpb.adapters.pdf_cleanup_budget.SOURCE_CALLS", 64)
    for _ in range(32):
        assert call(budget, "a")["timeout"] == 30
    with pytest.raises(BudgetBlocked, match="source_exhausted"):
        reserve(budget, "a", 90)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_budget05_invalid_timeout_does_not_mutate(value):
    budget = new_budget()
    before = copy.deepcopy(budget)
    with pytest.raises(BudgetBlocked):
        reserve(budget, "a", value)
    assert budget == before


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True])
def test_budget06_invalid_elapsed_preserves_reservation(value):
    budget = new_budget()
    reservation = reserve(budget, "a", 30)
    before = copy.deepcopy(budget)
    with pytest.raises(BudgetBlocked):
        settle(budget, reservation["id"], value)
    assert budget == before
