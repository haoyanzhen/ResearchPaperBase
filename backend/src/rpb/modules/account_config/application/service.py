"""Account request boundary; credentials are never represented in public results."""

from typing import Any

from rpb.modules.account_config.application.ports import AccountError, AccountPort


class AccountService:
    def __init__(self, store: AccountPort, origin: str) -> None:
        self.store, self.origin = store, origin

    def verify_origin(self, origin: str | None) -> None:
        if origin != self.origin:
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)

    def register(
        self, token: str, csrf: str, username: str, email: str, password: str
    ) -> dict[str, Any]:
        return self.store.register(token, csrf, username, email, password)

    def login(
        self, token: str, csrf: str, identifier: str, password: str
    ) -> tuple[dict[str, Any], str]:
        return self.store.login(token, csrf, identifier, password)
