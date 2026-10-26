import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi import FastAPI
from test_startup import test_probes_and_no_business_routes as assert_probe_contract

from rpb.api.health import live, ready

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "delivery", ROOT / "scripts/verify_skeleton_delivery.py"
)
assert spec and spec.loader
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def test_live_201_mutation_fails_application_contract(monkeypatch):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_api_route("/health/live", live, status_code=201)
    app.add_api_route("/health/ready", ready)
    monkeypatch.setattr("test_startup.create_app", lambda: app)
    with pytest.raises(AssertionError):
        assert_probe_contract(monkeypatch)


@pytest.mark.parametrize("status", [200, 201])
def test_wheel_network_probe_requires_exact_200(status):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"status": "alive"}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/health/live"
            if status == 200:
                assert delivery.probe_live(url) == 200
            else:
                with pytest.raises(AssertionError, match="Expected live HTTP 200, got 201"):
                    delivery.probe_live(url)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()
