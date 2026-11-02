# ruff: noqa: F811
"""PA02–05: isolated PostgreSQL, actual commits and deterministic interleavings."""

import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from test_paper_deduplication import candidates
from test_paper_processing import Prepared, confirm, confirmed_score
from test_paper_screening import edit as edit_score
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.analysis_lineage import currently_usable
from rpb.adapters.paper_analysis_worker import AnalysisWorker
from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.project import projects
from rpb.adapters.run_tables import commands, runs
from rpb.adapters.search_terms import load


def output():
    return dict(
        one_sentence_summary="研究结论",
        highlights=["亮点"],
        relevance_points=["主题关联"],
        methods="摘要未提供完整方法",
        innovations=[],
    )


class Generated:
    def __init__(self, hook=None, malformed=False):
        self.hook, self.malformed, self.calls = hook, malformed, []

    def generate(self, config, model, secret, inputs, authorize):
        with authorize():
            self.calls.append(copy.deepcopy(inputs))
        if self.hook:
            self.hook()
        return {"one_sentence_summary": "partial"} if self.malformed else output()


def ready(subject):
    c, h, _, app, _, _ = subject
    url = confirmed_score(subject)
    assert confirm(c, h, url)[0].status_code == 200
    assert ProcessingWorker(app.state.run_store, Prepared()).run_once()
    assert confirm(c, h, url)[0].status_code == 200
    return url


def generate(c, h, url, item=None, proof=None, key=None):
    item = item or candidates(c, url)[0]
    body = dict(expected_revision=item["revision"], acknowledged_risk_ids=[])
    if proof:
        body.update(
            confirmation_token=proof["confirmation_token"],
            acknowledged_risk_ids=[r["id"] for r in proof["risks"]],
        )
    return post(
        c, h, url + "/candidates/" + item["id"] + "/analysis/generate", body, key or str(uuid4())
    )


def manual(c, h, url, value=None, item=None):
    item = item or candidates(c, url)[0]
    return c.patch(
        url + "/candidates/" + item["id"],
        headers={**h, "Idempotency-Key": str(uuid4())},
        json={"expected_revision": item["revision"], "analysis": value or output()},
    )


def test_pa10_confirmed_text_generation_basis_and_no_publish(subject):
    c, h, _, app, engine, _ = subject
    url = ready(subject)
    item = candidates(c, url)[0]
    r = generate(c, h, url, key="pa10-generation-command")
    assert r.status_code == 202, r.text
    assert (
        generate(c, h, url, item, key="pa10-generation-command").json()["data"] == r.json()["data"]
    )
    provider = Generated()
    worker = AnalysisWorker(app.state.run_store, provider)
    assert worker.run_once()
    assert not worker.run_once()
    assert len(provider.calls) == 1
    assert provider.calls[0]["text"] == "Version 0"
    assert provider.calls[0]["text_source_kind"] == "abstract_fallback"
    item = candidates(c, url)[0]
    assert item["analysis"] == output() and item["analysis_state"] == "agent_draft"
    assert (
        item["analysis_basis"]["text_revision_id"]
        == item["processing"]["basis"]["text_revision_id"]
    )
    assert item["analysis_current"]
    task = c.get(r.json()["data"]["status_url"]).json()["data"]
    assert task["execution_status"] == "succeeded"
    accepted, _, _ = confirm(c, h, url)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["run"]["phase"] == "ingestion_preview"
    assert accepted.json()["data"]["run"]["published_knowledge_version_id"] is None
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        assert set(
            x["boundary"] for x in next(iter(run["analysis_jobs"].values()))["material_audit"]
        ) == {"read", "dispatch", "commit"}


def test_analysis_revision_records_actual_job_and_manual_parent_dependencies(subject):
    c, h, _, app, engine, _ = subject
    url = ready(subject)
    assert generate(c, h, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        project = (
            conn.execute(sa.select(projects).where(projects.c.id == UUID(run["project_id"])))
            .mappings()
            .one()
        )
        state = load(conn, project)
    candidate = run["candidates"][0]
    revision = candidate["analysis_basis"]["analysis_revision"]
    record = run["analysis_lineage"][revision]
    job = run["analysis_jobs"][record["dependencies"]["job_id"]]
    assert record["parent_analysis_revision"] is None
    assert record["dependencies"]["attempt_id"] == job["attempt_id"]
    assert record["dependencies"]["source_revisions"] == job["source_revisions"]
    assert record["dependencies"]["model_selection"] == job["model_selection"]
    assert currently_usable(run, candidate, state, project, UUID(run["owner_id"]))
    tampered = copy.deepcopy(run)
    tampered["analysis_lineage"][revision]["dependencies"]["material_audit"] = []
    assert not currently_usable(tampered, candidate, state, project, UUID(run["owner_id"]))
    tampered = copy.deepcopy(run)
    dep = tampered["analysis_lineage"][revision]["dependencies"]
    bad_job = tampered["analysis_jobs"][dep["job_id"]]
    dep["material_audit"].append("corrupt")
    bad_job["material_audit"] = copy.deepcopy(dep["material_audit"])
    assert not currently_usable(tampered, candidate, state, project, UUID(run["owner_id"]))
    tampered = copy.deepcopy(run)
    dep = tampered["analysis_lineage"][revision]["dependencies"]
    bad_job = tampered["analysis_jobs"][dep["job_id"]]
    for entry in dep["material_audit"]:
        entry.pop("classification_revision")
    bad_job["material_audit"] = copy.deepcopy(dep["material_audit"])
    assert not currently_usable(tampered, candidate, state, project, UUID(run["owner_id"]))
    tampered = copy.deepcopy(run)
    dep = tampered["analysis_lineage"][revision]["dependencies"]
    bad_job = tampered["analysis_jobs"][dep["job_id"]]
    removed = dep["source_ids"].pop()
    dep["source_revisions"].pop(removed)
    dep["material_audit"] = [
        x for x in dep["material_audit"] if x["source"]["source_id"] != removed
    ]
    for key in ("source_ids", "source_revisions", "material_audit"):
        bad_job[key] = copy.deepcopy(dep[key])
    assert not currently_usable(tampered, candidate, state, project, UUID(run["owner_id"]))
    assert {entry["boundary"] for entry in record["dependencies"]["material_audit"]} == {
        "read",
        "dispatch",
        "commit",
    }
    assert manual(c, h, url).status_code == 200
    with engine.connect() as conn:
        edited = conn.scalar(sa.select(runs.c.payload))
    new_revision = edited["candidates"][0]["analysis_basis"]["analysis_revision"]
    inherited = edited["analysis_lineage"][new_revision]
    assert inherited["parent_analysis_revision"] == revision
    assert inherited["dependencies"] == record["dependencies"]
    assert currently_usable(edited, edited["candidates"][0], state, project, UUID(run["owner_id"]))


def test_pa11_manual_fill_overwrite_rejection_and_failed_regeneration(subject):
    c, h, _, app, _, _ = subject
    url = ready(subject)
    assert manual(c, h, url).status_code == 200
    original = candidates(c, url)[0]
    assert original["analysis_state"] == "manual_edit"
    assert generate(c, h, url).status_code == 409
    proof = post(
        c,
        h,
        url + "/candidates/" + original["id"] + "/analysis/action-preview",
        {"expected_revision": original["revision"], "action": "generate"},
    ).json()["data"]
    assert proof["affected_items"][0]["content_scope"] == ["analysis"]
    assert generate(c, h, url, proof=proof).status_code == 202
    assert manual(c, h, url).status_code == 409
    assert AnalysisWorker(app.state.run_store, Generated(malformed=True)).run_once()
    after = candidates(c, url)[0]
    assert after["analysis"] == original["analysis"] and after["analysis_state"] == "manual_edit"
    assert after["revision"] == original["revision"] and after["analysis_error"]
    assert confirm(c, h, url)[0].status_code == 200


def test_pa12_failed_first_generation_requires_manual_completion(subject):
    c, h, _, app, _, _ = subject
    url = ready(subject)
    assert generate(c, h, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated(malformed=True)).run_once()
    run = c.get(url).json()["data"]
    assert run["waiting_items"][0]["confirmation"] is None
    assert manual(c, h, url, {"one_sentence_summary": "partial"}).status_code == 422
    assert manual(c, h, url).status_code == 200
    item = candidates(c, url)[0]
    assert item["analysis_current"] and item["analysis_error"] is None
    assert c.get(url).json()["data"]["steps"][0]["result_summary"]["analysis"]["failed"] == 0
    assert c.get(url).json()["data"]["analysis_tasks"][0]["execution_status"] == "failed"
    assert confirm(c, h, url)[0].status_code == 200


def test_pa13_stale_overwrite_and_processing_edit_invalidate_confirmation(subject):
    c, h, _, _, _, _ = subject
    url = ready(subject)
    assert manual(c, h, url).status_code == 200
    item = candidates(c, url)[0]
    proof = post(
        c,
        h,
        url + "/candidates/" + item["id"] + "/analysis/action-preview",
        {"expected_revision": item["revision"], "action": "generate"},
    ).json()["data"]
    assert manual(c, h, url, {**output(), "methods": "人工新方法"}).status_code == 200
    assert generate(c, h, url, proof=proof).status_code == 409
    _, path, body = confirm(c, h, url)
    item = candidates(c, url)[0]
    assert edit_score(c, h, url, item, score=9).status_code == 200
    assert not candidates(c, url)[0]["analysis_current"]
    assert post(c, h, path, body).status_code in {409, 412}


def test_pa14_cancel_late_generation_preserves_manual_content(subject):
    c, h, _, app, _, _ = subject
    url = ready(subject)
    assert manual(c, h, url).status_code == 200
    item = candidates(c, url)[0]
    proof = post(
        c,
        h,
        url + "/candidates/" + item["id"] + "/analysis/action-preview",
        {"expected_revision": item["revision"], "action": "generate"},
    ).json()["data"]
    assert generate(c, h, url, proof=proof).status_code == 202

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

    assert AnalysisWorker(app.state.run_store, Generated(hook=cancel)).run_once()
    after = candidates(c, url)[0]
    assert after["analysis"] == item["analysis"] and after["analysis_state"] == "manual_edit"
    assert c.get(url).json()["data"]["status"] == "cancelled"


def test_pa15_two_workers_single_dispatch_and_edit_mutex(subject):
    c, h, _, app, _, _ = subject
    url = ready(subject)
    assert generate(c, h, url).status_code == 202
    entered, release = Event(), Event()

    def wait():
        entered.set()
        assert release.wait(10)

    provider = Generated(hook=wait)
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(AnalysisWorker(app.state.run_store, provider).run_once)
        try:
            assert entered.wait(10)
            assert not AnalysisWorker(app.state.run_store, Generated()).run_once()
            assert manual(c, h, url).status_code == 409
            assert edit_score(c, h, url, candidates(c, url)[0], score=9).status_code == 409
        finally:
            release.set()
        assert future.result()
    assert len(provider.calls) == 1


@pytest.mark.parametrize("boundary", ["read", "dispatch", "commit"])
@pytest.mark.parametrize("revocation", ["account", "project", "classification"])
def test_pa16_current_authority_at_each_boundary(subject, boundary, revocation):
    from rpb.adapters.account import accounts
    from rpb.adapters.project import projects

    c, h, root, app, engine, _ = subject
    url = ready(subject)
    source_id = candidates(c, url)[0]["processing"]["selected_source_id"]
    response = generate(c, h, url)
    assert response.status_code == 202
    task_id = response.json()["data"]["task_id"]

    def revoke():
        if revocation == "classification":
            path = root + "/material-sources/" + source_id + "/classification"
            view = c.get(path).json()["data"]
            assert (
                post(
                    c,
                    h,
                    path + "/correct",
                    dict(
                        expected_revision=view["revision"],
                        content_revision=view["source"]["content_revision"],
                        classification="private",
                        basis="Actual source is private",
                        explicit_confirmation=True,
                    ),
                ).status_code
                == 200
            )
        else:
            with engine.begin() as conn:
                if revocation == "account":
                    conn.execute(accounts.update().values(enabled=False))
                else:
                    conn.execute(projects.update().values(status="archived"))

    class BeforeDispatch(Generated):
        def generate(self, config, model, secret, inputs, authorize):
            revoke()
            return super().generate(config, model, secret, inputs, authorize)

    provider = (
        BeforeDispatch()
        if boundary == "dispatch"
        else Generated(hook=revoke if boundary == "commit" else None)
    )
    if boundary == "read":
        revoke()
    AnalysisWorker(app.state.run_store, provider).run_once()
    assert len(provider.calls) == (1 if boundary == "commit" else 0)
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        assert run["analysis_jobs"][task_id]["state"] == "failed"
        assert not any(c.get("analysis") for c in run["candidates"])


def test_pa17_unknown_result_and_expired_lease_no_redispatch(subject):
    from datetime import UTC, datetime, timedelta

    c, h, _, app, engine, _ = subject
    url = ready(subject)
    assert generate(c, h, url).status_code == 202

    def expire():
        with engine.begin() as conn:
            row = conn.execute(sa.select(runs)).mappings().one()
            run = copy.deepcopy(row["payload"])
            next(iter(run["analysis_jobs"].values()))["lease_until"] = (
                datetime.now(UTC) - timedelta(seconds=1)
            ).isoformat()
            conn.execute(runs.update().where(runs.c.id == row["id"]).values(payload=run))

    provider = Generated(hook=expire)
    worker = AnalysisWorker(app.state.run_store, provider)
    assert worker.run_once() and not worker.run_once()
    assert len(provider.calls) == 1
    assert not candidates(c, url)[0].get("analysis")
    assert c.get(url).json()["data"]["analysis_tasks"][0]["error"]["code"] == "PROVIDER_FAILED"
    with engine.connect() as conn:
        payload = conn.scalar(sa.select(runs.c.payload))
        assert next(iter(payload["analysis_jobs"].values()))["error"] == "PROVIDER_RESULT_UNKNOWN"


def test_pa18_full_size_manual_content_and_cross_run_rejection(subject):
    c, h, root, _, _, _ = subject
    url = ready(subject)
    value = dict(
        one_sentence_summary="字" * 10000,
        methods="字" * 10000,
        highlights=["字" * 2000] * 100,
        relevance_points=["字" * 2000] * 100,
        innovations=["字" * 2000] * 100,
    )
    assert manual(c, h, url, value).status_code == 200
    assert candidates(c, url)[0]["analysis"] == value
    item = candidates(c, url)[0]
    wrong = root + "/construction-runs/" + str(uuid4())
    assert generate(c, h, wrong, item=item).status_code == 404
    assert (
        c.post(
            url + "/candidates/" + item["id"] + "/analysis/generate",
            json={"expected_revision": item["revision"], "acknowledged_risk_ids": []},
        ).status_code
        == 403
    )


def test_pa19_manual_receipt_failure_rolls_back_content(subject):
    from sqlalchemy import event

    c, h, _, _, engine, _ = subject
    url = ready(subject)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO " + commands.name):
            raise RuntimeError("injected receipt failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        assert manual(c, h, url).status_code == 500
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert not candidates(c, url)[0].get("analysis")


def test_pa20_partial_success_confirm_only_success_and_no_persistent_exclusion(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    other = next(x for x in candidates(c, url) if x["metadata"]["title"] == "Different")
    assert edit_score(c, h, url, other, valid=True).status_code == 200
    assert confirm(c, h, url)[0].status_code == 200
    assert ProcessingWorker(app.state.run_store, Prepared()).run_once()
    assert confirm(c, h, url)[0].status_code == 200
    eligible = [x for x in candidates(c, url) if x.get("processing")]
    assert len(eligible) == 2
    for i, item in enumerate(eligible):
        assert generate(c, h, url, item).status_code == 202
        assert AnalysisWorker(app.state.run_store, Generated(malformed=bool(i))).run_once()
    result = confirm(c, h, url)[0]
    assert result.status_code == 200
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        assert run["analysis_confirmation"]["candidate_ids"] == [eligible[0]["id"]]
        failed = next(x for x in run["candidates"] if x["id"] == eligible[1]["id"])
        assert failed["screening"]["valid"] is True and not failed.get("analysis")
        assert failed["analysis_error"]


def test_pa21_confirmed_regenerate_requires_preview_and_success_retains_original(subject):
    c, h, _, app, _, _ = subject
    url = ready(subject)
    assert generate(c, h, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    assert confirm(c, h, url)[0].status_code == 200
    original = candidates(c, url)[0]
    assert original["analysis_state"] == "confirmed"
    assert generate(c, h, url).status_code == 409
    proof = post(
        c,
        h,
        url + "/candidates/" + original["id"] + "/analysis/action-preview",
        {"action": "generate", "expected_revision": original["revision"]},
    ).json()["data"]
    assert generate(c, h, url, proof=proof).status_code == 202
    assert AnalysisWorker(app.state.run_store, Generated()).run_once()
    item = candidates(c, url)[0]
    assert item["analysis_history"][-1]["analysis"] == original["analysis"]
    assert item["processing"] == original["processing"]
    assert item["analysis_state"] == "agent_draft"
    assert c.get(url).json()["data"]["phase"] == "analysis"


def test_pa22_actual_pdf_requires_own_classification_not_abstract(subject):
    from test_paper_processing import pdf
    from test_paper_screening import classify

    c, h, root, app, _, _ = subject
    url = confirmed_score(subject)
    assert confirm(c, h, url)[0].status_code == 200

    class TextPDF(Prepared):
        def prepare(self, sources, authorize):
            value = super().prepare(sources, authorize)
            return {
                **value,
                "raw": pdf(),
                "text": "Full text different from abstract",
                "kind": "full_text",
            }

    assert ProcessingWorker(app.state.run_store, TextPDF()).run_once()
    assert confirm(c, h, url)[0].status_code == 200
    item = candidates(c, url)[0]
    assert generate(c, h, url).status_code == 409
    classify(c, h, root, item["processing"]["basis"]["document_asset_id"])
    assert generate(c, h, url).status_code == 202
    provider = Generated()
    assert AnalysisWorker(app.state.run_store, provider).run_once()
    assert provider.calls[0]["text"] == "Full text different from abstract"
    assert provider.calls[0]["text_source_kind"] == "full_text"


def test_pa23_frozen_parameters_and_current_credentials(subject):
    from cryptography.fernet import Fernet

    from rpb.adapters.llm_tables import configs

    c, h, _, app, engine, key = subject
    url = ready(subject)
    with engine.begin() as conn:
        row = conn.execute(sa.select(configs)).mappings().one()
        data = copy.deepcopy(row["data"])
        data["parameters"]["temperature"] = 1.5
        conn.execute(
            configs.update()
            .where(configs.c.id == row["id"])
            .values(data=data, secret_ciphertext=Fernet(key).encrypt(b"ANALYSIS-ROTATED-SECRET"))
        )
    captured = []

    class Rotated(Generated):
        def generate(self, config, model, secret, inputs, authorize):
            captured.append((copy.deepcopy(config), secret))
            return super().generate(config, model, secret, inputs, authorize)

    assert generate(c, h, url).status_code == 202
    assert AnalysisWorker(app.state.run_store, Rotated()).run_once()
    assert captured[0][1] == "ANALYSIS-ROTATED-SECRET"
    assert captured[0][0]["parameters"].get("temperature") != 1.5
    with engine.connect() as conn:
        assert "ANALYSIS-ROTATED-SECRET" not in str(conn.scalar(sa.select(runs.c.payload)))


@pytest.mark.parametrize("field", list(output()))
def test_pa24_nul_rejected_without_losing_manual_content_or_worker(subject, field):
    c, h, _, app, _, _ = subject
    url = ready(subject)
    assert manual(c, h, url).status_code == 200
    original = candidates(c, url)[0]
    value = output()
    value[field] = "valid\x00suffix" if isinstance(value[field], str) else ["valid\x00suffix"]
    assert manual(c, h, url, value).status_code == 422
    assert candidates(c, url)[0]["revision"] == original["revision"]
    proof = post(
        c,
        h,
        url + "/candidates/" + original["id"] + "/analysis/action-preview",
        {"expected_revision": original["revision"], "action": "generate"},
    ).json()["data"]
    queued = generate(c, h, url, proof=proof)
    assert queued.status_code == 202

    class InvalidText(Generated):
        def generate(self, config, model, secret, inputs, authorize):
            with authorize():
                return value

    worker = AnalysisWorker(app.state.run_store, InvalidText())
    assert worker.run_once()
    assert not worker.run_once()
    after = candidates(c, url)[0]
    assert after["analysis"] == original["analysis"]
    assert after["revision"] == original["revision"]
    assert after["analysis_state"] == "manual_edit"
    assert after["analysis_error"] == "PROVIDER_RESPONSE_INVALID"
    assert c.get(queued.json()["data"]["status_url"]).json()["data"]["execution_status"] == "failed"
