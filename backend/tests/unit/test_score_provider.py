"""Model protocol parsing cannot promote malformed or credential-bearing scores."""

import json

import pytest
from test_term_provider import Transport, authorized

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.paper_scoring_worker import ScoreProvider


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
@pytest.mark.parametrize("score", [0, 7, 10])
def test_scoring_protocol_and_boundaries(protocol, score):
    value = {"score": score, "theoretical": "theory", "technical": "tech", "relevance": "topic"}
    text = json.dumps(value)
    responses = {
        "openai_chat": {"choices": [{"message": {"content": text}}]},
        "openai_responses": {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
        },
        "anthropic_messages": {"content": [{"type": "text", "text": text}]},
        "gemini_content": {"candidates": [{"content": {"parts": [{"text": text}]}}]},
    }
    transport = Transport(responses[protocol])
    config = {
        "base_url": "https://example.invalid",
        "protocol": protocol,
        "api_version": "2023-06-01" if protocol == "anthropic_messages" else None,
        "timeout_seconds": 10,
        "parameters": {"max_output_tokens": 1024, "custom_params": {}},
    }
    inputs = {
        "topic": {"name": "topic"},
        "sources": [{"metadata": {"title": "title", "abstract": None}}],
    }
    assert (
        ScoreProvider(transport).score(config, "model", "PRIVATE-KEY", inputs, authorized) == value
    )
    assert "PRIVATE-KEY" not in json.dumps(transport.request_body)
    assert "null" in json.dumps(transport.request_body)


@pytest.mark.parametrize(
    "output",
    [
        "null",
        "{}",
        "[]",
        "not-json",
        '{"score":7,"theoretical":"PRIVATE-KEY","technical":"x","relevance":"x"}',
        '{"score":7,"theoretical":" ","technical":"x","relevance":"x"}',
    ],
)
def test_scoring_invalid_output_has_no_fake_score(output):
    config = {
        "base_url": "https://example.invalid",
        "protocol": "openai_chat",
        "api_version": None,
        "timeout_seconds": 10,
        "parameters": {"custom_params": {}},
    }
    with pytest.raises(ProviderFailure):
        ScoreProvider(Transport({"choices": [{"message": {"content": output}}]})).score(
            config, "model", "PRIVATE-KEY", {}, authorized
        )
