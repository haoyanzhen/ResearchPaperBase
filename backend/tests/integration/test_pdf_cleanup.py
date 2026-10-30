# ruff: noqa: F811
"""LP: isolated PostgreSQL and deterministic fake external services."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from test_paper_deduplication import candidates
from test_paper_processing import confirm, confirmed_score, pdf
from test_paper_screening import classify
from test_search_terms import subject  # noqa: F401

from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.pdf_cleanup_worker import CleanupWorker
from rpb.adapters.processing_tables import objects
from rpb.adapters.run_tables import runs


class TextPDF:
    def __init__(self, text="first\nsecond\n", hook=None):
        self.text, self.hook, self.calls = text, hook, []

    def prepare(self, sources, authorize):
        with authorize():
            self.calls.append(sources[0]["id"])
        if self.hook:
            self.hook()
        return {
            "text": self.text,
            "raw": pdf(),
            "source_id": sources[0]["id"],
            "kind": "full_text",
            "segments": [{"page": 1, "start_offset": 0, "end_offset": len(self.text)}],
            "diagnostics": [],
        }


class Model:
    def __init__(self, hook=None):
        self.calls, self.hook = [], hook

    def propose(self, config, model, secret, batch, timeout, authorize):
        with authorize():
            self.calls.append((copy.deepcopy(config), model, batch, timeout))
        if self.hook:
            self.hook()
        return {
            "boundaries": [
                {"after_line_id": line.identity, "separator": "space"} for line in batch.lines[:-1]
            ]
        }


def ready(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    # Worker-focused fixture seeds an already-frozen choice; public Start gets
    # separate transport/browser coverage before the engine is advertised.
    with engine.begin() as conn:
        value = conn.scalar(sa.select(runs.c.payload))
        value["request"]["pdf_extraction_engine"] = "llm_text_cleanup"
        conn.execute(runs.update().values(payload=value))
    assert confirm(c, h, url)[0].status_code == 200
    return url


def file_classify(subject, url):
    c, h, root, _, _, _ = subject
    item = candidates(c, url)[0]
    doc = item["cleanup_pending"]["document_asset_id"]
    classify(c, h, root, doc)
    return doc


def test_pl01_wait_classification_auto_continue_and_original_preserved(subject):
    c, h, _, app, engine, _ = subject
    url = ready(subject)
    pdfs, model = TextPDF(), Model()
    worker = CleanupWorker(app.state.run_store, pdfs, model)
    assert not ProcessingWorker(app.state.run_store, pdfs).run_once()
    assert worker.run_once()
    assert c.get(url).json()["data"]["status"] == "waiting_user"
    assert c.get(url).json()["data"]["waiting_items"][0]["confirmation"] is None
    assert not worker.run_once() and model.calls == []
    doc = file_classify(subject, url)
    assert worker.run_once() and len(model.calls) == 1
    assert worker.run_once()
    assert not worker.run_once()
    item = candidates(c, url)[0]
    result = item["processing"]
    assert result["status"] == "available" and result["text_preview"] == "first second\n"
    assert result["basis"]["document_asset_id"] == doc
    assert result["material_classification"]["confirmation_status"] == "confirmed"
    assert result["cleanup"]["output_tokens"] == 4096
    assert result["cleanup"]["output_defaulted"] is True
    with engine.connect() as conn:
        rows = list(conn.execute(sa.select(objects)).mappings())
        assert len(rows) == 2
        original = next(row for row in rows if str(row["id"]) == doc)
        assert original["text"] == "first\nsecond\n" and original["file_bytes"] == pdf()
        final = next(row for row in rows if str(row["id"]) != doc)
        assert final["text"] == "first second\n" and final["file_bytes"] is None
        run = conn.scalar(sa.select(runs.c.payload))
        assert run["processing_job"]["group_history"][0]["budget"]["calls"] == 1
    assert confirm(c, h, url)[0].status_code == 200


def test_pl02_cancelled_job_is_not_revived_by_classification(subject):
    c, _, _, app, engine, _ = subject
    url = ready(subject)
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    assert worker.run_once()
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run["status"] = "cancelled"
        conn.execute(runs.update().values(payload=run, status="cancelled"))
    file_classify(subject, url)
    assert not worker.run_once() and model.calls == []
    assert c.get(url).json()["data"]["status"] == "cancelled"


def test_pl03_crash_reservation_survives_restart_without_resending(subject):
    c, _, _, app, engine, _ = subject
    url = ready(subject)
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    file_classify(subject, url)

    class Crash(Model):
        def propose(self, *args):
            with args[-1]():
                pass
            raise RuntimeError("simulated process crash")

    import pytest

    with pytest.raises(RuntimeError):
        CleanupWorker(app.state.run_store, TextPDF(), Crash()).run_once()
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        assert run["processing_job"]["budget"]["pending"] is not None
        assert run["processing_job"]["budget"]["calls"] == 1
        run["processing_job"]["lease_until"] = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
        conn.execute(runs.update().values(payload=run))
    worker.run_once()
    assert model.calls == []
    assert c.get(url).json()["data"]["status"] == "failed"


def test_pl04_cancel_after_dispatch_discards_late_result(subject):
    c, _, _, app, engine, _ = subject
    url = ready(subject)

    def cancel():
        with engine.begin() as conn:
            value = conn.scalar(sa.select(runs.c.payload))
            value["status"] = "cancelled"
            conn.execute(runs.update().values(payload=value, status="cancelled"))

    worker = CleanupWorker(app.state.run_store, TextPDF(), Model(cancel))
    worker.run_once()
    file_classify(subject, url)
    worker.run_once()
    assert c.get(url).json()["data"]["status"] == "cancelled"
    assert "processing" not in candidates(c, url)[0]
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 1


def test_pl05_group_exhaustion_keeps_unattempted_sources_and_rejects_abstract(subject):
    c, _, _, app, engine, _ = subject
    url = ready(subject)
    worker = CleanupWorker(app.state.run_store, TextPDF("line\n" * 100), Model())
    worker.run_once()
    file_classify(subject, url)
    worker.run_once()
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run["processing_job"]["budget"]["seconds"] = 240
        conn.execute(runs.update().values(payload=run))
    worker.run_once()
    result = candidates(c, url)[0]["processing"]
    assert result["status"] == "failed" and result["text_source_kind"] is None
    assert [a["state"] for a in result["source_attempts"]] == ["failed", "not_attempted"]
    assert result["diagnostics"][0]["reason"] == "budget_exhausted"


def test_pl06_concurrent_workers_only_dispatch_once(subject):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    c, _, _, app, _, _ = subject
    url = ready(subject)
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    model = Model(pause)
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    file_classify(subject, url)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(worker.run_once)
        assert entered.wait(10)
        assert not CleanupWorker(app.state.run_store, TextPDF(), Model()).run_once()
        release.set()
        assert future.result()
    assert len(model.calls) == 1
    worker.run_once()
    assert candidates(c, url)[0]["processing"]["status"] == "available"


def test_pl07_all_cleanup_failures_use_only_real_abstract(subject):
    from rpb.adapters.llm_provider import ProviderFailure

    c, _, _, app, _, _ = subject
    url = ready(subject)

    class Bad(Model):
        def propose(self, *args):
            super().propose(*args)
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")

    model = Bad()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    for _ in range(2):
        assert worker.run_once()  # fetch current source
        file_classify(subject, url)
        assert worker.run_once()  # fail current source
    assert worker.run_once()  # no remaining full sources
    result = candidates(c, url)[0]["processing"]
    assert len(model.calls) == 2
    assert result["status"] == "degraded" and result["text_preview"] == "Version 0"
    assert result["text_source_kind"] == "abstract_fallback"
    assert len(result["diagnostics"]) == 2


def test_pl08_commit_rollback_does_not_repeat_model_or_lose_raw(subject, monkeypatch):
    import pytest

    c, _, _, app, engine, _ = subject
    url = ready(subject)
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    file_classify(subject, url)
    worker.run_once()
    original = worker.processing.commit_result

    def rollback(*args):
        original(*args)
        raise RuntimeError("commit rollback")

    monkeypatch.setattr(worker.processing, "commit_result", rollback)
    with pytest.raises(RuntimeError):
        worker.run_once()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 1
    monkeypatch.setattr(worker.processing, "commit_result", original)
    assert worker.run_once() and len(model.calls) == 1
    assert candidates(c, url)[0]["processing"]["status"] == "available"


def test_pl09_compare_route_scope_query_and_digest(subject):
    from uuid import uuid4

    c, _, _, app, engine, _ = subject
    url = ready(subject)
    worker = CleanupWorker(app.state.run_store, TextPDF(), Model())
    worker.run_once()
    doc = file_classify(subject, url)
    worker.run_once()
    worker.run_once()
    item = candidates(c, url)[0]
    path = url + "/candidates/" + item["id"] + "/processing-text"
    result = c.get(path)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["data"]["raw_text"] == "first\nsecond\n"
    assert result.json()["data"]["text"] == "first second\n"
    assert c.get(path, params={"knowledge_version_id": str(uuid4())}).status_code == 400
    assert c.get(path.replace(item["id"], str(uuid4()))).status_code == 404
    with engine.begin() as conn:
        from uuid import UUID

        conn.execute(objects.update().where(objects.c.id == UUID(doc)).values(text="tampered"))
    assert c.get(path).status_code == 409


def test_pl10_policy_revocation_during_call_rejects_output(subject):
    from test_search_terms import post

    c, h, root, app, _, _ = subject
    url = ready(subject)

    def revoke():
        policy = c.get(root + "/material-policy").json()["data"]
        assert (
            c.put(
                root + "/material-policy",
                headers=h,
                json={
                    "expected_revision": policy["revision"],
                    "mode": "public_only",
                    "risk_acknowledged": False,
                },
            ).status_code
            == 200
        )

    model = Model(revoke)
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    doc = candidates(c, url)[0]["cleanup_pending"]["document_asset_id"]
    path = root + "/material-sources/" + doc + "/classification"
    value = c.get(path).json()["data"]
    assert (
        post(
            c,
            h,
            path + "/confirm",
            {
                "expected_revision": value["revision"],
                "content_revision": value["source"]["content_revision"],
                "classification": "private",
                "basis": "actual private file",
                "explicit_confirmation": True,
            },
        ).status_code
        == 200
    )
    policy = c.get(root + "/material-policy").json()["data"]
    assert (
        c.put(
            root + "/material-policy",
            headers=h,
            json={
                "expected_revision": policy["revision"],
                "mode": "allow_private",
                "risk_acknowledged": True,
            },
        ).status_code
        == 200
    )
    worker.run_once()
    assert len(model.calls) == 1
    assert c.get(url).json()["data"]["status"] == "failed"
    assert "processing" not in candidates(c, url)[0]


def test_pl11_frozen_configuration(subject):
    c, _, _, app, engine, _ = subject
    url = ready(subject)
    # A frozen explicit output limit remains independent of later personal edits.
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run["cleanup_model_config"] = {
            **run["model_config"],
            "parameters": {"max_output_tokens": 8192},
        }
        conn.execute(runs.update().values(payload=run))
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    file_classify(subject, url)
    worker.run_once()
    worker.run_once()
    assert model.calls[0][0]["parameters"] == {"max_output_tokens": 8192}
    assert candidates(c, url)[0]["processing"]["cleanup"]["output_tokens"] == 8192


def test_pl12_start_choice_and_frozen_output_capacity_budget(subject):
    from test_construction_runs import Papers, setup
    from test_search_terms import post

    from rpb.adapters.run_worker import RunWorker

    c, h, root, app, engine, _ = subject
    body, _ = setup(subject)
    for bad in ("ocr", ["pypdf", "llm_text_cleanup"], None):
        assert (
            post(
                c, h, root + "/construction-runs", {**body, "pdf_extraction_engine": bad}
            ).status_code
            == 422
        )
    response = post(
        c, h, root + "/construction-runs", {**body, "pdf_extraction_engine": "llm_text_cleanup"}
    )
    assert response.status_code == 202, response.text
    assert RunWorker(app.state.run_store, Papers()).run_once()
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        settings = run["config_snapshot"]["pdf_cleanup"]
        assert settings["context_window_tokens"] == 262144
        assert settings["output_tokens"] == 4096 and settings["output_defaulted"]
        assert settings["budget_limits"]["source_seconds"] == 120
        assert settings["budget_limits"]["group_calls"] == 64
        assert run["cleanup_model_config"]["parameters"]["max_output_tokens"] == 4096
        assert "max_output_tokens" not in run["model_config"]["parameters"]


def test_pl13_no_text_layer_never_calls_model_and_retains_failed_file(subject):
    c, _, _, app, _, _ = subject
    url = ready(subject)

    class Blank(TextPDF):
        def prepare(self, sources, authorize):
            with authorize():
                self.calls.append(sources[0]["id"])
            return {
                "text": None,
                "raw": None,
                "kind": None,
                "source_id": None,
                "diagnostics": [{"source_id": sources[0]["id"], "reason": "no_usable_text"}],
                "fallback_file": {"source_id": sources[0]["id"], "raw": pdf()},
            }

    model, files = Model(), Blank()
    worker = CleanupWorker(app.state.run_store, files, model)
    assert worker.run_once() and worker.run_once() and worker.run_once()
    item = candidates(c, url)[0]
    assert item["processing"]["status"] == "degraded"
    assert item["processing"]["retained_file"]["document_asset_id"] in item["document_refs"]
    assert model.calls == [] and len(files.calls) == 2


def test_pl14_next_group_has_independent_frozen_budget(subject):
    from test_paper_screening import edit

    c, h, root, app, engine, _ = subject
    url = confirmed_score(subject)
    second = candidates(c, url)[2]
    assert edit(c, h, url, second, valid=True).status_code == 200
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run["request"]["pdf_extraction_engine"] = "llm_text_cleanup"
        conn.execute(runs.update().values(payload=run))
    assert confirm(c, h, url)[0].status_code == 200
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    # Explicitly simulate a previous exhausted budget, not elapsed wall-time sleeps.
    worker.run_once()
    file_classify(subject, url)
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run["processing_job"]["budget"]["seconds"] = 240
        conn.execute(runs.update().values(payload=run))
    worker.run_once()
    worker.run_once()
    second = candidates(c, url)[2]
    classify(c, h, root, second["cleanup_pending"]["document_asset_id"])
    worker.run_once()
    worker.run_once()
    items = candidates(c, url)
    assert items[0]["processing"]["status"] == "failed"
    assert items[2]["processing"]["status"] == "available"
    assert len(model.calls) == 1
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        assert [v["budget"]["calls"] for v in run["processing_job"]["group_history"]] == [0, 1]


@pytest.mark.parametrize("boundary", ["read", "dispatch", "result"])
@pytest.mark.parametrize("authority", ["project", "account"])
def test_pl15_revoke_at_each_model_boundary(subject, boundary, authority):
    from rpb.adapters.account import accounts
    from rpb.adapters.project import projects

    _, _, _, app, engine, _ = subject
    url = ready(subject)

    def revoke():
        with engine.begin() as conn:
            if authority == "project":
                conn.execute(
                    projects.update().values(authority_epoch=projects.c.authority_epoch + 1)
                )
            else:
                conn.execute(accounts.update().values(enabled=False))

    class Revoked(Model):
        def propose(self, *args):
            if boundary == "dispatch":
                revoke()
            value = super().propose(*args)
            if boundary == "result":
                revoke()
            return value

    model = Revoked()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    file_classify(subject, url)
    if boundary == "read":
        revoke()
    worker.run_once()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.status)) == "cancelled"
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 1
    assert len(model.calls) == (1 if boundary == "result" else 0)


@pytest.mark.parametrize("drift", ["raw_text", "source_revision", "missing_file"])
def test_pl16_frozen_input_drift_never_dispatches(subject, drift):
    from uuid import UUID, uuid4

    c, _, _, app, engine, _ = subject
    url = ready(subject)
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    doc = file_classify(subject, url)
    with engine.begin() as conn:
        if drift == "raw_text":
            conn.execute(
                objects.update().where(objects.c.id == UUID(doc)).values(text="different\n")
            )
        elif drift == "missing_file":
            conn.execute(objects.delete().where(objects.c.id == UUID(doc)))
        else:
            value = conn.scalar(sa.select(runs.c.payload))
            value["candidates"][0]["revision"] = str(uuid4())
            conn.execute(runs.update().values(payload=value))
    worker.run_once()
    assert model.calls == []
    assert c.get(url).json()["data"]["status"] == "failed"
    assert "processing" not in candidates(c, url)[0]


def test_pl17_reprocessing_retains_history_and_rejects_old_confirmation(subject):
    from uuid import uuid4

    from test_paper_screening import edit
    from test_search_terms import post

    c, h, _, app, _, _ = subject
    url = ready(subject)
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    first_file = file_classify(subject, url)
    worker.run_once()
    worker.run_once()
    response, path, old_confirmation = confirm(c, h, url)
    assert response.status_code == 200
    item = candidates(c, url)[0]
    old_revision = item["processing"]["basis"]["processing_revision"]
    assert edit(c, h, url, item, score=9).status_code == 200
    assert post(c, h, path, old_confirmation, str(uuid4())).status_code in {409, 412}
    assert confirm(c, h, url)[0].status_code == 200
    worker.run_once()
    second_file = file_classify(subject, url)
    assert second_file != first_file
    worker.run_once()
    worker.run_once()
    item = candidates(c, url)[0]
    assert item["processing"]["basis"]["processing_revision"] != old_revision
    assert item["processing"]["basis"]["confirmed_revision"] is None
    assert any(
        v["basis"]["processing_revision"] == old_revision for v in item["processing_history"]
    )
    assert first_file in item["document_refs"] and second_file in item["document_refs"]
    assert len(model.calls) == 2


def test_pl18_classification_revision_change_during_call_rejects_result(subject):
    from test_search_terms import post

    c, h, root, app, _, _ = subject
    url = ready(subject)
    doc = None

    def correct():
        path = root + "/material-sources/" + doc + "/classification"
        value = c.get(path).json()["data"]
        assert (
            post(
                c,
                h,
                path + "/correct",
                {
                    "expected_revision": value["revision"],
                    "content_revision": value["source"]["content_revision"],
                    "classification": "public",
                    "basis": "rechecked",
                    "explicit_confirmation": True,
                },
            ).status_code
            == 200
        )

    worker = CleanupWorker(app.state.run_store, TextPDF(), Model(correct))
    worker.run_once()
    doc = file_classify(subject, url)
    worker.run_once()
    assert c.get(url).json()["data"]["status"] == "failed"
    assert "processing" not in candidates(c, url)[0]


@pytest.mark.parametrize("after_failures", [1, 2])
def test_pl19_policy_revoke_blocks_next_source_and_final_abstract(subject, after_failures):
    from test_search_terms import post

    from rpb.adapters.llm_provider import ProviderFailure

    c, h, root, app, _, _ = subject
    url = ready(subject)
    policy = c.get(root + "/material-policy").json()["data"]
    assert (
        c.put(
            root + "/material-policy",
            headers=h,
            json={
                "expected_revision": policy["revision"],
                "mode": "allow_private",
                "risk_acknowledged": True,
            },
        ).status_code
        == 200
    )

    class Bad(Model):
        def propose(self, *args):
            super().propose(*args)
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")

    model, files = Bad(), TextPDF()
    worker = CleanupWorker(app.state.run_store, files, model)
    for _ in range(after_failures):
        worker.run_once()
        doc = candidates(c, url)[0]["cleanup_pending"]["document_asset_id"]
        path = root + "/material-sources/" + doc + "/classification"
        value = c.get(path).json()["data"]
        assert (
            post(
                c,
                h,
                path + "/confirm",
                {
                    "expected_revision": value["revision"],
                    "content_revision": value["source"]["content_revision"],
                    "classification": "private",
                    "basis": "actual private PDF",
                    "explicit_confirmation": True,
                },
            ).status_code
            == 200
        )
        worker.run_once()
    policy = c.get(root + "/material-policy").json()["data"]
    assert (
        c.put(
            root + "/material-policy",
            headers=h,
            json={
                "expected_revision": policy["revision"],
                "mode": "public_only",
                "risk_acknowledged": False,
            },
        ).status_code
        == 200
    )
    worker.run_once()
    assert len(files.calls) == after_failures and len(model.calls) == after_failures
    assert c.get(url).json()["data"]["status"] == "failed"
    assert "processing" not in candidates(c, url)[0]


def test_pl20_missing_classification_is_controlled_failure(subject):
    from rpb.adapters.project import projects
    from rpb.adapters.search_terms import load, save

    c, _, _, app, engine, _ = subject
    url = ready(subject)
    model = Model()
    worker = CleanupWorker(app.state.run_store, TextPDF(), model)
    worker.run_once()
    doc = candidates(c, url)[0]["cleanup_pending"]["document_asset_id"]
    with engine.begin() as conn:
        project = conn.execute(sa.select(projects)).mappings().one()
        state = load(conn, project)
        del state["sources"][doc]
        save(conn, project, state)
    worker.run_once()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.status)) == "cancelled"
    assert model.calls == []


def test_pl21_same_pdf_hash_in_another_project_never_authorizes_text_read(subject):
    from uuid import UUID, uuid4

    from test_project_commands import create

    c, h, root, app, engine, _ = subject
    url = ready(subject)
    worker = CleanupWorker(app.state.run_store, TextPDF(), Model())
    worker.run_once()
    original_doc = file_classify(subject, url)
    worker.run_once()
    worker.run_once()
    other = create(c, h, {"name": "Other project"}, str(uuid4())).json()["data"]
    other_run_id, other_doc_id = uuid4(), uuid4()
    with engine.begin() as conn:
        current = conn.execute(sa.select(runs)).mappings().one()
        foreign = copy.deepcopy(dict(current))
        foreign.update(id=other_run_id, project_id=UUID(other["id"]), status="cancelled")
        foreign["payload"].update(id=str(other_run_id), project_id=other["id"], status="cancelled")
        conn.execute(runs.insert().values(**foreign))
        row = dict(
            conn.execute(sa.select(objects).where(objects.c.id == UUID(original_doc)))
            .mappings()
            .one()
        )
        row.update(id=other_doc_id, run_id=other_run_id, project_id=UUID(other["id"]))
        conn.execute(objects.insert().values(**row))
        value = copy.deepcopy(current["payload"])
        candidate_id = value["candidates"][0]["id"]
        value["candidates"][0]["processing"]["cleanup"]["raw_text_id"] = str(other_doc_id)
        conn.execute(runs.update().where(runs.c.id == current["id"]).values(payload=value))
    path = url + "/candidates/" + candidate_id + "/processing-text"
    assert c.get(path).status_code == 410
    assert c.get(path.replace(root, "/api/v1/projects/" + other["id"])).status_code == 404
