"""Private LLM configuration transport and authorized durable task reads."""

import asyncio
import json
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from anyio import CancelScope
from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from rpb.modules.account_config.application.llm import LLMService
from rpb.modules.account_config.application.ports import AccountError


class LeasedStreamingResponse(StreamingResponse):
    def __init__(self, content: Any, lease: AbstractContextManager[None]) -> None:
        super().__init__(
            content, media_type="text/event-stream", headers={"Cache-Control": "no-store"}
        )
        self.lease = lease

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await run_in_threadpool(self.lease.__exit__, None, None, None)


class LLMWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    provider: str
    base_url: str
    protocol: str | None = None
    api_version: str | None = None
    parameters: dict[str, Any] | None = None
    timeout_seconds: int | None = None
    model_context_windows: dict[str, Any] | None = None
    secret: dict[str, Any] | None = None


class LLMPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    protocol: str | None = None
    api_version: str | None = None
    parameters: dict[str, Any] | None = None
    timeout_seconds: int | None = None
    model_context_windows: dict[str, Any] | None = None
    secret: dict[str, Any] | None = None


class ModelTest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model_id: Annotated[str, Field(min_length=1, max_length=200)]


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: Annotated[str | None, Field(min_length=1, max_length=128)] = None
    selection: dict[str, str] | None


def router_for(service: LLMService, *, system: bool = False) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    config_path = "/admin/llm-configs" if system else "/me/llm-configs"

    def call(
        request: Request,
        op: str,
        target: str | None = None,
        data: dict[str, Any] | None = None,
        write: bool = False,
    ) -> Any:
        return service.call(
            op,
            request.cookies.get("rpb_session", ""),
            request.headers.get("origin"),
            request.headers.get("x-csrf-token"),
            target,
            data,
            request.headers.get("idempotency-key"),
            write,
            request.headers.get("x-expected-actor"),
        )

    def env(request: Request, data: Any, idempotent: bool = False) -> dict[str, Any]:
        meta = {"request_id": request.state.request_id}
        if idempotent:
            meta["idempotency_expires_at"] = None
        return {"data": data, "meta": meta}

    @router.get(config_path)
    def listing(
        request: Request,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> Any:
        page = call(request, "list", data={"page_size": page_size, "cursor": cursor})
        result = env(request, {"items": page["items"]})
        result["meta"].update(next_cursor=page["next_cursor"], has_more=page["has_more"])
        return result

    @router.post(config_path, status_code=201)
    def create(request: Request, response: Response, body: LLMWrite) -> Any:
        values = body.model_dump(exclude_unset=True)
        if any(value is None for value in values.values()):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        data = call(request, "create", data=values, write=True)
        response.headers["Location"] = "/api/v1" + config_path + "/" + data["id"]
        result = env(request, data, True)
        result["meta"]["idempotency_expires_at"] = (
            (datetime.fromisoformat(data["created_at"]) + timedelta(hours=48))
            .isoformat()
            .replace("+00:00", "Z")
        )
        return result

    @router.get(config_path + "/{config_id}")
    def read(request: Request, config_id: str) -> Any:
        return env(request, call(request, "read", config_id))

    @router.patch(config_path + "/{config_id}")
    def update(request: Request, config_id: str, body: LLMPatch) -> Any:
        data = body.model_dump(exclude_unset=True)
        if any(value is None for value in data.values()):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        return env(request, call(request, "update", config_id, data, True))

    @router.delete(config_path + "/{config_id}", status_code=204)
    def delete(request: Request, config_id: str, expected_revision: str | None = None) -> Response:
        call(request, "delete", config_id, {"expected_revision": expected_revision}, True)
        return Response(status_code=204)

    @router.post(config_path + "/{config_id}/test", status_code=202)
    def test(request: Request, response: Response, config_id: str, body: ModelTest) -> Any:
        data = call(request, "test", config_id, body.model_dump(), True)
        response.headers["Location"] = data["status_url"]
        return env(request, data, True)

    @router.post(config_path + "/{config_id}/models/refresh", status_code=202)
    def refresh(request: Request, response: Response, config_id: str, body: Empty) -> Any:
        data = call(request, "refresh", config_id, {}, True)
        response.headers["Location"] = data["status_url"]
        return env(request, data, True)

    if system:
        return router

    @router.get("/me/model-options")
    def options(request: Request) -> Any:
        return env(request, call(request, "options"))

    @router.get("/me/model-selection")
    def selection(request: Request) -> Any:
        return env(request, call(request, "selection"))

    @router.put("/me/model-selection")
    def select(request: Request, body: Selection) -> Any:
        return env(request, call(request, "select", data=body.model_dump(), write=True))

    @router.get("/tasks/{task_id}")
    def task(request: Request, task_id: str) -> Any:
        return env(request, call(request, "task", task_id))

    @router.get("/tasks/{task_id}/result")
    def result(request: Request, task_id: str) -> Any:
        return env(request, call(request, "result", task_id))

    @router.get("/tasks/{task_id}/events")
    async def events(
        request: Request,
        task_id: str,
        after_event_id: str | None = None,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        snapshot = await run_in_threadpool(call, request, "events", task_id)
        cursor = last_event_id or after_event_id
        if last_event_id and after_event_id and last_event_id != after_event_id:
            raise AccountError("VALIDATION_CURSOR_MISMATCH", 400)
        position = 0
        if cursor:
            cursors = [item["cursor"] for item in snapshot["events"]]
            if cursor not in cursors:
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            position = cursors.index(cursor) + 1
            if datetime.fromisoformat(
                snapshot["events"][position - 1]["occurred_at"]
            ) < datetime.now(UTC) - timedelta(hours=24):
                raise AccountError(
                    "STATE_EVENT_REPLAY_UNAVAILABLE",
                    409,
                    details={"status_url": "/api/v1/tasks/" + task_id},
                )

        lease = service.store.event_lease(
            request.cookies.get("rpb_session", ""), request.headers.get("x-expected-actor")
        )
        await run_in_threadpool(lease.__enter__)

        async def content() -> Any:
            nonlocal position
            heartbeat = 0
            while not await request.is_disconnected():
                try:
                    current = await run_in_threadpool(call, request, "events", task_id)
                except AccountError:
                    return
                view = current["view"]
                for index, item in enumerate(current["events"][position:], position + 1):
                    state = item["execution_status"]
                    final = state in {"succeeded", "failed", "cancelled"}
                    payload = {
                        "execution_status": state,
                        "stage": view["stage"],
                        "business_state": None,
                    }
                    if final:
                        payload = {
                            "execution_status": state,
                            "result_refs": view["result_refs"],
                        }
                    event = {
                        "event_id": item["cursor"],
                        "sequence": index,
                        "task_id": task_id,
                        "project_id": view["project_id"],
                        "target": view["target"],
                        "attempt_id": view["attempt_id"],
                        "knowledge_version_id": None,
                        "task_revision": item["revision"],
                        "target_revision": None,
                        "occurred_at": item["occurred_at"],
                        "payload": payload,
                    }
                    yield (
                        "id: "
                        + item["cursor"]
                        + "\nevent: "
                        + ("done" if final else "status")
                        + "\ndata: "
                        + json.dumps(event)
                        + "\n\n"
                    )
                    position = index
                if view["execution_status"] in {"succeeded", "failed", "cancelled"}:
                    return
                await asyncio.sleep(1)
                heartbeat += 1
                if heartbeat == 15:
                    yield ": heartbeat\n\n"
                    heartbeat = 0

        return LeasedStreamingResponse(content(), lease)

    return router
