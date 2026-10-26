"""Actual cluster cleanup after failed or timed-out child tests, including internal commits."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_ac10_child_failure_cleans_real_cluster(request, monkeypatch, capsys, failure):
    target = json.loads(Path(request.config.getoption("--storage-target")).read_text())
    spec = importlib.util.spec_from_file_location(
        "storage_runner", ROOT / "scripts/run_storage_tests.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    original = subprocess.run

    def fail_child(args, **kwargs):
        if "pytest" in args:
            # Runner has already committed CREATE ROLE/CREATE DATABASE in real PG.
            if failure == "timeout":
                raise subprocess.TimeoutExpired("synthetic test child", 180)
            return subprocess.CompletedProcess(args, 9)
        return original(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_child)
    if failure == "timeout":
        with pytest.raises(subprocess.TimeoutExpired):
            runner.run_tests(Path(target["binary_dir"]))
    else:
        assert runner.run_tests(Path(target["binary_dir"])) == 9
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records[-1]["run_id"] == records[0]["run_id"]
    assert records[-1]["server_stopped"] and records[-1]["root_removed"]
    assert not Path(records[0]["root"]).exists()


def test_ac11_child_has_only_test_role_credentials(request):
    import psycopg

    path = Path(request.config.getoption("--storage-target"))
    target = json.loads(path.read_text())
    assert not (path.parent / "admin-password").exists()
    assert set(target) == {"host", "database", "username", "password", "run_id", "binary_dir"}
    with pytest.raises(psycopg.OperationalError, match="password authentication failed"):
        psycopg.connect(
            host=target["host"],
            dbname=target["database"],
            user="fixture_admin",
            password=target["password"],
            connect_timeout=5,
        )
