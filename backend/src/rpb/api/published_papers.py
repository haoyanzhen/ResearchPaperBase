"""Read version-bound paper revisions through the authenticated Project boundary."""

import base64
import binascii
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Request

from rpb.adapters.knowledge_baseline_papers import baseline_papers
from rpb.adapters.knowledge_paper_tables import paper_revisions
from rpb.adapters.knowledge_tables import heads
from rpb.adapters.runs import page
from rpb.modules.account_config.application.ports import AccountError


def router_for(store: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects/{project_id}")

    @router.get("/papers")
    def papers(
        request: Request,
        project_id: UUID,
        knowledge_version_id: UUID | None = None,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> Any:
        if set(request.query_params) - {"knowledge_version_id", "page_size", "cursor"}:
            raise AccountError("VALIDATION_BAD_REQUEST", 400)
        with store.account.authorized_connection(request.cookies.get("rpb_session", ""), None) as (
            conn,
            actor,
        ):
            expected = request.headers.get("x-expected-actor")
            if expected and expected != str(actor):
                raise AccountError("AUTH_SESSION_INVALID", 401)
            store.terms.project(conn, actor, project_id)
            if cursor and knowledge_version_id is None:
                try:
                    if len(cursor) > 4096:
                        raise ValueError()
                    claim = json.loads(base64.urlsafe_b64decode(cursor.split(".")[0]))
                    knowledge_version_id = UUID(claim["scope"][2])
                except ValueError, KeyError, TypeError, IndexError, binascii.Error, AttributeError:
                    raise AccountError("VALIDATION_CURSOR_MISMATCH", 400) from None
            version = knowledge_version_id or conn.scalar(
                sa.select(heads.c.version_id).where(heads.c.project_id == project_id)
            )
            if not version:
                raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
            from rpb.adapters.knowledge_tables import versions
            from rpb.adapters.run_tables import runs

            record = conn.execute(
                sa.select(versions.c.source_run_id, versions.c.manifest).where(
                    versions.c.project_id == project_id,
                    versions.c.id == version,
                    versions.c.sealed.is_(True),
                )
            )
            record = record.one_or_none()
            if record is None:
                raise AccountError("PERMISSION_RESOURCE_UNAVAILABLE", 404)
            members = baseline_papers(
                conn,
                {
                    "project_id": str(project_id),
                    "input_snapshot": {"base_knowledge_version_id": str(version)},
                },
            )
            source = record.source_run_id
            file_refs = {
                p["paper_revision_id"]: p.get("objects", {}).get("file")
                for p in record.manifest["papers"]
            }
            from rpb.adapters.knowledge_build_tables import graph_nodes

            graph_refs = dict(
                conn.execute(
                    sa.select(graph_nodes.c.identity_key, graph_nodes.c.id).where(
                        graph_nodes.c.project_id == project_id,
                        graph_nodes.c.view_id == UUID(record.manifest["graph_view_id"]),
                        graph_nodes.c.kind == "paper",
                    )
                ).all()
            )
            items = []
            for member in members:
                body = conn.scalar(
                    sa.select(paper_revisions.c.content).where(
                        paper_revisions.c.project_id == project_id,
                        paper_revisions.c.id == UUID(member["paper_revision_id"]),
                    )
                )
                processing = body["processing"]
                items.append(
                    {
                        "id": member["project_paper_id"],
                        "project_id": str(project_id),
                        "knowledge_version_id": str(version),
                        "asset_revision": member["paper_revision_id"],
                        "title": body["metadata"]["title"],
                        "metadata": body["metadata"],
                        "analysis": body["analysis"],
                        "screening": body["screening"],
                        "document_refs": [file_refs[member["paper_revision_id"]]]
                        if file_refs[member["paper_revision_id"]]
                        else [],
                        "graph_refs": [
                            str(
                                graph_refs[
                                    member["project_paper_id"] + ":" + member["paper_revision_id"]
                                ]
                            )
                        ],
                        "unavailable_reason": None,
                        "processing": {
                            k: (True if k == "participates_in_knowledge" else processing.get(k))
                            for k in (
                                "status",
                                "text_source_kind",
                                "failure_reason",
                                "participates_in_knowledge",
                            )
                        },
                    }
                )
            secret = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == source))[
                "confirmation_secret"
            ]
            result = page(
                items,
                {"page_size": page_size, "cursor": cursor},
                secret,
                [str(actor), str(project_id), str(version), "papers"],
            )
            next_cursor = result.pop("next_cursor")
            return {
                "data": {**result, "knowledge_version_id": str(version)},
                "meta": {
                    "request_id": request.state.request_id,
                    "next_cursor": next_cursor,
                    "has_more": next_cursor is not None,
                },
            }

    return router
