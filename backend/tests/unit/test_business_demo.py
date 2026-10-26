"""UI06: explicit demo scope rejects invalid targets before any connection."""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("case", ["missing", "wrong_identity", "permissions", "port"])
def test_demo_invalid_descriptor_never_connects(tmp_path, monkeypatch, case):
    spec = importlib.util.spec_from_file_location(
        "business_demo", ROOT / "scripts/run_business_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def refuse(*args, **kwargs):
        calls.append(True)
        raise AssertionError("No connection permitted")

    monkeypatch.setattr(sa, "create_engine", refuse)
    root = tmp_path / "rpb-db-example"
    root.mkdir(mode=0o700)
    target = root / "target.json"
    run_id = "rpb_test_" + "a" * 32
    target.write_text(
        json.dumps(
            dict(
                run_id=run_id,
                username=run_id if case != "wrong_identity" else "business",
                database=run_id,
                password="synthetic",
                host=str(root),
            )
        )
    )
    target.chmod(0o644 if case == "permissions" else 0o600)
    if case == "missing":
        target.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        module.create_demo(target, 80 if case == "port" else 8765)
    assert calls == []


def test_demo_without_explicit_postgres_refuses(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://do-not-use/business")
    monkeypatch.setattr(sys, "argv", ["engineering.py", "demo"])
    with pytest.raises(SystemExit, match="explicit --postgres-bin"):
        runpy.run_path(str(ROOT / "scripts/engineering.py"), run_name="__main__")
