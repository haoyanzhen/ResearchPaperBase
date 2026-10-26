"""Atomic private configuration, encrypted credentials and durable job records."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import sqlalchemy as sa
from cryptography.fernet import Fernet
from sqlalchemy.engine import Connection

from rpb.adapters.auth import AccountStore
from rpb.adapters.llm_tables import audit, commands, configs, selections, tasks
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.account_config.domain.llm_profiles import compile_for_model
from rpb.modules.account_config.domain.parameters import ParameterError, client_timeout


def event_record(state: str, revision: UUID, now: datetime) -> dict[str, Any]:
    return {
        "execution_status": state,
        "revision": str(revision),
        "occurred_at": now.isoformat().replace("+00:00", "Z"),
        "cursor": str(uuid4()),
    }


def public_error(code: str) -> dict[str, Any]:
    code = {
        "PROVIDER_RATE_LIMITED": "PROVIDER_UNAVAILABLE",
        "PROVIDER_RESPONSE_INVALID": "PROVIDER_FAILED",
        "PROVIDER_RESULT_UNKNOWN": "PROVIDER_FAILED",
    }.get(code, code)
    return {
        "code": code,
        "category": code.split("_")[0].lower(),
        "message": "连接测试未完成，请检查配置或重试。",
        "retryable": False,
        "details": None,
        "recovery": None,
    }


def uuid_value(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError, TypeError, AttributeError:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404) from None


def require_revision(actual: Any, supplied: Any) -> None:
    if supplied is None:
        raise AccountError("STATE_REVISION_REQUIRED", 428)
    if str(actual) != supplied:
        raise AccountError("STATE_REVISION_CONFLICT", 412)


class LLMStore:
    def __init__(self, account: AccountStore, encryption_key: bytes | None = None) -> None:
        self.account = account
        self.cipher = Fernet(encryption_key) if encryption_key else None

    @contextmanager
    def event_lease(self, token: str, expected_actor: str | None = None) -> Iterator[None]:
        with self.account.authorized_connection(token, None) as (_, actor):
            if expected_actor is not None and expected_actor != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
        with self.account.engine.connect() as conn:
            held = None
            try:
                for slot in range(6):
                    key = int.from_bytes(
                        hashlib.sha256(f"llm-sse:{actor}:{slot}".encode()).digest()[:8], signed=True
                    )
                    if conn.scalar(sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": key}):
                        held = key
                        break
                if held is None:
                    raise AccountError("STATE_RESOURCE_LIMIT", 429)
                yield
            finally:
                if held is not None:
                    conn.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": held})

    def config(self, conn: Connection, actor: UUID, identity: str) -> dict[str, Any]:
        row = (
            conn.execute(
                sa.select(configs).where(
                    configs.c.id == uuid_value(identity),
                    configs.c.owner_id == actor,
                    configs.c.deleted.is_(False),
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        return dict(row)

    def task(self, conn: Connection, actor: UUID, identity: str) -> dict[str, Any]:
        row = (
            conn.execute(
                sa.select(tasks).where(
                    tasks.c.id == uuid_value(identity), tasks.c.owner_id == actor
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
        self.config(conn, actor, str(row["config_id"]))
        return dict(row)

    def options(
        self, conn: Connection, actor: UUID, identity: str | None = None
    ) -> list[dict[str, Any]]:
        rows = (
            conn.execute(
                sa.select(configs).where(configs.c.owner_id == actor, configs.c.deleted.is_(False))
            )
            .mappings()
            .all()
        )
        output = []
        for config in rows:
            if identity and str(config["id"]) != identity:
                continue
            latest: dict[str, Any] = {}
            jobs = (
                conn.execute(
                    sa.select(tasks)
                    .where(
                        tasks.c.config_id == config["id"],
                        tasks.c.config_revision == config["revision"],
                        tasks.c.credential_revision == config["credential_revision"],
                        tasks.c.state.in_(["succeeded", "failed"]),
                    )
                    .order_by(tasks.c.created_at, tasks.c.id)
                )
                .mappings()
                .all()
            )
            for job in jobs:
                if job["operation"] == "test":
                    latest[job["model_id"]] = job["state"] == "succeeded"
                elif job["result"]:
                    for name in job["result"].get("discovered_models", []):
                        latest.setdefault(name, False)
            for name, valid in latest.items():
                output.append(
                    {
                        "source": "user",
                        "config_id": str(config["id"]),
                        "model_id": name,
                        "label": config["data"]["name"] + " / " + name,
                        "available": bool(valid and config["secret_ciphertext"]),
                        "unavailable_reason": None
                        if valid and config["secret_ciphertext"]
                        else "CONFIG_CONNECTION_FAILED",
                    }
                )
        return output

    def view(self, conn: Connection, actor: UUID, row: dict[str, Any]) -> dict[str, Any]:
        opts = self.options(conn, actor, str(row["id"]))
        tested = (
            conn.execute(
                sa.select(tasks)
                .where(
                    tasks.c.config_id == row["id"],
                    tasks.c.config_revision == row["revision"],
                    tasks.c.credential_revision == row["credential_revision"],
                    tasks.c.operation == "test",
                    tasks.c.state.in_(["succeeded", "failed"]),
                )
                .order_by(tasks.c.created_at.desc(), tasks.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return {
            "id": str(row["id"]),
            "revision": str(row["revision"]),
            "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
            "updated_at": row["updated_at"].isoformat().replace("+00:00", "Z"),
            **row["data"],
            "secret": {"configured": row["secret_ciphertext"] is not None, "hint": None},
            "connection_status": "available"
            if any(x["available"] for x in opts)
            else "unavailable"
            if tested
            else "untested",
            "last_test_at": tested["finished_at"].isoformat().replace("+00:00", "Z")
            if tested and tested["finished_at"]
            else None,
            "models": opts,
        }

    def task_view(self, row: dict[str, Any]) -> dict[str, Any]:
        identity = str(row["id"])
        base = "/api/v1/tasks/" + identity
        result = (
            []
            if row["result"] is None
            else [{"type": "connection_test", "id": identity, "url": base + "/result"}]
        )
        return {
            "task_id": identity,
            "attempt_id": str(row["attempt_id"]),
            "operation_id": "Config.TestLLM"
            if row["operation"] == "test"
            else "Config.RefreshModels",
            "target": {"type": "user_llm_config", "id": str(row["config_id"])},
            "project_id": None,
            "knowledge_version_id": None,
            "execution_status": row["state"],
            "status_url": base,
            "events_url": base + "/events",
            "cancel_url": None,
            "result_refs": result,
            "revision": str(row["revision"]),
            "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
            "updated_at": (row["finished_at"] or row["started_at"] or row["created_at"])
            .isoformat()
            .replace("+00:00", "Z"),
            "started_at": row["started_at"].isoformat().replace("+00:00", "Z")
            if row["started_at"]
            else None,
            "finished_at": row["finished_at"].isoformat().replace("+00:00", "Z")
            if row["finished_at"]
            else None,
            "stage": row["operation"],
            "business_state": None,
            "waiting_items": [],
            "cancel_requested_at": None,
            "error": public_error(row["error"]) if row["error"] else None,
            "warnings": [],
            "event_cursor": row["events"][-1]["cursor"],
            "partial_result_ref": None,
            "target_location": {
                "parent_type": None,
                "parent_id": None,
                "read_url": "/api/v1/me/llm-configs/" + str(row["config_id"]),
            },
            "material_use_notices": [],
        }

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        result = {k: v for k, v in data.items() if k not in {"secret", "expected_revision"}}
        if set(result) - {
            "name",
            "provider",
            "base_url",
            "parameters",
            "protocol",
            "api_version",
            "timeout_seconds",
        }:
            raise AccountError("VALIDATION_UNKNOWN_FIELD", 422)
        if not isinstance(result.get("name"), str) or not 1 <= len(result["name"].strip()) <= 200:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        result["name"] = result["name"].strip()
        if result.get("provider") not in {"openai", "anthropic", "gemini", "deepseek", "custom"}:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        url = result.get("base_url")
        if not isinstance(url, str) or len(url) > 2048:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or not parsed.port
                and parsed.netloc.endswith(":")
            ):
                raise ValueError()
        except ValueError:
            raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
        result["base_url"] = url.rstrip("/")
        defaults = {
            "openai": "openai_chat",
            "anthropic": "anthropic_messages",
            "gemini": "gemini_content",
            "deepseek": "openai_chat",
            "custom": "openai_chat",
        }
        result.setdefault("protocol", defaults[result["provider"]])
        allowed = {
            "openai": {"openai_chat", "openai_responses"},
            "anthropic": {"anthropic_messages"},
            "gemini": {"gemini_content"},
            "deepseek": {"openai_chat"},
            "custom": {"openai_chat", "openai_responses"},
        }
        if result["protocol"] not in allowed[result["provider"]]:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        result.setdefault("parameters", {})
        result.setdefault("api_version", "2023-06-01" if result["provider"] == "anthropic" else "")
        if (
            not isinstance(result["api_version"], str)
            or len(result["api_version"]) > 64
            or any(c in result["api_version"] for c in "\r\n")
        ):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        try:
            result["timeout_seconds"] = client_timeout(result.get("timeout_seconds"))
            compile_for_model(
                result["protocol"], "validation-model", result["parameters"], result["api_version"]
            )
        except ParameterError:
            raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
        return result

    def _secret(self, data: Any, previous: bytes | None) -> tuple[bytes | None, bool]:
        if data is None:
            return previous, False
        if type(data) is not dict or set(data) - {"operation", "value"}:
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        if data.get("operation") == "clear" and set(data) == {"operation"}:
            return None, previous is not None
        if (
            data.get("operation") != "set"
            or not isinstance(data.get("value"), str)
            or not 1 <= len(data["value"]) <= 4096
            or not data["value"].strip()
            or any(c in data["value"] for c in "\r\n")
        ):
            raise AccountError("VALIDATION_FIELD_INVALID", 422)
        if self.cipher is None:
            raise AccountError("CONFIG_SECRET_UNAVAILABLE", 409)
        return self.cipher.encrypt(data["value"].encode()), True

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
        with self.account.authorized_connection(token, csrf) as (conn, actor):
            if expected_actor is not None and expected_actor != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
            row = (
                self.config(conn, actor, target)
                if target and operation not in {"task", "result", "events"}
                else None
            )
            if operation == "list":
                items = [
                    self.view(conn, actor, dict(x))
                    for x in conn.execute(
                        sa.select(configs)
                        .where(configs.c.owner_id == actor, configs.c.deleted.is_(False))
                        .order_by(configs.c.created_at, configs.c.id)
                    ).mappings()
                ]
                cursor = data.get("cursor")
                start = 0
                if cursor:
                    identities = [item["id"] for item in items]
                    if cursor not in identities:
                        raise AccountError("VALIDATION_BAD_REQUEST", 400)
                    start = identities.index(cursor) + 1
                page = items[start : start + data["page_size"]]
                more = start + len(page) < len(items)
                return {
                    "items": page,
                    "next_cursor": page[-1]["id"] if more else None,
                    "has_more": more,
                }
            if operation == "read":
                assert row is not None
                return self.view(conn, actor, row)
            if operation == "options":
                return {"items": self.options(conn, actor)}
            if operation in {"selection", "select"}:
                selected = (
                    conn.execute(sa.select(selections).where(selections.c.owner_id == actor))
                    .mappings()
                    .first()
                )
                revision = (
                    str(selected["revision"])
                    if selected
                    else str(uuid5(NAMESPACE_URL, "rpb-selection:" + str(actor)))
                )
                selection = selected["selection"] if selected else None
                if operation == "select":
                    require_revision(revision, data.get("expected_revision"))
                    selection = data.get("selection")
                    if selection is not None and not any(
                        x["available"]
                        and {k: x[k] for k in ("source", "config_id", "model_id")} == selection
                        for x in self.options(conn, actor)
                    ):
                        raise AccountError("CONFIG_CONNECTION_FAILED", 409)
                    revision = str(uuid4())
                    if selected:
                        conn.execute(
                            selections.update()
                            .where(selections.c.owner_id == actor)
                            .values(revision=UUID(revision), selection=selection)
                        )
                    else:
                        conn.execute(
                            selections.insert().values(
                                owner_id=actor, revision=UUID(revision), selection=selection
                            )
                        )
                valid = selection is not None and any(
                    x["available"]
                    and {k: x[k] for k in ("source", "config_id", "model_id")} == selection
                    for x in self.options(conn, actor)
                )
                return {
                    "revision": revision,
                    "selection": selection,
                    "valid": valid,
                    "reason_code": None if valid else "CONFIG_CONNECTION_FAILED",
                }
            if operation in {"task", "result", "events"}:
                job = self.task(conn, actor, target or "")
                if operation == "events":
                    return {"events": job["events"], "view": self.task_view(job)}
                if operation == "task":
                    return self.task_view(job)
                if job["state"] not in {"succeeded", "failed"}:
                    raise AccountError("STATE_OPERATION_NOT_ALLOWED", 409)
                if not job["result"]:
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                return {"result_type": "connection_test", "payload": job["result"]}
            now = datetime.now(UTC)
            fingerprint = hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if operation in {"create", "test", "refresh"}:
                if (
                    not key
                    or not 16 <= len(key) <= 128
                    or not all(32 <= ord(c) <= 126 for c in key)
                ):
                    raise AccountError("VALIDATION_BAD_REQUEST", 400)
                lookup = sa.and_(
                    commands.c.owner_id == actor,
                    commands.c.operation == operation,
                    commands.c.target == (target or ""),
                    commands.c.key == key,
                )
                previous = conn.execute(sa.select(commands).where(lookup)).mappings().first()
                if previous:
                    self.config(conn, actor, str(previous["config_id"]))
                    if previous["fingerprint"] != fingerprint:
                        raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                    if operation != "create":
                        return self.task_view(self.task(conn, actor, previous["result"]["task_id"]))
                    return previous["result"]
            if operation in {"create", "update"}:
                if row:
                    require_revision(row["revision"], data.get("expected_revision"))
                values = self._validate({**(row["data"] if row else {}), **data})
                secret, secret_changed = self._secret(
                    data.get("secret"), row["secret_ciphertext"] if row else None
                )
                if row and values == row["data"] and not secret_changed:
                    return self.view(conn, actor, row)
                identity = row["id"] if row else uuid4()
                updates = {
                    "revision": uuid4(),
                    "credential_revision": uuid4()
                    if secret_changed or not row
                    else row["credential_revision"],
                    "data": values,
                    "secret_ciphertext": secret,
                    "updated_at": now,
                }
                if row:
                    conn.execute(configs.update().where(configs.c.id == identity).values(**updates))
                else:
                    conn.execute(
                        configs.insert().values(
                            id=identity, owner_id=actor, created_at=now, **updates
                        )
                    )
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        owner_id=actor,
                        config_id=identity,
                        operation=operation,
                        secret_operation=data.get("secret", {}).get("operation", "keep"),
                        revision=updates["revision"],
                        occurred_at=now,
                    )
                )
                result = self.view(conn, actor, self.config(conn, actor, str(identity)))
            elif operation == "delete":
                assert row is not None
                require_revision(row["revision"], data.get("expected_revision"))
                deletion_revision = uuid4()
                conn.execute(
                    audit.insert().values(
                        id=uuid4(),
                        owner_id=actor,
                        config_id=row["id"],
                        operation="delete",
                        secret_operation="clear",
                        revision=deletion_revision,
                        occurred_at=now,
                    )
                )
                conn.execute(
                    configs.update()
                    .where(configs.c.id == row["id"])
                    .values(
                        deleted=True,
                        secret_ciphertext=None,
                        revision=deletion_revision,
                        updated_at=now,
                    )
                )
                return None
            elif operation in {"test", "refresh"}:
                assert row is not None
                if not row["secret_ciphertext"] or self.cipher is None:
                    raise AccountError("CONFIG_SECRET_UNAVAILABLE", 409)
                model = data.get("model_id") if operation == "test" else None
                if operation == "test" and not isinstance(model, str):
                    raise AccountError("VALIDATION_FIELD_INVALID", 422)
                if operation == "test":
                    try:
                        compile_for_model(
                            row["data"]["protocol"],
                            str(model),
                            row["data"]["parameters"],
                            row["data"]["api_version"],
                        )
                    except ParameterError:
                        raise AccountError("VALIDATION_FIELD_INVALID", 422) from None
                identity = row["id"]
                job_id = uuid4()
                task_revision = uuid4()
                conn.execute(
                    tasks.insert().values(
                        id=job_id,
                        owner_id=actor,
                        config_id=identity,
                        revision=task_revision,
                        credential_revision=row["credential_revision"],
                        config_revision=row["revision"],
                        attempt_id=uuid4(),
                        operation=operation,
                        model_id=model,
                        input=row["data"],
                        state="queued",
                        created_at=now,
                        events=[event_record("queued", task_revision, now)],
                    )
                )
                result = self.task_view(self.task(conn, actor, str(job_id)))
            else:
                raise AccountError("VALIDATION_FIELD_INVALID", 422)
            if operation in {"create", "test", "refresh"}:
                conn.execute(
                    commands.insert().values(
                        owner_id=actor,
                        operation=operation,
                        target=target or "",
                        key=key,
                        fingerprint=fingerprint,
                        config_id=identity,
                        result=result,
                        expires_at=now + timedelta(hours=48),
                    )
                )
            return result
