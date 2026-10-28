"""Platform SMTP singleton and one-use OAuth handshakes."""

import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import sqlalchemy as sa
from cryptography.fernet import InvalidToken
from sqlalchemy.engine import Connection

from rpb.adapters import smtp_tables as tables
from rpb.adapters.auth import AccountStore, digest
from rpb.adapters.llm import event_record, require_revision
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.smtp_provider import OAuthProvider, endpoints
from rpb.adapters.sources import SourceStore
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.domain.smtp import SMTPError, validate

SMTP_ID = UUID("b9650192-4898-5cca-b4f9-9b10e2b28f57")


class SMTPStore(SourceStore):
    def __init__(
        self,
        account: AccountStore,
        encryption_key: bytes | None = None,
        origin: str = "http://localhost",
        oauth: OAuthProvider | None = None,
    ) -> None:
        super().__init__(account, encryption_key, system=True)
        self.configs, self.tasks, self.commands, self.audit = (
            tables.configs,
            tables.tasks,
            tables.commands,
            tables.audit,
        )
        self.origin, self.oauth = origin, oauth or OAuthProvider()

    @property
    def redirect_uri(self) -> str:
        return self.origin + "/api/v1/admin/smtp-config/oauth/callback"

    def singleton(self, conn: Connection, actor: UUID) -> dict[str, Any]:
        row = (
            conn.execute(sa.select(self.configs).where(self.configs.c.id == SMTP_ID))
            .mappings()
            .first()
        )
        if row is None:
            now = datetime.now(UTC)
            conn.execute(
                self.configs.insert().values(
                    id=SMTP_ID,
                    owner_id=actor,
                    revision=uuid4(),
                    credential_revision=uuid4(),
                    data={},
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.config(conn, actor, str(SMTP_ID))

    def encrypt(self, value: dict[str, Any]) -> bytes:
        if self.cipher is None:
            raise AccountError("CONFIG_SECRET_UNAVAILABLE", 409)
        return self.cipher.encrypt(json.dumps(value).encode())

    def decrypt(self, value: bytes | None) -> dict[str, Any]:
        if self.cipher is None or value is None:
            raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
        try:
            result = json.loads(self.cipher.decrypt(value))
            if not isinstance(result, dict):
                raise ValueError("Invalid material")
            return result
        except InvalidToken, ValueError, UnicodeError:
            raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE") from None

    def secret(self, row: dict[str, Any]) -> str:
        if row["data"]["auth_type"] == "none":
            return ""
        if self.cipher is None or row["secret_ciphertext"] is None:
            raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
        try:
            return self.cipher.decrypt(row["secret_ciphertext"]).decode()
        except InvalidToken, UnicodeError:
            raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE") from None

    def view(self, conn: Connection, actor: UUID, row: dict[str, Any]) -> dict[str, Any]:
        if not row["configured"]:
            return {"revision": str(row["revision"]), "configured": False, "config": None}
        source = super().view(conn, actor, row)
        data = dict(row["data"])
        if data["oauth"] is not None:
            data["oauth"] = {
                **data["oauth"],
                "client_secret": {"configured": row["secret_ciphertext"] is not None, "hint": None},
            }
        return {
            "revision": str(row["revision"]),
            "configured": True,
            "config": {
                **data,
                "secret": {
                    "configured": bool(
                        row["oauth_ciphertext"]
                        if data["auth_type"] == "token"
                        else row["secret_ciphertext"]
                    ),
                    "hint": None,
                },
                "oauth_status": row["oauth_status"],
                "connection_status": source["connection_status"],
                "last_test_at": source["last_test_at"],
            },
        }

    def task_view(self, row: dict[str, Any]) -> dict[str, Any]:
        value = super().task_view(row)
        value["operation_id"] = "Admin.TestSMTPConnection"
        value["target"] = {"type": "system_smtp_config", "id": str(SMTP_ID)}
        value["target_location"]["read_url"] = "/api/v1/admin/smtp-config"
        return value

    def audit_fact(
        self,
        conn: Connection,
        actor: UUID,
        row: dict[str, Any],
        operation: str,
        secret_operation: str = "keep",
    ) -> None:
        conn.execute(
            self.audit.insert().values(
                id=uuid4(),
                owner_id=actor,
                config_id=SMTP_ID,
                operation=operation,
                secret_operation=secret_operation,
                revision=row["revision"],
                occurred_at=datetime.now(UTC),
            )
        )

    def invoke(
        self,
        operation: str,
        token: str,
        csrf: str | None,
        target: str | None,
        data: dict[str, Any],
        key: str | None,
        expected_actor: str | None = None,
    ) -> Any:
        if operation in {"task", "result", "events"}:
            return super().invoke(operation, token, csrf, target, data, key, expected_actor)
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and expected_actor != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
            if not self.permitted_actor(conn, actor):
                raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
            row = self.singleton(conn, actor)
            if operation == "read":
                return self.view(conn, actor, row)
            now = datetime.now(UTC)
            fingerprint = hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if operation in {"test", "oauth_start"}:
                if (
                    not key
                    or not 16 <= len(key) <= 128
                    or not all(32 <= ord(c) <= 126 for c in key)
                ):
                    raise AccountError("VALIDATION_BAD_REQUEST", 400)
                previous = (
                    conn.execute(
                        sa.select(self.commands).where(
                            self.commands.c.owner_id == actor,
                            self.commands.c.operation == operation,
                            self.commands.c.target == str(SMTP_ID),
                            self.commands.c.key == key,
                        )
                    )
                    .mappings()
                    .first()
                )
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                    if operation == "test":
                        return self.task_view(self.task(conn, actor, previous["result"]["task_id"]))
                    return previous["result"]
            if operation == "save":
                require_revision(row["revision"], data.get("expected_revision"))
                try:
                    values = validate(data)
                except SMTPError as exc:
                    raise AccountError(exc.code, 422) from None
                binding = (
                    "provider",
                    "server",
                    "port",
                    "encryption",
                    "auth_type",
                    "username",
                    "oauth",
                )
                same_binding = all(row["data"].get(k) == values.get(k) for k in binding)
                change = (
                    data.get("oauth", {}).get("client_secret")
                    if values["auth_type"] == "token"
                    else data.get("secret")
                )
                if values["auth_type"] == "token" and data.get("secret") is not None:
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                if ("secret" in data and data["secret"] is None) or (
                    values["auth_type"] == "token"
                    and "client_secret" in data["oauth"]
                    and data["oauth"]["client_secret"] is None
                ):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                previous_secret = row["secret_ciphertext"] if same_binding else None
                secret, changed = self._secret(change, previous_secret)
                if values["auth_type"] == "none":
                    if data.get("secret") is not None:
                        raise AccountError("VALIDATION_FIELD_INVALID", 422)
                    secret = None
                changed = changed or row["secret_ciphertext"] != secret
                if values == row["data"] and not changed and row["configured"]:
                    return self.view(conn, actor, row)
                clear_grant = not same_binding or changed
                updates = {
                    "data": values,
                    "secret_ciphertext": secret,
                    "configured": True,
                    "revision": uuid4(),
                    "credential_revision": uuid4() if clear_grant else row["credential_revision"],
                    "updated_at": now,
                }
                if clear_grant:
                    updates.update(
                        oauth_ciphertext=None,
                        oauth_status="not_connected",
                        refresh_task_id=None,
                        refresh_attempt_id=None,
                    )
                conn.execute(
                    self.configs.update().where(self.configs.c.id == SMTP_ID).values(**updates)
                )
                row = self.config(conn, actor, str(SMTP_ID))
                self.audit_fact(conn, actor, row, "save", (change or {}).get("operation", "keep"))
                return self.view(conn, actor, row)
            if not row["configured"]:
                raise AccountError("CONFIG_CONNECTION_FAILED", 409)
            if operation == "test":
                identity, revision = uuid4(), uuid4()
                conn.execute(
                    self.tasks.insert().values(
                        id=identity,
                        owner_id=actor,
                        config_id=SMTP_ID,
                        revision=revision,
                        credential_revision=row["credential_revision"],
                        config_revision=row["revision"],
                        attempt_id=uuid4(),
                        operation="test",
                        input=row["data"],
                        state="queued",
                        created_at=now,
                        events=[event_record("queued", revision, now)],
                    )
                )
                result = self.task_view(self.task(conn, actor, str(identity)))
            elif operation == "oauth_start":
                require_revision(row["revision"], data.get("expected_revision"))
                if set(data) != {"expected_revision"} or row["data"]["auth_type"] != "token":
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                try:
                    self.secret(row)
                except ProviderFailure:
                    raise AccountError("CONFIG_SECRET_UNAVAILABLE", 409) from None
                state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
                expires = now + timedelta(minutes=10)
                conn.execute(
                    tables.handshakes.insert().values(
                        state_hash=digest(state),
                        owner_id=actor,
                        session_hash=digest(token),
                        config_revision=row["revision"],
                        credential_revision=row["credential_revision"],
                        verifier_ciphertext=self.encrypt({"verifier": verifier}),
                        expires_at=expires,
                    )
                )
                url, _, scope = endpoints(row["data"])
                query = {
                    "client_id": row["data"]["oauth"]["client_id"],
                    "redirect_uri": self.redirect_uri,
                    "response_type": "code",
                    "scope": scope,
                    "state": state,
                    "code_challenge": base64.urlsafe_b64encode(
                        hashlib.sha256(verifier.encode()).digest()
                    )
                    .decode()
                    .rstrip("="),
                    "code_challenge_method": "S256",
                    "prompt": "consent",
                    "login_hint": row["data"]["username"],
                }
                if row["data"]["provider"] == "gmail":
                    query["access_type"] = "offline"
                result = {
                    "authorization_url": url + "?" + urlencode(query),
                    "expires_at": expires.isoformat().replace("+00:00", "Z"),
                }
                self.audit_fact(conn, actor, row, "oauth_start")
            else:
                raise AccountError("VALIDATION_FIELD_INVALID", 422)
            conn.execute(
                self.commands.insert().values(
                    owner_id=actor,
                    operation=operation,
                    target=str(SMTP_ID),
                    key=key,
                    fingerprint=fingerprint,
                    config_id=SMTP_ID,
                    result=result,
                    expires_at=now + timedelta(hours=48),
                )
            )
            return result

    def callback(self, token: str, state: str, code: str | None, denied: bool = False) -> bool:
        # Consume state in its own transaction, before attempting token exchange.
        with self.account.authorized_connection(token, None) as (conn, actor):
            handshake = (
                conn.execute(
                    sa.select(tables.handshakes)
                    .where(tables.handshakes.c.state_hash == digest(state))
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            row = self.singleton(conn, actor)
            if (
                not self.permitted_actor(conn, actor)
                or not handshake
                or handshake["used"]
                or handshake["owner_id"] != actor
                or handshake["session_hash"] != digest(token)
                or handshake["expires_at"] <= datetime.now(UTC)
                or handshake["config_revision"] != row["revision"]
                or handshake["credential_revision"] != row["credential_revision"]
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            conn.execute(
                tables.handshakes.update()
                .where(tables.handshakes.c.state_hash == digest(state))
                .values(used=True)
            )
            try:
                verifier = self.decrypt(handshake["verifier_ciphertext"])["verifier"]
            except ProviderFailure:
                return False
            revision = row["revision"]
        if denied or not code or len(code) > 8192:
            return False
        try:
            # Current authorization and binding remain locked through exchange/commit.
            with self.account.authorized_connection(token, None) as (conn, actor):
                row = self.config(conn, actor, str(SMTP_ID))
                if (
                    not self.permitted_actor(conn, actor)
                    or row["revision"] != revision
                    or row["credential_revision"] != handshake["credential_revision"]
                ):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                result = self.oauth.exchange(
                    row["data"],
                    self.secret(row),
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                        "code_verifier": verifier,
                    },
                )
                if not result.get("refresh_token"):
                    raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
                self.save_grant(conn, actor, row, result)
            return True
        except ProviderFailure:
            return False

    def save_grant(
        self,
        conn: Connection,
        actor: UUID,
        row: dict[str, Any],
        result: dict[str, Any],
        previous: dict[str, Any] | None = None,
    ) -> None:
        grant = {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token") or (previous or {}).get("refresh_token"),
            "expires_at": (datetime.now(UTC) + timedelta(seconds=result["expires_in"])).isoformat(),
        }
        if not grant["refresh_token"]:
            raise ProviderFailure("CONFIG_SECRET_UNAVAILABLE")
        conn.execute(
            self.configs.update()
            .where(self.configs.c.id == SMTP_ID)
            .values(
                oauth_ciphertext=self.encrypt(grant),
                oauth_status="connected",
                refresh_task_id=None,
                refresh_attempt_id=None,
                credential_revision=uuid4(),
                updated_at=datetime.now(UTC),
            )
        )
        self.audit_fact(conn, actor, row, "oauth_credentials", "set")
