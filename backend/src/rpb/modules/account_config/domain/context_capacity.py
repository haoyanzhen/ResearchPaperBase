"""User-declared context capacity, not a Provider capability assertion."""

from typing import Any

DEFAULT_CONTEXT_WINDOW_TOKENS = 262_144
MAX_CONTEXT_WINDOW_TOKENS = 2_147_483_647


def validate_context_windows(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or len(value) > 1000:
        raise ValueError("invalid model context capacities")
    result = {}
    for model, capacity in value.items():
        if (
            not isinstance(model, str)
            or not 1 <= len(model) <= 200
            or model != model.strip()
            or type(capacity) is not int
            or not 1 <= capacity <= MAX_CONTEXT_WINDOW_TOKENS
        ):
            raise ValueError("invalid model context capacity")
        result[model] = capacity
    return result


def context_window(config: dict[str, Any], model: str) -> int:
    return validate_context_windows(config.get("model_context_windows", {})).get(
        model, DEFAULT_CONTEXT_WINDOW_TOKENS
    )
