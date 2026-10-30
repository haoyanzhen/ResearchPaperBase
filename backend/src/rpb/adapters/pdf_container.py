"""One-document Linux container runner for Windows, Linux and macOS hosts."""

import json
import logging
import shutil
import subprocess
import tempfile
from threading import Thread
from typing import Any
from uuid import uuid4

IMAGE = "rpb-pdf-parser:1"
OUTPUT_LIMIT = 2_000_000

# Only the PDF crosses stdin. No host mounts, application code or credentials.
BOOTSTRAP = """
import resource, sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
raw = sys.stdin.buffer.read(52_428_801)
if len(raw) > 52_428_800: raise SystemExit(2)
# The input file is exempt from the output-file budget, but bounded above.
resource.setrlimit(resource.RLIMIT_FSIZE, (52_428_800, 52_428_800))
Path('/work/input.pdf').write_bytes(raw)
del raw
resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
script = sys.argv[1]
sys.argv = ['extract', '/work/input.pdf', '/work/output.json']
exec(compile(script, '<pdf-engine>', 'exec'), {'__name__': '__main__'})
with open('/work/output.json', 'rb') as output:
    data = output.read(2_000_001)
if len(data) > 2_000_000: raise SystemExit(2)
sys.stdout.buffer.write(data)
"""


def failure(reason: str) -> dict[str, Any]:
    return {"reason": reason, "text": None, "segments": []}


def container_extract(
    script: str, raw: bytes, *, timeout: float, memory_kib: int
) -> dict[str, Any]:
    docker = shutil.which("docker")
    if docker is None:
        return failure("parser_unavailable")
    name = "rpb-pdf-" + uuid4().hex
    command = [
        docker,
        "run",
        "--pull=never",
        "--name",
        name,
        "--label=org.researchpaperbase.pdf-parser=1",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--memory=" + str(memory_kib) + "k",
        "--memory-swap=" + str(memory_kib) + "k",
        "--cpus=1",
        "--user=65534:65534",
        "--log-driver=none",
        "--tmpfs=/work:rw,noexec,nosuid,nodev,size=64m,mode=700,uid=65534,gid=65534",
        "--workdir=/work",
        "--entrypoint=python",
        "-i",
        IMAGE,
        "-I",
        "-B",
        "-c",
        BOOTSTRAP,
        script,
    ]
    result: dict[str, Any] = failure("parser_unavailable")
    cleanup_ok = False
    data = bytearray()
    process: subprocess.Popen[bytes] | None = None
    reader: Thread | None = None
    try:
        with tempfile.TemporaryFile() as source:
            source.write(raw)
            source.seek(0)
            process = subprocess.Popen(
                command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )

            def collect() -> None:
                assert process is not None and process.stdout is not None
                with process.stdout as stream:
                    while len(data) <= OUTPUT_LIMIT:
                        chunk = stream.read(min(65536, OUTPUT_LIMIT + 1 - len(data)))
                        if not chunk:
                            return
                        data.extend(chunk)
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass

            reader = Thread(target=collect, daemon=True)
            reader.start()
            process.wait(timeout=timeout)
            reader.join(timeout=1)
            if reader.is_alive() or len(data) > OUTPUT_LIMIT:
                result = failure("safety_limit")
            elif process.returncode in {125, 126, 127}:
                result = failure("parser_unavailable")
            elif process.returncode:
                result = failure("safety_limit")
            else:
                decoded = json.loads(data)
                result = decoded if isinstance(decoded, dict) else failure("safety_limit")
    except subprocess.TimeoutExpired:
        result = failure("safety_limit")
    except OSError, ValueError:
        result = failure("parser_unavailable")
    finally:
        # Stop and reap the CLI before cleanup; killing it alone is insufficient.
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
        if reader is not None:
            reader.join(timeout=1)
        try:
            cleanup = subprocess.run(
                [docker, "rm", "--force", name],
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            cleanup_ok = cleanup.returncode == 0
        except OSError, subprocess.TimeoutExpired:
            pass
        if not cleanup_ok:
            logging.getLogger(__name__).warning("PDF container cleanup unconfirmed: %s", name)
    return result if cleanup_ok else failure("parser_unavailable")
