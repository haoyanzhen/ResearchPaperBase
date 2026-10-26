"""Explicitly composed business API; callers own the engine and its lifecycle."""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from rpb.adapters.auth import AccountStore
from rpb.api.account import router_for
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.application.service import AccountService


def create_business_app(engine: Engine, origin: str) -> FastAPI:
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
    app.include_router(
        router_for(AccountService(AccountStore(engine), origin), parsed.scheme == "https")
    )

    def error(request: Request, code: str, status: int) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            headers={"Cache-Control": "no-store"},
            content={
                "error": {
                    "code": code,
                    "category": code.split("_", 1)[0].lower(),
                    "message": "Request could not be completed",
                    "retryable": False,
                    "details": None,
                    "recovery": None,
                },
                "meta": {"request_id": getattr(request.state, "request_id", str(uuid4()))},
            },
        )

    @app.exception_handler(AccountError)
    async def account_error(request: Request, exc: AccountError) -> JSONResponse:
        return error(request, exc.code, exc.status)

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
        try:
            response = await call_next(request)
        except Exception:
            return error(request, "STORAGE_INTERNAL_FAILURE", 500)
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
