"""Bounded POSIX process handshakes for local API/worker tests."""

import os
import selectors
import subprocess
import time
from contextlib import contextmanager


@contextmanager
def managed_process(args, env=None):
    process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, text=True)
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        if process.stdout:
            process.stdout.close()


def wait_for_line(process, expected, timeout=10):
    """Read complete lines under one deadline; partial output cannot extend it."""
    deadline = time.monotonic() + timeout
    pending = b""
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError("Process startup handshake timed out")
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError("Process exited before startup handshake")
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if expected in line.decode():
                    return
