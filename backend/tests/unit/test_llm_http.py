"""Explicit loopback-only HTTP target exercises wire behavior without paid services."""

import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from rpb.adapters.llm_provider import HTTPProvider, ProviderFailure


@pytest.fixture
def local_provider():
    records = []
    state = {"status": 200, "value": {"choices": [{"message": {"content": "OK"}}]}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            records.append(
                (
                    self.path,
                    dict(self.headers),
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if state.get("slow"):
                try:
                    for part in json.dumps(state["value"]).encode():
                        self.wfile.write(bytes([part]))
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    pass
            else:
                self.wfile.write(json.dumps(state["value"]).encode())

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


def test_ln01_explicit_internal_target_wire_and_no_redirect(local_provider):
    port, records, state = local_provider
    config = {
        "base_url": f"http://127.0.0.1:{port}/v1",
        "protocol": "openai_chat",
        "api_version": "",
        "parameters": {"temperature": 0},
        "timeout_seconds": 2,
    }
    with pytest.raises(ProviderFailure):
        HTTPProvider().execute(config, "test", "model", "PRIVATE")
    assert records == []
    provider = HTTPProvider(frozenset({("127.0.0.1", port)}))
    provider.execute(config, "test", "model", "PRIVATE")
    path, headers, body = records[0]
    assert path == "/v1/chat/completions" and headers["Authorization"] == "Bearer PRIVATE"
    assert body == {
        "temperature": 0,
        "model": "model",
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "stream": False,
    }
    for status, code in [
        (302, "CONFIG_CONNECTION_FAILED"),
        (401, "CONFIG_SECRET_UNAVAILABLE"),
        (429, "PROVIDER_RATE_LIMITED"),
        (404, "CONFIG_CONNECTION_FAILED"),
        (500, "CONFIG_CONNECTION_FAILED"),
    ]:
        state["status"] = status
        with pytest.raises(ProviderFailure, match=code):
            provider.execute(config, "test", "model", "PRIVATE")
    assert len(records) == 6


def test_ln02_mixed_dns_answers_refuse_before_connect(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    connected = []
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: connected.append(args))
    with pytest.raises(ProviderFailure):
        HTTPProvider().request(
            "https://example.invalid", "/models", "PRIVATE", "openai_chat", "", None, 2
        )
    assert not connected


def test_ln03_slow_response_obeys_total_deadline(local_provider):
    port, _, state = local_provider
    state["slow"] = True
    started = time.monotonic()
    with pytest.raises(ProviderFailure, match="PROVIDER_TIMEOUT"):
        HTTPProvider(frozenset({("127.0.0.1", port)})).request(
            f"http://127.0.0.1:{port}", "/test", "PRIVATE", "openai_chat", "", {}, 1
        )
    assert time.monotonic() - started < 2.5


def test_ln04_dns_wait_is_bounded_and_no_late_send(monkeypatch):
    from threading import Event

    from rpb.adapters.llm_provider import resolve_addresses

    entered, release, done = Event(), Event(), Event()

    def slow(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(3)
            return []
        finally:
            done.set()

    monkeypatch.setattr(socket, "getaddrinfo", slow)
    try:
        with pytest.raises(ProviderFailure, match="PROVIDER_TIMEOUT"):
            resolve_addresses("example.invalid", 443, time.monotonic() + 0.05)
        assert entered.is_set()
    finally:
        release.set()
        assert done.wait(3)


def test_ln05_connection_prepared_before_authorization(local_provider):
    import http.client
    from contextlib import contextmanager
    from unittest.mock import patch

    port, records, _ = local_provider
    connected = []
    original = http.client.HTTPConnection.connect

    def connect(conn):
        original(conn)
        connected.append(True)

    @contextmanager
    def revoked():
        assert connected == [True]
        raise ProviderFailure("PERMISSION_RESOURCE_UNAVAILABLE")
        yield

    with (
        patch.object(http.client.HTTPConnection, "connect", connect),
        pytest.raises(ProviderFailure, match="PERMISSION_RESOURCE_UNAVAILABLE"),
    ):
        HTTPProvider(frozenset({("127.0.0.1", port)})).request(
            f"http://127.0.0.1:{port}", "/test", "PRIVATE", "openai_chat", "", {}, 2, revoked
        )
    assert not records


def test_ln06_tls_handshake_receives_remaining_deadline(monkeypatch):
    from threading import Event

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    release = Event()

    def server():
        sock, _ = listener.accept()
        try:
            release.wait(3)
        finally:
            sock.close()

    thread = Thread(target=server, daemon=True)
    thread.start()
    original = socket.create_connection

    def slow_connect(*args, **kwargs):
        time.sleep(0.6)
        return original(*args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", slow_connect)
    started = time.monotonic()
    try:
        with pytest.raises(ProviderFailure, match="PROVIDER_TIMEOUT"):
            HTTPProvider(frozenset({("127.0.0.1", port)})).request(
                f"https://127.0.0.1:{port}", "/test", "PRIVATE", "openai_chat", "", {}, 1
            )
        assert time.monotonic() - started < 1.5
    finally:
        release.set()
        listener.close()
        thread.join(4)
