import hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
p=Path("docs/workorders/evidence/task047_llm_pdf_design_2026-10-30")
files=json.loads((p/"implementation-validation-baseline.json").read_text())["files"]
assert len(files)==20
for name,sha in files.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha,name
print("20 implementation artifacts match final validation baseline")
q=Path("docs/workorders/evidence/task046_processing_gate_2026-10-29")
for name,total in [("cleanup-db-final1",157),("cleanup-unit-final",433)]:
    run=json.loads((q/(name+"-run.json")).read_text());assert run["exit_code"]==0
    root=ET.parse(q/(name+"-tests.xml")).getroot(); cases=root.findall(".//testcase")
    assert len(cases)==total
    assert not root.findall(".//failure") and not root.findall(".//error") and not root.findall(".//skipped")
    print(name,total,"actual JUnit cases passed")
log=(q/"cleanup-db-final1.log").read_text()
assert '"server_stopped": true' in log and '"root_removed": true' in log
print("Final isolated PostgreSQL cleanup confirmed")
