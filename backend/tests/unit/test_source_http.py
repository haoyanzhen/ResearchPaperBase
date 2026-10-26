"""Actual loopback transport: auth headers, bounded XML/JSON and redirect refusal."""

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.source_provider import SourceProvider


@pytest.fixture
def source_http():
    records = []
    state = {"status": 200, "body": b"{}"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            records.append((self.path, dict(self.headers)))
            self.send_response(state["status"])
            self.end_headers()
            self.wfile.write(state["body"])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, records, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize(
    "provider,mode,body,auth",
    [
        (
            "arxiv",
            "anonymous",
            b'<feed xmlns="http://www.w3.org/2005/Atom"><totalResults xmlns="http://a9.com/-/spec/opensearch/1.1/">0</totalResults></feed>',
            None,
        ),
        ("openalex", "anonymous", {"meta": {"count": 0}, "results": []}, None),
        ("openalex", "api_key", {"meta": {"count": 0}, "results": []}, "Authorization"),
        ("semantic_scholar", "api_key", {"total": 0, "data": []}, "x-api-key"),
        ("ads", "api_key", {"response": {"numFound": 0, "docs": []}}, "Authorization"),
    ],
)
def test_sh01_real_headers_paths_and_explicit_network_target(
    source_http, provider, mode, body, auth
):
    port, records, state = source_http
    state["body"] = body if isinstance(body, bytes) else json.dumps(body).encode()
    cfg = {"provider": provider, "access_mode": mode, "base_url": f"http://127.0.0.1:{port}/v1"}
    with pytest.raises(ProviderFailure):
        SourceProvider().execute(cfg, "test", None, "PRIVATE")
    assert not records
    adapter = SourceProvider(frozenset({("127.0.0.1", port)}))
    adapter.execute(cfg, "test", None, "PRIVATE")
    path, headers = records[0]
    assert path.startswith("/v1/") and "electron" in path and "PRIVATE" not in path
    if auth:
        assert headers[auth] == ("PRIVATE" if auth == "x-api-key" else "Bearer PRIVATE")
    else:
        assert (
            "PRIVATE" not in str(headers)
            and "Authorization" not in headers
            and "x-api-key" not in headers
        )
    for status, code in [
        (302, "CONFIG_CONNECTION_FAILED"),
        (401, "CONFIG_SECRET_UNAVAILABLE"),
        (429, "PROVIDER_RATE_LIMITED"),
    ]:
        state["status"] = status
        with pytest.raises(ProviderFailure) as e:
            adapter.execute(cfg, "test", None, "PRIVATE")
        assert e.value.code == code


def test_sh02_revoked_dispatch_never_sends(source_http):
    port, records, state = source_http

    @contextmanager
    def revoked():
        raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
        yield

    with pytest.raises(ProviderFailure):
        SourceProvider(frozenset({("127.0.0.1", port)})).execute(
            {
                "provider": "arxiv",
                "access_mode": "anonymous",
                "base_url": f"http://127.0.0.1:{port}",
            },
            "test",
            None,
            "",
            revoked,
        )
    assert records == []
