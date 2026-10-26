"""Versioned protocol descriptors. Provider acceptance is established by explicit tests."""

from typing import Any

from rpb.modules.account_config.domain.parameters import (
    ModelCapabilities,
    ParameterError,
    compile_parameters,
)
from rpb.modules.account_config.domain.parameters import (
    ParameterSpec as Spec,
)

PROTOCOLS = ("openai_chat", "openai_responses", "anthropic_messages", "gemini_content")


def capabilities(protocol: str, model_id: str, api_version: str = "") -> ModelCapabilities:
    if protocol not in PROTOCOLS:
        raise ParameterError("protocol", "unsupported_protocol")
    if not isinstance(model_id, str) or not 1 <= len(model_id.strip()) <= 200:
        raise ParameterError("model_id", "invalid_model")
    prefix = ("generationConfig",) if protocol == "gemini_content" else ()
    token = {
        "openai_chat": "max_tokens",
        "openai_responses": "max_output_tokens",
        "anthropic_messages": "max_tokens",
        "gemini_content": "maxOutputTokens",
    }[protocol]
    fields = {
        "max_output_tokens": Spec("integer", prefix + (token,), 1, 1048576),
        "temperature": Spec(
            "number", prefix + ("temperature",), 0, 1 if protocol == "anthropic_messages" else 2
        ),
        "top_p": Spec("number", prefix + ("topP" if prefix else "top_p",), 0, 1),
    }
    custom: dict[str, Spec] = {}
    conflicts: tuple[tuple[str, str], ...] = ()
    if protocol != "openai_responses":
        stop = (
            "stopSequences"
            if prefix
            else "stop_sequences"
            if protocol == "anthropic_messages"
            else "stop"
        )
        fields["stop"] = Spec("strings", prefix + (stop,))
    if protocol in {"openai_chat", "gemini_content"}:
        fields["seed"] = Spec("integer", prefix + ("seed",), 0, 2147483647)
        for name in ("frequency_penalty", "presence_penalty"):
            target = name if not prefix else name.split("_")[0] + "Penalty"
            fields[name] = Spec("number", prefix + (target,), -2, 2)
    if protocol in {"anthropic_messages", "gemini_content"}:
        fields["top_k"] = Spec("integer", prefix + ("topK" if prefix else "top_k",), 1, 1000)
    if protocol == "openai_chat":
        custom["reasoning_effort"] = Spec(
            "string",
            ("reasoning_effort",),
            choices=("none", "minimal", "low", "medium", "high", "xhigh"),
        )
        custom["max_tokens"] = Spec("integer", (token,), 1, 1048576)
        custom["max_completion_tokens"] = Spec("integer", ("max_completion_tokens",), 1, 1048576)
        conflicts = (
            ("max_output_tokens", "max_completion_tokens"),
            ("max_tokens", "max_completion_tokens"),
        )
    if protocol == "openai_responses":
        custom["reasoning"] = Spec(
            "object",
            ("reasoning",),
            children={
                "effort": Spec(
                    "string",
                    ("effort",),
                    choices=("none", "minimal", "low", "medium", "high", "xhigh"),
                ),
            },
        )
    if protocol == "anthropic_messages":
        custom["thinking"] = Spec(
            "object",
            ("thinking",),
            children={
                "type": Spec("string", ("type",), choices=("enabled", "disabled", "adaptive")),
                "budget_tokens": Spec("integer", ("budget_tokens",), 1024, 1048575),
            },
        )
    if protocol == "gemini_content":
        custom["thinkingConfig"] = Spec(
            "object",
            prefix + ("thinkingConfig",),
            children={
                "thinkingBudget": Spec("integer", ("thinkingBudget",), -1, 1048576),
                "includeThoughts": Spec("boolean", ("includeThoughts",)),
            },
        )
    # Pinned, narrow compatibility facts; unknown identifiers still require explicit tests.
    reasoning = model_id in {"o1", "o3", "o3-mini", "o4-mini"} or model_id in {
        "o1-2024-12-17",
        "o3-2025-04-16",
        "o3-mini-2025-01-31",
        "o4-mini-2025-04-16",
    }
    if reasoning and protocol == "openai_chat" and not api_version:
        fields["max_output_tokens"] = Spec("integer", ("max_completion_tokens",), 1, 1048576)
        for unsupported in (
            "temperature",
            "top_p",
            "stop",
            "seed",
            "frequency_penalty",
            "presence_penalty",
        ):
            fields.pop(unsupported, None)
        custom.pop("max_tokens", None)
    return ModelCapabilities(
        protocol,
        api_version,
        model_id,
        fields,
        custom,
        conflicts,
        known=reasoning and protocol == "openai_chat" and not api_version,
    )


def compile_for_model(
    protocol: str, model_id: str, parameters: dict[str, Any], api_version: str = ""
) -> dict[str, Any]:
    cap = capabilities(protocol, model_id, api_version)
    payload = compile_parameters(parameters, cap)
    if protocol == "anthropic_messages" and "thinking" in payload:
        thinking = payload["thinking"]
        kind = thinking.get("type")
        if not kind or (kind == "enabled") != ("budget_tokens" in thinking):
            raise ParameterError("custom_params", "invalid_thinking_combination")
        if kind == "enabled":
            if "max_tokens" not in payload or thinking["budget_tokens"] >= payload["max_tokens"]:
                raise ParameterError(
                    "custom_params", "thinking_budget_requires_larger_output_limit"
                )
            if "temperature" in payload or "top_k" in payload:
                raise ParameterError("parameters", "thinking_sampling_conflict")
    return payload
