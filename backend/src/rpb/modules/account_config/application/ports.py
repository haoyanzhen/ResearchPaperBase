"""Account transaction port: implementations own one atomic operation per call."""

from typing import Any, Protocol
from uuid import UUID


class AccountError(Exception):
    def __init__(self, code: str, status: int, affected_account_id: UUID | None = None) -> None:
        self.code, self.status = code, status
        self.affected_account_id = affected_account_id
        super().__init__(code)


class AccountPort(Protocol):
    def csrf(self, token: str | None) -> tuple[str, str]: ...
    def register(
        self, token: str, csrf: str, username: str, email: str, password: str
    ) -> dict[str, Any]: ...
    def login(
        self, token: str, csrf: str, identifier: str, password: str
    ) -> tuple[dict[str, Any], str]: ...
    def logout(self, token: str, csrf: str) -> None: ...
    def read_self(self, token: str) -> dict[str, Any]: ...
    def update_self(
        self, token: str, csrf: str, revision: str | None, changes: dict[str, Any]
    ) -> dict[str, Any]: ...
