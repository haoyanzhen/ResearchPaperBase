# ruff: noqa: F811
"""Frozen baseline members are deduplicated before any paper processing."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from test_construction_runs import Papers, setup
from test_paper_deduplication import candidates
from test_paper_processing import confirm
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.knowledge_baseline_papers import content_digest
from rpb.adapters.knowledge_paper_tables import (
    paper_identities,
    paper_identity_titles,
    paper_revisions,
    project_papers,
    version_paper_pins,
)
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_worker import RunWorker


@pytest.mark.parametrize("member_count", [1, 2])
def test_baseline_match_blocks_processing_and_allows_explicit_correction(subject, member_count):
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
        "papers": [{"project_paper_id": str(p), "paper_revision_id": str(r)} for _, p, r in members]
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
    assert RunWorker(app.state.run_store, Papers()).run_once()
    url = path + "/" + current["id"]
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
