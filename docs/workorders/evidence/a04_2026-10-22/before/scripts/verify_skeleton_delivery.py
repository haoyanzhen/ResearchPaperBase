"""Clean-copy installation/build, lock rejection, and installed-wheel process smoke checks."""

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd, env=None, success=True):
    print("+", " ".join(map(str, args)), flush=True)
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    assert (result.returncode == 0) == success, result.returncode
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="rpb-skeleton-") as tmp:
        root = Path(tmp)
        for name in ("backend", "frontend", "scripts", "contracts"):
            shutil.copytree(
                ROOT / name,
                root / name,
                ignore=shutil.ignore_patterns(
                    ".venv",
                    "node_modules",
                    "dist",
                    "__pycache__",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    "test-results",
                    "*.tsbuildinfo",
                ),
            )
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("RPB_", "DATABASE_", "UV_PROJECT_ENVIRONMENT"))
        }
        run(["python3", "scripts/engineering.py", "install"], root, env)
        run(["python3", "scripts/engineering.py", "build"], root, env)
        pyproject = root / "backend/pyproject.toml"
        original = pyproject.read_text()
        pyproject.write_text(original.replace('version = "1.0.0"', 'version = "1.0.1"'))
        result = run(["uv", "sync", "--locked", "--offline"], root / "backend", env, success=False)
        assert "lockfile" in result.stderr.lower()
        pyproject.write_text(original)
        package = root / "frontend/package.json"
        original = package.read_text()
        data = json.loads(original)
        data["dependencies"]["react"] = "18.3.1"
        package.write_text(json.dumps(data))
        result = run(["npm", "ci", "--ignore-scripts"], root / "frontend", env, success=False)
        assert "lock" in result.stderr.lower()
        package.write_text(original)
        lock = root / "backend/uv.lock"
        lock_content = lock.read_bytes()
        lock.unlink()
        result = run(["python3", "scripts/engineering.py", "install"], root, env, success=False)
        assert "lock missing" in result.stderr
        lock.write_bytes(lock_content)
        result = run(
            ["python3", "scripts/engineering.py", "integration"],
            root,
            env | {"DATABASE_URL": "postgresql://private-marker/business"},
            success=False,
        )
        assert "No connection attempted" in result.stderr and "private-marker" not in result.stderr
        run(["uv", "venv", "--python", "3.14.4", str(root / "wheel-env")], root, env)
        python = root / "wheel-env/bin/python"
        wheel = next((root / "backend/dist").glob("*.whl"))
        run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(root / "runtime.txt"),
            ],
            root / "backend",
            env,
        )
        run(["uv", "pip", "sync", "--python", str(python), str(root / "runtime.txt")], root, env)
        run(["uv", "pip", "install", "--no-deps", "--python", str(python), str(wheel)], root, env)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        with (root / "api.log").open("w+") as log:
            api = subprocess.Popen(
                [str(root / "wheel-env/bin/rpb-api")],
                cwd=root,
                env=env | {"RPB_PORT": str(port)},
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    assert api.poll() is None, "API exited before live probe"
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health/live", timeout=1
                        ) as response:
                            assert json.load(response) == {"status": "alive"}
                        break
                    except urllib.error.URLError:
                        time.sleep(0.1)
                else:
                    raise AssertionError("API startup timed out")
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=2)
                    raise AssertionError("Skeleton must not claim readiness")
                except urllib.error.HTTPError as error:
                    assert error.code == 503
                    assert json.load(error) == {"status": "not_ready"}
                print("Installed wheel: live=200, ready=503; no business services enabled.")
            finally:
                api.send_signal(signal.SIGTERM)
                try:
                    api.wait(timeout=10)
                finally:
                    if api.poll() is None:
                        api.kill()
                        api.wait()
                log.seek(0)
                lifecycle = log.read()
                print(lifecycle)
                assert "Application shutdown complete" in lifecycle
                assert api.returncode in (0, -signal.SIGTERM)
    print("Clean environment removed; no database or provider accessed.")


if __name__ == "__main__":
    main()
