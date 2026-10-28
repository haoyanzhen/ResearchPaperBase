"""SMTP singleton and explicit OAuth entrypoints."""

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from rpb.modules.account_config.application.llm import LLMService
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.application.smtp import SMTPPort


class SMTPWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: str | None = None
    sender_email: str
    server: str
    port: int
    encryption: str
    auth_type: str
    username: str | None = None
    provider: str = "custom"
    oauth: dict[str, Any] | None = None
    secret: dict[str, Any] | None = None


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OAuthStart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: str | None = None


def router_for(store: SMTPPort, origin: str) -> APIRouter:
    service, router = LLMService(store, origin), APIRouter(prefix="/api/v1/admin/smtp-config")

    def call(
        request: Request, operation: str, data: dict[str, Any] | None = None, write: bool = False
    ) -> Any:
        return service.call(
            operation,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            None,
            data,
            request.headers.get("idempotency-key"),
            write,
            request.headers.get("x-expected-actor"),
        )

    def envelope(request: Request, data: Any) -> dict[str, Any]:
        return {"data": data, "meta": {"request_id": request.state.request_id}}

    @router.get("")
    def read(request: Request) -> Any:
        return envelope(request, call(request, "read"))

    @router.put("")
    def save(request: Request, body: SMTPWrite) -> Any:
        return envelope(request, call(request, "save", body.model_dump(exclude_unset=True), True))

    @router.post("/test", status_code=202)
    def test(request: Request, response: Response, body: Empty) -> Any:
        data = call(request, "test", {}, True)
        response.headers["Location"] = data["status_url"]
        value = envelope(request, data)
        value["meta"]["idempotency_expires_at"] = None
        return value

    @router.post("/oauth/start")
    def start(request: Request, body: OAuthStart) -> Any:
        return envelope(request, call(request, "oauth_start", body.model_dump(), True))

    @router.get("/oauth/callback")
    def callback(
        request: Request, state: str = "", code: str | None = None, error: str | None = None
    ) -> Response:
        ok = False
        try:
            ok = store.callback(
                request.cookies.get("rpb_session", ""), state, code, error is not None
            )
        except AccountError:
            pass
        return RedirectResponse(
            "/workspace?smtp_oauth=" + ("connected" if ok else "failed"),
            status_code=303,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    return router
