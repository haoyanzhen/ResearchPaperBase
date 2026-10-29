# ruff: noqa: F811
"""PD requirements: committed HTTP decisions, no knowledge writes, preserved sources."""

import copy
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_construction_runs import Papers, setup
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.run_tables import commands, runs
from rpb.adapters.run_worker import RunWorker


class RepeatedPapers(Papers):
    def search(self, *args):
        result = super().search(*args)
        base = result["items"][0]
        result["items"] = [
            base | {"title": title, "doi": f"10.1/{i}", "abstract": f"Version {i}"}
            for i, title in enumerate(["A: PAPER!", "a paper", "Different", "—。"])
        ]
        return result


def prepared(subject):
    c, h, root, app, _, _ = subject
    body, _ = setup(subject)
    accepted = post(c, h, root + "/construction-runs", body, "dedup-start-000001").json()["data"]
    assert RunWorker(app.state.run_store, RepeatedPapers()).run_once()
    url = root + "/construction-runs/" + accepted["run"]["id"]
    run = c.get(url).json()["data"]
    wait = run["waiting_items"][0]
    proof = wait["confirmation"]
    command = {
        k: proof[k] for k in ("subject_revision", "candidate_revision", "confirmation_token")
    }
    command.update(expected_revision=wait["revision"], acknowledged_risk_ids=[])
    return url, url + "/waiting-items/" + wait["id"] + "/confirm", command


def candidates(c, url):
    response = c.get(url + "/candidates")
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def correction(c, h, url, item, decision="distinct", target=None, key=None):
    body = {"expected_revision": item["revision"], "decision": decision, "reason": "human checked"}
    if target:
        body["matched_candidate_id"] = target
        body["matched_candidate_revision"] = next(
            (x["revision"] for x in candidates(c, url) if x["id"] == target), str(uuid4())
        )
    return post(
        c,
        h,
        url + "/candidates/" + item["id"] + "/deduplication-decision",
        body,
        key or str(uuid4()),
    )


def test_pd01_confirm_groups_and_preserves_raw_metadata(subject):
    c, h, _, _, engine, _ = subject
    url, confirm, body = prepared(subject)
    before = candidates(c, url)
    result = post(c, h, confirm, body, "dedup-confirm-00001")
    assert result.status_code == 200, result.text
    run = result.json()["data"]["run"]
    assert run["phase"] == "screening" and run["status"] == "waiting_user"
    assert run["steps"][0]["result_summary"]["deduplication"] == {
        "unique_count": 2,
        "duplicate_count": 1,
        "unresolved_count": 1,
    }
    after = candidates(c, url)
    for old, new in zip(before, after, strict=True):
        assert all(old[k] == new[k] for k in ("metadata", "source", "screening", "id"))
    assert after[0]["deduplication"]["group_id"] == after[1]["deduplication"]["group_id"]
    assert run["published_knowledge_version_id"] is None
    with engine.connect() as conn:
        row = conn.execute(sa.select(runs.c.payload)).scalar_one()
        assert row["retrieval_confirmation"]["candidate_revision"] == body["candidate_revision"]
    assert post(c, h, confirm, body, "dedup-confirm-00001").json()["data"] == result.json()["data"]
    assert post(c, h, confirm, body, "dedup-confirm-00002").status_code == 409


def test_pd02_human_split_merge_history_revisions_and_cancel(subject):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    first = candidates(c, url)
    split = correction(c, h, url, first[1], key="dedup-split-000001")
    assert split.status_code == 200, split.text
    assert split.json()["data"]["deduplication"]["origin"] == "human"
    assert (
        correction(c, h, url, first[1], key="dedup-split-000001").json()["data"]
        == split.json()["data"]
    )
    assert correction(c, h, url, first[1]).status_code == 412
    after = candidates(c, url)
    assert after[0]["revision"] != first[0]["revision"]
    assert after[0]["deduplication"]["group_id"] != after[1]["deduplication"]["group_id"]
    merged = correction(c, h, url, after[1], "match", after[0]["id"])
    assert merged.status_code == 200, merged.text
    history = merged.json()["data"]["deduplication"]["history"]
    assert [d["decision"] for d in history] == ["distinct", "match"]
    assert all(d["reason"] == "human checked" and d["actor_id"] and d["at"] for d in history)
    run = c.get(url).json()["data"]
    assert run["steps"][0]["result_summary"]["deduplication"]["duplicate_count"] == 1
    before_cancel = candidates(c, url)
    cancel = post(
        c,
        h,
        url + "/cancel",
        {"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
        "dedup-cancel-00001",
    )
    assert cancel.status_code == 200, cancel.text
    assert candidates(c, url) == before_cancel  # preserve human evidence and its source closure
    assert correction(c, h, url, before_cancel[0]).status_code == 409


@pytest.mark.parametrize(
    "field",
    [
        "expected_revision",
        "subject_revision",
        "candidate_revision",
        "confirmation_token",
        "acknowledged_risk_ids",
    ],
)
def test_pd03_bad_confirmation_never_writes(subject, field):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    original = copy.deepcopy(c.get(url).json()["data"])
    body[field] = ["unknown-risk"] if field == "acknowledged_risk_ids" else str(uuid4())
    assert post(c, h, confirm, body).status_code in {409, 412, 422}
    after = c.get(url).json()["data"]
    assert after["revision"] == original["revision"] and after["phase"] == "retrieval"
    assert all("deduplication" not in x for x in candidates(c, url))


def test_pd04_invalid_targets_idempotency_and_scope(subject):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    first = candidates(c, url)
    assert correction(c, h, url, first[0]).status_code == 409
    assert post(c, h, confirm, body).status_code == 200
    first = candidates(c, url)
    for target, status in [(str(uuid4()), 404), (first[0]["id"], 409), (first[3]["id"], 409)]:
        assert correction(c, h, url, first[0], "match", target).status_code == status
    assert correction(c, h, url, first[0], key="dedup-key-00000001").status_code == 200
    assert (
        correction(
            c, h, url, first[0], "match", first[1]["id"], key="dedup-key-00000001"
        ).status_code
        == 409
    )
    other_url = url.replace(url.split("/")[4], str(uuid4()))
    assert c.get(other_url + "/candidates").status_code == 404
    assert correction(c, h, other_url, first[0]).status_code == 404


def test_pd05_receipt_failure_rolls_back_decision(subject, monkeypatch):
    c, h, _, _, engine, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    first = candidates(c, url)
    with engine.connect() as conn:
        persisted_before = conn.execute(sa.select(runs.c.payload)).scalar_one()["candidates"]
    from sqlalchemy.engine import Connection

    execute = Connection.execute

    def fail(self, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and getattr(statement, "table", None) is commands:
            raise RuntimeError("receipt fault")
        return execute(self, statement, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", fail)
        assert correction(c, h, url, first[1]).status_code == 500
    assert candidates(c, url) == first
    with engine.connect() as conn:
        assert (
            conn.execute(sa.select(runs.c.payload)).scalar_one()["candidates"] == persisted_before
        )


def test_pd06_concurrent_corrections_serialize_and_reject_stale(subject, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from rpb.adapters import paper_deduplication

    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    item = candidates(c, url)[1]
    entered, release, submitted = Event(), Event(), Event()
    original = paper_deduplication.correct

    def pause(run, data, actor):
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return original(run, data, actor)

    monkeypatch.setattr(paper_deduplication, "correct", pause)

    def second():
        submitted.set()
        return correction(c, h, url, item, key="dedup-race-0000002")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(correction, c, h, url, item, key="dedup-race-0000001")
        assert entered.wait(10)
        other = pool.submit(second)
        assert submitted.wait(10)
        release.set()
        assert first.result(10).status_code == 200
        assert other.result(10).status_code == 412
    assert len(candidates(c, url)[1]["deduplication"]["history"]) == 1


def test_pd07_cancel_automatic_group_cleans_bodies_preserves_counts(subject):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    run = c.get(url).json()["data"]
    expected = run["steps"][0]["result_summary"]["deduplication"]
    assert (
        post(
            c,
            h,
            url + "/cancel",
            {"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
            "dedup-clean-000001",
        ).status_code
        == 200
    )
    assert candidates(c, url) == []
    assert c.get(url).json()["data"]["steps"][0]["result_summary"]["deduplication"] == expected


def test_pd08_stale_merge_target_is_rejected(subject):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    first = candidates(c, url)
    # A is in an unrelated group. B changes before A's old-page merge is submitted.
    assert correction(c, h, url, first[0], "match", first[2]["id"]).status_code == 200
    body = {
        "expected_revision": first[3]["revision"],
        "decision": "match",
        "matched_candidate_id": first[0]["id"],
        "matched_candidate_revision": first[0]["revision"],
        "reason": "old page selection",
    }
    before = candidates(c, url)
    response = post(
        c,
        h,
        url + "/candidates/" + first[3]["id"] + "/deduplication-decision",
        body,
        "dedup-stale-target1",
    )
    assert response.status_code == 412, response.text
    assert candidates(c, url) == before


def test_pd09_non_ascii_signature_is_rejected(subject):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    expiry = body["confirmation_token"].rsplit(".", 1)[0]
    body["confirmation_token"] = expiry + ".中文"
    response = post(c, h, confirm, body)
    assert response.status_code == 409, response.text
    assert c.get(url).json()["data"]["phase"] == "retrieval"


def test_pd10_other_user_and_csrf_denied_without_mutation(subject):
    from test_account_auth import ORIGIN, csrf, login, register
    from test_search_terms import TermsClient

    c, h, _, app, _, _ = subject
    url, confirm, body = prepared(subject)
    other = TermsClient(app, base_url=ORIGIN)
    headers = csrf(other)
    assert register(other, headers, "Bob", "bob@example.invalid").status_code == 201
    login(other, headers, "Bob")
    headers = csrf(other)
    assert post(other, headers, confirm, body).status_code == 404
    assert (
        c.post(
            confirm, headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}, json=body
        ).status_code
        == 403
    )
    assert c.get(url).json()["data"]["phase"] == "retrieval"
    assert post(c, h, confirm, body).status_code == 200
    item = candidates(c, url)[1]
    assert correction(other, headers, url, item).status_code == 404
    assert candidates(c, url)[1] == item


def test_pd11_archive_preserves_human_decisions_but_rejects_new_writes(subject):
    from test_construction_runs import archive

    c, h, root, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    item = candidates(c, url)[1]
    assert correction(c, h, url, item).status_code == 200
    before = candidates(c, url)
    assert archive(c, h, root).status_code == 200
    assert c.get(url).json()["data"]["status"] == "cancelled"
    assert candidates(c, url) == before
    assert correction(c, h, url, before[1]).status_code == 409


def test_pd12_expired_correctly_signed_confirmation_rejected(subject):
    import hmac
    from datetime import UTC, datetime, timedelta

    c, h, _, _, engine, _ = subject
    url, confirm, body = prepared(subject)
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
    expires = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    wait = run["waiting"]
    basis = ":".join([run["owner_id"], run["project_id"], wait["id"], wait["revision"], expires])
    signature = hmac.new(run["confirmation_secret"].encode(), basis.encode(), "sha256").hexdigest()
    body["confirmation_token"] = expires + "." + signature
    assert post(c, h, confirm, body).status_code == 409
    assert c.get(url).json()["data"]["phase"] == "retrieval"


def test_pd13_real_other_run_candidates_and_token_cannot_cross_scope(subject):
    from test_project_commands import create

    from rpb.adapters.source_tables import dispatch_limits

    c, h, _, app, engine, key = subject
    url, confirm, body = prepared(subject)
    project = create(c, h, key="dedup-second-project").json()["data"]
    second_root = "/api/v1/projects/" + project["id"]
    with engine.begin() as conn:
        conn.execute(dispatch_limits.delete())
    other_url, other_confirm, other_body = prepared((c, h, second_root, app, engine, key))
    # Both tokens are currently valid, but only for their original Run/input.
    assert (
        post(
            c,
            h,
            confirm,
            body | {"confirmation_token": other_body["confirmation_token"]},
            "dedup-foreign-token",
        ).status_code
        == 409
    )
    assert c.get(url).json()["data"]["phase"] == "retrieval"
    assert post(c, h, confirm, body, "dedup-confirm-first").status_code == 200
    assert post(c, h, other_confirm, other_body, "dedup-confirm-other").status_code == 200
    own, foreign = candidates(c, url), candidates(c, other_url)
    command = {
        "expected_revision": own[0]["revision"],
        "decision": "match",
        "reason": "wrong Run",
        "matched_candidate_id": foreign[0]["id"],
        "matched_candidate_revision": foreign[0]["revision"],
    }
    response = post(
        c,
        h,
        url + "/candidates/" + own[0]["id"] + "/deduplication-decision",
        command,
        "dedup-foreign-match",
    )
    assert response.status_code == 404, response.text
    assert candidates(c, url) == own and candidates(c, other_url) == foreign


@pytest.mark.parametrize("decision", ["distinct", "match"])
def test_pd14_empty_title_human_decision_retains_original_source(subject, decision):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    first = candidates(c, url)
    result = correction(
        c, h, url, first[3], decision, first[0]["id"] if decision == "match" else None
    )
    assert result.status_code == 200, result.text
    after = result.json()["data"]
    assert after["metadata"] == first[3]["metadata"] and after["source"] == first[3]["source"]
    assert after["deduplication"]["normalized_title"] is None
    assert after["deduplication"]["origin"] == "human"
    summary = c.get(url).json()["data"]["steps"][0]["result_summary"]["deduplication"]
    assert summary == {
        "unique_count": 3 if decision == "distinct" else 2,
        "duplicate_count": 1 if decision == "distinct" else 2,
        "unresolved_count": 0,
    }


@pytest.mark.parametrize("mode", ["match_missing_revision", "distinct_with_target", "blank_reason"])
def test_pd15_invalid_correction_fields_never_write(subject, mode):
    c, h, _, _, _, _ = subject
    url, confirm, body = prepared(subject)
    assert post(c, h, confirm, body).status_code == 200
    first = candidates(c, url)
    command = {
        "expected_revision": first[1]["revision"],
        "decision": "distinct",
        "reason": "reviewed",
    }
    if mode == "match_missing_revision":
        command.update(decision="match", matched_candidate_id=first[0]["id"])
    elif mode == "distinct_with_target":
        command.update(
            matched_candidate_id=first[0]["id"], matched_candidate_revision=first[0]["revision"]
        )
    else:
        command["reason"] = " \t"
    result = post(
        c,
        h,
        url + "/candidates/" + first[1]["id"] + "/deduplication-decision",
        command,
        "dedup-invalid-fields",
    )
    assert result.status_code in {422, 428}, result.text
    assert candidates(c, url) == first
