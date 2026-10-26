import uvicorn
from fastapi import FastAPI

from rpb.api.health import router
from rpb.bootstrap.config import Settings, load_process_settings


def create_app() -> FastAPI:
    Settings.load()
    app = FastAPI(title="RPB engineering skeleton", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)
    return app


def main() -> None:
    settings = load_process_settings()
    uvicorn.run(create_app(), host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
