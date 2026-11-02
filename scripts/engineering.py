"""Run from any directory. External services and business environments are never inferred."""

import argparse
import os
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
            "demo",
            "migration-history",
        ],
    )
    parser.add_argument("--postgres-bin", type=Path)
    parser.add_argument("--pgvector", action="store_true")
    args = parser.parse_args()
    action = args.action
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
        check_paths = (
            "src",
            "tests",
            "migrations",
            "../scripts/run_storage_tests.py",
            "../scripts/run_business_demo.py",
            "../scripts/check_architecture.py",
            "../scripts/engineering.py",
            "../scripts/verify_skeleton_delivery.py",
            "../scripts/delivery_snapshot.py",
        )
        backend("ruff", "check", *check_paths)
        backend("ruff", "format", "--check", *check_paths)
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
    elif action in {"integration", "demo"}:
        if args.postgres_bin is None:
            raise SystemExit(
                "Database integration unavailable: explicit --postgres-bin required. "
                "No connection attempted."
            )
        if action == "demo":
            # Replace the wrappers so terminal SIGINT reaches one supervisor and
            # its API child without uv forwarding a second interrupt mid-cleanup.
            interpreter = subprocess.check_output(
                [
                    "uv",
                    "run",
                    "--locked",
                    "python",
                    "-c",
                    "import sys; print(sys.executable)",
                ],
                cwd=ROOT / "backend",
                text=True,
            ).strip()
            os.execv(
                interpreter,
                [
                    interpreter,
                    str(ROOT / "scripts/run_storage_tests.py"),
                    "--postgres-bin",
                    str(args.postgres_bin.resolve()),
                    "--demo",
                    *(["--pgvector"] if args.pgvector else []),
                ],
            )
        backend(
            "python",
            "../scripts/run_storage_tests.py",
            "--postgres-bin",
            str(args.postgres_bin.resolve()),
            *(["--demo"] if action == "demo" else []),
            *(["--pgvector"] if args.pgvector else []),
        )
    elif action == "migration-history":
        backend("alembic", "history")


if __name__ == "__main__":
    main()
