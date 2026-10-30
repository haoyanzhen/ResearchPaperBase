"""Serve the built browser client against an explicit disposable test descriptor only."""

import argparse
import json
import os
import stat
from pathlib import Path
from threading import Event, Thread

import sqlalchemy as sa
import uvicorn
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from rpb.adapters.auth import AccountStore
from rpb.adapters.llm import LLMStore
from rpb.adapters.llm_provider import HTTPProvider
from rpb.adapters.llm_worker import LLMWorker
from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.paper_retrieval import PaperRetrieval
from rpb.adapters.paper_scoring_worker import ScoreProvider, ScoreWorker
from rpb.adapters.pdf_cleanup_provider import CleanupProvider
from rpb.adapters.pdf_cleanup_worker import CleanupWorker
from rpb.adapters.pdf_processing import PDFProvider
from rpb.adapters.run_worker import RunWorker
from rpb.adapters.search_term_worker import TermProvider, TermWorker
from rpb.adapters.smtp_worker import SMTPWorker
from rpb.adapters.source_provider import SourceProvider
from rpb.adapters.source_worker import SourceWorker
from rpb.adapters.sources import SourceStore
from rpb.bootstrap.business import create_business_app

ROOT = Path(__file__).resolve().parents[1]


def create_demo(
    target: Path, port: int, encryption_key: bytes | None = None
) -> tuple[FastAPI, sa.Engine]:
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid loopback port")
    target = target.resolve(strict=True)
    data = json.loads(target.read_text())
    run_id = data["run_id"]
    if (
        not run_id.startswith("rpb_test_")
        or len(run_id) != 41
        or data["database"] != run_id
        or data["username"] != run_id
        or Path(data["host"]).resolve() != target.parent
        or not target.parent.name.startswith("rpb-db-")
        or stat.S_IMODE(target.parent.stat().st_mode) != 0o700
        or stat.S_IMODE(target.stat().st_mode) != 0o600
    ):
        raise ValueError("Explicit disposable test target required")
    dist = ROOT / "frontend/dist"
    if not (dist / "index.html").is_file():
        raise ValueError("Build the browser client before starting the demo")
    engine = sa.create_engine(
        sa.URL.create(
            "postgresql+psycopg",
            username=run_id,
            password=data["password"],
            database=run_id,
            query={"host": data["host"], "port": "5432"},
        ),
        hide_parameters=True,
    )
    try:
        with engine.begin() as conn:
            cfg = Config(str(ROOT / "backend/alembic.ini"))
            cfg.attributes.update(connection=conn, test_run_id=run_id)
            command.upgrade(
                cfg, "head"
            )  # Checks database, role, marker and privileges.
        app = create_business_app(engine, f"http://127.0.0.1:{port}", encryption_key)
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/workspace", include_in_schema=False)
        def workspace() -> FileResponse:
            return FileResponse(dist / "index.html")

        return app, engine
    except BaseException:
        engine.dispose()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        # Validate the explicit disposable target before creating any credential key.
        app, engine = create_demo(args.target, args.port)
        engine.dispose()
        key_path = args.target.resolve().parent / "llm-demo.key"
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if key_path.is_symlink() or stat.S_IMODE(key_path.stat().st_mode) != 0o600:
                raise ValueError("Unsafe key file")
        else:
            with os.fdopen(descriptor, "wb") as output:
                output.write(Fernet.generate_key())
        key = key_path.read_bytes()
        app, engine = create_demo(args.target, args.port, key)
    except Exception:
        raise SystemExit(
            "Demo startup refused; explicit isolated target and built client required."
        ) from None
    stopped = Event()
    worker = LLMWorker(LLMStore(AccountStore(engine), key), HTTPProvider())

    system_worker = LLMWorker(
        LLMStore(AccountStore(engine), key, system=True), HTTPProvider()
    )
    source_worker = SourceWorker(
        SourceStore(AccountStore(engine), key), SourceProvider()
    )

    system_source_worker = SourceWorker(
        SourceStore(AccountStore(engine), key, system=True), SourceProvider()
    )

    smtp_worker = SMTPWorker(app.state.smtp_store)
    term_worker = TermWorker(app.state.term_store, TermProvider())
    run_worker = RunWorker(app.state.run_store, PaperRetrieval())
    score_worker = ScoreWorker(app.state.run_store, ScoreProvider())
    processing_worker = ProcessingWorker(app.state.run_store, PDFProvider())
    cleanup_worker = CleanupWorker(
        app.state.run_store, PDFProvider(), CleanupProvider()
    )

    def work() -> None:
        while not stopped.is_set():
            llm_work = worker.run_once()
            source_work = source_worker.run_once()
            system_work = system_worker.run_once()
            system_source_work = system_source_worker.run_once()
            smtp_work = smtp_worker.run_once()
            term_work = (
                term_worker.run_once()
                or run_worker.run_once()
                or score_worker.run_once()
                or processing_worker.run_once()
                or cleanup_worker.run_once()
            )
            if not (
                llm_work
                or source_work
                or system_work
                or system_source_work
                or smtp_work
                or term_work
            ):
                stopped.wait(0.5)

    thread = Thread(target=work, daemon=True)
    thread.start()
    try:
        print(
            f"Disposable demo: http://127.0.0.1:{args.port}/workspace (data removed on exit)",
            flush=True,
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    finally:
        stopped.set()
        thread.join(150)
        engine.dispose()


if __name__ == "__main__":
    main()
