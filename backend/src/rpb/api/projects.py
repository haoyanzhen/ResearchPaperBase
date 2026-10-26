"""Project.Create/Read transport only."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.project.application.service import ProjectService


class ProjectWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=10000)] = ""
    research_scope: Annotated[str, Field(max_length=10000)] = ""

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank name")
        return value


def router_for(service: ProjectService, origin: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects")

    def token(request: Request) -> str:
        token = request.cookies.get("rpb_session")
        if not token:
            raise AccountError("AUTH_REQUIRED", 401)
        return token

    def wire(value: Any) -> Any:
        return jsonable_encoder(
            value,
            custom_encoder={
                datetime: lambda t: t.astimezone(UTC).isoformat().replace("+00:00", "Z")
            },
        )

    @router.post("", status_code=201)
    def create(
        body: ProjectWrite,
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        session = token(request)
        if request.headers.get("origin") != origin or not x_csrf_token:
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        if (
            idempotency_key is None
            or not 16 <= len(idempotency_key) <= 128
            or any(not 32 <= ord(ch) <= 126 for ch in idempotency_key)
        ):
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        data, expires = service.create(session, x_csrf_token, idempotency_key, body.model_dump())
        response.headers["Location"] = f"/api/v1/projects/{data['id']}"
        return {
            "data": wire(data),
            "meta": {
                "request_id": request.state.request_id,
                "idempotency_expires_at": wire(expires),
            },
        }

    @router.get("/{project_id}")
    def read(project_id: UUID, request: Request) -> dict[str, Any]:
        return {
            "data": wire(service.read(token(request), project_id)),
            "meta": {"request_id": request.state.request_id},
        }

    return router
