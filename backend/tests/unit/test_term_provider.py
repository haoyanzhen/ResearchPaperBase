"""Explicit protocol output parsing; malformed/credential-bearing results fail closed."""

import json
from contextlib import contextmanager

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.search_term_worker import TermProvider


class Transport:
    def __init__(self, response):
        self.response = response
        self.request_body = None

    def request(self, base, path, secret, protocol, version, body, timeout, authorize):
        with authorize():
            self.request_body = body
        return self.response


@contextmanager
def authorized():
    yield


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
def test_term_provider_protocol_output(protocol):
    text = json.dumps(
        [
            {
                "query": "A AND B",
                "keywords": ["A"],
                "synonyms": ["a"],
                "exclusions": ["B"],
                "rationale": "r",
                "coverage": "c",
            }
        ]
    )
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
    result = TermProvider(transport).generate(
        config,
        "model",
        "secret",
        {"topic": {"name": "topic"}, "additional_requirements": "explicit"},
        authorized,
    )
    assert result[0]["query"] == "A AND B"
    assert "explicit" in json.dumps(transport.request_body)
    assert "secret" not in json.dumps(transport.request_body)


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        "[]",
        '[{"query":"secret"}]',
        '[{"query":"q","source_policy":{"mode":"all_resolvable"}}]',
        "[1]",
    ],
)
def test_term_provider_invalid_output_never_becomes_candidate(output):
    transport = Transport({"choices": [{"message": {"content": output}}]})
    config = {
        "base_url": "https://example.invalid",
        "protocol": "openai_chat",
        "api_version": None,
        "timeout_seconds": 10,
        "parameters": {"custom_params": {}},
    }
    with pytest.raises(ProviderFailure):
        TermProvider(transport).generate(
            config, "model", "secret", {"topic": {}, "additional_requirements": ""}, authorized
        )
