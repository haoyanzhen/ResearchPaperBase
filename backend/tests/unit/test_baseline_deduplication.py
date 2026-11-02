"""Human identity decisions must not depend on candidate list order."""

from uuid import uuid4

from rpb.adapters import paper_deduplication as dedup


def test_merge_into_human_distinct_group_keeps_explicit_leader():
    first, second = str(uuid4()), str(uuid4())
    run = {
        "status": "waiting_user",
        "input_snapshot": {"base_knowledge_version_id": None},
        "candidate_version": {"revision": str(uuid4())},
        "candidates": [
            {
                "id": identity,
                "revision": str(uuid4()),
                "metadata": {"title": "Same"},
                "screening": {"score": None, "valid": None},
            }
            for identity in (first, second)
        ],
    }
    dedup.initialize(
        run,
        [
            {
                "project_paper_id": str(uuid4()),
                "paper_revision_id": str(uuid4()),
                "normalized_title": "same",
            }
        ],
    )
    a, b = run["candidates"]
    dedup.correct(
        run,
        {
            "run_id": "r",
            "candidate_id": b["id"],
            "expected_revision": b["revision"],
            "decision": "distinct",
            "reason": "human checked",
        },
        "actor",
    )
    dedup.correct(
        run,
        {
            "run_id": "r",
            "candidate_id": a["id"],
            "expected_revision": a["revision"],
            "decision": "match",
            "matched_candidate_id": b["id"],
            "matched_candidate_revision": b["revision"],
            "reason": "same as distinct",
        },
        "actor",
    )
    assert b["deduplication"]["state"] == "distinct"
    assert a["deduplication"]["state"] == "match"
    assert a["deduplication"]["matched_candidate_id"] == b["id"]
    asset = run["baseline_papers"][0]["project_paper_id"]
    dedup.correct(
        run,
        {
            "run_id": "r",
            "candidate_id": b["id"],
            "expected_revision": b["revision"],
            "decision": "match",
            "matched_project_asset_id": asset,
            "reason": "different group",
        },
        "actor",
    )
    assert b["deduplication"]["state"] == "match_existing"
    assert a["deduplication"]["state"] == "distinct"
    assert a["deduplication"]["baseline_resolution"] == "distinct"
    inherited = a["deduplication"]["history"][-1]
    assert inherited["inherited_from_candidate_id"] == b["id"]
    assert inherited["reason"] == "human checked" and inherited["actor_id"] == "actor"


def test_matching_current_leader_to_group_member_respects_selected_target():
    first, second = str(uuid4()), str(uuid4())
    run = {
        "status": "waiting_user",
        "input_snapshot": {"base_knowledge_version_id": None},
        "candidate_version": {"revision": str(uuid4())},
        "candidates": [
            {
                "id": identity,
                "revision": str(uuid4()),
                "metadata": {"title": "Same"},
                "screening": {"score": None, "valid": None},
            }
            for identity in (first, second)
        ],
    }
    dedup.initialize(run, [])
    a, b = run["candidates"]
    dedup.correct(
        run,
        {
            "run_id": "r",
            "candidate_id": a["id"],
            "expected_revision": a["revision"],
            "decision": "match",
            "matched_candidate_id": b["id"],
            "matched_candidate_revision": b["revision"],
            "reason": "retain second source",
        },
        "actor",
    )
    assert b["deduplication"]["state"] == "distinct"
    assert a["deduplication"]["matched_candidate_id"] == b["id"]
