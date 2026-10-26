"""Create a disposable PostgreSQL 17 cluster, run storage tests, stop and remove it."""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]


def run_tests(binary_dir: Path, demo: bool = False) -> int:
    binary_dir = binary_dir.resolve(strict=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("PG", "RPB_")) and k != "DATABASE_URL"
    }
    version = subprocess.check_output(
        [str(binary_dir / "postgres"), "--version"], text=True, env=env
    )
    if not version.startswith("postgres (PostgreSQL) 17."):
        raise SystemExit("PostgreSQL 17 binaries required; no connection attempted")
    root = Path(tempfile.mkdtemp(prefix="rpb-db-", dir="/tmp")).resolve()
    run_id = "rpb_test_" + uuid4().hex
    admin_password = secrets.token_hex(32)
    test_password = secrets.token_hex(32)
    password_file = root / "admin-password"
    password_file.write_text(admin_password)
    password_file.chmod(0o600)
    data = root / "data"
    cleaned = False

    def pg(*args: str) -> None:
        subprocess.run(
            [str(binary_dir / args[0]), *args[1:]],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=60,
            start_new_session=True,  # PostgreSQL cleanup is owned by this supervisor.
        )

    try:
        pg(
            "initdb",
            "-D",
            str(data),
            "-U",
            "fixture_admin",
            "-A",
            "scram-sha-256",
            "--pwfile",
            str(password_file),
            "--no-locale",
            "-E",
            "UTF8",
        )
        password_file.unlink()  # Never expose fixture administrator credentials to child tests.
        # No TCP listener; socket and credentials live inside mode-0700 owned root.
        pg(
            "pg_ctl",
            "-D",
            str(data),
            "-l",
            str(root / "postgres.log"),
            "-o",
            f"-k {root} -h '' -p 5432 -c timezone=UTC",
            "-w",
            "start",
        )
        with psycopg.connect(
            host=str(root),
            dbname="postgres",
            user="fixture_admin",
            password=admin_password,
            autocommit=True,
        ) as admin:
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(run_id), sql.Literal(test_password))
            )
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(run_id), sql.Identifier(run_id)
                )
            )
            admin.execute(
                sql.SQL("ALTER DATABASE {} SET rpb.test_run_id = {}").format(
                    sql.Identifier(run_id), sql.Literal(run_id)
                )
            )
        target = root / "target.json"
        target.write_text(
            json.dumps(
                dict(
                    host=str(root),
                    database=run_id,
                    username=run_id,
                    password=test_password,
                    run_id=run_id,
                    binary_dir=str(binary_dir),
                )
            )
        )
        target.chmod(0o600)
        print(
            json.dumps(
                dict(
                    postgres=version.strip(),
                    run_id=run_id,
                    root=str(root),
                    tcp=False,
                    role_superuser=False,
                )
            ),
            flush=True,
        )
        if password_file.exists():
            raise RuntimeError("Fixture administrator credential cleanup failed")
        child = (
            [
                sys.executable,
                str(ROOT / "scripts/run_business_demo.py"),
                "--target",
                str(target),
            ]
            if demo
            else [
                sys.executable,
                "-m",
                "pytest",
                "tests/integration",
                "-q",
                "-s",
                "--storage-target",
                str(target),
            ]
        )
        # subprocess.run waits for/kills the sole child before the database cleanup.
        result = subprocess.run(child, cwd=ROOT / "backend", env=env, timeout=1800 if demo else 600)
        return result.returncode
    finally:
        # Never erase the directory of a server whose stop could not be verified.
        if (data / "postmaster.pid").exists():
            pg("pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop")
        if (data / "postmaster.pid").exists():
            raise RuntimeError(f"Cleanup incomplete; retained isolated root {root}")
        shutil.rmtree(root)
        cleaned = not root.exists()
        print(
            json.dumps(dict(run_id=run_id, server_stopped=True, root_removed=cleaned)),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", required=True, type=Path)
    parser.add_argument(
        "--demo", action="store_true", help="30-minute disposable loopback browser demo"
    )
    args = parser.parse_args()
    try:
        raise SystemExit(run_tests(args.postgres_bin, demo=args.demo))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
