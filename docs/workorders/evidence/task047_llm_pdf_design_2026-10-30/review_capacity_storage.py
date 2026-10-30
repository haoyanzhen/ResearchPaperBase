import sqlalchemy as sa
from uuid import UUID
from test_llm_configuration import llm,create,start,patch
from backend.tests.integration.conftest import db,storage
from rpb.adapters.llm_tables import configs

def test_legacy_capacity_read_preserves_database_and_revision(llm,db):
 c,h,worker,provider,_=llm
 initial=create(c,h).json()["data"]
 assert start(c,h,initial).status_code==202 and worker.run_once()
 with db[0].begin() as conn:
  row=conn.execute(sa.select(configs).where(configs.c.id==UUID(initial["id"]))).mappings().one()
  data=dict(row["data"]);data.pop("model_context_windows")
  conn.execute(configs.update().where(configs.c.id==row["id"]).values(data=data))
 loaded=c.get("/api/v1/me/llm-configs/"+initial["id"]).json()["data"]
 assert loaded["model_context_windows"]=={}
 assert loaded["models"][0]["context_window_tokens"]==262144
 assert loaded["revision"]==initial["revision"] and loaded["models"][0]["available"]
 with db[0].connect() as conn:
  actual=conn.execute(sa.select(configs.c.data).where(configs.c.id==UUID(initial["id"]))).scalar_one()
  assert "model_context_windows" not in actual
 changed=patch(c,h,loaded,model_context_windows={"model-a":4096}).json()["data"]
 assert changed["model_context_windows"]=={"model-a":4096}
 assert not changed["models"] and len(provider.calls)==1
