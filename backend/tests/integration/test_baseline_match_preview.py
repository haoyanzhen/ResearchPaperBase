# ruff: noqa: F811
"""A fully matched retrieval can be inspected without completing or locking its Run."""

import copy
from uuid import UUID, uuid4

import sqlalchemy as sa
from test_baseline_deduplication import baseline_run
from test_construction_runs import Papers
from test_paper_deduplication import candidates, correction
from test_paper_processing import confirm
from test_search_terms import subject  # noqa: F401

from rpb.adapters.knowledge_build_tables import publication_events
from rpb.adapters.knowledge_tables import heads, versions
from rpb.adapters.run_tables import runs, slots


class SamePaperTwice(Papers):
    def search(self, *args):
        result = super().search(*args)
        result["items"].append(
            result["items"][0]
            | {
                "title": "GRAPH!",
                "url": "https://arxiv.org/abs/2601.11111",
                "arxiv_id": "2601.11111",
            }
        )
        return result


def test_preview_is_bound_to_candidates_sources_and_pins(subject):
    c, h, root, app, engine, _ = subject
    url, version, _ = baseline_run(subject, 1, SamePaperTwice())
    assert "baseline_match_preview" not in c.get(url).json()["data"]
    assert confirm(c, h, url)[0].status_code == 200
    run_id = UUID(url.rsplit("/", 1)[1])
    query = sa.select(runs.c.payload).where(runs.c.id == run_id)
    with engine.connect() as conn:
        before = conn.scalar(query)
    preview = {
        "base_knowledge_version_id": str(version),
        "candidate_count": 2,
        "matched_paper_count": 1,
    }
    for _ in range(2):
        detail = c.get(url).json()["data"]
        assert detail["baseline_match_preview"] == preview
        assert detail["phase"] == "screening" and detail["status"] == "waiting_user"
        assert detail["completion"] is None and detail["published_knowledge_version_id"] is None
        assert not detail["waiting_items"][0]["allowed_actions"]
    with engine.connect() as conn:
        assert conn.scalar(query) == before
        assert conn.scalar(sa.select(heads.c.version_id)) == version
        assert conn.scalar(sa.select(sa.func.count()).select_from(versions)) == 1
        assert not conn.scalar(sa.select(publication_events.c.version_id))
        assert conn.scalar(sa.select(slots.c.occupant_run_id)) == run_id
    # All projected candidates remain editable after seeing a zero-addition preview.
    assert correction(c, h, url, candidates(c, url)[0]).status_code == 200
    assert "baseline_match_preview" not in c.get(url).json()["data"]

    def persist(payload):
        with engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == run_id).values(payload=payload))

    for patch in (
        {"status": "failed"},
        {"status": "skipped"},
        {"count": 1},
        {"limited": True},
        {"skipped_date": 1},
        {"config_id": str(uuid4())},
    ):
        altered = copy.deepcopy(before)
        altered["source_results"][0].update(patch)
        persist(altered)
        assert "baseline_match_preview" not in c.get(url).json()["data"], patch
    for key, value in (
        ("exhausted_sources", []),
        ("source_results", []),
        ("source_results", before["source_results"] * 2),
        ("candidates", []),
        ("baseline_papers", []),
        ("baseline_loaded_version_id", str(uuid4())),
    ):
        persist(before | {key: value})
        assert "baseline_match_preview" not in c.get(url).json()["data"], key
    for change in (
        "leader",
        "group",
        "asset",
        "resolution",
        "term_policy",
        "retrieval_mode",
        "missing_attestation",
    ):
        altered = copy.deepcopy(before)
        decision = altered["candidates"][0]["deduplication"]
        if change == "leader":
            altered["dedup_group_leaders"][decision["group_id"]] = altered["candidates"][1]["id"]
        elif change == "group":
            altered["candidates"][1]["deduplication"]["group_id"] = str(uuid4())
        elif change == "asset":
            decision["matched_project_asset_id"] = str(uuid4())
        elif change == "resolution":
            term = altered["resolution"]["executable"][0]
            term["rejected"] = [
                term["sources"][0]
                | {
                    "config_id": str(uuid4()),
                    "enabled": False,
                    "reason_code": "CONFIG_CONNECTION_FAILED",
                }
            ]
        elif change == "term_policy":
            altered["input_snapshot"]["selected_terms"][0]["content"]["source_policy"] = {
                "mode": "selected",
                "source_refs": [{"source": "user", "config_id": str(uuid4())}],
            }
        elif change == "retrieval_mode":
            altered["input_snapshot"]["graph_mode"] = "rebuild"
        else:
            del altered["exhausted_sources"]
        persist(altered)
        assert "baseline_match_preview" not in c.get(url).json()["data"], change
    persist(before)
    assert c.get(url).json()["data"]["baseline_match_preview"] == preview
