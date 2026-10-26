"""Project.Create/Read transport only."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.project.application.service import ProjectService


class ProjectWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=10000)] = ""
    research_scope: Annotated[str, Field(max_length=10000)] = ""

    @field_validator("name", "description", "research_scope", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank name")
        return value


class RequiredWhenPresent(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def reject_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("null is not supported")
        return value


class ProjectPatch(RequiredWhenPresent):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    description: Annotated[str | None, Field(max_length=10000)] = None
    research_scope: Annotated[str | None, Field(max_length=10000)] = None

    @field_validator("name", "description", "research_scope", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class LifecyclePreview(RequiredWhenPresent):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["archive", "delete"]
    expected_revision: Annotated[str | None, Field(min_length=1, max_length=128)] = None


class LifecycleCommand(RequiredWhenPresent):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    confirmation_token: Annotated[str | None, Field(min_length=1, max_length=4096)] = None
    acknowledged_risk_ids: list[str]


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

    @router.get("")
    def list_projects(
        request: Request,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        x_expected_actor: Annotated[UUID | None, Header()] = None,
    ) -> dict[str, Any]:
        if set(request.query_params) - {"page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        items, next_cursor = service.list_projects(
            token(request), page_size, cursor, x_expected_actor
        )
        return {
            "data": {"items": wire(items)},
            "meta": {
                "request_id": request.state.request_id,
                "next_cursor": next_cursor,
                "has_more": next_cursor is not None,
            },
        }

    @router.get("/{project_id}")
    def read(project_id: UUID, request: Request) -> dict[str, Any]:
        return {
            "data": wire(service.read(token(request), project_id)),
            "meta": {"request_id": request.state.request_id},
        }

    def private_write(request: Request, csrf: str | None) -> tuple[str, str]:
        session = token(request)
        if request.headers.get("origin") != origin or not csrf:
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        return session, csrf

    @router.patch("/{project_id}")
    def update(
        project_id: UUID,
        body: ProjectPatch,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        session, csrf = private_write(request, x_csrf_token)
        values = body.model_dump(exclude_unset=True)
        revision = values.pop("expected_revision", None)
        return {
            "data": wire(service.update(session, csrf, project_id, revision, values)),
            "meta": {"request_id": request.state.request_id},
        }

    @router.post("/{project_id}/action-preview")
    def preview(
        project_id: UUID,
        body: LifecyclePreview,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        session, csrf = private_write(request, x_csrf_token)
        return {
            "data": wire(
                service.preview(session, csrf, project_id, body.expected_revision, body.action)
            ),
            "meta": {"request_id": request.state.request_id},
        }

    @router.post("/{project_id}/archive")
    def archive(
        project_id: UUID,
        body: LifecycleCommand,
        request: Request,
        x_csrf_token: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        session, csrf = private_write(request, x_csrf_token)
        if (
            idempotency_key is None
            or not 16 <= len(idempotency_key) <= 128
            or any(not 32 <= ord(ch) <= 126 for ch in idempotency_key)
        ):
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        result, expires = service.change_state(
            session,
            csrf,
            project_id,
            "archive",
            body.expected_revision,
            body.confirmation_token,
            body.acknowledged_risk_ids,
            idempotency_key,
        )
        return {
            "data": wire(result),
            "meta": {
                "request_id": request.state.request_id,
                "idempotency_expires_at": wire(expires),
            },
        }

    @router.delete("/{project_id}", status_code=204)
    def delete(
        project_id: UUID,
        request: Request,
        expected_revision: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        confirmation_token: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
        acknowledged_risk_ids: Annotated[list[str], Query()] = [],
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> Response:
        session, csrf = private_write(request, x_csrf_token)
        if set(request.query_params) - {
            "expected_revision",
            "confirmation_token",
            "acknowledged_risk_ids",
        }:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        service.change_state(
            session,
            csrf,
            project_id,
            "delete",
            expected_revision,
            confirmation_token,
            acknowledged_risk_ids,
        )
        return Response(status_code=204)

    return router
