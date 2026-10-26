"""Real demo process owns its worker and persists encrypted queued jobs; no external calls."""

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from test_account_auth import csrf, login, register
from test_llm_configuration import create, start
from test_source_configuration import create as create_source
from test_source_configuration import start as start_source


@pytest.mark.parametrize("kind", ["llm", "source"])
def test_ld01_demo_worker_process_consumes_queue_without_provider_network(db, request, kind):
    root = Path(__file__).resolve().parents[3]
    target = Path(request.config.getoption("--storage-target"))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            str(root / "scripts/run_business_demo.py"),
            "--target",
            str(target),
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    origin = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=origin, headers={"Origin": origin}, timeout=2) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = client.get("/api/v1/auth/csrf")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert process.poll() is None and time.monotonic() < deadline
                time.sleep(0.05)
            h = csrf(client)
            h["Origin"] = origin
            assert register(client, h, "demo-user", "demo@example.invalid").status_code == 201
            assert login(client, h, "demo-user").status_code == 200
            h = csrf(client)
            h["Origin"] = origin
            creator, starter = (create, start) if kind == "llm" else (create_source, start_source)
            config = creator(client, h, base_url="http://127.0.0.1:9/v1").json()["data"]
            job = starter(client, h, config).json()["data"]
            deadline = time.monotonic() + 10
            while True:
                view = client.get(job["status_url"]).json()["data"]
                if view["execution_status"] == "failed":
                    break
                assert time.monotonic() < deadline
                time.sleep(0.05)
            assert view["error"]["code"] == "CONFIG_CONNECTION_FAILED"
            assert (target.parent / "llm-demo.key").stat().st_mode & 0o777 == 0o600
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=15)
        assert process.returncode in {0, -15} and "SENSITIVE" not in output
