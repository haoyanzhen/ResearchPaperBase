"""Observable skeleton rejection and no-storage contracts; no business database is used."""

import importlib.util
import os
import runpy
import socket
import sys
from pathlib import Path

import psycopg
import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from rpb.bootstrap.api import create_app

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def forbidden_io(monkeypatch):
    attempts = []

    def refuse(*args, **kwargs):
        attempts.append("connection attempted")
        raise AssertionError("Skeleton must not open storage/provider connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(psycopg, "connect", refuse)
    monkeypatch.setattr(sqlalchemy, "create_engine", refuse)
    return attempts


@pytest.mark.parametrize("entry", ["migration", "integration"])
@pytest.mark.parametrize("configured", [False, True])
def test_unavailable_storage_refuses_without_connection(
    entry, configured, monkeypatch, forbidden_io
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if configured:
        monkeypatch.setenv("DATABASE_URL", "postgresql://private-marker@invalid/business")
    if entry == "migration":
        with pytest.raises(RuntimeError, match="Migration execution unavailable") as error:
            runpy.run_path(str(ROOT / "backend/migrations/env.py"))
    else:
        monkeypatch.setattr(sys, "argv", ["engineering.py", "integration"])
        with pytest.raises(SystemExit, match="integration unavailable") as error:
            runpy.run_path(str(ROOT / "scripts/engineering.py"), run_name="__main__")
    assert "private-marker" not in str(error.value)
    assert forbidden_io == []


def test_api_probes_do_not_connect_with_ambient_business_configuration(monkeypatch, forbidden_io):
    for key in tuple(os.environ):
        if key.startswith("RPB_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("DATABASE_URL", "postgresql://private-marker@invalid/business")
    with TestClient(create_app()) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.post("/api/projects", json={"name": "forbidden"}).status_code == 404
    assert forbidden_io == []


@pytest.mark.parametrize("missing", ["backend/uv.lock", "frontend/package-lock.json"])
def test_missing_lock_refuses_before_install_and_preserves_files(tmp_path, monkeypatch, missing):
    spec = importlib.util.spec_from_file_location("engineering", ROOT / "scripts/engineering.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("backend/uv.lock", "frontend/package-lock.json"):
        p = tmp_path / name
        p.parent.mkdir(exist_ok=True)
        if name != missing:
            p.write_bytes(b"preserve exact lock bytes")
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    called = []
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: called.append(args))
    monkeypatch.setattr(sys, "argv", ["engineering.py", "install"])
    with pytest.raises(SystemExit, match="lock missing"):
        module.main()
    assert called == []
    assert before == {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }


def test_idle_worker_has_no_storage_activity(monkeypatch, forbidden_io, capsys):
    from threading import Event

    from rpb.bootstrap import worker

    for key in tuple(os.environ):
        if key.startswith("RPB_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("DATABASE_URL", "postgresql://private-marker@invalid/business")
    stop = Event()
    stop.set()
    monkeypatch.setattr(worker, "Event", lambda: stop)
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)
    monkeypatch.setattr(sys, "argv", ["worker", "--idle"])
    worker.main()
    output = capsys.readouterr()
    assert "task execution disabled; not ready" in output.out
    assert "stopped" in output.out
    assert "private-marker" not in output.out + output.err
    assert forbidden_io == []
