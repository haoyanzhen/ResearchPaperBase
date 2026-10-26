"""Transactional account authentication. No implicit engine/environment configuration."""

import hashlib
import hmac
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from rpb.adapters.account import accounts
from rpb.adapters.project import metadata as metadata
from rpb.modules.account_config.application.ports import AccountError

sessions = sa.Table(
    "auth_sessions",
    metadata,
    sa.Column("token_hash", sa.String(64), primary_key=True),
    sa.Column("csrf_hash", sa.String(64), nullable=False),
    sa.Column("account_id", sa.Uuid, sa.ForeignKey("accounts.id", name="fk_sessions_account")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),
)
sa.Index("ix_sessions_account", sessions.c.account_id)
# Every future account-governance writer must acquire this same transaction lock.
ACCOUNT_GOVERNANCE_LOCK = 710001


def key(value: str) -> str:
    return value.strip().casefold()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(
        password.encode(), salt=salt, n=2**15, r=8, p=3, dklen=32, maxmem=64 * 1024 * 1024
    )
    return f"scrypt$32768$8$3${salt.hex()}${hashed.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        kind, n, r, p, salt, expected = encoded.split("$")
        if (kind, n, r, p) != ("scrypt", "32768", "8", "3"):
            return False
        actual = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=32768,
            r=8,
            p=3,
            dklen=32,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual.hex(), expected)
    except ValueError, TypeError:
        return False


class AccountStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.dummy_hash = hash_password("not-a-real-account-password")

    @contextmanager
    def _transaction(self, token: str | None) -> Iterator[Connection]:
        try:
            with self.engine.begin() as conn:
                yield conn
        except AccountError as exc:
            if exc.code == "AUTH_ACCOUNT_DISABLED" and token and exc.affected_account_id:
                # Persist revocation after the rejected operation rolls back. Re-enabling
                # the account must never resurrect this already-invalidated credential.
                with self.engine.begin() as conn:
                    conn.execute(
                        sessions.update()
                        .where(
                            sessions.c.token_hash == digest(token),
                            sessions.c.account_id == exc.affected_account_id,
                        )
                        .values(revoked=True)
                    )
            raise

    @contextmanager
    def authorized_connection(
        self, token: str, csrf: str | None
    ) -> Iterator[tuple[Connection, UUID]]:
        """Account-owned authorization for a composed application transaction."""
        with self._transaction(token) as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            session = self._session(conn, token, csrf)
            if session["account_id"] is None:
                raise AccountError("AUTH_REQUIRED", 401)
            self._user(conn, session["account_id"])
            yield conn, session["account_id"]

    def _session(self, conn: Connection, token: str, csrf: str | None = None) -> dict[str, Any]:
        row = (
            conn.execute(
                sa.select(sessions).where(sessions.c.token_hash == digest(token)).with_for_update()
            )
            .mappings()
            .first()
        )
        if not row or row["revoked"] or row["expires_at"] <= datetime.now(UTC):
            raise AccountError("AUTH_SESSION_INVALID", 401)
        if csrf is not None and not hmac.compare_digest(row["csrf_hash"], digest(csrf)):
            raise AccountError("PERMISSION_CSRF_REJECTED", 403)
        return dict(row)

    def _new_session(self, conn: Connection, account_id: UUID | None) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        conn.execute(
            sessions.insert().values(
                token_hash=digest(token),
                csrf_hash=digest(csrf),
                account_id=account_id,
                created_at=now,
                expires_at=now + (timedelta(hours=24) if account_id else timedelta(minutes=30)),
            )
        )
        return token, csrf

    def _user(self, conn: Connection, account_id: UUID) -> dict[str, Any]:
        row = (
            conn.execute(sa.select(accounts).where(accounts.c.id == account_id)).mappings().first()
        )
        if not row:
            raise AccountError("AUTH_SESSION_INVALID", 401)
        if not row["enabled"]:
            raise AccountError("AUTH_ACCOUNT_DISABLED", 401, account_id)
        result = {
            name: row[name]
            for name in (
                "id",
                "revision",
                "created_at",
                "updated_at",
                "username",
                "email",
                "enabled",
                "is_admin",
            )
        }
        result["display_name"] = row["display_name"]
        result["last_login_at"] = conn.scalar(
            sa.select(sa.func.max(sessions.c.created_at)).where(sessions.c.account_id == account_id)
        )
        return result

    def csrf(self, token: str | None) -> tuple[str, str]:
        with self._transaction(token) as conn:
            if token:
                row = (
                    conn.execute(
                        sa.select(sessions)
                        .where(sessions.c.token_hash == digest(token))
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if row and not row["revoked"] and row["expires_at"] > datetime.now(UTC):
                    if row["account_id"]:
                        self._user(conn, row["account_id"])
                    csrf = secrets.token_urlsafe(32)
                    conn.execute(
                        sessions.update()
                        .where(sessions.c.token_hash == digest(token))
                        .values(csrf_hash=digest(csrf))
                    )
                    return token, csrf
            return self._new_session(conn, None)

    def register(
        self, token: str, csrf: str, username: str, email: str, password: str
    ) -> dict[str, Any]:
        hashed = hash_password(password)
        with self._transaction(token) as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            self._session(conn, token, csrf)
            keys = {key(username), key(email)}
            if conn.scalar(
                sa.select(
                    sa.exists().where(
                        sa.or_(accounts.c.username_key.in_(keys), accounts.c.email_key.in_(keys))
                    )
                )
            ):
                raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            first = not conn.scalar(sa.select(sa.exists().select_from(accounts)))
            identity = conn.scalar(
                accounts.insert()
                .values(
                    username=username,
                    email=email,
                    username_key=key(username),
                    email_key=key(email),
                    password_hash=hashed,
                    enabled=True,
                    is_admin=first,
                )
                .returning(accounts.c.id)
            )
            assert identity is not None
            return self._user(conn, identity)

    def login(
        self, token: str, csrf: str, identifier: str, password: str
    ) -> tuple[dict[str, Any], str]:
        # KDF work precedes the transaction. Recheck the exact hash under the governance lock.
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    sa.select(accounts).where(
                        sa.or_(
                            accounts.c.username_key == key(identifier),
                            accounts.c.email_key == key(identifier),
                        )
                    )
                )
                .mappings()
                .first()
            )
        valid = password_matches(password, row["password_hash"] if row else self.dummy_hash)
        with self._transaction(token) as conn:
            conn.execute(
                sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": ACCOUNT_GOVERNANCE_LOCK}
            )
            self._session(conn, token, csrf)
            if not row or not valid:
                raise AccountError("AUTH_INVALID_CREDENTIALS", 401)
            current = (
                conn.execute(sa.select(accounts).where(accounts.c.id == row["id"]))
                .mappings()
                .first()
            )
            if (
                not current
                or current["password_hash"] != row["password_hash"]
                or key(identifier) not in {current["username_key"], current["email_key"]}
            ):
                raise AccountError("AUTH_INVALID_CREDENTIALS", 401)
            self._user(conn, row["id"])
            conn.execute(
                sessions.update().where(sessions.c.token_hash == digest(token)).values(revoked=True)
            )
            new_token, _ = self._new_session(conn, row["id"])
            return self._user(conn, row["id"]), new_token

    def logout(self, token: str, csrf: str) -> None:
        with self._transaction(token) as conn:
            row = self._session(conn, token, csrf)
            if row["account_id"] is None:
                raise AccountError("AUTH_REQUIRED", 401)
            self._user(conn, row["account_id"])
            conn.execute(
                sessions.update().where(sessions.c.token_hash == digest(token)).values(revoked=True)
            )

    def read_self(self, token: str) -> dict[str, Any]:
        with self._transaction(token) as conn:
            row = self._session(conn, token)
            if row["account_id"] is None:
                raise AccountError("AUTH_REQUIRED", 401)
            return self._user(conn, row["account_id"])

    def update_self(
        self, token: str, csrf: str, revision: str | None, changes: dict[str, Any]
    ) -> dict[str, Any]:
        with self.authorized_connection(token, csrf) as (conn, actor):
            current = self._user(conn, actor)
            if revision is None:
                raise AccountError("STATE_REVISION_REQUIRED", 428)
            if revision != str(current["revision"]):
                raise AccountError("STATE_REVISION_CONFLICT", 412)
            if "email" in changes:
                normalized = key(changes["email"])
                if conn.scalar(
                    sa.select(
                        sa.exists().where(
                            accounts.c.id != actor,
                            sa.or_(
                                accounts.c.username_key == normalized,
                                accounts.c.email_key == normalized,
                            ),
                        )
                    )
                ):
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
            values = {k: v for k, v in changes.items() if current[k] != v}
            if values:
                if "email" in values:
                    values["email_key"] = key(values["email"])
                conn.execute(
                    accounts.update()
                    .where(accounts.c.id == actor)
                    .values(**values, revision=uuid4(), updated_at=datetime.now(UTC))
                )
            return self._user(conn, actor)
