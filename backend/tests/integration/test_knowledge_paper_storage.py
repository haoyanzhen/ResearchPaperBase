# ruff: noqa: F811
"""Paper identity is shared; Project content and immutable revisions are scoped."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_construction_runs import setup
from test_project_commands import create
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.knowledge_baseline_papers import baseline_papers, content_digest
from rpb.adapters.knowledge_paper_tables import (
    object_build_pins,
    object_lifecycle,
    paper_identities,
    paper_identity_titles,
    paper_revisions,
    project_papers,
    version_object_pins,
    version_paper_pins,
)
from rpb.adapters.knowledge_paper_tables import (
    objects as paper_objects,
)
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.project import construction_workspaces, projects
from rpb.adapters.project_commands import commands as project_create_commands
from rpb.adapters.run_tables import runs


def test_paper_identity_project_scope_and_immutable_revision(subject):
    client, headers, root, _, engine, _ = subject
    body, _ = setup(subject)
    run_id = UUID(
        post(client, headers, root + "/construction-runs", body, "paper-store-run-0001").json()[
            "data"
        ]["run"]["id"]
    )
    second = create(
        client, headers, {"name": "Another Project"}, "paper-store-project-0001"
    ).json()["data"]
    second_id = UUID(second["id"])
    with engine.connect() as conn:
        first_id = conn.scalar(sa.select(runs.c.project_id).where(runs.c.id == run_id))
    shared, same_title = uuid4(), uuid4()
    first_paper, second_paper, revision = uuid4(), uuid4(), uuid4()
    content = {"metadata": {"title": "Same, Title"}, "analysis": "private"}
    with engine.begin() as conn:
        conn.execute(paper_identities.insert(), [{"id": shared}, {"id": same_title}])
        conn.execute(
            paper_identity_titles.insert(),
            [
                {"identity_id": shared, "normalized_title": "same title"},
                {"identity_id": same_title, "normalized_title": "same title"},
            ],
        )
        conn.execute(
            project_papers.insert(),
            [
                {"id": first_paper, "project_id": first_id, "identity_id": shared},
                {"id": second_paper, "project_id": second_id, "identity_id": shared},
            ],
        )
        conn.execute(
            paper_revisions.insert().values(
                id=revision,
                project_id=first_id,
                project_paper_id=first_paper,
                run_id=run_id,
                candidate_id=uuid4(),
                content=content,
                digest=content_digest(content),
            )
        )
        object_id = uuid4()
        conn.execute(
            paper_objects.insert().values(
                id=object_id,
                project_id=first_id,
                paper_revision_id=revision,
                attempt_id=uuid4(),
                kind="text",
                source_revision_id=uuid4(),
                sha256="fixture",
                size_bytes=4,
                locators=[],
                dependencies=[],
            )
        )
        conn.execute(object_lifecycle.insert().values(project_id=first_id, object_id=object_id))
    # Once reclamation is marked, no build can acquire a new protection.
    with engine.begin() as conn:
        savepoint = conn.begin_nested()
        conn.execute(
            object_lifecycle.update()
            .where(
                object_lifecycle.c.project_id == first_id, object_lifecycle.c.object_id == object_id
            )
            .values(state="reclaiming")
        )
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(
                    object_build_pins.insert().values(
                        project_id=first_id,
                        object_id=object_id,
                        run_id=run_id,
                        attempt_id=uuid4(),
                        slot_epoch=1,
                    )
                )
        savepoint.rollback()
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                paper_revisions.update().where(paper_revisions.c.id == revision).values(content={})
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                paper_revisions.insert().values(
                    id=uuid4(),
                    project_id=first_id,
                    project_paper_id=second_paper,
                    run_id=run_id,
                    candidate_id=uuid4(),
                    content={},
                    digest="digest",
                )
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                project_papers.insert().values(id=uuid4(), project_id=first_id, identity_id=shared)
            )
    version_id, late_revision = uuid4(), uuid4()
    manifest = {
        "papers": [{"project_paper_id": str(first_paper), "paper_revision_id": str(revision)}]
    }
    draft = dict(
        id=version_id,
        project_id=first_id,
        source_run_id=run_id,
        manifest=manifest,
        manifest_digest=content_digest(manifest),
        ready_proof={},
        sealed=False,
        published_at=datetime.now(UTC),
    )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(versions.insert().values(**draft))
    with engine.begin() as conn:
        conn.execute(
            paper_revisions.insert().values(
                id=late_revision,
                project_id=first_id,
                project_paper_id=first_paper,
                run_id=run_id,
                candidate_id=uuid4(),
                content={},
                digest="late",
            )
        )
        with conn.begin_nested():
            conn.execute(versions.insert().values(**draft))
        with pytest.raises(DBAPIError):
            with conn.begin_nested():
                conn.execute(heads.insert().values(project_id=first_id, version_id=version_id))
        conn.execute(
            version_paper_pins.insert().values(
                project_id=first_id,
                version_id=version_id,
                paper_revision_id=revision,
            )
        )
        conn.execute(
            version_object_pins.insert().values(
                project_id=first_id,
                version_id=version_id,
                object_id=object_id,
            )
        )
        conn.execute(versions.update().where(versions.c.id == version_id).values(sealed=True))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(paper_revisions.delete().where(paper_revisions.c.id == revision))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(paper_objects.delete().where(paper_objects.c.id == object_id))
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                version_object_pins.delete().where(version_object_pins.c.version_id == version_id)
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                version_paper_pins.delete().where(version_paper_pins.c.version_id == version_id)
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                version_paper_pins.insert().values(
                    project_id=first_id,
                    version_id=version_id,
                    paper_revision_id=late_revision,
                )
            )
    with engine.connect() as conn:
        actual = baseline_papers(
            conn,
            {
                "project_id": str(first_id),
                "input_snapshot": {"base_knowledge_version_id": str(version_id)},
            },
        )
        assert actual == [
            {
                "project_paper_id": str(first_paper),
                "paper_revision_id": str(revision),
                "normalized_title": "same title",
            }
        ]
    with engine.begin() as conn:
        conn.execute(
            project_create_commands.delete().where(project_create_commands.c.project_id == first_id)
        )
        conn.execute(
            construction_workspaces.delete().where(construction_workspaces.c.project_id == first_id)
        )
        conn.execute(projects.delete().where(projects.c.id == first_id))
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.select(paper_identities.c.id).where(paper_identities.c.id == shared))
            == shared
        )
        assert (
            conn.scalar(sa.select(project_papers.c.id).where(project_papers.c.id == second_paper))
            == second_paper
        )
