"""Research session persistence through the current account and Project boundaries."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_read import latest_published
from rpb.adapters.research_tables import catalogs, commands, sessions
from rpb.adapters.runs import page
from rpb.modules.account_config.application.ports import AccountError


class ResearchStore:
    def __init__(self, terms: Any) -> None:
        self.terms, self.account = terms, terms.account

    @staticmethod
    def view(row: Any, version: Any) -> dict[str, Any]:
        return {
            **{k: str(row[k]) for k in ("id", "project_id", "revision")},
            "title": row["title"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat().replace("+00:00", "Z"),
            "updated_at": row["updated_at"].isoformat().replace("+00:00", "Z"),
            "latest_knowledge_version_id": str(version["id"]),
            "last_execution_knowledge_version_id": None,
            "current_attempt_id": None,
            "available_actions": [],
            "no_project_evidence": not bool(
                version["manifest"].get("papers") or version["manifest"].get("materials")
            ),
        }

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
            project = self.terms.project(conn, actor, UUID(str(target)), operation == "create")
            # The shared Project lock serializes this resolution with publication.
            version = latest_published(conn, project["id"])
            if operation == "read":
                row = (
                    conn.execute(
                        sa.select(sessions).where(
                            sessions.c.project_id == project["id"],
                            sessions.c.id == UUID(data["session_id"]),
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
                return self.view(row, version)
            secret = conn.scalar(
                sa.select(catalogs.c.cursor_secret).where(catalogs.c.project_id == project["id"])
            )
            if operation == "list":
                rows = conn.execute(
                    sa.select(sessions)
                    .where(sessions.c.project_id == project["id"])
                    .order_by(sessions.c.created_at.desc(), sessions.c.id.desc())
                ).mappings()
                return page(
                    [self.view(row, version) for row in rows],
                    data,
                    secret or "empty-catalog",
                    [str(actor), str(project["id"]), "research-sessions"],
                )
            if operation != "create":
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            if not key or not 16 <= len(key) <= 128 or any(not 32 <= ord(c) <= 126 for c in key):
                raise AccountError("VALIDATION_BAD_REQUEST", 400)
            timestamp = datetime.now(UTC)
            fingerprint = content_digest(data["body"])
            condition = sa.and_(
                commands.c.project_id == project["id"],
                commands.c.actor_id == actor,
                commands.c.key == key,
            )
            old = conn.execute(sa.select(commands).where(condition)).mappings().first()
            if old and old["expires_at"] > timestamp:
                if old["fingerprint"] != fingerprint:
                    raise AccountError("STATE_IDEMPOTENCY_CONFLICT", 409)
                return old["result"]
            if old:
                conn.execute(commands.delete().where(condition))
            row = dict(
                id=uuid4(),
                project_id=project["id"],
                revision=uuid4(),
                title=data["body"].get("title") or "新研究会话",
                status="active",
                created_at=timestamp,
                updated_at=timestamp,
            )
            if secret is None:
                conn.execute(
                    catalogs.insert().values(
                        project_id=project["id"], cursor_secret=secrets.token_hex(32)
                    )
                )
            conn.execute(sessions.insert().values(**row))
            expires = timestamp + timedelta(hours=24)
            result = {
                "value": self.view(row, version),
                "expires_at": expires.isoformat().replace("+00:00", "Z"),
                "original_request_id": data["request_id"],
            }
            conn.execute(
                commands.insert().values(
                    project_id=project["id"],
                    actor_id=actor,
                    key=key,
                    fingerprint=fingerprint,
                    result=result,
                    expires_at=expires,
                )
            )
            return result
