"""Administrator-only security singleton."""

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from rpb.modules.account_config.application.llm import LLMService


class SecurityWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: str | None = None
    connection_timeout_seconds: int = Field(ge=1)
    connection_retry_count: int = Field(ge=0, le=5)
    config_snapshot_retention_days: int = Field(ge=1)
    diagnostic_scope: Literal["minimal", "standard"]


def router_for(service: LLMService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin/security-config")

    def call(request: Request, data: dict[str, Any] | None = None) -> dict[str, Any]:
        value = service.call(
            "read" if data is None else "save",
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            data=data,
            write=data is not None,
            expected_actor=request.headers.get("x-expected-actor"),
        )
        return {"data": value, "meta": {"request_id": request.state.request_id}}

    @router.get("")
    def read(request: Request) -> dict[str, Any]:
        return call(request)

    @router.put("")
    def save(request: Request, body: SecurityWrite) -> dict[str, Any]:
        return call(request, body.model_dump(exclude_unset=True))

    return router
