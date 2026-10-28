"""Administrator transport boundary; authorization remains transactional in the port."""

from typing import Any, Protocol

from rpb.modules.account_config.application.ports import AccountError


class AdminPort(Protocol):
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


class AdminService:
    def __init__(self, store: AdminPort, origin: str) -> None:
        self.store, self.origin = store, origin

    def call(
        self,
        operation: str,
        token: str,
        origin: str | None,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None,
    ) -> Any:
        if not token:
            raise AccountError("AUTH_REQUIRED", 401)
        if operation != "list" and (origin != self.origin or not csrf):
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        return self.store.invoke(
            operation,
            token,
            csrf if operation != "list" else None,
            target,
            data,
            key,
            expected_actor,
        )
