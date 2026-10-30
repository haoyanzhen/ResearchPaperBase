"""Declared model capacity defaults/overrides and strict metadata validation."""

import pytest

from rpb.modules.account_config.domain.context_capacity import (
    context_window,
    validate_context_windows,
)


def test_capacity_default_override_and_model_isolation():
    assert context_window({}, "unknown-model") == 262144
    data = {"model_context_windows": {"large": 524288, "small": 8192}}
    assert context_window(data, "large") == 524288
    assert context_window(data, "small") == 8192
    assert context_window(data, "other") == 262144
    assert context_window({"model_context_windows": {}}, "large") == 262144


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"": 1},
        {"x": True},
        {"x": 0},
        {"x": -1},
        {"x": 1.5},
        {"x": "256K"},
        {"x": 2147483648},
        {" x": 8192},
        {"x" * 201: 1},
    ],
)
def test_capacity_rejects_invalid_metadata(value):
    with pytest.raises(ValueError):
        validate_context_windows(value)


def test_capacity_boundaries_and_map_copy():
    values = {"one": 1, "max": 2147483647}
    result = validate_context_windows(values)
    result["one"] = 2
    assert values["one"] == 1
    with pytest.raises(ValueError):
        validate_context_windows({str(i): 1 for i in range(1001)})
