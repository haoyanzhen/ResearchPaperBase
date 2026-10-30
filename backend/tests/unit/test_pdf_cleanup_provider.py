"""Provider boundary: chosen model, text-only payload and one authorized dispatch."""

import json
from contextlib import contextmanager

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.pdf_cleanup_provider import CleanupProvider
from rpb.adapters.pdf_text_cleanup import prepare

PROTOCOLS = ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]


def config(protocol):
    return {
        "protocol": protocol,
        "base_url": "https://example.test",
        "api_version": "",
        "parameters": {"max_output_tokens": 1024},
        "timeout_seconds": 20,
        "model_context_windows": {"chosen-model": 524288},
    }


def batch():
    return prepare(
        "first\nsecond\n", [{"page": 1, "start_offset": 0, "end_offset": 13}], max_input_bytes=4096
    ).batches[0]


def response(protocol, text):
    return {
        "openai_chat": {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]},
        "openai_responses": {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        },
        "anthropic_messages": {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
        },
        "gemini_content": {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]
        },
    }[protocol]


class HTTP:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def request(self, base, path, secret, protocol, version, body, timeout, authorize):
        with authorize():
            self.calls.append((path, body, timeout))
        return self.reply


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_lcp01_one_text_request_uses_selected_model_parameters_and_authority(protocol):
    reply = {"boundaries": [{"after_line_id": "p1:l1", "separator": "space"}]}
    http = HTTP(response(protocol, json.dumps(reply)))
    checks = []

    @contextmanager
    def authorized():
        checks.append("current permission checked")
        yield

    result = CleanupProvider(http).propose(
        config(protocol), "chosen-model", "secret-value", batch(), 5, authorized
    )
    assert result == reply and len(http.calls) == 1 and len(checks) == 1
    path, body, timeout = http.calls[0]
    assert timeout == 5
    if protocol == "gemini_content":
        assert path == "/models/chosen-model:generateContent"
        assert body["generationConfig"]["maxOutputTokens"] == 1024
    else:
        assert body["model"] == "chosen-model"
        assert body["max_output_tokens" if protocol == "openai_responses" else "max_tokens"] == 1024
    payload = json.dumps(body)
    assert "model_context_windows" not in payload and "524288" not in payload
    assert "first" in payload and "second" in payload
    assert (
        "secret-value" not in payload and "image_url" not in payload and "file_data" not in payload
    )


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_lcp02_current_denial_dispatches_nothing(protocol):
    http = HTTP({})

    @contextmanager
    def denied():
        raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
        yield

    with pytest.raises(ProviderFailure, match="PERMISSION_RESOURCE_UNAVAILABLE"):
        CleanupProvider(http).propose(config(protocol), "chosen", "secret", batch(), 1, denied)
    assert http.calls == []


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("bad", ['{"text":"rewritten"}', "null", "not JSON"])
def test_lcp03_invalid_output_is_failure_without_retry_or_model_switch(protocol, bad):
    http = HTTP(response(protocol, bad))

    @contextmanager
    def authorized():
        yield

    with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
        CleanupProvider(http).propose(config(protocol), "chosen", "secret", batch(), 1, authorized)
    assert len(http.calls) == 1


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("broken", ["incomplete", "malformed"])
def test_lcp04_incomplete_or_malformed_envelope_cannot_succeed(protocol, broken):
    valid = json.dumps({"boundaries": [{"after_line_id": "p1:l1", "separator": "space"}]})
    value = response(protocol, valid)
    if broken == "malformed":
        value = {"choices": [None], "output": [None], "content": [None], "candidates": [None]}
    elif protocol == "openai_chat":
        value["choices"][0]["finish_reason"] = "length"
    elif protocol == "openai_responses":
        value["status"] = "incomplete"
    elif protocol == "anthropic_messages":
        value["stop_reason"] = "max_tokens"
    else:
        value["candidates"][0]["finishReason"] = "MAX_TOKENS"
    http = HTTP(value)

    @contextmanager
    def authorized():
        yield

    with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
        CleanupProvider(http).propose(config(protocol), "chosen", "secret", batch(), 1, authorized)
    assert len(http.calls) == 1


@pytest.mark.parametrize("timeout", [0, -1, 31, float("nan"), float("inf")])
def test_lcp05_invalid_time_budget_is_rejected_before_dispatch(timeout):
    http = HTTP({})

    @contextmanager
    def authorized():
        yield

    with pytest.raises(ProviderFailure, match="CONFIG_CONNECTION_FAILED"):
        CleanupProvider(http).propose(
            config("openai_chat"), "chosen", "secret", batch(), timeout, authorized
        )
    assert http.calls == []


@pytest.mark.parametrize("final_present", [True, False])
def test_lcp06_gemini_thought_is_not_the_final_proposal(final_present):
    reply = {"boundaries": [{"after_line_id": "p1:l1", "separator": "space"}]}
    parts = [{"thought": True, "text": "Internal summary" if final_present else json.dumps(reply)}]
    if final_present:
        parts.append({"text": json.dumps(reply)})
    http = HTTP({"candidates": [{"finishReason": "STOP", "content": {"parts": parts}}]})

    @contextmanager
    def authorized():
        yield

    provider = CleanupProvider(http)
    selected_config = config("gemini_content")
    selected_config["parameters"]["custom_params"] = {"thinkingConfig": {"includeThoughts": True}}
    if final_present:
        assert (
            provider.propose(selected_config, "chosen", "secret", batch(), 1, authorized) == reply
        )
    else:
        with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
            provider.propose(selected_config, "chosen", "secret", batch(), 1, authorized)
    assert len(http.calls) == 1

    assert http.calls[0][1]["generationConfig"]["thinkingConfig"]["includeThoughts"] is True


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_lcp07_missing_output_uses_engine_default_without_mutating_config(protocol):
    from contextlib import nullcontext

    original = config(protocol)
    original["parameters"] = {}
    reply = {"boundaries": [{"after_line_id": "p1:l1", "separator": "space"}]}
    http = HTTP(response(protocol, json.dumps(reply)))
    CleanupProvider(http).propose(original, "chosen-model", "secret-value", batch(), 5, nullcontext)
    body = http.calls[0][1]
    payload = body.get("generationConfig", body)
    key = (
        "maxOutputTokens"
        if protocol == "gemini_content"
        else "max_output_tokens"
        if protocol == "openai_responses"
        else "max_tokens"
    )
    assert payload[key] == 4096
    assert original["parameters"] == {}
