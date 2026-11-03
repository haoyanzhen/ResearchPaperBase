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


class ZeroPapers(Papers):
    def search(self, *args):
        return super().search(*args) | {"items": []}


def test_zero_retrieval_requires_complete_frozen_sources(subject):
    c, h, _, _, engine, _ = subject
    url, _, _ = baseline_run(subject, 1, ZeroPapers())
    assert confirm(c, h, url)[0].status_code == 200
    rid = UUID(url.rsplit("/", 1)[1])
    with engine.connect() as conn:
        before = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == rid))
    result = before["source_results"][0]
    fact = before["exhausted_sources"][0]
    for patch in (
        {"source_results": []},
        {"source_results": [result | {"status": "failed"}]},
        {"source_results": [result | {"status": "skipped"}]},
        {"source_results": [result | {"limited": True}]},
        {"source_results": [result | {"skipped_date": 1}]},
        {"retrieval_proof_version": None},
        {"exhausted_sources": []},
        {"exhausted_sources": [fact, fact]},
        {"exhausted_sources": [[*fact[:3], False]]},
        {"exhausted_sources": [[*fact[:3], 1]]},
    ):
        with engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == rid).values(payload=before | patch))
        detail = c.get(url).json()["data"]
        assert "baseline_match_preview" not in detail, patch
        assert not detail["waiting_items"][0]["allowed_actions"]
        assert detail["status"] == "waiting_user" and detail["completion"] is None


def test_zero_first_retrieval_has_no_existing_version_to_verify(subject):
    from test_construction_runs import setup
    from test_search_terms import post

    from rpb.adapters.run_worker import RunWorker

    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    path = root + "/construction-runs"
    run = post(c, h, path, body, str(uuid4())).json()["data"]["run"]
    assert RunWorker(app.state.run_store, ZeroPapers()).run_once()
    url = path + "/" + run["id"]
    assert confirm(c, h, url)[0].status_code == 200
    detail = c.get(url).json()["data"]
    assert "baseline_match_preview" not in detail and detail["completion"] is None
    assert not detail["waiting_items"][0]["allowed_actions"]
    with engine.connect() as conn:
        assert not conn.scalar(sa.select(sa.func.count()).select_from(versions))


def test_zero_with_invalid_skipped_count_fails_at_retrieval(subject):
    class InvalidCount(ZeroPapers):
        def search(self, *args):
            return super().search(*args) | {"skipped_date": False}

    c, _, _, _, engine, _ = subject
    url, version, _ = baseline_run(subject, 1, InvalidCount())
    detail = c.get(url).json()["data"]
    assert detail["status"] == "failed" and detail["completion"] is None
    assert (
        detail["steps"][0]["result_summary"]["sources"][0]["error"] == "PROVIDER_RESPONSE_INVALID"
    )
    with engine.connect() as conn:
        assert conn.scalar(sa.select(heads.c.version_id)) == version


def test_excluded_preview_requires_current_verdict_for_each_new_group(subject):
    from test_paper_screening import edit

    class Mixed(Papers):
        def search(self, *args):
            result = super().search(*args)
            paper = result["items"][0]
            result["items"] = [paper | {"title": t} for t in ("graph", "First", "FIRST!", "Second")]
            return result

    c, h, _, _, engine, _ = subject
    url, base, _ = baseline_run(subject, 1, Mixed())
    assert confirm(c, h, url)[0].status_code == 200
    new = [v for v in candidates(c, url) if v["deduplication"]["state"] == "distinct"]
    assert len(new) == 2
    assert edit(c, h, url, new[0], valid=False).status_code == 200
    assert "baseline_match_preview" not in c.get(url).json()["data"]
    assert edit(c, h, url, new[1], valid=False).status_code == 200
    assert c.get(url).json()["data"]["baseline_match_preview"] == {
        "candidate_count": 4,
        "matched_paper_count": 1,
        "excluded_paper_count": 2,
        "base_knowledge_version_id": str(base),
    }
    rid = UUID(url.rsplit("/", 1)[1])
    with engine.connect() as conn:
        original = conn.scalar(sa.select(runs.c.payload).where(runs.c.id == rid))
    for field, changes in [
        ("screening", {"screening_error": "PROVIDER_TIMEOUT"}),
        ("screening", {"screening_stale": True}),
        ("screening", {"screening_modified_by": str(uuid4())}),
        ("screening", {"screening": original["candidates"][-1]["screening"] | {"valid": True}}),
        (
            "duplicate",
            {"screening": original["candidates"][2]["screening"] | {"reason": "conflict"}},
        ),
        ("source", {"retrieval_proof_version": None}),
        ("source", {"exhausted_sources": []}),
    ]:
        changed = copy.deepcopy(original)
        if field == "source":
            changed.update(changes)
        else:
            changed["candidates"][2 if field == "duplicate" else -1].update(changes)
        with engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == rid).values(payload=changed))
        assert "baseline_match_preview" not in c.get(url).json()["data"]
    with engine.begin() as conn:
        conn.execute(runs.update().where(runs.c.id == rid).values(payload=original))
    assert correction(c, h, url, candidates(c, url)[1]).status_code == 200
    assert "baseline_match_preview" not in c.get(url).json()["data"]
