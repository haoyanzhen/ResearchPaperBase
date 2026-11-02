# ruff: noqa: F811
"""Preview reflects confirmed analysis without granting ingestion or publication."""

import copy
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_paper_analysis import Generated, generate, ready
from test_paper_deduplication import candidates
from test_paper_processing import confirm
from test_project_commands import create
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.immutable_files import ImmutableFileStore
from rpb.adapters.ingestion_confirmation import accept_locked, signature, validate
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_build_tables import (
    chunks,
    embeddings,
    graph_edges,
    graph_extractions,
    graph_labels,
    graph_nodes,
    graph_supports,
    graph_views,
    vector_views,
)
from rpb.adapters.knowledge_graph_builder import build_graph_view
from rpb.adapters.knowledge_object_stage import require_build_protection, stage_objects
from rpb.adapters.knowledge_paper_stage import stage_paper
from rpb.adapters.knowledge_paper_tables import (
    object_build_pins,
    object_lifecycle,
    paper_identities,
    paper_identity_titles,
    paper_revisions,
    project_papers,
    version_paper_pins,
)
from rpb.adapters.knowledge_paper_tables import objects as staged_objects
from rpb.adapters.knowledge_tables import versions
from rpb.adapters.knowledge_vector_builder import build_vector_view
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.local_embeddings import LocalEmbeddings
from rpb.adapters.paper_analysis_worker import AnalysisWorker
from rpb.adapters.run_tables import runs, slots
from rpb.adapters.runs import persist, transition
from rpb.modules.account_config.application.ports import AccountError
from rpb.modules.knowledge.domain.graph_validation import Claim, Entity


class FakePort:
    def __init__(self, permit):
        self.permit = permit
        self.profile = {
            "model_id": "intfloat/multilingual-e5-base",
            "weights_revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
            "weights_digest": ("a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7"),
            "tokenizer_revision": (
                "721e17b7fb6b2a3388d0a9c6ff8a99784672cdacd98e2b6cb9cdab92237be08e"
            ),
            "dimension": 768,
            "normalization": "l2",
            "distance": "cosine",
            "query_prefix": "query: ",
            "passage_prefix": "passage: ",
            "runtime_digest": "1" * 64,
        }
        self.profile["profile_id"] = content_digest(self.profile)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def offsets(self, text):
        with self.permit():
            return [(i, i + 1) for i in range(len(text))]

    def passage_length(self, text):
        with self.permit():
            return len(text) + 4

    def embed(self, text):
        with self.permit():
            return [1.0] + [0.0] * 767


def embedding_factory():
    factory = FakePort
    model_dir = os.environ.get("E5_TEST_MODEL_DIR")
    python_executable = os.environ.get("E5_TEST_PYTHON")
    if model_dir and python_executable:

        def factory(permit):
            env = dict(os.environ)
            env.update(
                RPB_EMBEDDING_MODEL_DIR=model_dir,
                RPB_EMBEDDING_WEIGHTS_SHA256=(
                    "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7"
                ),
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
            )
            return LocalEmbeddings(
                [
                    python_executable,
                    str(Path(__file__).resolve().parents[3] / "embedding-runtime/worker.py"),
                ],
                env,
                permit,
            )

    return factory


def test_ingestion_preview_confirmed_subset_and_no_writes(subject):
    client, headers, _, app, engine, _ = subject
    url = ready(subject)
    assert client.get(url + "/ingestion-preview").status_code == 409
    item = candidates(client, url)[0]
    assert generate(client, headers, url, item).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    with engine.connect() as conn:
        before = conn.scalar(sa.select(runs.c.payload))
    response = client.get(url + "/ingestion-preview")
    assert response.status_code == 200, response.text
    preview = response.json()["data"]
    assert preview["valid_papers"] == [item["id"]]
    assert preview["degraded"] == [{"candidate_id": item["id"], "reason": "使用摘要降级文本"}]
    assert preview["risks"][0]["id"] == "ABSTRACT_ONLY"
    assert preview["waiting_item"]["allowed_actions"] == []
    wait = preview["waiting_item"]
    proof = wait["confirmation"]
    assert proof["blocked_reasons"]
    token = proof["confirmation_token"]
    assert validate(before, before["owner_id"], token, ["ABSTRACT_ONLY"])
    assert not validate(before, before["owner_id"], token, [])
    assert not validate(before, str(uuid4()), token, ["ABSTRACT_ONLY"])
    changed = copy.deepcopy(before)
    changed["candidates"][0]["metadata"]["title"] += " altered"
    assert not validate(changed, before["owner_id"], token, ["ABSTRACT_ONLY"])
    pending_score = copy.deepcopy(before)
    pending_score["scoring_jobs"][str(uuid4())] = {"state": "running"}
    assert not validate(pending_score, before["owner_id"], token, ["ABSTRACT_ONLY"])
    rejected = client.post(
        url + "/waiting-items/" + wait["id"] + "/confirm",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_revision": wait["revision"],
            "subject_revision": proof["subject_revision"],
            "candidate_revision": proof["candidate_revision"],
            "confirmation_token": proof["confirmation_token"],
            "acknowledged_risk_ids": [],
        },
    )
    assert rejected.status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.payload)) == before
    assert client.get(url).json()["data"]["published_knowledge_version_id"] is None
    wrong_project = url.replace(before["project_id"], str(uuid4()))
    assert client.get(wrong_project + "/ingestion-preview").status_code == 404
    assert (
        client.get(url.replace(before["id"], str(uuid4())) + "/ingestion-preview").status_code
        == 404
    )

    mixed = copy.deepcopy(before)
    pending = copy.deepcopy(mixed["candidates"][0])
    pending.update(id=str(uuid4()), screening_error="PROVIDER_RESPONSE_INVALID")
    pending["screening"]["valid"] = None
    mixed["candidates"].append(pending)
    stale = copy.deepcopy(pending)
    stale.update(id=str(uuid4()), screening_error=None, screening_stale=True)
    stale["screening"]["valid"] = False
    mixed["candidates"].append(stale)
    source_id = str(uuid4())
    mixed["resolution"]["failed"].append(
        {
            "term_id": str(uuid4()),
            "resolution": {
                "rejected": [{"config_id": source_id, "reason_code": "CONFIG_SECRET_UNAVAILABLE"}]
            },
        }
    )
    mixed["source_results"].append(
        {
            "status": "failed",
            "term_id": str(uuid4()),
            "config_id": str(uuid4()),
            "error": "CONFIG_CONNECTION_FAILED",
        }
    )
    with engine.begin() as conn:
        conn.execute(runs.update().where(runs.c.id == UUID(before["id"])).values(payload=mixed))
    result = client.get(url + "/ingestion-preview")
    assert result.status_code == 200, result.text
    failures = result.json()["data"]["failed"]
    assert any(
        f.get("candidate_id") == pending["id"] and f["reason"] == "PROVIDER_RESPONSE_INVALID"
        for f in failures
    )
    assert any(f.get("reason") == "CONFIG_CONNECTION_FAILED" for f in failures)
    assert any(
        f.get("config_id") == source_id and f["reason"] == "CONFIG_SECRET_UNAVAILABLE"
        for f in failures
    )
    assert any(
        f.get("candidate_id") == stale["id"] and f["reason"] == "筛选依据已失效，需重新筛选"
        for f in result.json()["data"]["skipped"]
    )


@pytest.mark.parametrize(
    "graph_case",
    ["semantic", "semantic_multi", "ambiguous", "identity_race", "reimport", "empty", "failure"],
)
def test_internal_confirmation_atomically_freezes_candidate_without_publishing(
    subject, tmp_path, monkeypatch, graph_case
):
    client, headers, _, app, engine, _ = subject
    if graph_case == "semantic_multi":
        from test_paper_processing import Prepared

        def choose_second(self, sources, authorize):
            with authorize():
                pass
            source = sources[1]
            return dict(
                text=source["metadata"]["abstract"],
                raw=None,
                source_id=source["id"],
                kind="abstract_fallback",
                segments=[],
                diagnostics=[],
            )

        monkeypatch.setattr(Prepared, "prepare", choose_second)
    url = ready(subject)
    assert generate(client, headers, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    with engine.connect() as conn:
        before = conn.scalar(sa.select(runs.c.payload))
    wait = client.get(url + "/ingestion-preview").json()["data"]["waiting_item"]
    proof = wait["confirmation"]
    body = {
        "waiting_item_id": wait["id"],
        "expected_revision": wait["revision"],
        "subject_revision": proof["subject_revision"],
        "candidate_revision": proof["candidate_revision"],
        "confirmation_token": proof["confirmation_token"],
        "acknowledged_risk_ids": ["ABSTRACT_ONLY"],
    }
    actor, project, identity = (UUID(before[key]) for key in ("owner_id", "project_id", "id"))
    empty = copy.deepcopy(before)
    empty["analysis_confirmation"]["candidate_ids"] = []
    expiry = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    empty_body = {
        **body,
        "acknowledged_risk_ids": [],
        "confirmation_token": expiry + "." + signature(empty, str(actor), expiry),
    }
    with pytest.raises(AccountError):
        with engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == identity).values(payload=empty))
            accept_locked(conn, app.state.run_store, actor, project, identity, empty_body)
    stale_base = copy.deepcopy(before)
    stale_base["input_snapshot"]["base_knowledge_version_id"] = str(uuid4())
    stale_base["baseline_loaded_version_id"] = stale_base["input_snapshot"][
        "base_knowledge_version_id"
    ]
    stale_body = {
        **body,
        "confirmation_token": expiry + "." + signature(stale_base, str(actor), expiry),
    }
    with pytest.raises(AccountError):
        with engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == identity).values(payload=stale_base))
            accept_locked(conn, app.state.run_store, actor, project, identity, stale_body)
    with pytest.raises(AccountError):
        with engine.begin() as conn:
            accept_locked(
                conn,
                app.state.run_store,
                actor,
                project,
                identity,
                {**body, "acknowledged_risk_ids": []},
            )
    with engine.begin() as conn:
        frozen = accept_locked(conn, app.state.run_store, actor, project, identity, body)
        assert frozen["candidate_version"]["content_locked"] is True
        assert frozen["candidate_version"]["state"] == "preparing"
        assert frozen["ingestion_confirmation"]["candidate_snapshot"] == before["candidates"]
    with engine.connect() as conn:
        saved = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        assert saved["status"] == "running" and saved["phase"] == "knowledge_build"
        assert saved["ingestion_confirmation"]["candidate_revision"] == before["candidate_revision"]
        assert saved["ingestion_confirmation"]["accepted_attempt_id"] == before["attempt_id"]
        assert saved["attempt_id"] != before["attempt_id"]
    candidate_id = UUID(saved["ingestion_confirmation"]["preview"]["valid_papers"][0])
    attempt = UUID(saved["attempt_id"])
    other_project = None
    old_project_paper = None
    if graph_case == "identity_race":
        with engine.begin() as conn:
            stage_paper(conn, app.state.run_store, actor, project, identity, attempt, candidate_id)
    if graph_case in {"ambiguous", "reimport", "identity_race"}:
        from rpb.modules.construction.domain.paper_identity import normalized_paper_title

        other_project = UUID(
            create(client, headers, {"name": "Other Project"}, str(uuid4())).json()["data"]["id"]
        )
        other_run, other_version = uuid4(), uuid4()
        title = next(
            c["metadata"]["title"] for c in saved["candidates"] if c["id"] == str(candidate_id)
        )
        with engine.begin() as conn:
            conn.execute(
                runs.insert().values(
                    id=other_run,
                    project_id=other_project,
                    owner_id=actor,
                    status="failed",
                    revision=uuid4(),
                    payload={},
                    created_at=datetime.now(UTC),
                )
            )
            conn.execute(
                versions.insert().values(
                    id=other_version,
                    project_id=other_project,
                    source_run_id=other_run,
                    manifest={},
                    manifest_digest="fixture",
                    ready_proof={},
                    sealed=False,
                    published_at=datetime.now(UTC),
                )
            )
            for _ in range(2):
                global_id, project_paper, revision = uuid4(), uuid4(), uuid4()
                conn.execute(paper_identities.insert().values(id=global_id))
                conn.execute(
                    paper_identity_titles.insert().values(
                        identity_id=global_id, normalized_title=normalized_paper_title(title)
                    )
                )
                conn.execute(
                    project_papers.insert().values(
                        id=project_paper, project_id=other_project, identity_id=global_id
                    )
                )
                conn.execute(
                    paper_revisions.insert().values(
                        id=revision,
                        project_id=other_project,
                        project_paper_id=project_paper,
                        run_id=other_run,
                        candidate_id=uuid4(),
                        content={},
                        digest="fixture",
                    )
                )
                conn.execute(
                    version_paper_pins.insert().values(
                        project_id=other_project,
                        version_id=other_version,
                        paper_revision_id=revision,
                    )
                )
            conn.execute(
                versions.update().where(versions.c.id == other_version).values(sealed=True)
            )
            if graph_case == "reimport":
                old_run, old_version, old_identity, old_project_paper, old_revision = (
                    uuid4() for _ in range(5)
                )
                conn.execute(
                    runs.insert().values(
                        id=old_run,
                        project_id=project,
                        owner_id=actor,
                        status="failed",
                        revision=uuid4(),
                        payload={},
                        created_at=datetime.now(UTC),
                    )
                )
                conn.execute(
                    paper_identities.insert().values(id=old_identity, unresolved_project_id=project)
                )
                conn.execute(
                    paper_identity_titles.insert().values(
                        identity_id=old_identity, normalized_title=normalized_paper_title(title)
                    )
                )
                conn.execute(
                    project_papers.insert().values(
                        id=old_project_paper, project_id=project, identity_id=old_identity
                    )
                )
                conn.execute(
                    paper_revisions.insert().values(
                        id=old_revision,
                        project_id=project,
                        project_paper_id=old_project_paper,
                        run_id=old_run,
                        candidate_id=uuid4(),
                        content={},
                        digest="fixture",
                    )
                )
                conn.execute(
                    versions.insert().values(
                        id=old_version,
                        project_id=project,
                        source_run_id=old_run,
                        manifest={},
                        manifest_digest="fixture",
                        ready_proof={},
                        sealed=False,
                        published_at=datetime.now(UTC),
                    )
                )
                conn.execute(
                    version_paper_pins.insert().values(
                        project_id=project, version_id=old_version, paper_revision_id=old_revision
                    )
                )
                conn.execute(
                    versions.update().where(versions.c.id == old_version).values(sealed=True)
                )
    with pytest.raises(AccountError):
        with engine.begin() as conn:
            stage_paper(
                conn,
                app.state.run_store,
                actor,
                project,
                identity,
                UUID(before["attempt_id"]),
                candidate_id,
            )
    if graph_case == "identity_race":
        with pytest.raises(AccountError, match="STATE_REVISION_CONFLICT"):
            with engine.begin() as conn:
                stage_paper(
                    conn, app.state.run_store, actor, project, identity, attempt, candidate_id
                )
        return
    if graph_case == "reimport":
        # Retrieval alone is not an explicit, confirmed reimport after removal.
        for distinct in (False, True):
            with pytest.raises(AccountError):
                with engine.begin() as conn:
                    if distinct:
                        injected = copy.deepcopy(saved)
                        candidate = next(
                            c for c in injected["candidates"] if c["id"] == str(candidate_id)
                        )
                        candidate["deduplication"]["baseline_resolution"] = "distinct"
                        injected["ingestion_confirmation"]["candidate_snapshot"] = copy.deepcopy(
                            injected["candidates"]
                        )
                        conn.execute(
                            runs.update().where(runs.c.id == identity).values(payload=injected)
                        )
                    stage_paper(
                        conn, app.state.run_store, actor, project, identity, attempt, candidate_id
                    )
        return
    with engine.begin() as conn:
        staged = stage_paper(
            conn, app.state.run_store, actor, project, identity, attempt, candidate_id
        )
    with engine.begin() as conn:
        assert (
            stage_paper(conn, app.state.run_store, actor, project, identity, attempt, candidate_id)
            == staged
        )
    if other_project is not None:
        if old_project_paper is not None:
            assert staged["project_paper_id"] == str(old_project_paper)
        with engine.connect() as conn:
            row = conn.execute(
                sa.select(project_papers.c.identity_id, paper_identities.c.unresolved_project_id)
                .join(paper_identities, paper_identities.c.id == project_papers.c.identity_id)
                .where(project_papers.c.id == UUID(staged["project_paper_id"]))
            ).one()
            assert row.unresolved_project_id == project
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as conn:
                conn.execute(
                    project_papers.insert().values(
                        id=uuid4(), project_id=other_project, identity_id=row.identity_id
                    )
                )
    with engine.connect() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(paper_revisions)
                .where(
                    paper_revisions.c.project_id == project, paper_revisions.c.run_id == identity
                )
            )
            == 1
        )
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(versions)
                .where(versions.c.project_id == project, versions.c.source_run_id == identity)
            )
            == 0
        )
    real_read = ImmutableFileStore.read
    reads = []

    def delete_after_read(self, project_id, attempt_id, object_id, digest):
        data = real_read(self, project_id, attempt_id, object_id, digest)
        reads.append(object_id)
        if len(reads) == 1:
            (tmp_path / str(project_id) / str(attempt_id) / str(object_id)).unlink()
        return data

    with monkeypatch.context() as patch:
        patch.setattr(ImmutableFileStore, "read", delete_after_read)
        with pytest.raises(AccountError):
            stage_objects(
                app.state.run_store, tmp_path, actor, project, identity, attempt, candidate_id
            )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(staged_objects)) == 0
    if graph_case == "semantic":
        import rpb.adapters.knowledge_object_stage as object_stage

        reads_during_lease = []

        class ExpiringClock(datetime):
            @classmethod
            def now(cls, tz=None):
                current = datetime.now(tz)
                return current + timedelta(hours=1) if len(reads_during_lease) >= 2 else current

        def expire_during_second_read(self, *args):
            data = real_read(self, *args)
            reads_during_lease.append(True)
            return data

        with monkeypatch.context() as patch:
            patch.setattr(object_stage, "datetime", ExpiringClock)
            patch.setattr(ImmutableFileStore, "read", expire_during_second_read)
            with pytest.raises(AccountError):
                stage_objects(
                    app.state.run_store, tmp_path, actor, project, identity, attempt, candidate_id
                )
        with engine.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(staged_objects)) == 0
            assert conn.scalar(sa.select(sa.func.count()).select_from(object_build_pins)) == 0
    stored = stage_objects(
        app.state.run_store, tmp_path, actor, project, identity, attempt, candidate_id
    )
    assert len(stored) == 1 and stored[0]["kind"] == "text"
    with engine.connect() as conn:
        pinned = (
            conn.execute(
                sa.select(object_build_pins).where(
                    object_build_pins.c.project_id == project,
                    object_build_pins.c.object_id == UUID(stored[0]["object_id"]),
                    object_build_pins.c.run_id == identity,
                    object_build_pins.c.attempt_id == attempt,
                )
            )
            .mappings()
            .one()
        )
        assert pinned["slot_epoch"] == saved["slot_epoch"]
        require_build_protection(
            conn,
            project,
            UUID(stored[0]["object_id"]),
            identity,
            attempt,
            saved["slot_epoch"],
            saved["lease_until"],
        )
        with pytest.raises(AccountError):
            require_build_protection(
                conn,
                project,
                UUID(stored[0]["object_id"]),
                identity,
                uuid4(),
                saved["slot_epoch"],
                saved["lease_until"],
            )
        with pytest.raises(AccountError):
            require_build_protection(
                conn,
                project,
                UUID(stored[0]["object_id"]),
                identity,
                attempt,
                saved["slot_epoch"] + 1,
                saved["lease_until"],
            )
        with pytest.raises(AccountError):
            require_build_protection(
                conn,
                project,
                UUID(stored[0]["object_id"]),
                identity,
                attempt,
                saved["slot_epoch"],
                (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            )
    for action in ("update", "delete"):
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as conn:
                statement = (
                    object_build_pins.update().values(slot_epoch=saved["slot_epoch"] + 1)
                    if action == "update"
                    else object_build_pins.delete()
                )
                conn.execute(
                    statement.where(
                        object_build_pins.c.project_id == project,
                        object_build_pins.c.object_id == UUID(stored[0]["object_id"]),
                    )
                )
    with pytest.raises(sa.exc.DBAPIError):
        with engine.begin() as conn:
            conn.execute(
                object_lifecycle.update()
                .where(
                    object_lifecycle.c.project_id == project,
                    object_lifecycle.c.object_id == UUID(stored[0]["object_id"]),
                )
                .values(state="reclaiming")
            )
    assert (
        stage_objects(
            app.state.run_store, tmp_path, actor, project, identity, attempt, candidate_id
        )
        == stored
    )

    factory = embedding_factory()
    model_dir = os.environ.get("E5_TEST_MODEL_DIR")
    python_executable = os.environ.get("E5_TEST_PYTHON")
    if model_dir and python_executable:
        built = build_vector_view(
            app.state.run_store, tmp_path, actor, project, identity, attempt, factory
        )
    else:
        dispatched, release = Event(), Event()

        class BlockingPort(FakePort):
            def embed(self, text):
                with self.permit():
                    pass
                dispatched.set()
                assert release.wait(10)
                return [1.0] + [0.0] * 767

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                build_vector_view,
                app.state.run_store,
                tmp_path,
                actor,
                project,
                identity,
                attempt,
                BlockingPort,
            )
            try:
                assert dispatched.wait(10)
                with pytest.raises(AccountError) as busy:
                    build_vector_view(
                        app.state.run_store, tmp_path, actor, project, identity, attempt, FakePort
                    )
                assert busy.value.code == "LOCK_CONTENT_BUSY"
            finally:
                release.set()
            built = future.result(timeout=20)

    profile = built["profile"]
    assert profile["embedding_profile_id"] == profile["embedding"]["profile_id"]
    assert all(
        profile[key]
        for key in (
            "chunker_revision",
            "extractor_schema_revision",
            "extractor_prompt_revision",
            "extractor_config_digest",
            "graph_rules_revision",
            "lexical_revision",
        )
    )
    assert built["profile_id"] == content_digest(profile)

    def never_start_model(permit):
        raise AssertionError("sealed result must be reused without another model call")

    assert (
        build_vector_view(
            app.state.run_store, tmp_path, actor, project, identity, attempt, never_start_model
        )
        == built
    )
    with engine.connect() as conn:
        view = (
            conn.execute(sa.select(vector_views).where(vector_views.c.id == UUID(built["view_id"])))
            .mappings()
            .one()
        )
        assert view["sealed"] and view["digest"] == built["digest"]
        assert conn.scalar(sa.select(sa.func.count()).select_from(chunks)) == len(built["chunks"])
        assert conn.scalar(sa.select(sa.func.count()).select_from(embeddings)) == len(
            built["chunks"]
        )

    class FakeGraph:
        calls = 0

        def extract(self, config, model, secret, text, metadata, authorize):
            with authorize():
                self.calls += 1
                assert metadata == {} and text.startswith("Version")
            if graph_case == "failure":
                raise ProviderFailure("PROVIDER_TIMEOUT")
            if graph_case == "empty":
                return [], []
            return [Entity("concept", "Version", 0, 7)], [Claim("chunk", 0, "mentions", 0, 7)]

    graph_provider = FakeGraph()
    if graph_case == "failure":
        with pytest.raises(ProviderFailure):
            build_graph_view(
                app.state.run_store, tmp_path, actor, project, identity, attempt, graph_provider
            )
        with engine.connect() as conn:
            failed = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            assert failed["status"] == "failed" and failed["graph_build_claim"]["state"] == "failed"
            assert conn.scalar(sa.select(sa.func.count()).select_from(graph_views)) == 0
            assert (
                conn.scalar(
                    sa.select(sa.func.count())
                    .select_from(versions)
                    .where(versions.c.project_id == project)
                )
                == 0
            )
        return
    graph = build_graph_view(
        app.state.run_store, tmp_path, actor, project, identity, attempt, graph_provider
    )
    assert graph_provider.calls == len(built["chunks"])
    if graph_case == "semantic_multi":
        with engine.connect() as conn:
            live = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            candidate = next(c for c in live["candidates"] if c["id"] == str(candidate_id))
            assert candidate["processing"]["selected_source_id"] != candidate["id"]
            title = (
                conn.execute(
                    sa.select(graph_labels).where(
                        graph_labels.c.view_id == UUID(graph["view_id"]),
                        graph_labels.c.label == candidate["metadata"]["title"],
                    )
                )
                .mappings()
                .one()
            )
            assert title["dependencies"]["source_ids"] == [candidate["id"]]
            assert candidate["id"] in title["dependencies"]["source_revisions"]
    with engine.connect() as conn:
        view = (
            conn.execute(sa.select(graph_views).where(graph_views.c.id == UUID(graph["view_id"])))
            .mappings()
            .one()
        )
        assert view["sealed"] and view["digest"] == graph["digest"]
        assert conn.scalar(sa.select(sa.func.count()).select_from(graph_extractions)) == len(
            built["chunks"]
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(graph_nodes)) >= (
            3 if graph_case == "semantic" else 2
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(graph_edges)) >= (
            2 if graph_case == "semantic" else 1
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(graph_supports)) >= (
            2 if graph_case == "semantic" else 1
        )
    assert (
        build_graph_view(
            app.state.run_store, tmp_path, actor, project, identity, attempt, graph_provider
        )
        == graph
    )
    assert graph_provider.calls == len(built["chunks"])
    if graph_case == "semantic_multi":
        with engine.connect() as conn:
            live = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            candidate = next(c for c in live["candidates"] if c["id"] == str(candidate_id))
            assert candidate["processing"]["selected_source_id"] != candidate["id"]
            title = (
                conn.execute(
                    sa.select(graph_labels).where(
                        graph_labels.c.view_id == UUID(graph["view_id"]),
                        graph_labels.c.label == candidate["metadata"]["title"],
                    )
                )
                .mappings()
                .one()
            )
            assert title["dependencies"]["source_ids"] == [candidate["id"]]
            assert candidate["id"] in title["dependencies"]["source_revisions"]
    from rpb.adapters.first_publication import commit_ready

    barrier = build_graph_view(
        app.state.run_store,
        tmp_path,
        actor,
        project,
        identity,
        attempt,
        graph_provider,
        publish=True,
        tokenizer_factory=factory,
    )
    args = (app.state.run_store, actor, project, identity, attempt, barrier["read_barrier_id"])
    if graph_case == "semantic_multi":
        path = subject[2] + "/material-sources/" + str(candidate_id) + "/classification"
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
                    "basis": "Revoked after graph proof",
                    "explicit_confirmation": True,
                },
                str(uuid4()),
            ).status_code
            == 200
        )
        with pytest.raises(AccountError):
            commit_ready(*args)
        with engine.connect() as conn:
            assert not conn.scalar(sa.select(versions.c.id).where(versions.c.project_id == project))
        return
    if graph_case == "semantic":

        def fail_after_head(conn, cursor, statement, parameters, ctx, executemany):
            if statement.startswith("INSERT INTO knowledge_project_heads"):
                raise RuntimeError("publication rollback probe")

        sa.event.listen(engine, "after_cursor_execute", fail_after_head)
        try:
            with pytest.raises(RuntimeError, match="rollback probe"):
                commit_ready(*args)
        finally:
            sa.event.remove(engine, "after_cursor_execute", fail_after_head)
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    sa.select(sa.func.count())
                    .select_from(versions)
                    .where(versions.c.project_id == project)
                )
                == 0
            )
            assert conn.scalar(sa.select(runs.c.status).where(runs.c.id == identity)) == "running"
            assert (
                conn.scalar(
                    sa.select(object_build_pins.c.run_id).where(
                        object_build_pins.c.run_id == identity
                    )
                )
                == identity
            )
        version = commit_ready(*args)
        assert commit_ready(*args) == version
        from rpb.adapters.knowledge_build_tables import publication_events

        event = publication_events.c.version_id == UUID(version)
        with engine.begin() as conn:
            assert (
                conn.execute(publication_events.update().where(event).values(state="sent")).rowcount
                == 1
            )
        for statement in (
            publication_events.delete(),
            publication_events.update().values(graph_view_id=uuid4()),
        ):
            with pytest.raises(sa.exc.DBAPIError):
                with engine.begin() as conn:
                    conn.execute(statement.where(event))
        with engine.connect() as conn:
            assert conn.scalar(sa.select(publication_events.c.state).where(event)) == "sent"

        return
    if graph_case == "empty":
        from rpb.adapters.first_publication_worker import FirstPublicationWorker

        with engine.begin() as conn:
            interrupted = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            interrupted["publication_claim"] = {"id": str(uuid4()), "state": "running"}
            interrupted["lease_until"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            persist(conn, interrupted)
        worker = FirstPublicationWorker(
            app.state.run_store, tmp_path, never_start_model, graph_provider
        )
        assert worker.run_once()
        assert not worker.run_once()
        with engine.connect() as conn:
            interrupted = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
            assert interrupted["publication_claim"]["state"] == "unknown"
            assert interrupted["error"] == "PROVIDER_RESULT_UNKNOWN"
            assert (
                conn.scalar(sa.select(slots.c.occupant_run_id).where(slots.c.project_id == project))
                == identity
            )
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        transition(run, "cancelled")
        persist(conn, run)
    with pytest.raises(AccountError):
        commit_ready(*args)
    with pytest.raises(AccountError):
        with engine.begin() as conn:
            stage_paper(conn, app.state.run_store, actor, project, identity, attempt, candidate_id)
    with pytest.raises(AccountError):
        stage_objects(
            app.state.run_store, tmp_path, actor, project, identity, attempt, candidate_id
        )


def test_confirmed_full_text_stages_separate_private_text_and_pdf(subject, tmp_path):
    from test_paper_processing import Prepared, confirmed_score, pdf
    from test_paper_screening import classify

    from rpb.adapters.paper_processing import ProcessingWorker

    client, headers, root, app, engine, _ = subject
    url = confirmed_score(subject)
    assert confirm(client, headers, url)[0].status_code == 200
    pdf_bytes = pdf()

    class FullText(Prepared):
        def prepare(self, sources, authorize):
            return {
                **super().prepare(sources, authorize),
                "raw": pdf_bytes,
                "text": "Actual full text",
                "kind": "full_text",
            }

    assert ProcessingWorker(app.state.run_store, FullText()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    candidate = candidates(client, url)[0]
    classify(client, headers, root, candidate["processing"]["basis"]["document_asset_id"])
    assert generate(client, headers, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    wait = client.get(url + "/ingestion-preview").json()["data"]["waiting_item"]
    proof = wait["confirmation"]
    body = {
        "waiting_item_id": wait["id"],
        "expected_revision": wait["revision"],
        "subject_revision": proof["subject_revision"],
        "candidate_revision": proof["candidate_revision"],
        "confirmation_token": proof["confirmation_token"],
        "acknowledged_risk_ids": [],
    }
    with engine.connect() as conn:
        before = conn.scalar(sa.select(runs.c.payload))
    actor, project, identity = (UUID(before[key]) for key in ("owner_id", "project_id", "id"))
    with engine.begin() as conn:
        accepted = accept_locked(conn, app.state.run_store, actor, project, identity, body)
    attempt, candidate_id = UUID(accepted["attempt_id"]), UUID(candidate["id"])
    staged = stage_objects(
        app.state.run_store, tmp_path, actor, project, identity, attempt, candidate_id
    )
    assert {item["kind"] for item in staged} == {"text", "file"}
    files = ImmutableFileStore(tmp_path)
    for item in staged:
        data = files.read(project, attempt, UUID(item["object_id"]), item["sha256"])
        assert data == (b"Actual full text" if item["kind"] == "text" else pdf_bytes)


@pytest.mark.parametrize("revoke", [False, True])
def test_vector_failure_records_diagnostic_and_releases_writer(subject, tmp_path, revoke):
    client, headers, root, app, engine, _ = subject
    url = ready(subject)
    assert generate(client, headers, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    wait = client.get(url + "/ingestion-preview").json()["data"]["waiting_item"]
    proof = wait["confirmation"]
    body = {
        "waiting_item_id": wait["id"],
        "expected_revision": wait["revision"],
        "subject_revision": proof["subject_revision"],
        "candidate_revision": proof["candidate_revision"],
        "confirmation_token": proof["confirmation_token"],
        "acknowledged_risk_ids": ["ABSTRACT_ONLY"],
    }
    with engine.connect() as conn:
        before = conn.scalar(sa.select(runs.c.payload))
    actor, project, identity = (UUID(before[key]) for key in ("owner_id", "project_id", "id"))
    with engine.begin() as conn:
        accepted = accept_locked(conn, app.state.run_store, actor, project, identity, body)

    def fail_worker(permit):
        if revoke:
            source_id = accepted["candidates"][0]["processing"]["selected_source_id"]
            path = root + "/material-sources/" + source_id + "/classification"
            current = client.get(path).json()["data"]
            changed = post(
                client,
                headers,
                path + "/correct",
                {
                    "expected_revision": current["revision"],
                    "content_revision": current["source"]["content_revision"],
                    "classification": "private",
                    "basis": "限制后续使用",
                    "explicit_confirmation": True,
                },
                "vector-revoke-policy-01",
            )
            assert changed.status_code == 200, changed.text
        raise RuntimeError("worker failed")

    with pytest.raises(RuntimeError):
        build_vector_view(
            app.state.run_store,
            tmp_path,
            actor,
            project,
            identity,
            UUID(accepted["attempt_id"]),
            fail_worker,
        )
    with engine.connect() as conn:
        saved = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == identity))
        assert saved["status"] == "failed"
        assert saved["vector_build_claim"]["state"] == "failed"
        assert saved["vector_build_claim"]["error"] == "VECTOR_BUILD_FAILED"
        assert (
            conn.scalar(sa.select(slots.c.occupant_run_id).where(slots.c.project_id == project))
            is None
        )
        assert conn.scalar(sa.select(sa.func.count()).select_from(vector_views)) == 0
