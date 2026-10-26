"""Operational probes only; these are not P0 business API contracts."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    # No storage, authentication or task execution is wired yet.
    return JSONResponse(status_code=503, content={"status": "not_ready"})
