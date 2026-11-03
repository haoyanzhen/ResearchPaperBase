# ruff: noqa: F811
"""Rebuild protected paper inputs in a new isolated view without consuming the old graph."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_incremental_vector_view import EmptyGraph, members, published_baseline_and_second_run
from test_ingestion_preview import FakePort, accepted_full_text_run  # noqa: F401
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters import first_publication, knowledge_graph_builder
from rpb.adapters.first_publication_worker import FirstPublicationWorker
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import graph_extractions, publication_events
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_tables import runs


@pytest.mark.parametrize(
    "case", ["changed_profile", "changed_dependency", "revoked", "graph_failed", "late_file"]
)
def test_rebuild_publication(subject, accepted_full_text_run, tmp_path, monkeypatch, case):
    client, headers, root, app, engine, _ = subject
    baseline = accepted_full_text_run[0]
    first = baseline[-1]
    sid = first["ingestion_confirmation"]["preview"]["valid_papers"][0]
    path = root + "/material-sources/" + sid + "/classification"

    def classify(value):
        current = client.get(path).json()["data"]
        response = post(
            client,
            headers,
            path + "/correct",
            {
                "expected_revision": current["revision"],
                "content_revision": current["source"]["content_revision"],
                "classification": value,
                "basis": "Independently reviewed source permission",
                "explicit_confirmation": True,
            },
            str(uuid4()),
        )
        assert response.status_code == 200, response.text

    def reclassify():
        classify("private")
        classify("public")

    base, before, second = published_baseline_and_second_run(
        subject,
        baseline,
        tmp_path,
        EmptyGraph(),
        graph_mode="rebuild",
        after_preview=reclassify if case == "changed_dependency" else None,
    )
    old_papers = client.get(root + "/papers", params={"knowledge_version_id": str(base)}).json()
    extracted, embedded = [], []

    class Port(FakePort):
        def __init__(self, permit):
            super().__init__(permit)
            if case == "changed_profile":
                self.profile.pop("profile_id")
                self.profile["runtime_digest"] = "2" * 64
                self.profile["profile_id"] = content_digest(self.profile)

        def embed(self, text):
            embedded.append(text)
            return super().embed(text)

    class Graph(EmptyGraph):
        def extract(self, config, model, secret, text, metadata, authorize):
            if case == "revoked" and not extracted:
                classify("private")
            with authorize():
                extracted.append(text)
                if case == "graph_failed":
                    raise RuntimeError("fixture extraction failure")
                return [], []

    def forbidden(*args, **kwargs):
        pytest.fail("a rebuild attempted to reuse the old graph")

    monkeypatch.setattr(knowledge_graph_builder, "read_baseline_graph", forbidden)
    monkeypatch.setattr(knowledge_graph_builder, "copy_graph_members", forbidden)
    if case == "late_file":
        commit = first_publication.commit_ready

        def lose_file(*args):
            (
                tmp_path
                / first["project_id"]
                / first["attempt_id"]
                / before["papers"][0]["objects"]["file"]
            ).unlink()
            return commit(*args)

        monkeypatch.setattr(first_publication, "commit_ready", lose_file)
    worker = FirstPublicationWorker(app.state.run_store, tmp_path, Port, Graph())
    assert worker.run_once()
    assert not worker.run_once()
    with engine.connect() as conn:
        latest = conn.scalar(sa.select(heads.c.version_id))
        result = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(second["id"])))
        assert conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == base)) == before
        event_count = conn.scalar(sa.select(sa.func.count()).select_from(publication_events))
        if case in {"revoked", "graph_failed", "late_file"}:
            assert latest == base and event_count == 1 and result["status"] == "failed"
            if case == "revoked":
                assert extracted == []
            return
        assert result["status"] == "succeeded", result["error"]
        assert latest != base and event_count == 2
        rebuilt = conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == latest))
        assert len(rebuilt["papers"]) == 2 and before["papers"][0] in rebuilt["papers"]
        old_vectors = members(conn, UUID(before["vector_view_id"]))
        new_vectors = members(conn, UUID(rebuilt["vector_view_id"]))
        assert (
            len(old_vectors) == 1
            and len(new_vectors) == 2
            and (case != "changed_profile" or old_vectors.isdisjoint(new_vectors))
        )
        assert len(embedded) == len(extracted) == 2 and set(embedded) == set(extracted)
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(graph_extractions)
                .where(graph_extractions.c.view_id == UUID(rebuilt["graph_view_id"]))
            )
            == 2
        )
        if case == "changed_profile":
            assert rebuilt["build_profile"] != before["build_profile"]
    assert (
        client.get(root + "/papers", params={"knowledge_version_id": str(base)}).json()["data"]
        == old_papers["data"]
    )
