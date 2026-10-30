import json
from pathlib import Path
from jsonschema import Draft202012Validator
import pytest

@pytest.mark.parametrize("name",["LLMWrite","LLMPatch","LLMView"])
def test_trailing_linebreak_model_id_rejected_by_contract(name):
 schema=json.loads(Path("contracts/p0.openapi.json").read_text())["components"]["schemas"][name]["properties"]["model_context_windows"]
 assert not Draft202012Validator(schema).is_valid({"model-a\n":262144})
