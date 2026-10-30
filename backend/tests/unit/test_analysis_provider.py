"""PA01/02: four wire protocols, explicit parameters, incomplete output and injection boundary."""

import copy
import json
from contextlib import contextmanager

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.paper_analysis_provider import AnalysisProvider

VALUE = dict(
    one_sentence_summary="Summary",
    highlights=[],
    relevance_points=["Relevant"],
    methods="Not stated",
    innovations=[],
)


def response(protocol, text):
    if protocol == "openai_chat":
        return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
    if protocol == "openai_responses":
        return {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        }
    if protocol == "anthropic_messages":
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}


class HTTP:
    def __init__(self, value):
        self.value, self.calls = value, []

    def request(self, *args):
        with args[-1]():
            self.calls.append(copy.deepcopy(args[:-1]))
        return self.value


@contextmanager
def permit():
    yield


def config(protocol):
    return dict(
        protocol=protocol,
        parameters={"max_output_tokens": 2048},
        api_version=None,
        base_url="https://example.invalid",
        timeout_seconds=30,
    )


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
def test_pa_provider_complete_and_original_final_text(protocol):
    http = HTTP(response(protocol, json.dumps(VALUE)))
    inputs = {
        "topic": "topic",
        "text": "UNTRUSTED\nfull text",
        "text_source_kind": "abstract_fallback",
    }
    before = copy.deepcopy(inputs)
    assert (
        AnalysisProvider(http).generate(config(protocol), "custom-model", "secret", inputs, permit)
        == VALUE
    )
    assert len(http.calls) == 1 and inputs == before
    body = http.calls[0][5]
    prompt = (
        body["messages"][0]["content"]
        if protocol in {"openai_chat", "anthropic_messages"}
        else body["input"]
        if protocol == "openai_responses"
        else body["contents"][0]["parts"][0]["text"]
    )
    assert json.loads(prompt.split("Input: ", 1)[1]) == inputs
    assert "context_window_tokens" not in body and "abstract_fallback" in json.dumps(body)


@pytest.mark.parametrize(
    "text",
    [
        "{}",
        "[]",
        "null",
        "bad-json",
        json.dumps({**VALUE, "type": "paper"}),
        json.dumps(VALUE)[:-1] + ',"methods":"duplicate"}',
        json.dumps({**VALUE, "methods": "secret"}),
    ],
)
def test_pa_provider_invalid_and_secret_echo_rejected_without_retry(text):
    http = HTTP(response("openai_chat", text))
    with pytest.raises(ProviderFailure):
        AnalysisProvider(http).generate(config("openai_chat"), "custom-model", "secret", {}, permit)
    assert len(http.calls) == 1


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
def test_pa_provider_truncated_even_valid_json_rejected(protocol):
    value = response(protocol, json.dumps(VALUE))
    if protocol == "openai_chat":
        value["choices"][0]["finish_reason"] = "length"
    elif protocol == "openai_responses":
        value["status"] = "incomplete"
    elif protocol == "anthropic_messages":
        value["stop_reason"] = "max_tokens"
    else:
        value["candidates"][0]["finishReason"] = "MAX_TOKENS"
    with pytest.raises(ProviderFailure):
        AnalysisProvider(HTTP(value)).generate(
            config(protocol), "custom-model", "secret", {}, permit
        )


def test_pa_provider_default_not_replaced_by_pdf_cleanup_default():
    cfg = config("openai_chat")
    cfg["parameters"] = {}
    http = HTTP(response("openai_chat", json.dumps(VALUE)))
    AnalysisProvider(http).generate(cfg, "custom-model", "secret", {}, permit)
    assert "max_tokens" not in http.calls[0][5]
    assert "max_completion_tokens" not in http.calls[0][5]
    assert cfg["parameters"] == {}


def test_pa_provider_declared_small_capacity_rejects_before_dispatch_without_truncation():
    cfg = config("openai_chat")
    cfg["model_context_windows"] = {"custom-model": 1024}
    http = HTTP(response("openai_chat", json.dumps(VALUE)))
    inputs = {"text": "long final text" * 500}
    with pytest.raises(ProviderFailure):
        AnalysisProvider(http).generate(cfg, "custom-model", "secret", inputs, permit)
    assert http.calls == [] and inputs["text"] == "long final text" * 500
