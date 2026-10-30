"""Manual Construction retrieval HTTP boundary."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response

from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.construction.application.terms import TermService


def router_for(service: TermService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}/construction-runs")

    def call(
        request: Request, project_id: UUID, operation: str, data: Any = None, write: bool = False
    ) -> Any:
        value = service.call(
            operation,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            str(project_id),
            {**(data or {}), **({"_request_id": request.state.request_id} if write else {})},
            request.headers.get("idempotency-key"),
            write,
            request.headers.get("x-expected-actor"),
        )
        meta = {"request_id": request.state.request_id}
        if write and operation not in {"preview_score", "preview_analysis"}:
            meta["idempotency_expires_at"] = value["expires_at"]
            if value["original_request_id"] != request.state.request_id:
                meta["original_request_id"] = value["original_request_id"]
            value = value["value"]
        if operation in {"list_runs", "candidates", "input_revisions"}:
            cursor = value.pop("next_cursor")
            meta.update(next_cursor=cursor, has_more=cursor is not None)
        return {"data": value, "meta": meta}

    @router.get("")
    def listing(
        request: Request, project_id: UUID, page_size: int = 20, cursor: str | None = None
    ) -> Any:
        if set(request.query_params) - {"page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        return call(request, project_id, "list_runs", {"page_size": page_size, "cursor": cursor})

    @router.post("", status_code=202)
    def start(request: Request, response: Response, project_id: UUID, body: dict[str, Any]) -> Any:
        value = call(request, project_id, "start", body, True)
        response.headers["Location"] = value["data"]["task"]["status_url"]
        return value

    @router.get("/{run_id}")
    def read(request: Request, project_id: UUID, run_id: UUID) -> Any:
        return call(request, project_id, "read_run", {"run_id": str(run_id)})

    @router.get("/{run_id}/candidates")
    def candidates(
        request: Request,
        project_id: UUID,
        run_id: UUID,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> Any:
        if set(request.query_params) - {"page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        return call(
            request,
            project_id,
            "candidates",
            {"run_id": str(run_id), "page_size": page_size, "cursor": cursor},
        )

    @router.get("/{run_id}/candidates/{candidate_id}/processing-text")
    def processing_text(
        request: Request, response: Response, project_id: UUID, run_id: UUID, candidate_id: UUID
    ) -> Any:
        if request.query_params:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        response.headers["Cache-Control"] = "no-store"
        return call(
            request,
            project_id,
            "processing_text",
            {"run_id": str(run_id), "candidate_id": str(candidate_id)},
        )

    @router.get("/{run_id}/candidates/{candidate_id}/file-access")
    def file_access(
        request: Request,
        project_id: UUID,
        run_id: UUID,
        candidate_id: UUID,
        document_asset_id: UUID,
    ) -> Any:
        if set(request.query_params) != {"document_asset_id"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        return call(
            request,
            project_id,
            "file_access",
            {
                "run_id": str(run_id),
                "candidate_id": str(candidate_id),
                "document_id": str(document_asset_id),
            },
        )

    @router.get("/{run_id}/candidates/{candidate_id}/files/{document_id}/download")
    def file_download(
        request: Request, project_id: UUID, run_id: UUID, candidate_id: UUID, document_id: UUID
    ) -> Response:
        if request.query_params:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        value = call(
            request,
            project_id,
            "file_download",
            {
                "run_id": str(run_id),
                "candidate_id": str(candidate_id),
                "document_id": str(document_id),
            },
        )
        return Response(
            content=value["data"],
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="paper.pdf"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/{run_id}/input-revisions")
    def inputs(
        request: Request,
        project_id: UUID,
        run_id: UUID,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> Any:
        if set(request.query_params) - {"page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        return call(
            request,
            project_id,
            "input_revisions",
            {"run_id": str(run_id), "page_size": page_size, "cursor": cursor},
        )

    @router.post("/{run_id}/cancel")
    def cancel(request: Request, project_id: UUID, run_id: UUID, body: dict[str, Any]) -> Any:
        if "run_id" in body:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(request, project_id, "cancel", {**body, "run_id": str(run_id)}, True)

    @router.post("/{run_id}/waiting-items/{waiting_item_id}/confirm")
    def confirm(
        request: Request,
        project_id: UUID,
        run_id: UUID,
        waiting_item_id: UUID,
        body: dict[str, Any],
    ) -> Any:
        if {"run_id", "waiting_item_id"} & body.keys():
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request,
            project_id,
            "confirm_retrieval",
            {**body, "run_id": str(run_id), "waiting_item_id": str(waiting_item_id)},
            True,
        )

    @router.post("/{run_id}/candidates/{candidate_id}/deduplication-decision")
    def correct(
        request: Request, project_id: UUID, run_id: UUID, candidate_id: UUID, body: dict[str, Any]
    ) -> Any:
        if {"run_id", "candidate_id"} & body.keys():
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request,
            project_id,
            "correct_deduplication",
            {**body, "run_id": str(run_id), "candidate_id": str(candidate_id)},
            True,
        )

    @router.post("/{run_id}/screening/action-preview")
    def score_preview(
        request: Request, project_id: UUID, run_id: UUID, body: dict[str, Any]
    ) -> Any:
        if "run_id" in body:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(request, project_id, "preview_score", {**body, "run_id": str(run_id)}, True)

    @router.post("/{run_id}/screening/score", status_code=202)
    def score(
        request: Request, response: Response, project_id: UUID, run_id: UUID, body: dict[str, Any]
    ) -> Any:
        if "run_id" in body:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        value = call(request, project_id, "score", {**body, "run_id": str(run_id)}, True)
        response.headers["Location"] = value["data"]["status_url"]
        return value

    @router.post("/{run_id}/candidates/{candidate_id}/analysis/action-preview")
    def analysis_preview(
        request: Request, project_id: UUID, run_id: UUID, candidate_id: UUID, body: dict[str, Any]
    ) -> Any:
        if {"run_id", "candidate_id"} & body.keys():
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request,
            project_id,
            "preview_analysis",
            {**body, "run_id": str(run_id), "candidate_id": str(candidate_id)},
            True,
        )

    @router.post("/{run_id}/candidates/{candidate_id}/analysis/generate", status_code=202)
    def analysis_generate(
        request: Request,
        response: Response,
        project_id: UUID,
        run_id: UUID,
        candidate_id: UUID,
        body: dict[str, Any],
    ) -> Any:
        if {"run_id", "candidate_id"} & body.keys():
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        value = call(
            request,
            project_id,
            "generate_analysis",
            {**body, "run_id": str(run_id), "candidate_id": str(candidate_id)},
            True,
        )
        response.headers["Location"] = value["data"]["status_url"]
        return value

    @router.patch("/{run_id}/candidates/{candidate_id}")
    def edit_candidate(
        request: Request, project_id: UUID, run_id: UUID, candidate_id: UUID, body: dict[str, Any]
    ) -> Any:
        if {"run_id", "candidate_id"} & body.keys():
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        return call(
            request,
            project_id,
            "edit_candidate",
            {**body, "run_id": str(run_id), "candidate_id": str(candidate_id)},
            True,
        )

    return router
