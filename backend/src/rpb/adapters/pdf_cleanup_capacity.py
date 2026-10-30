"""Declared model capacity and conservative, text-only cleanup batch planning."""

import copy
import json
from dataclasses import replace
from typing import Any

from rpb.adapters.pdf_text_cleanup import Batch, CleanupInvalid, CleanupPlan, prepare
from rpb.modules.account_config.domain.context_capacity import context_window
from rpb.modules.account_config.domain.llm_profiles import compile_for_model

DEFAULT_OUTPUT_TOKENS = 4096
FRAMING_RESERVE = 2048


def effective_config(config: dict[str, Any], model: str) -> tuple[dict[str, Any], int, bool]:
    """D-PDF-04: preserve explicit aliases; only this engine defaults to 4096."""
    result = copy.deepcopy(config)
    parameters = result["parameters"]
    defaulted = "max_output_tokens" not in parameters and not any(
        key in parameters.get("custom_params", {})
        for key in ("max_tokens", "max_completion_tokens")
    )
    if defaulted:
        parameters["max_output_tokens"] = DEFAULT_OUTPUT_TOKENS
    compiled = compile_for_model(
        result["protocol"], model, result["parameters"], result["api_version"]
    )
    payload = compiled.get("generationConfig", compiled)
    value = next(
        (
            payload[k]
            for k in ("max_tokens", "max_completion_tokens", "max_output_tokens", "maxOutputTokens")
            if k in payload
        ),
        None,
    )
    if value is None:
        raise CleanupInvalid("missing output capacity")
    return result, int(value), defaulted


def plan_for_model(text: str, segments: Any, config: dict[str, Any], model: str) -> CleanupPlan:
    """One UTF-8 byte per estimated token, plus framing/output reserves.

    This deliberately overestimates ordinary text. It is not a tokenizer or a
    guarantee about a Provider's hidden framing/reasoning; Provider overflow or
    truncation still fails explicitly. No original text is truncated.
    """
    effective, output, _ = effective_config(config, model)
    available = context_window(effective, model) - output - FRAMING_RESERVE
    if available <= 0:
        raise CleanupInvalid("context exhausted by output and framing")
    plan = prepare(text, segments, max_input_bytes=available)
    compiled = compile_for_model(
        effective["protocol"], model, effective["parameters"], effective["api_version"]
    )
    thinking = compiled.get("thinking", {}).get("budget_tokens", 0)
    thinking = max(
        thinking,
        compiled.get("generationConfig", {}).get("thinkingConfig", {}).get("thinkingBudget", 0),
    )
    response_capacity = output - thinking - min(1024, output // 4)
    batches = []
    for batch in plan.batches:
        start = 0
        while start < len(batch.lines) - 1:
            size = len(b'{"boundaries":[]}')
            end = start
            while end < len(batch.lines) - 1:
                entry = {"after_line_id": batch.lines[end].identity, "separator": "paragraph_break"}
                needed = len(json.dumps(entry).encode()) + 2
                if size + needed > response_capacity:
                    break
                size += needed
                end += 1
            if end == start:
                raise CleanupInvalid("boundary exceeds output capacity")
            batches.append(Batch(batch.lines[start : end + 1], batch.raw_digest))
            start = end
    return replace(plan, batches=tuple(batches))
