"""Construction command boundary; HTTP and persistence are injected."""

from typing import Any, Protocol

from rpb.modules.account_config.application.ports import AccountError


class TermPort(Protocol):
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


class TermService:
    def __init__(self, store: TermPort, origin: str) -> None:
        self.store, self.origin = store, origin

    def call(
        self,
        operation: str,
        token: str,
        origin: str | None,
        csrf: str | None,
        project_id: str,
        data: dict[str, Any],
        key: str | None,
        write: bool,
        actor: str | None,
    ) -> Any:
        if not token:
            raise AccountError("AUTH_REQUIRED", 401)
        if write and (origin != self.origin or not csrf):
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        return self.store.invoke(
            operation, token, csrf if write else None, project_id, data, key, actor
        )
