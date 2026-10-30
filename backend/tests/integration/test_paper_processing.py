# ruff: noqa: F811
"""PP: explicit isolated PostgreSQL, real commits, real PDFs; no external traffic."""

import copy
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from test_paper_deduplication import candidates, correction
from test_paper_screening import Scores, edit, ready_score, score_request
from test_search_terms import post, subject  # noqa: F401

from rpb.adapters.paper_processing import ProcessingWorker
from rpb.adapters.paper_scoring_worker import ScoreWorker
from rpb.adapters.pdf_processing import PDFProvider
from rpb.adapters.processing_tables import objects
from rpb.adapters.run_tables import runs


def pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Real pipeline paper text) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    data = io.BytesIO()
    writer.write(data)
    return data.getvalue()


class Prepared:
    def __init__(self, hook=None, failure=False):
        self.hook, self.failure, self.calls = hook, failure, []

    def prepare(self, sources, authorize):
        with authorize():
            self.calls.append(copy.deepcopy(sources))
        if self.hook:
            self.hook()
        if self.failure:
            return dict(text=None, raw=None, source_id=None, kind=None, segments=[], diagnostics=[])
        return dict(
            text=sources[0]["metadata"]["abstract"],
            raw=None,
            source_id=sources[0]["id"],
            kind="abstract_fallback",
            segments=[],
            diagnostics=[dict(source_id=sources[0]["id"], reason="source_unavailable")],
        )


def confirmed_score(subject):
    c, h, _, app, _, _ = subject
    url = ready_score(subject)
    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 202
    assert ScoreWorker(app.state.run_store, Scores()).run_once()
    return url


def confirm(c, h, url, key=None):
    run = c.get(url).json()["data"]
    wait = run["waiting_items"][0]
    proof = wait["confirmation"]
    assert proof is not None, run
    body = dict(
        expected_revision=wait["revision"],
        subject_revision=proof["subject_revision"],
        candidate_revision=proof["candidate_revision"],
        confirmation_token=proof["confirmation_token"],
        acknowledged_risk_ids=[],
    )
    path = url + "/waiting-items/" + wait["id"] + "/confirm"
    return post(c, h, path, body, key or str(uuid4())), path, body


def test_pp10_confirm_gate_partial_success_fallback_confirmation_and_edit(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    before = candidates(c, url)
    r, path, body = confirm(c, h, url, "pp-screening-command-0001")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["run"]["status"] == "running"
    assert post(c, h, path, body, "pp-screening-command-0001").json()["data"] == r.json()["data"]
    assert edit(c, h, url, before[0], valid=False).status_code == 409
    provider = Prepared()
    assert ProcessingWorker(app.state.run_store, provider).run_once()
    assert len(provider.calls) == 1  # invalid and missing-title candidates are not processed
    item = candidates(c, url)[0]
    p = item["processing"]
    assert p["status"] == "degraded" and p["text_preview"] == "Version 0"
    assert p["basis"]["document_asset_id"] is None and not p["participates_in_knowledge"]
    assert p["source_ids"] == [before[0]["id"], before[1]["id"]]
    with engine.connect() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        obj = conn.execute(sa.select(objects)).mappings().one()
        assert obj["text"] == "Version 0" and obj["file_bytes"] is None
        assert set(run["processing_job"]["boundaries"]) == {"read", "dispatch", "commit"}
    assert post(c, h, path, body, str(uuid4())).status_code in {409, 412}
    r, _, _ = confirm(c, h, url)
    assert r.status_code == 200 and r.json()["data"]["run"]["phase"] == "analysis"
    assert r.json()["data"]["run"]["published_knowledge_version_id"] is None
    item = candidates(c, url)[0]
    assert item["processing"]["basis"]["confirmed_revision"]
    assert edit(c, h, url, item, score=9).status_code == 200
    run = c.get(url).json()["data"]
    assert run["phase"] == "screening"
    assert candidates(c, url)[0]["processing"]["basis"]["confirmed_revision"] is None
    assert not ProcessingWorker(app.state.run_store, provider).run_once()


def test_pp11_real_pdf_pipeline_file_read_ownership_and_classification(subject):
    c, h, root, app, engine, _ = subject
    url = confirmed_score(subject)
    # Frozen provider metadata supplies a PDF URL. Real parsing, fake network bytes.
    with engine.begin() as conn:
        run = conn.scalar(sa.select(runs.c.payload))
        run["candidates"][0]["metadata"]["url"] = "https://example.org/paper.pdf"
        conn.execute(runs.update().values(payload=run))
    assert confirm(c, h, url)[0].status_code == 200

    class Files(PDFProvider):
        def download(self, link, authorize):
            with authorize():
                return pdf()

    assert ProcessingWorker(app.state.run_store, Files()).run_once()
    items = candidates(c, url)
    item = items[0]
    p = item["processing"]
    identity = p["basis"]["document_asset_id"]
    assert p["status"] == "available" and "Real pipeline paper text" in p["text_preview"]
    assert p["material_classification"]["classification"] == "private"
    assert p["material_classification"]["confirmation_status"] == "unconfirmed"
    access = c.get(
        url + "/candidates/" + item["id"] + "/file-access", params={"document_asset_id": identity}
    )
    assert access.status_code == 200, access.text
    link = access.json()["data"]["download_url"]
    response = c.get(link)
    assert response.status_code == 200 and response.content == pdf()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert c.get(link.replace(item["id"], items[1]["id"])).status_code == 404
    assert c.get(link.replace(root, root[:-36] + str(uuid4()))).status_code == 404
    assert c.get(link, params={"knowledge_version_id": str(uuid4())}).status_code == 400
    with engine.begin() as conn:
        conn.execute(objects.update().where(objects.c.id == UUID(identity)).values(file_bytes=None))
    assert c.get(link).status_code == 410


def test_pp12_cancel_after_dispatch_discards_late_text(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    assert confirm(c, h, url)[0].status_code == 200

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

    assert ProcessingWorker(app.state.run_store, Prepared(cancel)).run_once()
    assert c.get(url).json()["data"]["status"] == "cancelled"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 0
    assert candidates(c, url)[0]["screening"]["score"] == 7


def test_pp13_concurrent_workers_dispatch_once(subject):
    c, h, _, app, _, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)
    entered, release = Event(), Event()

    def wait():
        entered.set()
        assert release.wait(10)

    fake = Prepared(wait)
    worker = ProcessingWorker(app.state.run_store, fake)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(worker.run_once)
        assert entered.wait(10)
        try:
            assert not pool.submit(worker.run_once).result(5)
        finally:
            release.set()
        assert first.result(10)
    assert len(fake.calls) == 1


def test_pp14_all_processing_failure_has_no_analysis_confirmation(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)
    assert ProcessingWorker(app.state.run_store, Prepared(failure=True)).run_once()
    run = c.get(url).json()["data"]
    assert run["status"] == "waiting_user"
    assert run["waiting_items"][0]["confirmation"] is None
    assert candidates(c, url)[0]["processing"]["status"] == "failed"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 0
    # Failed parsing does not make the user's screening decision immutable.
    assert edit(c, h, url, candidates(c, url)[0], valid=False).status_code == 200


@pytest.mark.parametrize("boundary", ["read", "dispatch", "commit"])
@pytest.mark.parametrize("authority", ["project", "account"])
def test_pp15_project_revocation_rejects_at_each_boundary(subject, boundary, authority):
    from rpb.adapters.account import accounts
    from rpb.adapters.project import projects

    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)

    def revoke():
        with engine.begin() as conn:
            conn.execute(
                projects.update().values(status="archived")
            ) if authority == "project" else conn.execute(accounts.update().values(enabled=False))

    class Revoked(Prepared):
        def prepare(self, sources, authorize):
            if boundary == "dispatch":
                revoke()
            result = super().prepare(sources, authorize)
            if boundary == "commit":
                revoke()
            return result

    fake = Revoked()
    if boundary == "read":
        revoke()
    ProcessingWorker(app.state.run_store, fake).run_once()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 0
        assert conn.scalar(sa.select(runs.c.status)) == "cancelled"
    assert len(fake.calls) == (1 if boundary == "commit" else 0)


def test_pp16_old_confirmation_after_group_edit_rejected(subject):
    c, h, _, app, _, _ = subject
    url = confirmed_score(subject)
    run = c.get(url).json()["data"]
    w = run["waiting_items"][0]
    proof = w["confirmation"]
    first = candidates(c, url)[0]
    assert correction(c, h, url, first).status_code == 200
    r = post(
        c,
        h,
        url + "/waiting-items/" + w["id"] + "/confirm",
        dict(
            expected_revision=w["revision"],
            subject_revision=proof["subject_revision"],
            candidate_revision=proof["candidate_revision"],
            confirmation_token=proof["confirmation_token"],
            acknowledged_risk_ids=[],
        ),
    )
    assert r.status_code in {409, 412}
    assert not ProcessingWorker(app.state.run_store, Prepared()).run_once()


@pytest.mark.parametrize("change", ["expired", "actor", "project", "wait"])
def test_pp17_confirmation_binding_and_immutable_rejection(subject, monkeypatch, change):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters import runs as module

    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    with engine.connect() as conn:
        original = conn.scalar(sa.select(runs.c.payload))
    other = copy.deepcopy(original)
    if change in {"actor", "project"}:
        other[change + "_id" if change == "project" else "owner_id"] = str(uuid4())
    if change == "wait":
        other["waiting"]["revision"] = str(uuid4())

    class Earlier(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) - timedelta(minutes=11)

    with monkeypatch.context() as m:
        if change == "expired":
            m.setattr(module, "datetime", Earlier)
        proof = app.state.run_store.waiting(other)[0]["confirmation"]
    wait = original["waiting"]
    r = post(
        c,
        h,
        url + "/waiting-items/" + wait["id"] + "/confirm",
        dict(
            expected_revision=wait["revision"],
            subject_revision=original["effective_input_revision"],
            candidate_revision=original["candidate_revision"],
            confirmation_token=proof["confirmation_token"],
            acknowledged_risk_ids=[],
        ),
    )
    assert r.status_code == 409
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.payload)) == original


def test_pp18_partial_failures_and_unchanged_group_reuse(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    assert edit(c, h, url, candidates(c, url)[2], valid=True).status_code == 200
    confirm(c, h, url)
    fake = Prepared()
    worker = ProcessingWorker(app.state.run_store, fake)
    assert worker.run_once()
    items = candidates(c, url)
    first_basis = copy.deepcopy(items[0]["processing"]["basis"])
    confirm(c, h, url)
    items = candidates(c, url)
    assert edit(c, h, url, items[2], score=8).status_code == 200
    assert not candidates(c, url)[0]["processing_stale"]
    assert candidates(c, url)[0]["processing"]["basis"]["confirmed_revision"]
    confirm(c, h, url)
    again = Prepared(failure=True)
    assert ProcessingWorker(app.state.run_store, again).run_once()
    assert len(again.calls) == 1
    items = candidates(c, url)
    assert items[0]["processing"]["basis"]["text_revision_id"] == first_basis["text_revision_id"]
    assert items[2]["processing"]["status"] == "failed"
    assert confirm(c, h, url)[0].status_code == 200
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 2


def test_pp19_failed_rescore_preserves_processing_confirmation_then_success_invalidates(subject):
    c, h, _, app, _, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)
    ProcessingWorker(app.state.run_store, Prepared()).run_once()
    confirm(c, h, url)
    prior = candidates(c, url)[0]["processing"]["basis"]["confirmed_revision"]
    body = score_request(c, url)
    body["candidate_ids"] = body["candidate_ids"][:1]
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
    assert any(i["kind"] == "confirmation_invalidation" for i in proof["affected_items"])
    body.update(
        confirmation_token=proof["confirmation_token"], acknowledged_risk_ids=["replace_screening"]
    )
    response = post(c, h, url + "/screening/score", body, str(uuid4()))
    assert response.status_code == 202, response.text
    assert ScoreWorker(app.state.run_store, Scores([None])).run_once()
    assert c.get(url).json()["data"]["phase"] == "analysis"
    assert candidates(c, url)[0]["processing"]["basis"]["confirmed_revision"] == prior
    response = post(c, h, url + "/screening/score", body, str(uuid4()))
    assert response.status_code == 202, response.text
    assert ScoreWorker(app.state.run_store, Scores([9])).run_once()
    assert c.get(url).json()["data"]["phase"] == "screening"
    assert candidates(c, url)[0]["processing"]["basis"]["confirmed_revision"] is None
    assert candidates(c, url)[0]["processing_history"][0]["basis"]["confirmed_revision"] == prior


def test_pp20_receipt_failure_rolls_back_processing_acceptance(subject):
    from rpb.adapters.run_tables import commands

    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    with engine.connect() as conn:
        original = conn.scalar(sa.select(runs.c.payload))

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO " + commands.name):
            raise RuntimeError("receipt fault")

    sa.event.listen(engine, "before_cursor_execute", fail)
    try:
        assert confirm(c, h, url)[0].status_code == 500
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail)
    with engine.connect() as conn:
        assert conn.scalar(sa.select(runs.c.payload)) == original
    assert not ProcessingWorker(app.state.run_store, Prepared()).run_once()


def test_pp21_retained_unparsed_pdf_not_the_abstract_text_document(subject):
    c, h, _, app, _, _ = subject
    url = confirmed_score(subject)

    class Blank(PDFProvider):
        def download(self, link, authorize):
            with authorize():
                writer = PdfWriter()
                writer.add_blank_page(612, 792)
                out = io.BytesIO()
                writer.write(out)
                return out.getvalue()

    assert confirm(c, h, url)[0].status_code == 200
    assert ProcessingWorker(app.state.run_store, Blank()).run_once()
    item = candidates(c, url)[0]
    assert item["processing"]["status"] == "degraded"
    assert item["processing"]["basis"]["document_asset_id"] is None
    identity = item["processing"]["retained_file"]["document_asset_id"]
    assert identity in item["document_refs"]
    assert (
        c.get(url + "/candidates/" + item["id"] + "/files/" + identity + "/download").status_code
        == 200
    )


def test_pp22_processing_projection_schema_and_migration_refusal(subject, db):
    import json
    from pathlib import Path

    from alembic import command
    from jsonschema import Draft202012Validator

    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)
    ProcessingWorker(app.state.run_store, Prepared()).run_once()
    spec = json.loads((Path(__file__).parents[3] / "contracts/p0.openapi.json").read_text())
    for name, value in [
        ("RetrievalRunView", c.get(url).json()["data"]),
        ("RetrievalCandidate", candidates(c, url)[0]),
    ]:
        Draft202012Validator(
            {"$ref": "#/components/schemas/" + name, "components": spec["components"]}
        ).validate(value)
    _, cfg = db
    with pytest.raises(RuntimeError, match="Refusing to discard processing objects"):
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "0014_construction_runs")
    with engine.connect() as conn:
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0015_processing_objects"
        )


def test_pp25_duplicate_group_commit_is_idempotent(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    assert edit(c, h, url, candidates(c, url)[2], valid=True).status_code == 200
    confirm(c, h, url)

    class Duplicate(ProcessingWorker):
        def commit_group(self, run_id, job_id, group, result, final):
            first = super().commit_group(run_id, job_id, group, result, final)
            if not final:
                with engine.connect() as conn:
                    before = conn.scalar(sa.select(runs.c.payload))
                    count = conn.scalar(sa.select(sa.func.count()).select_from(objects))
                assert super().commit_group(run_id, job_id, group, result, final)
                with engine.connect() as conn:
                    assert conn.scalar(sa.select(runs.c.payload)) == before
                    assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == count
            return first

    assert Duplicate(app.state.run_store, Prepared()).run_once()
    assert c.get(url).json()["data"]["status"] == "waiting_user"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 2


def test_pp26_expired_execution_lease_rejects_late_commit(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)

    def expire():
        with engine.begin() as conn:
            run = conn.scalar(sa.select(runs.c.payload))
            run["processing_job"]["lease_until"] = "2000-01-01T00:00:00+00:00"
            conn.execute(runs.update().values(payload=run))

    assert ProcessingWorker(app.state.run_store, Prepared(hook=expire)).run_once()
    assert c.get(url).json()["data"]["status"] == "failed"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 0


def test_pp29_processing_commit_rollback_has_no_partial_success(subject, monkeypatch):
    from rpb.adapters import paper_processing

    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    confirm(c, h, url)

    def fail(*args):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(paper_processing, "save", fail)
    worker = ProcessingWorker(app.state.run_store, Prepared())
    with pytest.raises(RuntimeError, match="injected"):
        worker.run_once()
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 0
        run = conn.scalar(sa.select(runs.c.payload))
        assert run["processing_job"]["state"] == "running"
        assert "processing" not in run["candidates"][0]
    assert not worker.run_once()  # live lease never blindly redispatches unknown work


def test_pp30_freeze_order_activity_mutual_exclusion_and_no_changed_payload_replay(subject):
    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    before = candidates(c, url)
    r, path, body = confirm(c, h, url, "processing-idempotent-0030")
    assert r.status_code == 200
    changed = dict(body, candidate_revision=str(uuid4()))
    assert post(c, h, path, changed, "processing-idempotent-0030").status_code == 409
    assert correction(c, h, url, before[1], "distinct").status_code == 409
    assert post(c, h, url + "/screening/score", score_request(c, url)).status_code == 409
    with engine.connect() as conn:
        frozen = conn.scalar(sa.select(runs.c.payload))["processing_job"]["groups"][0]["sources"]
    assert [s["id"] for s in frozen] == [before[0]["id"], before[1]["id"]]
    fake = Prepared()
    assert ProcessingWorker(app.state.run_store, fake).run_once()
    assert fake.calls[0] == frozen


def test_pp32_accepted_confirmation_token_expiry_does_not_revoke_persisted_job(
    subject, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from rpb.adapters import runs as run_module

    c, h, _, app, engine, _ = subject
    url = confirmed_score(subject)
    response, _, body = confirm(c, h, url)
    assert response.status_code == 200
    expires = datetime.fromisoformat(body["confirmation_token"].rsplit(".", 1)[0])

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(hours=1)

    monkeypatch.setattr(run_module, "datetime", Later)
    assert Later.now(UTC) > expires
    assert ProcessingWorker(app.state.run_store, Prepared()).run_once()
    assert c.get(url).json()["data"]["status"] == "waiting_user"
    assert candidates(c, url)[0]["processing"]["status"] == "degraded"
    with engine.connect() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(objects)) == 1
