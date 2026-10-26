"""Explicitly composed business API; callers own the engine and its lifecycle."""

import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from rpb.adapters.auth import AccountStore
from rpb.adapters.configuration_tasks import ConfigurationTasks
from rpb.adapters.construction import ConstructionInitializer
from rpb.adapters.llm import LLMStore
from rpb.adapters.project_commands import ProjectUnitOfWork
from rpb.adapters.sources import SourceStore
from rpb.api.account import router_for
from rpb.api.llm import router_for as llm_router
from rpb.api.projects import router_for as projects_router
from rpb.api.sources import router_for as sources_router
from rpb.modules.account_config.application.llm import LLMService
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.application.service import AccountService
from rpb.modules.project.application.service import ProjectService


def create_business_app(
    engine: Engine, origin: str, encryption_key: bytes | None = None
) -> FastAPI:
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"})
    ):
        raise ValueError("Explicit same-origin HTTPS or loopback HTTP origin required")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    account = AccountStore(engine)
    sources = SourceStore(account, encryption_key)
    app.include_router(sources_router(LLMService(sources, origin)))
    app.include_router(
        llm_router(
            LLMService(ConfigurationTasks(LLMStore(account, encryption_key), sources), origin)
        )
    )
    app.include_router(router_for(AccountService(account, origin), parsed.scheme == "https"))
    app.include_router(
        projects_router(ProjectService(ProjectUnitOfWork(account, ConstructionInitializer)), origin)
    )

    def error(
        request: Request, code: str, status: int, details: dict[str, Any] | None = None
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            headers={
                "Cache-Control": "no-store",
                **({"Retry-After": "5"} if status == 429 else {}),
            },
            content={
                "error": {
                    "code": code,
                    "category": {"CONFIG": "configuration", "LOCK": "lock_conflict"}.get(
                        code.split("_", 1)[0], code.split("_", 1)[0].lower()
                    ),
                    "message": "资源不可用"
                    if code == "PERMISSION_RESOURCE_UNAVAILABLE"
                    else "Request could not be completed",
                    "retryable": False,
                    "details": details,
                    "recovery": None,
                },
                "meta": {"request_id": getattr(request.state, "request_id", str(uuid4()))},
            },
        )

    @app.exception_handler(AccountError)
    async def account_error(request: Request, exc: AccountError) -> JSONResponse:
        return error(request, exc.code, exc.status, exc.details)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        code = (
            "VALIDATION_UNKNOWN_FIELD"
            if any(e["type"] == "extra_forbidden" for e in exc.errors())
            else "VALIDATION_FIELD_INVALID"
        )
        return error(request, code, 422)

    @app.middleware("http")
    async def boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip()
                != "application/json"
            ):
                return error(request, "VALIDATION_UNSUPPORTED_FORMAT", 415)
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 65536:
                    return error(request, "VALIDATION_PAYLOAD_TOO_LARGE", 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
            if (
                request.url.path.startswith(
                    ("/api/v1/me/llm-configs", "/api/v1/me/data-source-configs")
                )
                and request._body.strip()
            ):

                def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
                    result: dict[str, object] = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("Duplicate key")
                        result[key] = value
                    return result

                try:
                    decoded = json.loads(request._body, object_pairs_hook=unique)
                    json.dumps(decoded, ensure_ascii=False, allow_nan=False).encode("utf-8")
                except ValueError, UnicodeError, RecursionError:
                    return error(request, "VALIDATION_FIELD_INVALID", 422)
            if request.method == "DELETE" and request._body.strip():
                return error(request, "VALIDATION_BAD_REQUEST", 400)
        try:
            response = await call_next(request)
        except Exception:
            return error(request, "STORAGE_INTERNAL_FAILURE", 500)
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
