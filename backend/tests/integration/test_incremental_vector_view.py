# ruff: noqa: F811
"""A genuinely published baseline and a second, internally accepted retrieval Run."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_construction_runs import Papers
from test_ingestion_preview import FakePort, accepted_vector_run  # noqa: F401
from test_paper_analysis import Generated, generate
from test_paper_deduplication import candidates
from test_paper_processing import Prepared, confirm
from test_paper_screening import Scores, classify, score_request
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.first_publication_worker import FirstPublicationWorker
from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import chunks, embeddings, vector_members, vector_views
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.knowledge_vector_builder import build_vector_view
from rpb.adapters.paper_analysis_worker import AnalysisWorker
from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.paper_scoring_worker import ScoreWorker
from rpb.adapters.run_tables import runs
from rpb.adapters.run_worker import RunWorker
from rpb.adapters.source_tables import dispatch_limits
from rpb.modules.account_config.application.ports import AccountError


class EmptyGraph:
    def extract(self, config, model, secret, text, metadata, authorize):
        with authorize():
            return [], []


def published_baseline_and_second_run(subject, accepted_vector_run, tmp_path, graph_provider):
    client, headers, root, app, engine, _ = subject
    store = app.state.run_store
    actor, project, _, first = accepted_vector_run
    worker = FirstPublicationWorker(store, tmp_path, FakePort, graph_provider)
    assert worker.run_once()
    with engine.connect() as conn:
        base = conn.scalar(sa.select(heads.c.version_id).where(heads.c.project_id == project))
        assert base
        manifest = conn.scalar(sa.select(versions.c.manifest).where(versions.c.id == base))
    request = {
        k: first["request"][k]
        for k in ("selected_terms", "retrieval_range", "model_selection", "result_limit_per_source")
    }
    url, identity = second_preview(client, headers, root, store, engine, request)
    wait = client.get(url + "/ingestion-preview").json()["data"]["waiting_item"]
    assert wait["allowed_actions"] == ["confirm_ingestion_preview"]
    body = {
        k: wait["confirmation"][k]
        for k in ("subject_revision", "candidate_revision", "confirmation_token")
    }
    body.update(
        expected_revision=wait["revision"],
        acknowledged_risk_ids=["ABSTRACT_ONLY"],
    )
    command = url + "/waiting-items/" + wait["id"] + "/confirm"
    key = str(uuid4())
    accepted = post(client, headers, command, body, key)
    assert accepted.status_code == 200, accepted.text
    assert post(client, headers, command, body, key).json()["data"] == accepted.json()["data"]
    with engine.connect() as conn:
        second = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
    return base, manifest, second


def second_preview(client, headers, root, store, engine, request):
    path = root + "/construction-runs"
    start = post(client, headers, path, request, str(uuid4()))
    assert start.status_code == 202, start.text
    identity = UUID(start.json()["data"]["run"]["id"])
    url = path + "/" + str(identity)
    # The two simulated retrievals occur in separate provider pacing windows.
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    assert RunWorker(store, Papers()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    items = candidates(client, url)
    for item in items:
        classify(client, headers, root, item["id"])
    assert (
        post(
            client, headers, url + "/screening/score", score_request(client, url), str(uuid4())
        ).status_code
        == 202
    )
    assert ScoreWorker(store, Scores()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    assert ProcessingWorker(store, Prepared()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    assert generate(client, headers, url).status_code == 202
    assert AnalysisWorker(store, Generated()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    return url, identity


def members(conn, view):
    return set(
        conn.scalars(
            sa.select(vector_members.c.embedding_id).where(vector_members.c.view_id == view)
        )
    )


@pytest.mark.parametrize(
    "case", ["success", "profile_changed", "revoked_at_commit", "lost_text_at_commit"]
)
def test_incremental_vector_members(subject, accepted_vector_run, tmp_path, monkeypatch, case):
    client, headers, root, app, engine, _ = subject
    store = app.state.run_store
    actor, project, _, first = accepted_vector_run
    base, manifest, second = published_baseline_and_second_run(
        subject, accepted_vector_run, tmp_path, EmptyGraph()
    )
    identity = UUID(second["id"])
    old_view = UUID(manifest["vector_view_id"])
    with engine.connect() as conn:
        inherited = members(conn, old_view)
        assert inherited
    calls = []

    class Port(FakePort):
        def __init__(self, permit):
            super().__init__(permit)
            if case == "profile_changed":
                self.profile["runtime_digest"] = "2" * 64
                self.profile.pop("profile_id")
                self.profile["profile_id"] = content_digest(self.profile)

        def embed(self, text):
            calls.append(text)
            return super().embed(text)

        def __exit__(self, *args):
            if case == "lost_text_at_commit":
                text = manifest["papers"][0]["objects"]["text"]
                (tmp_path / str(project) / first["attempt_id"] / text).unlink()
            if case == "revoked_at_commit":
                source = first["ingestion_confirmation"]["preview"]["valid_papers"][0]
                path = root + "/material-sources/" + source + "/classification"
                cls = client.get(path).json()["data"]
                changed = post(
                    client,
                    headers,
                    path + "/correct",
                    {
                        "expected_revision": cls["revision"],
                        "content_revision": cls["source"]["content_revision"],
                        "classification": "private",
                        "basis": "restrict retained source",
                        "explicit_confirmation": True,
                    },
                    str(uuid4()),
                )
                assert changed.status_code == 200
                read = ImmutableFileStore.read

                def guard_read(store, project_id, attempt_id, object_id, expected_digest):
                    assert str(object_id) != manifest["papers"][0]["objects"]["text"], (
                        "read after revocation"
                    )
                    return read(store, project_id, attempt_id, object_id, expected_digest)

                monkeypatch.setattr(ImmutableFileStore, "read", guard_read)

    args = (store, tmp_path, actor, project, identity, UUID(second["attempt_id"]))
    if case == "success":
        result = build_vector_view(*args, Port)

        def unexpected(permit):
            pytest.fail("sealed incremental replay started a model")

        assert build_vector_view(*args, unexpected) == result
    else:
        with pytest.raises(
            AccountError,
            match={
                "profile_changed": "STATE_REVISION_CONFLICT",
                "revoked_at_commit": "STATE_OPERATION_NOT_ALLOWED",
                "lost_text_at_commit": "STORAGE_FILE_UNAVAILABLE",
            }[case],
        ):
            build_vector_view(*args, Port)
    assert calls == ([] if case == "profile_changed" else ["Research result"])
    with engine.connect() as conn:
        assert conn.scalar(sa.select(heads.c.version_id)) == base
        assert conn.scalar(sa.select(sa.func.count()).select_from(versions)) == 1
        assert members(conn, old_view) == inherited
        new_view = conn.scalar(
            sa.select(vector_views.c.id).where(vector_views.c.run_id == identity)
        )
        if case == "success":
            added = set(
                conn.scalars(
                    sa.select(embeddings.c.id)
                    .join(chunks, embeddings.c.chunk_id == chunks.c.id)
                    .where(chunks.c.run_id == identity)
                )
            )
            assert len(added) == 1 and added.isdisjoint(inherited)
            assert members(conn, new_view) == inherited | added
        else:
            assert new_view is None
