"""Compile explicitly selected configuration parameters without I/O or implicit defaults."""

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

MAX_JSON_BYTES = 16384
MAX_DEPTH = 6
MAX_ITEMS = 64
ADAPTER_REVISION = "parameters-v1"

# These fields belong to the application, credentials or transport, never to user generation knobs.
RESERVED = frozenset(
    {
        "model",
        "messages",
        "input",
        "system",
        "instructions",
        "tools",
        "tool_choice",
        "stream",
        "headers",
        "authorization",
        "api_key",
        "secret",
        "base_url",
        "url",
        "user",
        "user_id",
        "project_id",
        "metadata",
        "provider",
        "store",
        "callback",
        "timeout",
        "timeout_seconds",
        "response_format",
        "previous_response_id",
    }
)
COMMON = frozenset(
    {
        "temperature",
        "top_p",
        "max_output_tokens",
        "stop",
        "seed",
        "frequency_penalty",
        "presence_penalty",
        "top_k",
    }
)


class ParameterError(ValueError):
    """Safe field path and reason only: never echo submitted values."""

    def __init__(self, field: str, reason: str) -> None:
        self.field, self.reason = field, reason
        super().__init__(f"{field}: {reason}")


@dataclass(frozen=True)
class ParameterSpec:
    kind: str
    target: tuple[str, ...]
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    children: dict[str, ParameterSpec] | None = None
    item: ParameterSpec | None = None


@dataclass(frozen=True)
class ModelCapabilities:
    protocol: str
    api_version: str
    model_id: str
    fields: dict[str, ParameterSpec]
    custom: dict[str, ParameterSpec]
    conflicts: tuple[tuple[str, str], ...] = ()
    known: bool = True


def _check_json(value: Any, field: str = "parameters", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ParameterError(field, "too_deep")
    if value is None or type(value) in {bool, str, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ParameterError(field, "non_finite")
        return
    if type(value) not in {dict, list}:
        raise ParameterError(field, "invalid_json_type")
    if len(value) > MAX_ITEMS:
        raise ParameterError(field, "too_many_items")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ParameterError(field, "invalid_key")
            _check_json(child, field, depth + 1)
    else:
        for child in value:
            _check_json(child, field, depth + 1)


def parse_parameter_json(text: str) -> dict[str, Any]:
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise ParameterError("parameters", "invalid_json") from None
    if size > MAX_JSON_BYTES:
        raise ParameterError("parameters", "too_large")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ParameterError("parameters", "duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=unique)
    except ParameterError:
        raise
    except ValueError, UnicodeError, RecursionError:
        raise ParameterError("parameters", "invalid_json") from None
    validate_structure(value)
    return dict(value)


def validate_structure(value: Any) -> None:
    if type(value) is not dict:
        raise ParameterError("parameters", "object_required")
    _check_json(value)
    # Bound serialized size even when entry is an already-decoded transport object.
    try:
        size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except ValueError, UnicodeError:
        raise ParameterError("parameters", "invalid_json") from None
    if size > MAX_JSON_BYTES:
        raise ParameterError("parameters", "too_large")
    if set(value) - COMMON - {"custom_params"}:
        raise ParameterError("parameters", "unknown_field")
    if "custom_params" in value and type(value["custom_params"]) is not dict:
        raise ParameterError("custom_params", "object_required")


def _validate(value: Any, spec: ParameterSpec, field: str) -> None:
    kind = spec.kind
    valid = (
        (kind == "number" and type(value) in {int, float})
        or (kind == "integer" and type(value) is int)
        or (kind == "boolean" and type(value) is bool)
        or (kind == "string" and type(value) is str)
        or (
            kind == "strings"
            and type(value) is list
            and 1 <= len(value) <= 4
            and all(type(v) is str and 1 <= len(v) <= 200 for v in value)
        )
        or (kind == "object" and type(value) is dict)
        or (kind == "array" and type(value) is list)
    )
    if not valid:
        raise ParameterError(field, "invalid_type")
    if kind in {"number", "integer"}:
        if spec.minimum is not None and value < spec.minimum:
            raise ParameterError(field, "below_minimum")
        if spec.maximum is not None and value > spec.maximum:
            raise ParameterError(field, "above_maximum")
    if kind == "string" and (len(value) > 200 or not value):
        raise ParameterError(field, "invalid_length")
    if kind == "object":
        if spec.children is None or set(value) - set(spec.children):
            raise ParameterError(field, "unsupported_object_field")
        for key, child in value.items():
            if key in RESERVED:
                raise ParameterError(field, "protected_target")
            _validate(child, spec.children[key], field)
    if kind == "array":
        if spec.item is None:
            raise ParameterError(field, "unsupported_array")
        for child in value:
            _validate(child, spec.item, field)
    if spec.choices and value not in spec.choices:
        raise ParameterError(field, "invalid_choice")


def compile_parameters(
    parameters: dict[str, Any], capabilities: ModelCapabilities
) -> dict[str, Any]:
    """Return generation fields only. Callers retain model/messages/credential ownership."""
    validate_structure(parameters)
    supplied = [
        (key, value, capabilities.fields, key)
        for key, value in parameters.items()
        if key != "custom_params"
    ]
    supplied += [
        (key, value, capabilities.custom, "custom_params")
        for key, value in parameters.get("custom_params", {}).items()
    ]
    present = {key for key, _, _, _ in supplied}
    for left, right in capabilities.conflicts:
        if left in present and right in present:
            raise ParameterError("parameters", "conflicting_fields")
    result: dict[str, Any] = {}
    used: list[tuple[str, ...]] = []
    for key, value, registry, field in supplied:
        spec = registry.get(key)
        # The registry is trusted code but cannot expand application-owned fields.
        if key in RESERVED or spec is None:
            raise ParameterError(field, "unsupported_field")
        if not spec.target or any(part in RESERVED or not part for part in spec.target):
            raise ParameterError(field, "protected_target")
        if any(
            path[: len(spec.target)] == spec.target or spec.target[: len(path)] == path
            for path in used
        ):
            raise ParameterError(field, "duplicate_target")
        _validate(value, spec, field)
        used.append(spec.target)
        target = result
        for part in spec.target[:-1]:
            target = target.setdefault(part, {})
        target[spec.target[-1]] = deepcopy(value)
    return result


def client_timeout(value: Any = None, *, deployment_limit: int = 120) -> int:
    """Transport-only bounded option. It never enters the generation payload."""
    if type(deployment_limit) is not int or not 1 <= deployment_limit <= 600:
        raise ParameterError("deployment_limit", "invalid_limit")
    if value is None:
        return min(30, deployment_limit)
    if type(value) is not int or not 1 <= value <= deployment_limit:
        raise ParameterError("timeout_seconds", "invalid_timeout")
    return value
