"""Serve the built browser client against an explicit disposable test descriptor only."""

import argparse
import json
import stat
from pathlib import Path

import sqlalchemy as sa
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rpb.bootstrap.business import create_business_app

ROOT = Path(__file__).resolve().parents[1]


def create_demo(target: Path, port: int) -> tuple[FastAPI, sa.Engine]:
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
            command.upgrade(cfg, "head")  # Checks database, role, marker and privileges.
        app = create_business_app(engine, f"http://127.0.0.1:{port}")
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
        app, engine = create_demo(args.target, args.port)
    except Exception:
        raise SystemExit(
            "Demo startup refused; explicit isolated target and built client required."
        ) from None
    try:
        print(
            f"Disposable demo: http://127.0.0.1:{args.port}/workspace (data removed on exit)",
            flush=True,
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
