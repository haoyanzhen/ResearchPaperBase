"""Run from any directory. External services and business environments are never inferred."""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], cwd: Path = ROOT) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def backend(*args: str) -> None:
    run(["uv", "run", "--locked", *args], ROOT / "backend")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "install",
            "check",
            "build",
            "api",
            "worker",
            "ui",
            "e2e",
            "integration",
            "migration-history",
        ],
    )
    action = parser.parse_args().action
    if action == "install":
        if (
            not (ROOT / "backend/uv.lock").is_file()
            or not (ROOT / "frontend/package-lock.json").is_file()
        ):
            raise SystemExit("Dependency lock missing; installation refused.")
        run(["uv", "sync", "--locked"], ROOT / "backend")
        run(["npm", "ci", "--no-audit", "--no-fund"], ROOT / "frontend")
        run(
            [
                "uv",
                "venv",
                "--python",
                "3.14",
                "--allow-existing",
                str(ROOT / "contracts/.venv"),
            ]
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(ROOT / "contracts/.venv/bin/python"),
                "-r",
                "contracts/requirements.txt",
            ]
        )
    elif action == "check":
        backend(
            "ruff",
            "check",
            "src",
            "tests",
            "../scripts/check_architecture.py",
            "../scripts/engineering.py",
            "../scripts/verify_skeleton_delivery.py",
        )
        backend(
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "../scripts/check_architecture.py",
            "../scripts/engineering.py",
            "../scripts/verify_skeleton_delivery.py",
        )
        backend("mypy", "src")
        backend("pytest", "-q")
        run([str(ROOT / "contracts/.venv/bin/python"), "scripts/check_api_contracts.py"])
        run(
            [
                str(ROOT / "contracts/.venv/bin/python"),
                "-m",
                "unittest",
                "discover",
                "-s",
                "scripts/tests",
                "-v",
            ]
        )
        run(["npm", "run", "check"], ROOT / "frontend")
        run(["npm", "test"], ROOT / "frontend")
    elif action == "build":
        run(["uv", "build", "--no-sources"], ROOT / "backend")
        run(["npm", "run", "build"], ROOT / "frontend")
    elif action == "api":
        backend("rpb-api")
    elif action == "worker":
        backend("rpb-worker", "--idle")
    elif action == "ui":
        run(["npm", "run", "dev"], ROOT / "frontend")
    elif action == "e2e":
        run(["npm", "run", "test:e2e"], ROOT / "frontend")
    elif action == "integration":
        raise SystemExit(
            "Database integration unavailable: isolated fixture and business schema "
            "not implemented. No connection attempted."
        )
    elif action == "migration-history":
        backend("alembic", "history")


if __name__ == "__main__":
    main()
