"""Resolve published knowledge while the caller holds the authorized Project lock."""

from typing import Any
from uuid import UUID

import sqlalchemy as sa

from rpb.adapters.knowledge_tables import heads, versions
from rpb.modules.account_config.application.ports import AccountError


def latest_published(conn: Any, project_id: UUID) -> Any:
    record = (
        conn.execute(
            sa.select(versions)
            .join(
                heads,
                sa.and_(
                    heads.c.project_id == versions.c.project_id, heads.c.version_id == versions.c.id
                ),
            )
            .where(versions.c.project_id == project_id, versions.c.sealed.is_(True))
        )
        .mappings()
        .first()
    )
    if record is None:
        raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
    return record
