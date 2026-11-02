# ruff: noqa: F811
"""Real pgvector and graph-view constraint tests; fixtures do not publish knowledge."""

import hashlib
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_construction_runs import setup
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.knowledge_build_tables import (
    chunks,
    embeddings,
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_views,
    profiles,
    vector_members,
    vector_views,
)
from rpb.adapters.knowledge_graph_seal import (
    GraphViewIncomplete,
    seal_graph_view,
    verify_graph_view,
)
from rpb.adapters.knowledge_vector_seal import VectorViewIncomplete, seal_vector_view
from rpb.adapters.run_tables import runs


def test_pgvector_scoped_members_and_sealed_views(subject):
    client, headers, root, _, engine, _ = subject
    body, _ = setup(subject)
    run_id = UUID(
        post(client, headers, root + "/construction-runs", body, "build-store-start-01").json()[
            "data"
        ]["run"]["id"]
    )
    with engine.connect() as conn:
        project = conn.scalar(sa.select(runs.c.project_id).where(runs.c.id == run_id))
        assert (
            conn.scalar(sa.text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            == "0.8.1"
        )
    chunk_id, embedding_id, view_id, graph_id, node_id, open_graph, seal_view, empty_view = (
        uuid4() for _ in range(8)
    )
    built_graph, empty_graph = uuid4(), uuid4()
    text_revision_id = uuid4()
    scope = {
        "slot_epoch": 1,
        "input_revision": uuid4(),
        "candidate_revision": uuid4(),
        "build_profile_id": "profile",
        "dependency_digest": "dependency",
    }
    with engine.begin() as conn:
        conn.execute(profiles.insert().values(id="profile-a", body={"dimension": 768}))
        conn.execute(profiles.insert().values(id="profile-b", body={"dimension": 768}))
        conn.execute(
            chunks.insert().values(
                id=chunk_id,
                project_id=project,
                run_id=run_id,
                asset_id=uuid4(),
                asset_revision=uuid4(),
                text_revision_id=text_revision_id,
                start_offset=0,
                end_offset=4,
                text_digest=hashlib.sha256("甲乙丙丁".encode()).hexdigest(),
                source_kind="full_text",
                chunker_revision="v1",
                locators=[],
                dependencies=[],
            )
        )
        conn.execute(
            embeddings.insert().values(
                id=embedding_id,
                project_id=project,
                chunk_id=chunk_id,
                profile_id="profile-a",
                embedding=[1.0] + [0.0] * 767,
            )
        )
        conn.execute(
            vector_views.insert().values(
                id=view_id,
                project_id=project,
                run_id=run_id,
                attempt_id=uuid4(),
                profile_id="profile-a",
                **scope,
            )
        )
        conn.execute(
            vector_members.insert().values(
                project_id=project,
                view_id=view_id,
                embedding_id=embedding_id,
                profile_id="profile-a",
            )
        )
        conn.execute(
            vector_views.insert().values(
                id=seal_view,
                project_id=project,
                run_id=run_id,
                attempt_id=uuid4(),
                profile_id="profile-a",
                **scope,
            )
        )
        conn.execute(
            vector_views.insert().values(
                id=empty_view,
                project_id=project,
                run_id=run_id,
                attempt_id=uuid4(),
                profile_id="profile-a",
                **scope,
            )
        )
        conn.execute(
            vector_members.insert().values(
                project_id=project,
                view_id=seal_view,
                embedding_id=embedding_id,
                profile_id="profile-a",
            )
        )
        conn.execute(
            graph_views.insert().values(
                id=graph_id, project_id=project, run_id=run_id, attempt_id=uuid4(), **scope
            )
        )
        conn.execute(
            graph_nodes.insert().values(
                project_id=project,
                view_id=graph_id,
                id=node_id,
                kind="paper",
                identity_key="paper-one",
            )
        )
        conn.execute(
            graph_views.insert().values(
                id=open_graph, project_id=project, run_id=run_id, attempt_id=uuid4(), **scope
            )
        )
        for identity in (built_graph, empty_graph):
            conn.execute(
                graph_views.insert().values(
                    id=identity,
                    project_id=project,
                    run_id=run_id,
                    attempt_id=uuid4(),
                    **scope,
                )
            )
        conn.execute(
            graph_extractions.insert().values(
                project_id=project,
                view_id=built_graph,
                chunk_id=chunk_id,
                extractor_revision="test",
                result_digest="digest",
                dependencies=[],
            )
        )
        conn.execute(
            graph_nodes.insert().values(
                project_id=project,
                view_id=open_graph,
                id=node_id,
                kind="paper",
                identity_key="paper-one",
            )
        )
        conn.execute(
            vector_views.update()
            .where(vector_views.c.id == view_id)
            .values(sealed=True, digest="fixture")
        )
        conn.execute(
            graph_views.update()
            .where(graph_views.c.id == graph_id)
            .values(sealed=True, digest="fixture")
        )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(vector_members.delete().where(vector_members.c.view_id == view_id))
    with pytest.raises(VectorViewIncomplete):
        with engine.begin() as conn:
            seal_vector_view(conn, project, seal_view, {uuid4()})
    with pytest.raises(VectorViewIncomplete):
        with engine.begin() as conn:
            seal_vector_view(conn, project, seal_view, set())
    with pytest.raises(VectorViewIncomplete):
        with engine.begin() as conn:
            conn.execute(
                vector_members.insert().values(
                    project_id=project,
                    view_id=seal_view,
                    embedding_id=uuid4(),
                    profile_id="profile-a",
                )
            )
            seal_vector_view(conn, project, seal_view, {chunk_id})
    with engine.begin() as conn:
        assert len(seal_vector_view(conn, project, empty_view, set())) == 64
    with pytest.raises(GraphViewIncomplete):
        with engine.begin() as conn:
            seal_graph_view(conn, project, built_graph, set())
    for bad_source in (
        {
            "kind": "text",
            "chunk_id": str(chunk_id),
            "text_revision_id": str(text_revision_id),
            "start_offset": 0,
            "end_offset": 1,
        },
        {
            "kind": "text",
            "chunk_id": str(uuid4()),
            "text_revision_id": str(uuid4()),
            "start_offset": 0,
            "end_offset": 1,
        },
        {
            "kind": "metadata",
            "asset_id": str(uuid4()),
            "asset_revision": str(uuid4()),
            "metadata_revision": str(uuid4()),
            "field": "title",
        },
    ):
        with pytest.raises(GraphViewIncomplete, match="outside frozen source"):
            with engine.begin() as conn:
                conn.execute(
                    graph_nodes.insert().values(
                        project_id=project,
                        view_id=built_graph,
                        id=node_id,
                        kind="paper",
                        identity_key="unresolved",
                    )
                )
                conn.execute(
                    graph_labels.insert().values(
                        project_id=project,
                        view_id=built_graph,
                        id=uuid4(),
                        node_id=node_id,
                        label="unresolved",
                        source=bad_source,
                        dependencies=[],
                    )
                )
                seal_graph_view(conn, project, built_graph, {chunk_id}, {chunk_id: "甲乙丙丁"})
    with engine.begin() as conn:
        conn.execute(
            graph_nodes.insert().values(
                project_id=project,
                view_id=built_graph,
                id=node_id,
                kind="concept",
                identity_key="乙",
            )
        )
        conn.execute(
            graph_labels.insert().values(
                project_id=project,
                view_id=built_graph,
                id=uuid4(),
                node_id=node_id,
                label="乙",
                dependencies=[],
                source={
                    "kind": "text",
                    "chunk_id": str(chunk_id),
                    "text_revision_id": str(text_revision_id),
                    "start_offset": 1,
                    "end_offset": 2,
                },
            )
        )
        digest = seal_graph_view(conn, project, built_graph, {chunk_id}, {chunk_id: "甲乙丙丁"})
        assert len(seal_graph_view(conn, project, empty_graph, set())) == 64
    with engine.connect() as conn:
        assert (
            verify_graph_view(conn, project, built_graph, {chunk_id}, {chunk_id: "甲乙丙丁"})
            == digest
        )
        with pytest.raises(GraphViewIncomplete, match="readback text differs"):
            verify_graph_view(conn, project, built_graph, {chunk_id}, {chunk_id: "甲乙丙错"})

    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                graph_extractions.delete().where(graph_extractions.c.view_id == built_graph)
            )
    with engine.begin() as conn:
        digest = seal_vector_view(conn, project, seal_view, {chunk_id})
        assert len(digest) == 64
    with engine.begin() as conn:
        sealed = (
            conn.execute(sa.select(vector_views).where(vector_views.c.id == seal_view))
            .mappings()
            .one()
        )
        assert sealed["sealed"] and sealed["digest"] == digest
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(vector_members.delete().where(vector_members.c.view_id == seal_view))
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                graph_nodes.insert().values(
                    project_id=project,
                    view_id=graph_id,
                    id=uuid4(),
                    kind="method",
                    identity_key="late",
                )
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                embeddings.update()
                .where(embeddings.c.id == embedding_id)
                .values(embedding=[1.0] + [0.0] * 767)
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                embeddings.insert().values(
                    id=uuid4(),
                    project_id=project,
                    chunk_id=chunk_id,
                    profile_id="profile-b",
                    embedding=[0.0] * 768,
                )
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                graph_edges.insert().values(
                    project_id=project,
                    view_id=open_graph,
                    id=uuid4(),
                    source_id=node_id,
                    target_id=uuid4(),
                    predicate="related_to",
                    extractor_revision="v1",
                    dependencies=[],
                )
            )
