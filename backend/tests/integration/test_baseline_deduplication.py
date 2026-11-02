# ruff: noqa: F811
"""Frozen baseline members are deduplicated before any paper processing."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_construction_runs import Papers, setup
from test_paper_analysis import Generated, generate
from test_paper_deduplication import RepeatedPapers, candidates
from test_paper_processing import Prepared, confirm
from test_paper_screening import Scores, classify, score_request
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.ingestion_confirmation import accept_locked, signature
from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_paper_stage import stage_paper
from rpb.adapters.knowledge_paper_tables import (
    paper_identities,
    paper_identity_titles,
    paper_revisions,
    project_papers,
    version_paper_pins,
)
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.paper_analysis_worker import AnalysisWorker
from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.paper_scoring_worker import ScoreWorker
from rpb.adapters.run_tables import runs
from rpb.adapters.run_worker import RunWorker
from rpb.modules.account_config.application.ports import AccountError


def baseline_run(subject, member_count, provider, *, entry_fields=None, **manifest_fields):
    client, headers, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    seed = post(client, headers, path, body, "baseline-seed-command-01").json()["data"]["run"]
    project_id, seed_id, version_id = UUID(root.rsplit("/", 1)[1]), UUID(seed["id"]), uuid4()
    cancel = post(
        client,
        headers,
        path + "/" + seed["id"] + "/cancel",
        {
            "expected_revision": seed["revision"],
            "attempt_id": seed["task"]["attempt_id"],
        },
        "baseline-seed-cancel-01",
    )
    assert cancel.status_code == 200
    members = [(uuid4(), uuid4(), uuid4()) for _ in range(member_count)]
    manifest = {
        **manifest_fields,
        "papers": [
            {"project_paper_id": str(p), "paper_revision_id": str(r), **(entry_fields or {})}
            for _, p, r in members
        ],
    }
    content = {"metadata": {"title": "graph"}}
    with engine.begin() as conn:
        for identity, paper, revision in members:
            conn.execute(paper_identities.insert().values(id=identity))
            conn.execute(
                paper_identity_titles.insert().values(
                    identity_id=identity, normalized_title="graph"
                )
            )
            conn.execute(
                project_papers.insert().values(
                    id=paper, project_id=project_id, identity_id=identity
                )
            )
            conn.execute(
                paper_revisions.insert().values(
                    id=revision,
                    project_id=project_id,
                    project_paper_id=paper,
                    run_id=seed_id,
                    candidate_id=uuid4(),
                    content=content,
                    digest=content_digest(content),
                )
            )
        conn.execute(
            versions.insert().values(
                id=version_id,
                project_id=project_id,
                source_run_id=seed_id,
                manifest=manifest,
                manifest_digest=content_digest(manifest),
                ready_proof={},
                sealed=False,
                published_at=datetime.now(UTC),
            )
        )
        for _, _, revision in members:
            conn.execute(
                version_paper_pins.insert().values(
                    project_id=project_id,
                    version_id=version_id,
                    paper_revision_id=revision,
                )
            )
        conn.execute(versions.update().where(versions.c.id == version_id).values(sealed=True))
        conn.execute(heads.insert().values(project_id=project_id, version_id=version_id))
    current = post(client, headers, path, body, "baseline-new-command-0001").json()["data"]["run"]
    assert RunWorker(app.state.run_store, provider).run_once()
    url = path + "/" + current["id"]
    return url, version_id, members


@pytest.mark.parametrize("member_count", [1, 2])
def test_baseline_match_blocks_processing_and_allows_explicit_correction(subject, member_count):
    client, headers, _, _, _, _ = subject
    url, _, members = baseline_run(subject, member_count, Papers())
    assert confirm(client, headers, url)[0].status_code == 200
    item = candidates(client, url)[0]
    assert item["deduplication"]["state"] == (
        "match_existing" if member_count == 1 else "needs_existing_resolution"
    )
    assert len(item["deduplication"]["baseline_matches"]) == member_count
    assert not item.get("processing")
    run = client.get(url).json()["data"]
    rejected = post(
        client,
        headers,
        url + "/screening/score",
        {
            "expected_revision": run["candidate_revision"],
            "candidate_ids": [item["id"]],
            "acknowledged_risk_ids": [],
        },
        "baseline-block-score-01",
    )
    assert rejected.status_code == 409
    matched = post(
        client,
        headers,
        url + "/candidates/" + item["id"] + "/deduplication-decision",
        {
            "expected_revision": item["revision"],
            "decision": "match",
            "matched_project_asset_id": str(members[0][1]),
            "reason": "核对已有论文",
        },
        "baseline-match-existing-01",
    )
    assert matched.status_code == 200, matched.text
    item = matched.json()["data"]
    assert item["deduplication"]["state"] == "match_existing"
    assert item["deduplication"]["history"][-1]["matched_project_asset_id"] == str(members[0][1])
    response = post(
        client,
        headers,
        url + "/candidates/" + item["id"] + "/deduplication-decision",
        {
            "expected_revision": item["revision"],
            "decision": "distinct",
            "reason": "不同论文",
        },
        "baseline-distinct-cmd-01",
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["deduplication"]["state"] == "distinct"


@pytest.mark.parametrize(
    "manifest_fields",
    [{}, {"materials": []}, {"materials": [str(UUID(int=1))]}, {"materials": None}],
)
def test_incremental_confirmation_freezes_retained_revisions_before_staging(
    subject, manifest_fields
):
    client, headers, root, app, engine, _ = subject
    url, version, members = baseline_run(subject, 2, RepeatedPapers(), **manifest_fields)
    assert confirm(client, headers, url)[0].status_code == 200
    store = app.state.run_store
    classify(
        client,
        headers,
        root,
        client.get(root + "/construction-workspace").json()["data"]["topic_source"]["source_id"],
    )
    for item in candidates(client, url):
        classify(client, headers, root, item["id"])
    assert (
        post(client, headers, url + "/screening/score", score_request(client, url)).status_code
        == 202
    )
    assert ScoreWorker(store, Scores()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    assert ProcessingWorker(store, Prepared()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200
    assert generate(client, headers, url).status_code == 202
    assert AnalysisWorker(store, Generated()).run_once()
    assert confirm(client, headers, url)[0].status_code == 200

    preview = client.get(url + "/ingestion-preview").json()["data"]
    assert preview["base_knowledge_version_id"] == str(version)
    wait = preview["waiting_item"]
    assert not wait["allowed_actions"]
    body = {
        key: wait["confirmation"][key]
        for key in ("subject_revision", "candidate_revision", "confirmation_token")
    }
    body.update(
        waiting_item_id=wait["id"],
        expected_revision=wait["revision"],
        acknowledged_risk_ids=["ABSTRACT_ONLY"],
    )
    run_id = UUID(url.rsplit("/", 1)[1])
    project = UUID(root.rsplit("/", 1)[1])
    query = sa.select(runs.c.payload).where(runs.c.id == run_id)
    with engine.connect() as conn:
        before = conn.scalar(query)
    actor = UUID(before["owner_id"])
    if manifest_fields.get("materials", []) != []:
        with pytest.raises(AccountError, match="STATE_OPERATION_NOT_ALLOWED"):
            with engine.begin() as conn:
                accept_locked(conn, store, actor, project, run_id, body)
        with engine.connect() as conn:
            assert conn.scalar(query) == before
        return
    expires = body["confirmation_token"].rsplit(".", 1)[0]
    for change in (
        {"mode": "revision_only"},
        {"pending_revision_ids": [str(uuid4())]},
        {"supplement_ids": [str(uuid4())]},
    ):
        changed = before | {"input_snapshot": before["input_snapshot"] | change}
        with pytest.raises(AccountError, match="STATE_OPERATION_NOT_ALLOWED"):
            with engine.begin() as conn:
                conn.execute(runs.update().where(runs.c.id == run_id).values(payload=changed))
                accept_locked(
                    conn,
                    store,
                    actor,
                    project,
                    run_id,
                    body
                    | {
                        "confirmation_token": expires
                        + "."
                        + signature(changed, str(actor), expires)
                    },
                )
    with pytest.raises(AccountError, match="STATE_CONFIRMATION_STALE"):
        with engine.begin() as conn:
            conn.execute(
                runs.update()
                .where(runs.c.id == run_id)
                .values(payload=before | {"baseline_papers": []})
            )
            accept_locked(conn, store, actor, project, run_id, body)
    with engine.begin() as conn:
        assert conn.scalar(query) == before
        saved = accept_locked(conn, store, actor, project, run_id, body)
    retained = saved["ingestion_confirmation"]["retained_papers"]
    assert [(p["project_paper_id"], p["paper_revision_id"]) for p in retained] == sorted(
        (str(p), str(r)) for _, p, r in members
    )
    candidate = UUID(preview["valid_papers"][0])
    attempt = UUID(saved["attempt_id"])
    with pytest.raises(AccountError, match="STATE_REVISION_CONFLICT"):
        with engine.begin() as conn:
            bad = saved | {
                "ingestion_confirmation": saved["ingestion_confirmation"] | {"retained_papers": []}
            }
            conn.execute(runs.update().where(runs.c.id == run_id).values(payload=bad))
            stage_paper(conn, store, actor, project, run_id, attempt, candidate)
    with engine.begin() as conn:
        staged = stage_paper(conn, store, actor, project, run_id, attempt, candidate)
        assert staged["project_paper_id"] not in {str(p) for _, p, _ in members}
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.select(heads.c.version_id).where(heads.c.project_id == project))
            == version
        )
        assert set(
            conn.scalars(
                sa.select(version_paper_pins.c.paper_revision_id).where(
                    version_paper_pins.c.version_id == version
                )
            )
        ) == {r for _, _, r in members}
        assert conn.scalar(sa.select(sa.func.count()).select_from(versions)) == 1


def test_incremental_rejects_manifest_that_disagrees_with_pinned_paper_content(subject):
    client, headers, _, _, engine, _ = subject
    url, version, _ = baseline_run(subject, 1, Papers(), entry_fields={"digest": "0" * 64})
    before = client.get(url).json()["data"]
    rejected = confirm(client, headers, url)[0]
    assert rejected.status_code == 410
    assert rejected.json()["error"]["code"] == "STORAGE_FILE_UNAVAILABLE"
    root = url.split("/construction-runs/")[0]
    papers = client.get(root + "/papers", params={"knowledge_version_id": str(version)})
    assert papers.status_code == 410
    assert papers.json()["error"]["code"] == "STORAGE_FILE_UNAVAILABLE"
    assert client.get(url).json()["data"]["candidate_revision"] == before["candidate_revision"]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(heads.c.version_id)) == version
