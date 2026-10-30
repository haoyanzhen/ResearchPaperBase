"""Protocol payloads and false-success rejection without external Provider calls."""

from contextlib import nullcontext

import pytest

from rpb.adapters.llm_provider import HTTPProvider, ProviderFailure
from rpb.modules.account_config.domain.llm_profiles import compile_for_model
from rpb.modules.account_config.domain.parameters import ParameterError


class CapturingProvider(HTTPProvider):
    def __init__(self, response):
        super().__init__()
        self.response = response
        self.sent = None

    def request(self, *args):
        self.sent = args
        with args[-1]():
            return self.response


CASES = [
    (
        "openai_chat",
        "/chat/completions",
        {"choices": [{"message": {"content": "OK"}}]},
        {"choices": [{}]},
    ),
    (
        "openai_responses",
        "/responses",
        {"status": "completed", "output": [{"type": "message", "content": [{"text": "OK"}]}]},
        {"status": "failed", "output": [{"type": "reasoning"}]},
    ),
    (
        "anthropic_messages",
        "/messages",
        {"content": [{"type": "text", "text": "OK"}]},
        {"content": [{}]},
    ),
    (
        "gemini_content",
        "/models/model-a:generateContent",
        {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]},
        {"candidates": [{"finishReason": "SAFETY"}]},
    ),
]


@pytest.mark.parametrize("protocol,path,good,bad", CASES)
def test_lp07_protocol_request_and_false_success(protocol, path, good, bad):
    config = {
        "protocol": protocol,
        "base_url": "https://example.invalid/v1",
        "api_version": "2023-06-01",
        "parameters": {"temperature": 0, "max_output_tokens": 100},
        "timeout_seconds": 7,
        "model_context_windows": {"model-a": 524288},
    }
    provider = CapturingProvider(good)
    result = provider.execute(config, "test", "model-a", "PRIVATE", nullcontext)
    assert provider.sent[1] == path
    assert provider.sent[-2] == 7
    body = provider.sent[5]
    assert "model_context_windows" not in str(body) and "524288" not in str(body)
    assert "timeout_seconds" not in body and "PRIVATE" not in str(body)
    assert result["test_overrides"] == {} and result["tested_parameters"]
    assert "OK" in str(body) and "project" not in str(body)
    provider.response = bad
    with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
        provider.execute(config, "test", "model-a", "PRIVATE")
    provider.response = {**good, "error": {"message": "PRIVATE"}}
    with pytest.raises(ProviderFailure, match="PROVIDER_RESPONSE_INVALID"):
        provider.execute(config, "test", "model-a", "PRIVATE")


def test_lp08_protocol_conflicts_and_thinking_budget():
    for params in [
        {"max_output_tokens": 100, "custom_params": {"max_completion_tokens": 100}},
        {"custom_params": {"max_tokens": 100, "max_completion_tokens": 100}},
    ]:
        with pytest.raises(ParameterError):
            compile_for_model("openai_chat", "model", params)
    with pytest.raises(ParameterError):
        compile_for_model("openai_responses", "model", {"stop": ["end"]})
    params = {
        "max_output_tokens": 2048,
        "custom_params": {"thinking": {"type": "enabled", "budget_tokens": 1024}},
    }
    assert (
        compile_for_model("anthropic_messages", "model", params)["thinking"]["budget_tokens"]
        == 1024
    )
    for wrong in [
        dict(params, max_output_tokens=1024),
        dict(params, temperature=0),
        {"custom_params": {"thinking": {"type": "enabled"}}},
    ]:
        with pytest.raises(ParameterError):
            compile_for_model("anthropic_messages", "model", wrong)
    assert compile_for_model(
        "gemini_content",
        "model",
        {"custom_params": {"thinkingConfig": {"includeThoughts": False, "thinkingBudget": 0}}},
    ) == {"generationConfig": {"thinkingConfig": {"includeThoughts": False, "thinkingBudget": 0}}}


def test_lp09_anthropic_default_test_override_is_explicit():
    provider = CapturingProvider({"content": [{"type": "text", "text": "OK"}]})
    result = provider.execute(
        {
            "protocol": "anthropic_messages",
            "base_url": "https://example.invalid",
            "api_version": "2023-06-01",
            "parameters": {},
            "timeout_seconds": 30,
        },
        "test",
        "model",
        "PRIVATE",
    )
    assert result["test_overrides"] == {"max_tokens": 32}
    assert result["tested_parameters"] == {}
    assert provider.sent[5]["max_tokens"] == 32


def test_lp10_known_model_and_api_version_capability_key():
    from rpb.modules.account_config.domain.llm_profiles import capabilities

    assert compile_for_model("openai_chat", "o3", {"max_output_tokens": 100}) == {
        "max_completion_tokens": 100
    }
    with pytest.raises(ParameterError):
        compile_for_model("openai_chat", "o3", {"temperature": 0})
    assert capabilities("openai_chat", "o3").known
    assert not capabilities("openai_chat", "o3", "unregistered-version").known
    assert not capabilities("openai_chat", "custom-new-model").known
