"""Administrator account operations; no private content reads."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, model_validator

from rpb.api.account import Register
from rpb.modules.account_config.application.admin import AdminService

Action = Literal[
    "change_email", "enable", "disable", "grant_admin", "revoke_admin", "reset_password", "delete"
]


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Action
    expected_revision: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def parameters(self) -> Preview:
        if self.action == "change_email":
            if not self.email or len(self.email) > 254:
                raise ValueError("email required")
            Register.valid_email(self.email)
        elif "email" in self.model_fields_set:
            raise ValueError("email not allowed")
        if "expected_revision" in self.model_fields_set and not self.expected_revision:
            raise ValueError("invalid revision")
        return self


class Update(Preview):
    action: Literal["change_email", "enable", "disable", "grant_admin", "revoke_admin"]
    confirmation_token: str | None = None
    acknowledged_risk_ids: list[str]


class Reset(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: str | None = None
    confirmation_token: str | None = None
    acknowledged_risk_ids: list[str]


def router_for(service: AdminService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin/users")

    def call(request: Request, operation: str, target: str | None, data: dict[str, Any]) -> Any:
        return service.call(
            operation,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            target,
            data,
            request.headers.get("idempotency-key"),
            request.headers.get("x-expected-actor"),
        )

    def envelope(request: Request, data: Any) -> Any:
        return {"data": data, "meta": {"request_id": request.state.request_id}}

    @router.get("")
    def listing(
        request: Request,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> Any:
        page = call(request, "list", None, {"page_size": page_size, "cursor": cursor})
        result = envelope(request, {"items": page["items"]})
        result["meta"].update(next_cursor=page["next_cursor"], has_more=page["has_more"])
        return result

    @router.post("/{user_id}/action-preview")
    def preview(request: Request, user_id: str, body: Preview) -> Any:
        return envelope(
            request, call(request, "preview", user_id, body.model_dump(exclude_unset=True))
        )

    @router.patch("/{user_id}")
    def update(request: Request, user_id: str, body: Update) -> Any:
        return envelope(
            request, call(request, "update", user_id, body.model_dump(exclude_unset=True))
        )

    @router.post("/{user_id}/reset-password")
    def reset(request: Request, user_id: str, body: Reset) -> Any:
        result = call(
            request,
            "reset",
            user_id,
            {**body.model_dump(exclude_unset=True), "action": "reset_password"},
        )
        expires = result.pop("_expires")
        response = envelope(request, result)
        response["meta"]["idempotency_expires_at"] = expires
        return response

    @router.delete("/{user_id}")
    def delete(
        request: Request,
        user_id: str,
        expected_revision: str | None = None,
        confirmation_token: str | None = None,
        acknowledged_risk_ids: Annotated[list[str], Query()] = [],
    ) -> Any:
        return envelope(
            request,
            call(
                request,
                "delete",
                user_id,
                {
                    "action": "delete",
                    "expected_revision": expected_revision,
                    "confirmation_token": confirmation_token,
                    "acknowledged_risk_ids": acknowledged_risk_ids,
                },
            ),
        )

    return router
