"""Requirement-oriented parameter tests; no network, database or business mutation."""

from copy import deepcopy

import pytest

from rpb.modules.account_config.domain.parameters import (
    ModelCapabilities,
    ParameterError,
    client_timeout,
    compile_parameters,
    parse_parameter_json,
)
from rpb.modules.account_config.domain.parameters import (
    ParameterSpec as Spec,
)


def capabilities() -> ModelCapabilities:
    return ModelCapabilities(
        "fixture",
        "v1",
        "model-a",
        fields={
            "temperature": Spec("number", ("temperature",), 0, 2),
            "top_p": Spec("number", ("top_p",), 0, 1),
            "max_output_tokens": Spec("integer", ("max_tokens",), 1, 65536),
            "stop": Spec("strings", ("stop",)),
            "seed": Spec("integer", ("seed",), 0, 2**32 - 1),
        },
        custom={
            "reasoning": Spec(
                "object",
                ("reasoning",),
                children={
                    "effort": Spec("string", ("effort",), choices=("low", "high")),
                },
            ),
            "enabled": Spec("boolean", ("thinking", "enabled")),
            "budget": Spec("integer", ("thinking", "budget"), 1, 1000),
            "max_tokens": Spec("integer", ("max_tokens",), 1, 65536),
            "labels": Spec("array", ("labels",), item=Spec("string", ("value",))),
        },
    )


def test_lp01_omit_defaults_preserve_zero_false_and_input() -> None:
    cap = capabilities()
    assert compile_parameters({}, cap) == {}
    value = {"temperature": 0, "custom_params": {"enabled": False, "budget": 32}}
    original = deepcopy(value)
    assert compile_parameters(value, cap) == {
        "temperature": 0,
        "thinking": {"enabled": False, "budget": 32},
    }
    assert value == original
    assert compile_parameters({"max_output_tokens": 20}, cap) == {"max_tokens": 20}


def test_lp01_objects_arrays_are_detached_and_unknown_model_can_be_tested() -> None:
    cap = capabilities()
    value = {"stop": ["END"], "custom_params": {"reasoning": {"effort": "low"}, "labels": ["a"]}}
    result = compile_parameters(value, cap)
    result["reasoning"]["effort"] = "high"
    result["stop"].append("other")
    assert value["custom_params"]["reasoning"] == {"effort": "low"}
    assert value["stop"] == ["END"]
    unknown = ModelCapabilities("fixture", "v1", "unknown", cap.fields, cap.custom, known=False)
    assert compile_parameters({"temperature": 0}, unknown) == {"temperature": 0}
    # Compilation supplies protocol-checked inputs for explicit testing, not model availability.
    assert unknown.known is False


@pytest.mark.parametrize(
    "value",
    [
        {"temperature": True},
        {"temperature": -0.01},
        {"temperature": 2.01},
        {"top_p": 1.1},
        {"max_output_tokens": 0},
        {"max_output_tokens": 1.5},
        {"max_output_tokens": 65537},
        {"seed": -1},
        {"stop": []},
        {"stop": ["x"] * 5},
        {"stop": [1]},
        {"stop": [""]},
        {"temperature": None},
        {"custom_params": {"reasoning": {"effort": "unknown"}}},
        {"custom_params": {"reasoning": {"unknown": "value"}}},
        {"custom_params": {"labels": [True]}},
        {"custom_params": {"enabled": "false"}},
        {"custom_params": {"budget": 1001}},
        {"custom_params": []},
        {"unknown": "PRIVATE_VALUE"},
        {"custom_params": {"unregistered": 0}},
    ],
)
def test_lp02_invalid_and_unsupported_parameters_rejected(value: dict) -> None:
    with pytest.raises(ParameterError) as exc:
        compile_parameters(value, capabilities())
    assert "PRIVATE_VALUE" not in str(exc.value)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_lp02_nonfinite_rejected(number: float) -> None:
    with pytest.raises(ParameterError, match="non_finite"):
        compile_parameters({"temperature": number}, capabilities())


def test_lp03_alias_and_parent_conflicts_rejected_in_both_orders() -> None:
    cap = capabilities()
    with pytest.raises(ParameterError, match="duplicate_target"):
        compile_parameters({"max_output_tokens": 32, "custom_params": {"max_tokens": 32}}, cap)
    for fields in [
        {
            "root": Spec("object", ("thinking",), children={}),
            "leaf": Spec("boolean", ("thinking", "on")),
        },
        {
            "leaf": Spec("boolean", ("thinking", "on")),
            "root": Spec("object", ("thinking",), children={}),
        },
    ]:
        values = {k: {} if k == "root" else True for k in fields}
        with pytest.raises(ParameterError, match="duplicate_target"):
            compile_parameters(
                {"custom_params": values}, ModelCapabilities("f", "v", "m", {}, fields)
            )
    incompatible = ModelCapabilities(
        "f", "v", "m", cap.fields, cap.custom, (("temperature", "top_p"),)
    )
    with pytest.raises(ParameterError, match="conflicting_fields"):
        compile_parameters({"temperature": 1, "top_p": 1}, incompatible)


@pytest.mark.parametrize(
    "name",
    [
        "model",
        "messages",
        "input",
        "system",
        "tools",
        "tool_choice",
        "api_key",
        "headers",
        "base_url",
        "project_id",
        "stream",
        "provider",
        "store",
        "response_format",
    ],
)
def test_lp04_application_fields_protected_even_if_registered(name: str) -> None:
    cap = ModelCapabilities("f", "v", "m", {}, {name: Spec("string", (name,))})
    with pytest.raises(ParameterError):
        compile_parameters({"custom_params": {name: "PRIVATE_VALUE"}}, cap)
    cap = ModelCapabilities("f", "v", "m", {}, {"alias": Spec("string", (name,))})
    with pytest.raises(ParameterError, match="protected_target"):
        compile_parameters({"custom_params": {"alias": "PRIVATE_VALUE"}}, cap)


@pytest.mark.parametrize(
    "text",
    [
        '{"temperature":0,"temperature":1}',
        '{"custom_params":{"reasoning":{"effort":"low","effort":"high"}}}',
        '{"temperature":NaN}',
        '{"temperature":Infinity}',
        "[]",
        "null",
        "{",
        '{"custom_params":{"a":{"b":{"c":{"d":{"e":{"f":1}}}}}}}',
    ],
)
def test_lp05_malformed_duplicate_nonfinite_deep_json_rejected(text: str) -> None:
    with pytest.raises(ParameterError):
        parse_parameter_json(text)


def test_lp05_resource_bounds_and_json_types() -> None:
    with pytest.raises(ParameterError, match="too_large"):
        parse_parameter_json('{"custom_params":{"x":"' + "a" * 16384 + '"}}')
    with pytest.raises(ParameterError, match="too_many_items"):
        compile_parameters({"custom_params": {str(i): i for i in range(65)}}, capabilities())
    with pytest.raises(ParameterError, match="invalid_json_type"):
        compile_parameters({"temperature": {1, 2}}, capabilities())
    with pytest.raises(ParameterError, match="invalid_key"):
        compile_parameters({"custom_params": {1: 0}}, capabilities())
    with pytest.raises(ParameterError, match="too_large"):
        compile_parameters({"custom_params": {"labels": ["a" * 16384]}}, capabilities())
    assert parse_parameter_json('{"temperature":0,"custom_params":{"enabled":false}}') == {
        "temperature": 0,
        "custom_params": {"enabled": False},
    }


def test_lp06_client_timeout_is_separate_and_bounded() -> None:
    assert client_timeout() == 30
    assert client_timeout(deployment_limit=20) == 20
    assert client_timeout(120) == 120
    for value in [0, -1, 121, True, 1.5, "30"]:
        with pytest.raises(ParameterError):
            client_timeout(value)
    for limit in [0, 601, True]:
        with pytest.raises(ParameterError):
            client_timeout(deployment_limit=limit)
    with pytest.raises(ParameterError):
        compile_parameters({"custom_params": {"timeout_seconds": 10}}, capabilities())


@pytest.mark.parametrize(
    "text", ['{"seed":' + "1" * 5000 + "}", '{"custom_params":{"x":"' + chr(0xD800) + '"}}']
)
def test_lp05_numeric_decoder_and_surrogate_errors_are_safe(text: str) -> None:
    with pytest.raises(ParameterError, match="invalid_json"):
        parse_parameter_json(text)
