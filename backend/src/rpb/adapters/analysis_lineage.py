"""Fail closed when a generated analysis cannot be traced to its actual inputs."""

from typing import Any
from uuid import UUID

from rpb.adapters.search_terms import allowed, classification, source_for
from rpb.modules.account_config.application.ports import AccountError


def currently_usable(run: Any, candidate: Any, state: Any, project: Any, actor: Any) -> bool:
    """Check provenance and current policy; this alone is not a publication proof."""
    try:
        revision = candidate["analysis_basis"]["analysis_revision"]
        records = run["analysis_lineage"]
        seen: set[str] = set()
        inherited = None
        while revision:
            if revision in seen:
                return False
            seen.add(revision)
            record = records[revision]
            dependency = record["dependencies"]
            if not isinstance(dependency, dict) or (
                inherited is not None and dependency != inherited
            ):
                return False
            inherited = dependency
            revision = record["parent_analysis_revision"]
        if not inherited or inherited.get("kind") != "agent":
            return False
        job = run["analysis_jobs"][inherited["job_id"]]
        if (
            job["state"] != "succeeded"
            or job["candidate_id"] != candidate["id"]
            or job["attempt_id"] != inherited["attempt_id"]
            or job["source_ids"] != inherited["source_ids"]
            or job["source_revisions"] != inherited["source_revisions"]
            or job["model_selection"] != inherited["model_selection"]
            or job["config_revision"] != inherited["config_revision"]
            or job.get("material_audit", []) != inherited["material_audit"]
            or job["processing_basis"] != candidate["processing"]["basis"]
        ):
            return False
        source_ids = inherited["source_ids"]
        processing = candidate["processing"]
        expected = list(
            dict.fromkeys(
                sid
                for sid in (
                    source_for(project)["source_id"],
                    processing["selected_source_id"],
                    processing["basis"]["document_asset_id"],
                )
                if sid is not None
            )
        )
        if not source_ids or source_ids != expected:
            return False
        audits = inherited["material_audit"]
        for sid in source_ids:
            if classification(state, project, sid)["source"]["content_revision"] != inherited[
                "source_revisions"
            ][sid] or not allowed(state, actor, project, sid):
                return False
            for boundary in ("read", "dispatch", "commit"):
                matching = [
                    entry
                    for entry in audits
                    if (
                        entry.get("boundary") == boundary
                        and entry.get("source", {}).get("source_id") == sid
                        and entry.get("source", {}).get("content_revision")
                        == inherited["source_revisions"][sid]
                        and entry.get("permitted") is True
                        and entry.get("actor_id") == job["owner_id"]
                        and entry.get("project_id") == str(project["id"])
                    )
                ]
                if not matching:
                    return False
                for entry in matching:
                    UUID(entry["classification_revision"])
                    UUID(entry["policy_revision"])
        return True
    except AccountError, AttributeError, KeyError, TypeError, ValueError:
        return False
