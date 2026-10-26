import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from process_support import managed_process, wait_for_line
from pydantic import ValidationError

from rpb.bootstrap.api import create_app
from rpb.bootstrap.config import Settings


def clean_env():
    return {key: value for key, value in os.environ.items() if not key.startswith("RPB_")}


def test_config_has_no_storage_or_provider_fallback():
    settings = Settings.load({})
    assert settings.model_dump() == {
        "environment": "development",
        "host": "127.0.0.1",
        "port": 8000,
    }


@pytest.mark.parametrize(
    "values",
    [
        {"RPB_PORT": "0"},
        {"RPB_PORT": "1023"},
        {"RPB_PORT": "65536"},
        {"RPB_PORT": "bad"},
        {"RPB_HOST": "0.0.0.0"},
        {"RPB_ENVIRONMENT": "production"},
        {"RPB_DATABASE_URL": "postgresql://secret@business/db"},
    ],
)
def test_invalid_or_unimplemented_configuration_refused(values):
    with pytest.raises(ValidationError):
        Settings.load(values)


def test_config_valid_boundaries():
    for port in (1024, 65535):
        assert Settings.load({"RPB_PORT": str(port), "RPB_ENVIRONMENT": "test"}).port == port


def test_probes_and_no_business_routes(monkeypatch):
    for key in os.environ:
        if key.startswith("RPB_"):
            monkeypatch.delenv(key)
    with TestClient(create_app()) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "alive"}
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json() == {"status": "not_ready"}
        for path in ("/api/projects", "/docs", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.post("/api/projects", json={"name": "must not exist"}).status_code == 404


@pytest.mark.parametrize("module", ["api", "worker"])
@pytest.mark.parametrize(
    "invalid",
    [
        {"RPB_PORT": "private-marker"},
        {"RPB_ENVIRONMENT": "private-marker"},
        {"RPB_HOST": "private-marker"},
        {"RPB_DATABASE_URL": "postgresql://private-marker/business"},
    ],
)
def test_process_rejects_configuration_without_leaking_values(module, invalid):
    result = subprocess.run(
        [sys.executable, "-m", f"rpb.bootstrap.{module}"],
        env=clean_env() | invalid,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stderr == "Invalid process configuration; startup refused.\n"
    assert "private-marker" not in result.stdout + result.stderr


def test_worker_refuses_task_execution():
    result = subprocess.run(
        [sys.executable, "-m", "rpb.bootstrap.worker"],
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "Task execution unavailable" in result.stderr


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
def test_worker_idle_lifecycle(stop_signal):
    with managed_process(
        [sys.executable, "-m", "rpb.bootstrap.worker", "--idle"], env=clean_env()
    ) as process:
        wait_for_line(process, "task execution disabled; not ready")
        process.send_signal(stop_signal)
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0
        assert "stopped" in output


def test_migration_refuses_even_with_business_configuration():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(root / "alembic.ini"), "upgrade", "head"],
        capture_output=True,
        text=True,
        env=clean_env() | {"DATABASE_URL": "postgresql://private-marker/db"},
        timeout=10,
    )
    assert result.returncode != 0
    assert "Migration execution unavailable" in result.stderr
    assert "private-marker" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "prefix", ["", "import sys; sys.stdout.write('partial'); sys.stdout.flush(); "]
)
def test_worker_missing_startup_signal_times_out_and_is_reaped(prefix):
    import time

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="handshake timed out"):
        with managed_process(
            [sys.executable, "-c", prefix + "import time; time.sleep(30)"]
        ) as process:
            wait_for_line(process, "ready", timeout=0.2)
    assert process.poll() is not None
    assert time.monotonic() - started < 5


def test_worker_exit_before_handshake_is_reaped():
    with pytest.raises(RuntimeError, match="exited before"):
        with managed_process([sys.executable, "-c", "pass"]) as process:
            wait_for_line(process, "ready", timeout=2)
    assert process.poll() is not None


def test_app_factory_rejects_invalid_configuration(monkeypatch):
    monkeypatch.setenv("RPB_PORT", "invalid")
    with pytest.raises(ValidationError):
        create_app()
