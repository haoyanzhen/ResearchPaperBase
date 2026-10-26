"""P0 authentication transport. Public views never serialize adapter rows implicitly."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.application.service import AccountService


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: Annotated[str, Field(min_length=1, max_length=64)]
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("username")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank username")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()):
            raise ValueError("invalid email")
        return value


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    identifier: str
    password: str


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


def router_for(service: AccountService, secure: bool) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def token(request: Request) -> str:
        return request.cookies.get("rpb_session", "")

    def write_guard(request: Request, csrf: str | None) -> str:
        service.verify_origin(request.headers.get("origin"))
        if not csrf:
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        return csrf

    def cookie(response: Response, value: str) -> None:
        response.set_cookie(
            "rpb_session", value, httponly=True, secure=secure, samesite="lax", path="/"
        )

    def envelope(request: Request, data: Any) -> dict[str, Any]:
        return {
            "data": jsonable_encoder(
                data,
                custom_encoder={
                    datetime: lambda t: t.astimezone(UTC).isoformat().replace("+00:00", "Z")
                },
            ),
            "meta": {"request_id": request.state.request_id},
        }

    @router.get("/auth/csrf")
    def csrf(request: Request, response: Response) -> dict[str, Any]:
        session, value = service.store.csrf(token(request))
        cookie(response, session)
        return envelope(request, {"csrf_token": value})

    @router.post("/auth/register", status_code=201)
    def register(
        body: Register,
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        data = service.register(
            token(request),
            write_guard(request, x_csrf_token),
            body.username,
            body.email,
            body.password,
        )
        response.headers["Location"] = "/api/v1/me"
        return envelope(request, data)

    @router.post("/auth/login")
    def login(
        body: Login,
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        user, session = service.login(
            token(request), write_guard(request, x_csrf_token), body.identifier, body.password
        )
        cookie(response, session)
        return envelope(request, {"user": user})

    @router.post("/auth/logout")
    def logout(
        body: Empty,
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        service.store.logout(token(request), write_guard(request, x_csrf_token))
        response.delete_cookie(
            "rpb_session", httponly=True, secure=secure, samesite="lax", path="/"
        )
        return envelope(request, {"logged_out": True})

    @router.get("/me")
    def read_self(request: Request) -> dict[str, Any]:
        if not token(request):
            raise AccountError("AUTH_REQUIRED", 401)
        return envelope(request, service.store.read_self(token(request)))

    return router
