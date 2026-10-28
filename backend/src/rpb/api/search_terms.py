"""Project-scoped search term and existing material-policy transport."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.application.terms import TermService


def router_for(service: TermService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}")
    cw = "/construction-workspace"

    def call(
        request: Request,
        project_id: UUID,
        operation: str,
        data: dict[str, Any] | None = None,
        write: bool = False,
        receipt: bool = False,
    ) -> Any:
        result = service.call(
            operation,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            str(project_id),
            {**(data or {}), **({"_request_id": request.state.request_id} if receipt else {})},
            request.headers.get("idempotency-key"),
            write,
            request.headers.get("x-expected-actor"),
        )
        meta: dict[str, Any] = {"request_id": request.state.request_id}
        if receipt:
            meta["idempotency_expires_at"] = result["expires_at"]
            if result["original_request_id"] != request.state.request_id:
                meta["original_request_id"] = result["original_request_id"]
            result = result["value"]
        return {"data": result, "meta": meta}

    @router.get(cw)
    def read(request: Request, project_id: UUID) -> Any:
        return call(request, project_id, "workspace")

    @router.get(cw + "/source-options")
    def source_options(request: Request, project_id: UUID) -> Any:
        return call(request, project_id, "source_options")

    @router.patch(cw)
    def config(request: Request, project_id: UUID, body: dict[str, Any]) -> Any:
        return call(request, project_id, "save_config", body, True)

    @router.get(cw + "/search-terms")
    def listing(
        request: Request,
        project_id: UUID,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
    ) -> Any:
        if set(request.query_params) - {"page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        result = call(request, project_id, "list_terms", {"page_size": page_size, "cursor": cursor})
        next_cursor = result["data"].pop("next_cursor")
        result["meta"].update(next_cursor=next_cursor, has_more=next_cursor is not None)
        return result

    @router.post(cw + "/search-terms", status_code=201)
    def add(request: Request, response: Response, project_id: UUID, body: dict[str, Any]) -> Any:
        result = call(request, project_id, "add_term", body, True, True)
        response.headers["Location"] = (
            f"/api/v1/projects/{project_id}/construction-workspace/search-terms/{result['data']['id']}"
        )
        return result

    @router.post(cw + "/search-terms/generate", status_code=202)
    def generate(
        request: Request, response: Response, project_id: UUID, body: dict[str, Any]
    ) -> Any:
        result = call(request, project_id, "generate", body, True, True)
        response.headers["Location"] = result["data"]["status_url"]
        return result

    @router.get(cw + "/search-terms/{term_id}")
    def term(request: Request, project_id: UUID, term_id: UUID) -> Any:
        return call(request, project_id, "read_term", {"term_id": str(term_id)})

    @router.patch(cw + "/search-terms/{term_id}")
    def edit(request: Request, project_id: UUID, term_id: UUID, body: dict[str, Any]) -> Any:
        if "term_id" in body:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(request, project_id, "edit_term", {**body, "term_id": str(term_id)}, True)

    @router.delete(cw + "/search-terms/{term_id}", status_code=204)
    def delete(
        request: Request, project_id: UUID, term_id: UUID, expected_revision: str | None = None
    ) -> Response:
        if set(request.query_params) - {"expected_revision"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        call(
            request,
            project_id,
            "delete_term",
            {"term_id": str(term_id), "expected_revision": expected_revision},
            True,
        )
        return Response(status_code=204)

    @router.post(cw + "/search-terms/{term_id}/confirm")
    def confirm(request: Request, project_id: UUID, term_id: UUID, body: dict[str, Any]) -> Any:
        if set(body) - {"expected_revision", "confirmation_token", "acknowledged_risk_ids"}:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request, project_id, "confirm_term", {**body, "term_id": str(term_id)}, True, True
        )

    @router.post(cw + "/search-terms/{term_id}/discard")
    def discard(request: Request, project_id: UUID, term_id: UUID, body: dict[str, Any]) -> Any:
        if set(body) - {"expected_revision"}:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request, project_id, "discard_term", {**body, "term_id": str(term_id)}, True, True
        )

    @router.get("/material-policy")
    def policy(request: Request, project_id: UUID) -> Any:
        return call(request, project_id, "policy")

    @router.put("/material-policy")
    def set_policy(request: Request, project_id: UUID, body: dict[str, Any]) -> Any:
        return call(request, project_id, "set_policy", body, True)

    @router.get("/material-sources/{source_id}/classification")
    def classification(request: Request, project_id: UUID, source_id: UUID) -> Any:
        return call(request, project_id, "classification", {"source_id": str(source_id)})

    @router.post("/material-sources/{source_id}/classification/confirm")
    def classify(request: Request, project_id: UUID, source_id: UUID, body: dict[str, Any]) -> Any:
        if "source_id" in body:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request, project_id, "classify", {**body, "source_id": str(source_id)}, True, True
        )

    @router.post("/material-sources/{source_id}/classification/correct")
    def correct(request: Request, project_id: UUID, source_id: UUID, body: dict[str, Any]) -> Any:
        if "source_id" in body:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request,
            project_id,
            "correct_classification",
            {**body, "source_id": str(source_id)},
            True,
            True,
        )

    return router
