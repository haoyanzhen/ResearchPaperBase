# ruff: noqa: F811
"""PS: real commits and HTTP; model and paper providers are deterministic fakes."""

import copy
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_paper_deduplication import candidates, correction, prepared
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.paper_scoring_worker import ScoreWorker
from rpb.adapters.run_tables import runs


class Scores:
    def __init__(self, outputs=None, hook=None):
        self.outputs = outputs or [7, 0]
        self.calls = []
        self.hook = hook

    def score(self, config, model, secret, inputs, authorize):
        with authorize():
            self.calls.append(copy.deepcopy(inputs))
        if self.hook:
            self.hook()
            self.hook = None
        score = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        if isinstance(score, Exception):
            raise score
        return {"score": score, "theoretical": "theory", "technical": "tech", "relevance": "topic"}


def classify(c, h, root, source_id):
    path = root + "/material-sources/" + source_id + "/classification"
    v = c.get(path).json()["data"]
    r = post(
        c,
        h,
        path + "/confirm",
        {
            "expected_revision": v["revision"],
            "content_revision": v["source"]["content_revision"],
            "classification": "public",
            "basis": "Actual public metadata and topic checked",
            "explicit_confirmation": True,
        },
    )
    assert r.status_code == 200, r.text


def ready_score(subject, classify_all=True):
    c, h, root, app, _, _ = subject
    url, confirm, command = prepared(subject)
    assert post(c, h, confirm, command).status_code == 200
    if classify_all:
        workspace = c.get(root + "/construction-workspace").json()["data"]
        classify(c, h, root, workspace["topic_source"]["source_id"])
        for item in candidates(c, url):
            classify(c, h, root, item["id"])
    return url


def score_request(c, url):
    run = c.get(url).json()["data"]
    return {
        "expected_revision": run["candidate_revision"],
        "candidate_ids": [
            i["id"] for i in candidates(c, url) if i["deduplication"]["state"] == "distinct"
        ],
        "acknowledged_risk_ids": [],
    }


def edit(c, h, url, item, **patch):
    return c.patch(
        url + "/candidates/" + item["id"],
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={
            "expected_revision": item["revision"],
            "screening": {"reason": "human reviewed", **patch},
        },
    )


def test_ps01_group_inputs_scores_metadata_and_frozen_model(subject):
    c, h, _, app, engine, _ = subject
    url = ready_score(subject)
    before = candidates(c, url)
    body = score_request(c, url)
    r = post(c, h, url + "/screening/score", body, "score-accept-00001")
    assert r.status_code == 202, r.text
    assert (
        post(c, h, url + "/screening/score", body, "score-accept-00001").json()["data"]
        == r.json()["data"]
    )
    fake = Scores()
    assert ScoreWorker(app.state.run_store, fake).run_once()
    after = candidates(c, url)
    assert len(fake.calls) == 2
    assert [x["metadata"]["abstract"] for x in fake.calls[0]["sources"]] == [
        "Version 0",
        "Version 1",
    ]
    assert [i["screening"]["score"] for i in after] == [7, 7, 0, None]
    assert [i["screening"]["valid"] for i in after] == [True, True, False, None]
    assert all(a["metadata"] == b["metadata"] for a, b in zip(after, before, strict=True))
    summary = c.get(url).json()["data"]["steps"][0]["result_summary"]["screening"]
    assert summary == dict(valid_count=1, invalid_count=1, pending_count=0, failed_count=0)
    assert c.get(url).json()["data"]["published_knowledge_version_id"] is None
    with engine.connect() as conn:
        data = conn.scalar(sa.select(runs.c.payload))
        job = next(iter(data["scoring_jobs"].values()))
        assert job["config"] == data["model_config"]
        assert {a["boundary"] for a in job["material_audit"]} == {"read", "dispatch", "commit"}
    assert not ScoreWorker(app.state.run_store, fake).run_once()


@pytest.mark.parametrize("bad", [None, True, -1, 11, "7", float("nan")])
def test_ps02_invalid_model_preserves_undetermined(subject, bad):
    c, h, _, app, _, _ = subject
    url = ready_score(subject)
    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 202
    assert ScoreWorker(app.state.run_store, Scores([bad, 10])).run_once()
    items = candidates(c, url)
    assert items[0]["screening"]["score"] is None and items[0]["screening"]["valid"] is None
    assert items[0]["screening_error"] == "PROVIDER_RESPONSE_INVALID"
    assert items[2]["screening"]["score"] == 10


def test_ps03_unconfirmed_sources_reject_no_task(subject):
    c, h, _, _, engine, _ = subject
    url = ready_score(subject, False)
    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 409
    with engine.connect() as conn:
        assert not conn.scalar(sa.select(runs.c.payload)).get("scoring_jobs")


def test_ps04_human_edit_preview_stale_and_failed_regeneration(subject):
    c, h, _, app, _, _ = subject
    url = ready_score(subject)
    item = candidates(c, url)[0]
    r = edit(c, h, url, item, score=8, valid=False)
    assert r.status_code == 200, r.text
    body = score_request(c, url)
    assert post(c, h, url + "/screening/score", body).status_code == 409
    preview = post(
        c,
        h,
        url + "/screening/action-preview",
        {
            "action": "score",
            "expected_revision": body["expected_revision"],
            "candidate_ids": body["candidate_ids"],
        },
    )
    assert preview.status_code == 200, preview.text
    proof = preview.json()["data"]
    assert len(proof["affected_items"]) == 2
    assert proof["affected_items"][0]["content_scope"] == ["screening"]
    before = candidates(c, url)
    body.update(
        confirmation_token=proof["confirmation_token"], acknowledged_risk_ids=["replace_screening"]
    )
    assert post(c, h, url + "/screening/score", body).status_code == 202
    assert edit(c, h, url, before[0], score=2).status_code == 409
    assert correction(c, h, url, before[0]).status_code == 409
    assert ScoreWorker(app.state.run_store, Scores([None])).run_once()
    after = candidates(c, url)
    assert after[0]["screening"] == before[0]["screening"]
    assert after[0]["screening_state"] == "manual_edit"
    # Old group revision and overwrite confirmation cannot be reused for a new command.
    assert post(c, h, url + "/screening/score", body, str(uuid4())).status_code == 412


def test_ps05_cancel_late_output_preserves_human_content(subject):
    c, h, _, app, _, _ = subject
    url = ready_score(subject)
    assert edit(c, h, url, candidates(c, url)[0], score=8).status_code == 200
    body = score_request(c, url)
    proof = post(
        c,
        h,
        url + "/screening/action-preview",
        {
            "action": "score",
            "expected_revision": body["expected_revision"],
            "candidate_ids": body["candidate_ids"],
        },
    ).json()["data"]
    body.update(
        confirmation_token=proof["confirmation_token"], acknowledged_risk_ids=["replace_screening"]
    )
    assert post(c, h, url + "/screening/score", body).status_code == 202
    before = candidates(c, url)

    def cancel():
        run = c.get(url).json()["data"]
        assert (
            post(
                c,
                h,
                url + "/cancel",
                {"expected_revision": run["revision"], "attempt_id": run["task"]["attempt_id"]},
            ).status_code
            == 200
        )

    assert ScoreWorker(app.state.run_store, Scores([10], cancel)).run_once()
    assert candidates(c, url) == before
    assert c.get(url).json()["data"]["status"] == "cancelled"


def test_ps06_dedup_conflicting_human_scores_need_new_judgment(subject):
    c, h, _, _, _, _ = subject
    url = ready_score(subject)
    assert edit(c, h, url, candidates(c, url)[0], score=8, valid=True).status_code == 200
    assert edit(c, h, url, candidates(c, url)[2], score=3, valid=False).status_code == 200
    items = candidates(c, url)
    assert correction(c, h, url, items[2], "match", items[0]["id"]).status_code == 200
    items = candidates(c, url)
    assert items[0]["screening_stale"] and items[2]["screening_stale"]
    stats = c.get(url).json()["data"]["steps"][0]["result_summary"]["screening"]
    assert stats["valid_count"] == stats["invalid_count"] == 0 and stats["pending_count"] == 1
    assert {i["screening"]["score"] for i in items[:3]} == {3, 8}
    assert edit(c, h, url, items[0], score=6, valid=False).status_code == 200
    assert all(i["screening"]["score"] == 6 for i in candidates(c, url)[:3])


def test_ps07_policy_revoked_after_dispatch_rejects_result(subject):
    c, h, root, app, _, _ = subject
    url = ready_score(subject)
    item = candidates(c, url)[0]
    path = root + "/material-sources/" + item["id"] + "/classification"
    v = c.get(path).json()["data"]
    assert (
        post(
            c,
            h,
            path + "/correct",
            dict(
                expected_revision=v["revision"],
                content_revision=v["source"]["content_revision"],
                classification="private",
                basis="Private source correction",
                explicit_confirmation=True,
            ),
        ).status_code
        == 200
    )
    policy = c.get(root + "/material-policy").json()["data"]
    assert (
        c.put(
            root + "/material-policy",
            headers=h,
            json=dict(
                expected_revision=policy["revision"], mode="allow_private", risk_acknowledged=True
            ),
        ).status_code
        == 200
    )
    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 202

    def revoke():
        p = c.get(root + "/material-policy").json()["data"]
        assert (
            c.put(
                root + "/material-policy",
                headers=h,
                json=dict(
                    expected_revision=p["revision"], mode="public_only", risk_acknowledged=False
                ),
            ).status_code
            == 200
        )

    fake = Scores([10], revoke)
    assert ScoreWorker(app.state.run_store, fake).run_once()
    assert len(fake.calls) == 1  # Next dispatch is denied; the first result also cannot commit.
    assert all(i["screening"]["score"] is None for i in candidates(c, url))
    assert c.get(url).json()["data"]["scoring_tasks"][0]["execution_status"] == "failed"


def test_ps08_second_worker_no_duplicate_dispatch_and_locks(subject):
    c, h, _, app, _, _ = subject
    url = ready_score(subject)
    body = score_request(c, url)
    accepted = post(c, h, url + "/screening/score", body)
    assert accepted.status_code == 202
    assert post(c, h, url + "/screening/score", body, str(uuid4())).status_code == 409
    second = Scores()

    def interleave():
        assert not ScoreWorker(app.state.run_store, second).run_once()

    first = Scores([7], interleave)
    assert ScoreWorker(app.state.run_store, first).run_once()
    assert len(first.calls) == 2 and second.calls == []
    task = c.get(accepted.json()["data"]["status_url"])
    assert task.status_code == 200 and task.json()["data"]["execution_status"] == "succeeded"


def test_ps09_failed_receipt_rolls_back_queued_task(subject):
    c, h, _, _, engine, _ = subject
    url = ready_score(subject)
    from sqlalchemy import event

    # Use the real mapped table name, not a mock transaction boundary.
    from rpb.adapters.run_tables import commands

    injected = []

    def inject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO " + commands.name):
            injected.append(True)
            raise RuntimeError("receipt unavailable")

    event.listen(engine, "before_cursor_execute", inject)
    try:
        assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 500
        assert injected == [True]
    finally:
        event.remove(engine, "before_cursor_execute", inject)
    assert not c.get(url).json()["data"]["scoring_tasks"]


@pytest.mark.parametrize(
    "change",
    [
        dict(candidate_ids=[]),
        dict(candidate_ids=[str(uuid4())]),
        dict(model_selection={}),
        dict(expected_revision=str(uuid4())),
    ],
)
def test_ps10_bad_scope_or_revision_never_creates_job(subject, change):
    c, h, _, _, _, _ = subject
    url = ready_score(subject)
    body = score_request(c, url) | change
    assert post(c, h, url + "/screening/score", body).status_code in {404, 412, 422}
    assert not c.get(url).json()["data"]["scoring_tasks"]


def test_ps11_credential_echo_not_persisted_and_human_rescore_success(subject):
    c, h, _, app, engine, _ = subject
    url = ready_score(subject)
    assert edit(c, h, url, candidates(c, url)[0], score=3, valid=False).status_code == 200

    def confirmed():
        body = score_request(c, url)
        proof = post(
            c,
            h,
            url + "/screening/action-preview",
            dict(
                action="score",
                expected_revision=body["expected_revision"],
                candidate_ids=body["candidate_ids"],
            ),
            str(uuid4()),
        ).json()["data"]
        return body | dict(
            confirmation_token=proof["confirmation_token"],
            acknowledged_risk_ids=["replace_screening"],
        )

    class Echo(Scores):
        def score(self, config, model, secret, inputs, authorize):
            result = super().score(config, model, secret, inputs, authorize)
            result["theoretical"] = secret
            return result

    assert post(c, h, url + "/screening/score", confirmed()).status_code == 202
    assert ScoreWorker(app.state.run_store, Echo()).run_once()
    with engine.connect() as conn:
        import json

        assert "SECRET-TERM-KEY" not in json.dumps(conn.scalar(sa.select(runs.c.payload)))
    assert candidates(c, url)[0]["screening"]["score"] == 3
    assert post(c, h, url + "/screening/score", confirmed(), str(uuid4())).status_code == 202
    assert ScoreWorker(app.state.run_store, Scores([10])).run_once()
    item = candidates(c, url)[0]
    assert item["screening"]["score"] == 10 and item["screening"]["valid"] is True
    assert item["screening_state"] == "agent_draft"
    assert any(
        h["screening"]["score"] == 3 and h["state"] == "manual_edit"
        for h in item["screening_history"]
    )

    # Explicit overwrite leaves an agent draft; saved human history still survives cancellation.
    assert (
        post(c, h, url + "/screening/score", score_request(c, url), str(uuid4())).status_code == 202
    )
    assert ScoreWorker(app.state.run_store, Scores([8])).run_once()
    run = c.get(url).json()["data"]
    assert (
        post(
            c,
            h,
            url + "/cancel",
            dict(expected_revision=run["revision"], attempt_id=run["task"]["attempt_id"]),
            str(uuid4()),
        ).status_code
        == 200
    )
    assert any(
        entry["state"] == "manual_edit" and entry["screening"]["score"] == 3
        for entry in candidates(c, url)[0]["screening_history"]
    )


def test_ps12_non_ascii_confirmation(subject):
    c, h, _, _, _, _ = subject
    url = ready_score(subject)
    assert edit(c, h, url, candidates(c, url)[0], valid=False).status_code == 200
    body = score_request(c, url) | dict(
        confirmation_token="2026-10-30T00:00:00Z.汉字", acknowledged_risk_ids=["replace_screening"]
    )
    assert post(c, h, url + "/screening/score", body).status_code == 409


def test_ps13_other_owner_and_missing_csrf_cannot_score_or_edit(subject):
    from test_account_auth import ORIGIN, csrf, login, register
    from test_search_terms import TermsClient

    c, h, _, app, _, _ = subject
    url = ready_score(subject)
    body = score_request(c, url)
    other = TermsClient(app, base_url=ORIGIN)
    headers = csrf(other)
    assert register(other, headers, "Bob", "bob@example.invalid").status_code == 201
    login(other, headers, "Bob")
    headers = csrf(other)
    assert post(other, headers, url + "/screening/score", body).status_code == 404
    assert (
        c.post(
            url + "/screening/score",
            headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
            json=body,
        ).status_code
        == 403
    )
    item = candidates(c, url)[0]
    assert edit(other, headers, url, item, score=2).status_code == 404
    assert candidates(c, url)[0] == item
    assert not c.get(url).json()["data"]["scoring_tasks"]


def test_ps14_cancel_machine_scores_removes_unpublished_text_copies(subject):
    c, h, _, app, engine, _ = subject
    url = ready_score(subject)
    for _ in range(3):
        assert (
            post(c, h, url + "/screening/score", score_request(c, url), str(uuid4())).status_code
            == 202
        )
        assert ScoreWorker(app.state.run_store, Scores()).run_once()
    run = c.get(url).json()["data"]
    assert (
        post(
            c,
            h,
            url + "/cancel",
            dict(expected_revision=run["revision"], attempt_id=run["task"]["attempt_id"]),
        ).status_code
        == 200
    )
    assert candidates(c, url) == []
    with engine.connect() as conn:
        data = conn.scalar(sa.select(runs.c.payload))
        assert all(j["input"] == {} and j["results"] == [] for j in data["scoring_jobs"].values())
    assert c.get(url).json()["data"]["steps"][0]["result_summary"]["screening"]["valid_count"] == 1


def test_ps15_timeout_partial_failure_and_expired_lease(subject):
    from rpb.adapters.llm_provider import ProviderFailure

    c, h, _, app, engine, _ = subject
    url = ready_score(subject)
    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 202
    assert ScoreWorker(
        app.state.run_store, Scores([ProviderFailure("PROVIDER_TIMEOUT"), 7])
    ).run_once()
    values = candidates(c, url)
    assert (
        values[0]["screening"]["score"] is None
        and values[0]["screening_error"] == "PROVIDER_TIMEOUT"
    )
    assert values[2]["screening"]["score"] == 7
    accepted = post(c, h, url + "/screening/score", score_request(c, url), str(uuid4()))
    assert accepted.status_code == 202
    before = candidates(c, url)

    def expire():
        with engine.begin() as conn:
            row = conn.execute(sa.select(runs)).mappings().one()
            payload = copy.deepcopy(row["payload"])
            for job in payload["scoring_jobs"].values():
                if job["state"] == "running":
                    job["lease_until"] = "2000-01-01T00:00:00+00:00"
            conn.execute(runs.update().where(runs.c.id == row["id"]).values(payload=payload))

    assert ScoreWorker(app.state.run_store, Scores([10], expire)).run_once()
    assert candidates(c, url) == before
    assert (
        c.get(accepted.json()["data"]["status_url"]).json()["data"]["error"]["code"]
        == "PROVIDER_FAILED"
    )
    with engine.connect() as conn:
        payload = conn.scalar(sa.select(runs.c.payload))
        task_id = accepted.json()["data"]["task_id"]
        assert payload["scoring_jobs"][task_id]["error"] == "PROVIDER_RESULT_UNKNOWN"


def test_ps16_frozen_parameters_current_rotated_credentials(subject):
    from cryptography.fernet import Fernet

    from rpb.adapters.llm_tables import configs

    c, h, _, app, engine, key = subject
    url = ready_score(subject)
    captured = []
    with engine.begin() as conn:
        row = conn.execute(sa.select(configs)).mappings().one()
        data = copy.deepcopy(row["data"])
        data["parameters"]["temperature"] = 1.5
        conn.execute(
            configs.update()
            .where(configs.c.id == row["id"])
            .values(data=data, secret_ciphertext=Fernet(key).encrypt(b"NEW-SECRET"))
        )

    class Rotated(Scores):
        def score(self, config, model, secret, inputs, authorize):
            captured.append((copy.deepcopy(config), secret))
            return super().score(config, model, secret, inputs, authorize)

    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 202
    assert ScoreWorker(app.state.run_store, Rotated()).run_once()
    assert captured and all(secret == "NEW-SECRET" for _, secret in captured)
    assert all(config["parameters"].get("temperature") != 1.5 for config, _ in captured)
    assert candidates(c, url)[0]["screening"]["score"] == 7


def test_ps17_preview_is_read_only_without_idempotency_key(subject):
    from rpb.adapters.run_tables import commands

    c, h, _, _, engine, _ = subject
    url = ready_score(subject)
    assert edit(c, h, url, candidates(c, url)[0], valid=False).status_code == 200
    body = score_request(c, url)
    request = dict(
        action="score",
        expected_revision=body["expected_revision"],
        candidate_ids=body["candidate_ids"],
    )
    with engine.connect() as conn:
        before = conn.scalar(sa.select(runs.c.payload))
        count = conn.scalar(sa.select(sa.func.count()).select_from(commands))
    for _ in range(2):
        response = c.post(url + "/screening/action-preview", headers=h, json=request)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["risks"]
        assert "idempotency_expires_at" not in response.json()["meta"]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.payload)) == before
        assert conn.scalar(sa.select(sa.func.count()).select_from(commands)) == count


@pytest.mark.parametrize("change", ["expired", "selection", "run", "actor", "revision"])
def test_ps18_confirmation_binds_expiry_scope_and_identity(subject, monkeypatch, change):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters import paper_screening

    c, h, _, _, engine, _ = subject
    url = ready_score(subject)
    assert edit(c, h, url, candidates(c, url)[0], valid=False).status_code == 200
    body = score_request(c, url)
    # Issue a valid preview for another identity/scope or an earlier time, then submit
    # against the actual unchanged Run. No signed payload is hand-forged by this test.
    with engine.connect() as conn:
        original = conn.scalar(sa.select(runs.c.payload))
    preview_run = copy.deepcopy(original)
    if change in {"run", "actor", "revision"}:
        field = {"run": "id", "actor": "owner_id", "revision": "candidate_revision"}[change]
        preview_run[field] = str(uuid4())
    ids = body["candidate_ids"][:1] if change == "selection" else body["candidate_ids"]

    class Earlier(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) - timedelta(minutes=11)

    with monkeypatch.context() as m:
        if change == "expired":
            m.setattr(paper_screening, "datetime", Earlier)
        proof = paper_screening.preview(
            preview_run,
            dict(
                run_id=preview_run["id"],
                action="score",
                expected_revision=preview_run["candidate_revision"],
                candidate_ids=ids,
            ),
        )
    body.update(
        confirmation_token=proof["confirmation_token"], acknowledged_risk_ids=["replace_screening"]
    )
    response = post(c, h, url + "/screening/score", body, str(uuid4()))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFIRMATION_STALE"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.payload)) == original


@pytest.mark.parametrize("boundary", ["read", "dispatch", "commit"])
@pytest.mark.parametrize("revocation", ["account", "project", "classification"])
def test_ps19_current_authority_at_each_scoring_boundary(subject, boundary, revocation):
    from rpb.adapters.account import accounts
    from rpb.adapters.project import projects

    c, h, root, app, engine, _ = subject
    url = ready_score(subject)
    source_id = candidates(c, url)[0]["id"]
    response = post(c, h, url + "/screening/score", score_request(c, url))
    assert response.status_code == 202
    task_id = response.json()["data"]["task_id"]

    def revoke():
        if revocation == "classification":
            path = root + "/material-sources/" + source_id + "/classification"
            view = c.get(path).json()["data"]
            result = post(
                c,
                h,
                path + "/correct",
                dict(
                    expected_revision=view["revision"],
                    content_revision=view["source"]["content_revision"],
                    classification="private",
                    basis="Content classified private before next boundary",
                    explicit_confirmation=True,
                ),
            )
            assert result.status_code == 200
        else:
            with engine.begin() as conn:
                # Deterministic committed governance change, isolated to this fixture's DB.
                if revocation == "account":
                    conn.execute(accounts.update().values(enabled=False))
                else:
                    conn.execute(projects.update().values(status="archived"))

    class BeforeDispatch(Scores):
        def score(self, config, model, secret, inputs, authorize):
            revoke()
            return super().score(config, model, secret, inputs, authorize)

    fake = (
        BeforeDispatch([10])
        if boundary == "dispatch"
        else Scores([10], revoke if boundary == "commit" else None)
    )
    if boundary == "read":
        revoke()
    ScoreWorker(app.state.run_store, fake).run_once()
    assert len(fake.calls) == (1 if boundary == "commit" else 0)
    with engine.connect() as conn:
        payload = conn.scalar(sa.select(runs.c.payload))
        assert payload["scoring_jobs"][task_id]["state"] == "failed"
        assert all(item["screening"]["score"] is None for item in payload["candidates"])
        assert payload["scoring_jobs"][task_id]["results"] == []
