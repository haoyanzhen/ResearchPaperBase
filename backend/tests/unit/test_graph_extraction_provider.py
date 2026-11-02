"""Single-slice extraction rejects fabricated evidence and provider failures."""

import json

import pytest
from test_analysis_provider import HTTP, config, permit, response

from rpb.adapters.graph_extraction_provider import GraphExtractionProvider
from rpb.adapters.llm_provider import ProviderFailure


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
def test_one_slice_and_valid_empty_extraction(protocol):
    http = HTTP(response(protocol, json.dumps({"entities": [], "claims": []})))
    result = GraphExtractionProvider(http).extract(
        config(protocol), "custom-model", "secret", "input text", {"title": "paper"}, permit
    )
    assert result == ([], []) and len(http.calls) == 1
    body = http.calls[0][5]
    prompt = (
        body["messages"][0]["content"]
        if protocol in {"openai_chat", "anthropic_messages"}
        else body["input"]
        if protocol == "openai_responses"
        else body["contents"][0]["parts"][0]["text"]
    )
    assert json.loads(prompt.split("Input: ", 1)[1]) == {
        "text": "input text",
        "metadata": {"title": "paper"},
    }


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        '{"entities":[],"claims":[],"claims":[]}',
        '{"entities":[{"kind":"method","label":"fake","start":0,"end":4}],"claims":[]}',
        '{"entities":[],"claims":[],"instruction":"publish"}',
        "secret",
    ],
)
def test_malformed_or_unsupported_proposal_never_becomes_empty_success(output):
    http = HTTP(response("openai_chat", output))
    with pytest.raises(ProviderFailure) as error:
        GraphExtractionProvider(http).extract(
            config("openai_chat"), "custom-model", "secret", "real", {}, permit
        )
    assert error.value.code == "PROVIDER_RESPONSE_INVALID" and len(http.calls) == 1


@pytest.mark.parametrize(
    "protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_content"]
)
@pytest.mark.parametrize("state", ["missing", None, "truncated"])
def test_empty_extraction_requires_explicit_successful_completion(protocol, state):
    payload = response(protocol, '{"entities":[],"claims":[]}')
    owner, key = {
        "openai_chat": (payload.get("choices", [{}])[0], "finish_reason"),
        "openai_responses": (payload, "status"),
        "anthropic_messages": (payload, "stop_reason"),
        "gemini_content": (payload.get("candidates", [{}])[0], "finishReason"),
    }[protocol]
    if state == "missing":
        owner.pop(key)
    else:
        owner[key] = state
    with pytest.raises(ProviderFailure) as error:
        GraphExtractionProvider(HTTP(payload)).extract(
            config(protocol), "custom-model", "secret", "input text", {}, permit
        )
    assert error.value.code == "PROVIDER_RESPONSE_INVALID"
