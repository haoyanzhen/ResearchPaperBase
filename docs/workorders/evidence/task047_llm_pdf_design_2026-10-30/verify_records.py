import json, re, hashlib
from pathlib import Path
paths = ['tasks/046-paper-processing-gate.md', 'tasks/047-llm-pdf-extraction-design.md', 'docs/PROJECT_STATUS.md']
for name in paths:
    p = Path(name); text = p.read_text()
    assert '2026-10-30' in text and re.search(r'v1\.\d+', text)
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
        if '://' in target or target.startswith('#'): continue
        assert (p.parent / target.split('#')[0]).resolve().exists(), (name, target)
base = Path('docs/workorders/evidence/task046_processing_gate_2026-10-29')
expected = json.loads((base/'delivery-artifacts.json').read_text())
expected.update(json.loads((base/'platform-artifacts.json').read_text()))
drift = [p for p, h in expected.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h]
assert set(drift) <= {'tasks/046-paper-processing-gate.md', 'docs/PROJECT_STATUS.md'}, drift
assert 'M-P0-15于2026-10-30获用户明确接受' in Path('docs/PROJECT_STATUS.md').read_text()
print(json.dumps({'references_versions':'pass', 'accepted_code_drift':False, 'record_changes':drift, 'real_platform_validation':'still_open'},ensure_ascii=False))
