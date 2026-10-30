import sqlalchemy as sa
from test_pdf_cleanup import TextPDF, Model, ready, file_classify
from test_search_terms import subject
from test_paper_deduplication import candidates
from backend.tests.integration.conftest import db, storage
from rpb.adapters.pdf_cleanup_worker import CleanupWorker
from rpb.adapters.run_tables import runs


def test_review_group_budget_keeps_attempted_source(subject):
    c,h,_,app,engine,_ = subject
    url=ready(subject)
    model=Model()
    worker=CleanupWorker(app.state.run_store, TextPDF("line\n"*100), model)
    assert worker.run_once()
    file_classify(subject,url)
    assert worker.run_once()
    assert len(model.calls)==1
    with engine.begin() as conn:
        run=conn.scalar(sa.select(runs.c.payload))
        job=run["processing_job"]
        source_id=job["prepared"]["source_id"]
        assert job["budget"]["calls"]==1 and job["replies"]
        job["budget"]["seconds"]=job["budget"]["limits"]["group_seconds"]
        conn.execute(runs.update().values(payload=run))
    assert worker.run_once()
    result=candidates(c,url)[0]["processing"]
    attempted=next(x for x in result["source_attempts"] if x["source_id"]==source_id)
    assert attempted["state"] == "failed", result


def test_review_policy_revoked_after_failure_before_fallback(subject):
    from rpb.adapters.llm_provider import ProviderFailure
    from test_search_terms import post
    c,h,root,app,engine,_=subject
    url=ready(subject)
    class Bad(Model):
        def propose(self,*args):
            super().propose(*args)
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
    worker=CleanupWorker(app.state.run_store,TextPDF(),Bad())
    policy=c.get(root+"/material-policy").json()["data"]
    assert c.put(root+"/material-policy",headers=h,json={"expected_revision":policy["revision"],"mode":"allow_private","risk_acknowledged":True}).status_code==200
    for _ in range(2):
        assert worker.run_once()
        doc=candidates(c,url)[0]["cleanup_pending"]["document_asset_id"]
        path=root+"/material-sources/"+doc+"/classification"
        value=c.get(path).json()["data"]
        assert post(c,h,path+"/confirm",{"expected_revision":value["revision"],"content_revision":value["source"]["content_revision"],"classification":"private","basis":"private PDF checked","explicit_confirmation":True}).status_code==200
        assert worker.run_once()
    policy=c.get(root+"/material-policy").json()["data"]
    assert c.put(root+"/material-policy",headers=h,json={"expected_revision":policy["revision"],"mode":"public_only","risk_acknowledged":False}).status_code==200
    worker.run_once()
    assert "processing" not in candidates(c,url)[0], candidates(c,url)[0].get("processing")
    assert c.get(url).json()["data"]["status"]=="failed"


def test_review_policy_revoked_after_failure_before_next_source(subject):
    from rpb.adapters.llm_provider import ProviderFailure
    from test_search_terms import post
    c,h,root,app,engine,_=subject
    url=ready(subject)
    class Bad(Model):
        def propose(self,*args):
            super().propose(*args)
            raise ProviderFailure("PROVIDER_RESPONSE_INVALID")
    worker=CleanupWorker(app.state.run_store,TextPDF(),Bad())
    policy=c.get(root+"/material-policy").json()["data"]
    assert c.put(root+"/material-policy",headers=h,json={"expected_revision":policy["revision"],"mode":"allow_private","risk_acknowledged":True}).status_code==200
    for _ in range(1):
        assert worker.run_once()
        doc=candidates(c,url)[0]["cleanup_pending"]["document_asset_id"]
        path=root+"/material-sources/"+doc+"/classification"
        value=c.get(path).json()["data"]
        assert post(c,h,path+"/confirm",{"expected_revision":value["revision"],"content_revision":value["source"]["content_revision"],"classification":"private","basis":"private PDF checked","explicit_confirmation":True}).status_code==200
        assert worker.run_once()
    policy=c.get(root+"/material-policy").json()["data"]
    assert c.put(root+"/material-policy",headers=h,json={"expected_revision":policy["revision"],"mode":"public_only","risk_acknowledged":False}).status_code==200
    worker.run_once()
    assert "processing" not in candidates(c,url)[0], candidates(c,url)[0].get("processing")
    assert c.get(url).json()["data"]["status"]=="failed"


def test_review_compare_rejects_other_existing_project_and_object(subject):
    from uuid import UUID,uuid4
    from test_project_commands import create
    from rpb.adapters.processing_tables import objects
    c,h,root,app,engine,_=subject
    url=ready(subject)
    worker=CleanupWorker(app.state.run_store,TextPDF(),Model())
    worker.run_once()
    doc=file_classify(subject,url)
    worker.run_once();worker.run_once()
    item=candidates(c,url)[0]
    path=url+"/candidates/"+item["id"]+"/processing-text"
    assert c.get(path).status_code==200
    second=create(c,h,{"name":"Second","description":"","research_scope":""},str(uuid4()))
    assert second.status_code==201,second.text
    second_id=second.json()["data"]["id"]
    assert c.get(path.replace(root,"/api/v1/projects/"+second_id)).status_code==404
    with engine.begin() as conn:
        conn.execute(objects.update().where(objects.c.id==UUID(doc)).values(project_id=UUID(second_id)))
    denied=c.get(path)
    assert denied.status_code==410 and "first" not in denied.text
