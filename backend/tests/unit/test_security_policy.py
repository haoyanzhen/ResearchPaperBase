"""Policy tests derive observable side effects from the safe retry requirement."""

from contextlib import nullcontext

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.security import DEFAULTS, execute_test
from rpb.adapters.security import test_config as bounded_config


class Provider:
    def __init__(self, failures):
        self.failures, self.calls = list(failures), []

    def execute(self, config, operation, model, secret, authorize):
        with authorize():
            self.calls.append(dict(config))
            if self.failures:
                raise self.failures.pop(0)
            return {"ok": True}


def test_security_budget_only_tightens_and_does_not_edit_input():
    config = {"timeout_seconds": 120, "parameters": {"temperature": 0.2}}
    assert bounded_config(config, DEFAULTS)["timeout_seconds"] == 30
    assert bounded_config({"timeout_seconds": 3}, DEFAULTS)["timeout_seconds"] == 3
    assert config["timeout_seconds"] == 120
    assert (
        bounded_config({}, {**DEFAULTS, "connection_timeout_seconds": 60})["timeout_seconds"] == 60
    )


def test_proven_unsubmitted_connection_can_retry_with_total_budget():
    provider = Provider([ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=False)])
    result, attempts = execute_test(
        provider,
        {"timeout_seconds": 10},
        "test",
        "m",
        "secret",
        nullcontext,
        {**DEFAULTS, "connection_retry_count": 2},
    )
    assert result == {"ok": True} and attempts == 2
    assert 0 < provider.calls[1]["timeout_seconds"] <= provider.calls[0]["timeout_seconds"] <= 10


@pytest.mark.parametrize(
    "failure",
    [
        ProviderFailure("CONFIG_CONNECTION_FAILED"),
        ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=True),
        ProviderFailure("PROVIDER_TIMEOUT", submitted=True),
        ProviderFailure("CONFIG_SECRET_UNAVAILABLE", submitted=False),
        ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE", submitted=False),
        ProviderFailure("PROVIDER_RESULT_UNKNOWN", submitted=False),
        ProviderFailure("PROVIDER_RATE_LIMITED", submitted=False),
    ],
)
def test_uncertain_paid_or_rejected_request_never_replayed(failure):
    provider = Provider([failure])
    with pytest.raises(ProviderFailure) as error:
        execute_test(
            provider,
            {},
            "test",
            "m",
            "secret",
            nullcontext,
            {**DEFAULTS, "connection_retry_count": 5},
        )
    assert error.value is failure and len(provider.calls) == 1


def test_zero_retries_does_not_repeat_even_proven_unsubmitted_request():
    provider = Provider([ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=False)])
    with pytest.raises(ProviderFailure):
        execute_test(provider, {}, "test", "m", "secret", nullcontext, DEFAULTS)
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "phase,expected_connects,expected_requests",
    [
        ("connect", 2, 1),
        ("response", 1, 1),
        ("write", 1, 1),
    ],
)
def test_real_http_adapter_marks_only_pre_request_connection_failures_retryable(
    monkeypatch,
    phase,
    expected_connects,
    expected_requests,
):
    import io

    import rpb.adapters.llm_provider as network

    seen = {"connect": 0, "request": 0}

    class Response(io.BytesIO):
        status = 200

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            seen["connect"] += 1
            if phase == "connect" and seen["connect"] == 1:
                raise ConnectionRefusedError()

        def request(self, *args, **kwargs):
            seen["request"] += 1
            if phase == "write":
                raise BrokenPipeError()

        def getresponse(self):
            if phase == "response":
                raise ConnectionResetError()
            return Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        def close(self):
            pass

    monkeypatch.setattr(
        network, "resolve_addresses", lambda *args: [(2, 1, 6, "", ("127.0.0.1", 1234))]
    )
    monkeypatch.setattr(network.http.client, "HTTPConnection", Connection)
    config = {
        "base_url": "http://127.0.0.1:1234",
        "protocol": "openai_chat",
        "api_version": "",
        "parameters": {},
        "timeout_seconds": 10,
    }
    provider = network.HTTPProvider(frozenset({("127.0.0.1", 1234)}))
    if phase == "connect":
        _, attempts = execute_test(
            provider,
            config,
            "test",
            "m",
            "secret",
            nullcontext,
            {**DEFAULTS, "connection_retry_count": 5},
        )
        assert attempts == 2
    else:
        with pytest.raises(ProviderFailure) as error:
            execute_test(
                provider,
                config,
                "test",
                "m",
                "secret",
                nullcontext,
                {**DEFAULTS, "connection_retry_count": 5},
            )
        assert error.value.submitted is True
    assert seen == {"connect": expected_connects, "request": expected_requests}


def test_retry_count_is_additional_attempts_and_budget_never_restarts(monkeypatch):
    import rpb.adapters.security as security

    provider = Provider([ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=False)] * 7)
    with pytest.raises(ProviderFailure) as error:
        execute_test(
            provider,
            {"timeout_seconds": 10},
            "test",
            "m",
            "secret",
            nullcontext,
            {**DEFAULTS, "connection_retry_count": 5},
        )
    assert len(provider.calls) == 6 and error.value.attempts == 6
    provider = Provider([ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=False)])
    ticks = iter([0, 0, 11])
    monkeypatch.setattr(security, "monotonic", lambda: next(ticks))
    with pytest.raises(ProviderFailure) as error:
        execute_test(
            provider,
            {"timeout_seconds": 10},
            "test",
            "m",
            "secret",
            nullcontext,
            {**DEFAULTS, "connection_retry_count": 5},
        )
    assert error.value.code == "PROVIDER_TIMEOUT" and len(provider.calls) == 1


def test_very_large_positive_timeout_has_a_representable_runtime_budget():
    from datetime import UTC, datetime, timedelta
    from threading import TIMEOUT_MAX

    bounded = bounded_config({}, {**DEFAULTS, "connection_timeout_seconds": 10**100})
    assert 0 < bounded["timeout_seconds"] < TIMEOUT_MAX
    assert datetime.now(UTC) + timedelta(seconds=bounded["timeout_seconds"] + 30)


@pytest.mark.parametrize("ticks,expected", [([0, 11], 0), ([0, 0, 11], 1), ([0, 0, 1, 11], 2)])
def test_expired_total_budget_reports_actual_completed_attempts(monkeypatch, ticks, expected):
    import rpb.adapters.security as security

    clock = iter(ticks)
    monkeypatch.setattr(security, "monotonic", lambda: next(clock))
    provider = Provider(
        [ProviderFailure("CONFIG_CONNECTION_FAILED", submitted=False) for _ in range(expected)]
    )
    with pytest.raises(ProviderFailure) as error:
        execute_test(
            provider,
            {"timeout_seconds": 10},
            "test",
            "m",
            "secret",
            nullcontext,
            {**DEFAULTS, "connection_retry_count": 5},
        )
    assert error.value.code == "PROVIDER_TIMEOUT"
    assert len(provider.calls) == expected
    assert error.value.attempts == expected
