import json
from contextlib import nullcontext
import pytest
from rpb.adapters.pdf_cleanup_provider import CleanupProvider
from rpb.adapters.llm_provider import ProviderFailure
from rpb.adapters.pdf_text_cleanup import prepare,reconstruct
from backend.tests.unit.test_pdf_cleanup_provider import HTTP,config,batch,response,PROTOCOLS

REPLY={"boundaries":[{"after_line_id":"p1:l1","separator":"space"}]}

def test_gemini_thought_summary_not_parsed_as_final_answer():
    c=config("gemini_content");c["parameters"]["custom_params"]={"thinkingConfig":{"includeThoughts":True}}
    envelope=response("gemini_content",json.dumps(REPLY))
    envelope["candidates"][0]["content"]["parts"].insert(0,{"thought":True,"text":"reasoning summary"})
    http=HTTP(envelope)
    result=CleanupProvider(http).propose(c,"gemini-2.5-flash","secret-value",batch(),5,nullcontext)
    assert result==REPLY and len(http.calls)==1

def test_gemini_thought_only_cannot_become_final_proposal():
    envelope=response("gemini_content",json.dumps(REPLY))
    envelope["candidates"][0]["content"]["parts"][0]["thought"]=True
    with pytest.raises(ProviderFailure,match="PROVIDER_RESPONSE_INVALID"):
        CleanupProvider(HTTP(envelope)).propose(config("gemini_content"),"gemini-2.5-flash","secret-value",batch(),5,nullcontext)

@pytest.mark.parametrize("protocol",PROTOCOLS)
def test_credential_echo_rejected_without_response_leak(protocol):
    http=HTTP(response(protocol,'{"boundaries":[],"secret":"secret-value"}'))
    with pytest.raises(ProviderFailure) as e:
        CleanupProvider(http).propose(config(protocol),"chosen","secret-value",batch(),5,nullcontext)
    assert "secret-value" not in str(e.value) and len(http.calls)==1

@pytest.mark.parametrize("raw",["a\r\nb\r\n","\n  x\n\n","α😀\n中\n","x\u2028y\nz\n"])
def test_identity_separators_preserve_every_original_character(raw):
    plan=prepare(raw,[{"page":1,"start_offset":0,"end_offset":len(raw)}],max_input_bytes=700)
    replies=[{"boundaries":[{"after_line_id":l.identity,"separator":"line_break"} for l in b.lines[:-1]]} for b in plan.batches]
    result=reconstruct(plan,replies)
    assert result["text"]==raw
    for m in result["line_mapping"]:
        assert raw[m["raw_start_offset"]:m["raw_end_offset"]]==result["text"][m["start_offset"]:m["end_offset"]]
