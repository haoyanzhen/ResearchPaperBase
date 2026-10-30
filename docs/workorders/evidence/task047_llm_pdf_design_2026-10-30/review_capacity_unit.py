import json
from contextlib import nullcontext
import pytest
from rpb.adapters.pdf_cleanup_provider import CleanupProvider
from backend.tests.unit.test_pdf_cleanup_provider import HTTP,config,batch,response,PROTOCOLS

@pytest.mark.parametrize("protocol",PROTOCOLS)
def test_capacity_never_transmitted_as_generation_parameter(protocol):
 c=config(protocol);c["model_context_windows"]={"chosen-model":524288}
 answer={"boundaries":[{"after_line_id":"p1:l1","separator":"space"}]}
 h=HTTP(response(protocol,json.dumps(answer)))
 assert CleanupProvider(h).propose(c,"chosen-model","test-secret",batch(),3,nullcontext)==answer
 assert len(h.calls)==1
 payload=json.dumps(h.calls[0][1]);assert "model_context_windows" not in payload and "context_window_tokens" not in payload and "524288" not in payload
