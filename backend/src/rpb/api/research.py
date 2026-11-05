"""Authenticated session creation and recovery; reading never starts generation."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.research.application.sessions import ResearchService


class ResearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1, max_length=200)] = "新研究会话"

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Blank title")
        return value


def router_for(service: ResearchService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}/research-sessions")

    def call(request: Request, project_id: UUID, operation: str, data: Any) -> Any:
        result = service.call(
            operation,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            str(project_id),
            data,
            request.headers.get("idempotency-key"),
            operation == "create",
            request.headers.get("x-expected-actor"),
        )
        meta: dict[str, Any] = {"request_id": request.state.request_id}
        if operation == "create":
            meta["idempotency_expires_at"] = result["expires_at"]
            if result["original_request_id"] != request.state.request_id:
                meta["original_request_id"] = result["original_request_id"]
            result = result["value"]
        if operation == "list":
            cursor = result.pop("next_cursor")
            meta.update(next_cursor=cursor, has_more=cursor is not None)
        return {"data": result, "meta": meta}

    @router.post("", status_code=201)
    def create(request: Request, response: Response, project_id: UUID, body: ResearchCreate) -> Any:
        result = call(
            request,
            project_id,
            "create",
            {"body": body.model_dump(), "request_id": request.state.request_id},
        )
        response.headers["Location"] = (
            f"/api/v1/projects/{project_id}/research-sessions/{result['data']['id']}"
        )
        return result

    @router.get("")
    def listing(
        request: Request,
        project_id: UUID,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: Annotated[str | None, Query(max_length=4096)] = None,
    ) -> Any:
        if set(request.query_params) - {"page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        return call(request, project_id, "list", {"page_size": page_size, "cursor": cursor})

    @router.get("/{session_id}")
    def read(request: Request, project_id: UUID, session_id: UUID) -> Any:
        if request.query_params:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        return call(request, project_id, "read", {"session_id": str(session_id)})

    return router
