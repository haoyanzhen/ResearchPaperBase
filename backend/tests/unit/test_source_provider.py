"""SP: fixed queries, scoped authentication, genuine protocol response evidence."""

from contextlib import nullcontext

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.source_provider import SourceProvider
from rpb.modules.account_config.domain.sources import SourceError, validate_source


@pytest.mark.parametrize(
    "provider,response",
    [
        (
            "arxiv",
            b'<feed xmlns="http://www.w3.org/2005/Atom"><totalResults xmlns="http://a9.com/-/spec/opensearch/1.1/">0</totalResults></feed>',
        ),
        ("openalex", {"meta": {"count": 0}, "results": []}),
        ("semantic_scholar", {"total": 0, "data": []}),
        ("ads", {"response": {"numFound": 0, "docs": []}}),
    ],
)
def test_sp01_protocol_evidence_and_fixed_nonbusiness_query(provider, response, monkeypatch):
    adapter = SourceProvider()
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr(adapter, "request", request)
    config = {"provider": provider, "base_url": "https://api.invalid", "access_mode": "api_key"}
    assert adapter.execute(config, "test", None, "secret", nullcontext) == {}
    args, kwargs = calls[0]
    assert "electron" in args[1] and args[2] == "secret" and args[6] == 30
    assert kwargs["response_format"] == ("xml" if provider == "arxiv" else "json")
    config["access_mode"] = "anonymous"
    adapter.execute(config, "test", None, "private", nullcontext)
    assert calls[1][0][2] == ""


@pytest.mark.parametrize(
    "provider,response",
    [
        ("arxiv", b"<html>ok</html>"),
        ("arxiv", b'<!DOCTYPE x [<!ENTITY test "bad">]><feed/>'),
        ("openalex", {"results": []}),
        ("openalex", {"meta": {"count": True}, "results": []}),
        ("semantic_scholar", {"total": 0}),
        ("ads", {"response": {"numFound": -1, "docs": []}}),
        ("ads", {"error": "secret", "response": {"numFound": 0, "docs": []}}),
    ],
)
def test_sp02_html_and_false_success_rejected(provider, response, monkeypatch):
    adapter = SourceProvider()
    monkeypatch.setattr(adapter, "request", lambda *a, **k: response)
    with pytest.raises(ProviderFailure) as e:
        adapter.execute(
            {"provider": provider, "base_url": "https://api.invalid", "access_mode": "anonymous"},
            "test",
            None,
            "",
            nullcontext,
        )
    assert e.value.code == "PROVIDER_RESPONSE_INVALID" and "secret" not in str(e.value)


def test_sp03_missing_key_prevents_network(monkeypatch):
    adapter = SourceProvider()
    monkeypatch.setattr(adapter, "request", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(ProviderFailure):
        adapter.execute(
            {"provider": "ads", "base_url": "https://api.invalid", "access_mode": "api_key"},
            "test",
            None,
            "",
            nullcontext,
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"provider": "public_file"},
        {"access_mode": "api_key"},
        {"file_url": "https://x.invalid/file.pdf"},
        {"base_url": "https://secret@x.invalid"},
        {"base_url": "https://x.invalid/#fragment"},
        {"rate_limit_per_minute": False},
        {"enabled": 0},
    ],
)
def test_sp04_input_rejection_and_no_mutation(patch):
    data = {
        "name": "test",
        "provider": "arxiv",
        "base_url": "https://x.invalid/api",
        "access_mode": "anonymous",
        **patch,
    }
    before = dict(data)
    with pytest.raises(SourceError):
        validate_source(data)
    assert data == before


@pytest.mark.parametrize("error", [{}, "", None, False])
def test_sp05_error_field_never_proves_success(error, monkeypatch):
    adapter = SourceProvider()
    monkeypatch.setattr(
        adapter,
        "request",
        lambda *a, **k: {"error": error, "response": {"numFound": 0, "docs": []}},
    )
    with pytest.raises(ProviderFailure):
        adapter.execute(
            {"provider": "ads", "base_url": "https://api.invalid", "access_mode": "api_key"},
            "test",
            None,
            "KEY",
        )


@pytest.mark.parametrize(
    "code,category",
    [
        ("CONFIG_SECRET_UNAVAILABLE", "configuration"),
        ("CONFIG_CONNECTION_FAILED", "configuration"),
        ("LOCK_CONTENT_BUSY", "lock_conflict"),
    ],
)
def test_sp06_shared_llm_task_error_categories(code, category):
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator

    from rpb.adapters.llm import public_error

    error = public_error(code)
    assert error["category"] == category
    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/p0.openapi.json").read_text()
    )
    Draft202012Validator(
        {"$ref": "#/components/schemas/TaskError", "components": spec["components"]}
    ).validate(error)
