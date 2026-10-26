"""Explicit idle process for lifecycle checks; never claims or completes tasks."""

import argparse
import signal
import sys
from threading import Event

from rpb.bootstrap.config import load_process_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idle", action="store_true", help="run an inactive skeleton process")
    args = parser.parse_args()
    load_process_settings()
    if not args.idle:
        print("Task execution unavailable; use --idle only for skeleton checks.", file=sys.stderr)
        raise SystemExit(2)
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    print("Worker skeleton alive; task execution disabled; not ready.", flush=True)
    stopped.wait()
    print("Worker skeleton stopped.", flush=True)


if __name__ == "__main__":
    main()
