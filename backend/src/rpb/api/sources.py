"""Private source configuration HTTP boundary."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from rpb.modules.account_config.application.llm import LLMService
from rpb.modules.account_config.application.ports import AccountError


class SourceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    provider: str
    base_url: str
    access_mode: str
    enabled: bool = True
    rate_limit_per_minute: int | None = None
    secret: dict[str, Any] | None = None


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: str | None = None
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    access_mode: str | None = None
    enabled: bool | None = None
    rate_limit_per_minute: int | None = None
    secret: dict[str, Any] | None = None


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def router_for(service: LLMService, *, system: bool = False) -> APIRouter:
    base = "/api/v1/admin/data-source-configs" if system else "/api/v1/me/data-source-configs"
    router = APIRouter(prefix=base)

    def call(
        request: Request,
        operation: str,
        target: str | None = None,
        data: dict[str, Any] | None = None,
        write: bool = False,
    ) -> Any:
        return service.call(
            operation,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            target,
            data,
            request.headers.get("idempotency-key"),
            write,
            request.headers.get("x-expected-actor"),
        )

    def envelope(request: Request, data: Any) -> dict[str, Any]:
        return {"data": data, "meta": {"request_id": request.state.request_id}}

    def values(body: BaseModel) -> dict[str, Any]:
        data = body.model_dump(exclude_unset=True)
        if any(v is None and k != "rate_limit_per_minute" for k, v in data.items()):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        return data

    @router.get("")
    def listing(
        request: Request,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> Any:
        page = call(request, "list", data={"page_size": page_size, "cursor": cursor})
        result = envelope(request, {"items": page["items"]})
        result["meta"].update(next_cursor=page["next_cursor"], has_more=page["has_more"])
        return result

    @router.post("", status_code=201)
    def create(request: Request, response: Response, body: SourceWrite) -> Any:
        data = call(request, "create", data=values(body), write=True)
        response.headers["Location"] = base + "/" + data["id"]
        result = envelope(request, data)
        result["meta"]["idempotency_expires_at"] = (
            (datetime.fromisoformat(data["created_at"]) + timedelta(hours=48))
            .isoformat()
            .replace("+00:00", "Z")
        )
        return result

    @router.get("/{config_id}")
    def read(request: Request, config_id: str) -> Any:
        return envelope(request, call(request, "read", config_id))

    @router.patch("/{config_id}")
    def update(request: Request, config_id: str, body: SourcePatch) -> Any:
        return envelope(request, call(request, "update", config_id, values(body), True))

    @router.delete("/{config_id}", status_code=204)
    def delete(request: Request, config_id: str, expected_revision: str | None = None) -> Response:
        call(request, "delete", config_id, {"expected_revision": expected_revision}, True)
        return Response(status_code=204)

    @router.post("/{config_id}/test", status_code=202)
    def test(request: Request, response: Response, config_id: str, body: Empty) -> Any:
        data = call(request, "test", config_id, {}, True)
        response.headers["Location"] = data["status_url"]
        result = envelope(request, data)
        result["meta"]["idempotency_expires_at"] = None
        return result

    return router
