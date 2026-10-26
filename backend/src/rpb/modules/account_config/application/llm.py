"""LLM configuration boundary and typed adapter port."""

from contextlib import AbstractContextManager
from typing import Any, Protocol

from rpb.modules.account_config.application.ports import AccountError


class LLMPort(Protocol):
    def event_lease(
        self, token: str, expected_actor: str | None = None
    ) -> AbstractContextManager[None]: ...

    def invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None = None,
    ) -> Any: ...


class LLMService:
    def __init__(self, store: LLMPort, origin: str) -> None:
        self.store, self.origin = store, origin

    def call(
        self,
        operation: str,
        token: str,
        origin: str | None,
        csrf: str | None,
        target: str | None = None,
        data: dict[str, Any] | None = None,
        key: str | None = None,
        write: bool = False,
        expected_actor: str | None = None,
    ) -> Any:
        if not token:
            raise AccountError("AUTH_REQUIRED", 401)
        if write and (origin != self.origin or not csrf):
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        return self.store.invoke(
            operation, token, csrf if write else None, target, data or {}, key, expected_actor
        )
