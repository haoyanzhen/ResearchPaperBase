# ruff: noqa: F811
"""Graph reuse through actual first publication and a confirmed second Run."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_incremental_vector_view import published_baseline_and_second_run
from test_ingestion_preview import FakePort, accepted_vector_run  # noqa: F401
from test_paper_processing import Prepared
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.knowledge_build_tables import (
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_supports,
    graph_views,
)
from rpb.adapters.knowledge_graph_builder import build_graph_view
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.knowledge_vector_builder import build_vector_view
from rpb.adapters.run_tables import runs, slots
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.knowledge.domain.graph_validation import Claim, Entity


class Extractor:
    def __init__(self):
        self.inputs = []

    def extract(self, config, model, secret, text, metadata, authorize):
        assert metadata == {}
        with authorize():
            self.inputs.append(text)
        offset = text.index("e")
        return [Entity("concept", "e", offset, offset + 1)], [
            Claim("asset", 0, "mentions", offset, offset + 1)
        ]


@pytest.fixture(autouse=True)
def text_from_secondary_record(monkeypatch):
    prepare = Prepared.prepare

    def reordered(self, sources, authorize):
        return prepare(self, sources[1:] + sources[:1], authorize)

    monkeypatch.setattr(Prepared, "prepare", reordered)


@pytest.mark.parametrize(
    "case", ["success", "revoked", "empty_new", "mismatched_proof", "wrong_count", "lost_claim"]
)
def test_incremental_graph_members(subject, accepted_vector_run, tmp_path, monkeypatch, case):
    client, headers, root, app, engine, _ = subject
    actor, project, _, first = accepted_vector_run
    bad_proof = case in {"mismatched_proof", "wrong_count"}
    original = Extractor()

    # Rewrite only this fixture's INSERT; the one-shot listener is detached even on failure.
    def corrupt_proof(conn, clause, multiparams, params, options):
        if getattr(clause, "is_insert", False) and clause.table is versions:
            proof = dict(clause.compile().params["ready_proof"])
            if case == "wrong_count":
                proof["counts"] = proof["counts"] | {"assertions": 0}
            else:
                proof["dependency_set_digest"] = "wrong"
            clause = clause.values(ready_proof=proof)
        return clause, multiparams, params

    if bad_proof:
        sa.event.listen(engine, "before_execute", corrupt_proof, retval=True)
    try:
        base, manifest, second = published_baseline_and_second_run(
            subject, accepted_vector_run, tmp_path, original
        )
    finally:
        if bad_proof:
            sa.event.remove(engine, "before_execute", corrupt_proof)
    assert original.inputs == ["Version 1"]
    old = UUID(manifest["graph_view_id"])
    args = (
        app.state.run_store,
        tmp_path,
        actor,
        project,
        UUID(second["id"]),
        UUID(second["attempt_id"]),
    )
    vector = build_vector_view(*args, FakePort)

    class Next(Extractor):
        def extract(self, *args):
            proposal = super().extract(*args)
            if case == "lost_claim":
                with engine.begin() as conn:
                    run_id = UUID(second["id"])
                    live = conn.scalar(
                        sa.select(runs.c.payload).where(runs.c.id == run_id).with_for_update()
                    )
                    live["graph_build_claim"]["attempt_id"] = str(uuid4())
                    conn.execute(runs.update().where(runs.c.id == run_id).values(payload=live))
            if case == "revoked":
                source = first["ingestion_confirmation"]["preview"]["valid_papers"][0]
                candidate = next(c for c in first["candidates"] if c["id"] == source)
                assert candidate["processing"]["selected_source_id"] != source
                path = root + "/material-sources/" + source + "/classification"
                cls = client.get(path).json()["data"]
                assert (
                    post(
                        client,
                        headers,
                        path + "/correct",
                        {
                            "expected_revision": cls["revision"],
                            "content_revision": cls["source"]["content_revision"],
                            "classification": "private",
                            "basis": "Restrict baseline",
                            "explicit_confirmation": True,
                        },
                        str(uuid4()),
                    ).status_code
                    == 200
                )

                def forbidden_graph_read(*args):
                    pytest.fail("read protected graph labels after metadata revocation")

                monkeypatch.setattr(
                    "rpb.adapters.knowledge_graph_baseline.verify_graph_view", forbidden_graph_read
                )
            return ([], []) if case == "empty_new" else proposal

    provider = Next()

    def records(conn, table, view):
        return [
            dict(row)
            for row in conn.execute(
                sa.select(table).where(table.c.view_id == view).order_by(*table.primary_key.columns)
            ).mappings()
        ]

    tables = (graph_extractions, graph_nodes, graph_edges, graph_labels, graph_supports)
    with engine.connect() as conn:
        history = [records(conn, table, old) for table in tables]
    if case in {"revoked", "mismatched_proof", "wrong_count", "lost_claim"}:
        error = "STORAGE_FILE_UNAVAILABLE" if bad_proof else "STATE_OPERATION_NOT_ALLOWED"
        with pytest.raises(AccountError, match=error):
            build_graph_view(*args, provider)
    else:
        graph = build_graph_view(*args, provider)
        assert build_graph_view(*args, provider) == graph
        ready = build_graph_view(*args, provider, publish=True, tokenizer_factory=FakePort)
        assert UUID(ready["read_barrier_id"])
    assert provider.inputs == ([] if bad_proof else ["Research result"])
    with engine.connect() as conn:
        assert conn.scalar(sa.select(heads.c.version_id)) == base
        assert conn.scalar(sa.select(sa.func.count()).select_from(versions)) == 1
        assert [records(conn, table, old) for table in tables] == history
        view = conn.scalar(
            sa.select(graph_views.c.id).where(graph_views.c.run_id == UUID(second["id"]))
        )
        if case in {"revoked", "mismatched_proof", "wrong_count", "lost_claim"}:
            assert view is None
            if case == "lost_claim":
                live = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == UUID(second["id"])))
                assert live["status"] == live["graph_build_claim"]["state"] == "running"
                assert live["graph_build_claim"]["attempt_id"] != second["attempt_id"]
                assert conn.scalar(
                    sa.select(slots.c.occupant_run_id).where(slots.c.project_id == project)
                ) == UUID(second["id"])
            return
        assert view != old and str(view) == graph["view_id"]
        for table, old_rows in zip(tables, history, strict=True):
            current = records(conn, table, view)
            assert all(row | {"view_id": view} in current for row in old_rows)
        assert {str(r["chunk_id"]) for r in records(conn, graph_extractions, view)} == set(
            vector["chunks"]
        )
        belongs = {
            r["id"] for r in records(conn, graph_edges, view) if r["predicate"] == "belongs_to"
        }
        assert {
            str(r["chunk_id"])
            for r in records(conn, graph_supports, view)
            if r["edge_id"] in belongs
        } == set(vector["chunks"])
        entities = [r for r in records(conn, graph_nodes, view) if r["kind"] == "concept"]
        assert len(entities) == 1 and entities[0]["identity_key"] == "e"
        mentions = {
            r["id"]
            for r in records(conn, graph_edges, view)
            if r["predicate"] == "mentions" and r["target_id"] == entities[0]["id"]
        }
        support_chunks = {
            str(r["chunk_id"])
            for r in records(conn, graph_supports, view)
            if r["edge_id"] in mentions
        }
        expected_chunks = (
            {str(r["chunk_id"]) for r in history[0]}
            if case == "empty_new"
            else set(vector["chunks"])
        )
        assert support_chunks == expected_chunks
