import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

base = Path('docs/workorders/evidence/task047_llm_pdf_design_2026-10-30')
runs = Path('docs/workorders/evidence/task046_processing_gate_2026-10-29')
baseline = json.loads((base / 'implementation-validation-baseline.json').read_text())
for path, digest in baseline['files'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
for name, count in [('cleanup-db-final1', 157), ('cleanup-unit-final', 433)]:
    cases = ET.parse(runs / (name + '-tests.xml')).findall('.//testcase')
    assert len(cases) == count
    assert all(not any(c.find(tag) is not None for tag in ('failure', 'error', 'skipped')) for c in cases)
for name in baseline['runs'] + ['cleanup-contract-tests1', 'cleanup-contract2', 'cleanup-frontend2']:
    assert json.loads((runs / (name + '-run.json')).read_text())['exit_code'] == 0
    assert (runs / (name + '-summary.json')).is_file()
log = (runs / 'cleanup-db-final1.log').read_text()
assert '"server_stopped": true' in log and '"root_removed": true' in log
versions = {'tasks/047-llm-pdf-extraction-design.md': 'v1.4', 'docs/PROJECT_STATUS.md': 'v1.116', 'docs/design/04-01_p0_operation_contracts.md': 'v1.28', 'docs/design/04-04_llm_parameter_contracts.md': 'v1.3'}
for path, version in versions.items():
    content = Path(path).read_text()
    assert version in content and '2026-10-30' in content, path
    if path.startswith('tasks/') or path == 'docs/PROJECT_STATUS.md':
        for target in re.findall(r'\]\(([^)]+)\)', content):
            if '://' not in target and not target.startswith('#'):
                assert (Path(path).parent / target.split('#')[0]).exists(), (path, target)
assert 'S6最终证据追加复核' in (base / 'review-s3.md').read_text()
subprocess.run(['git', 'diff', '--check'], check=True)
assert not subprocess.check_output(['git', 'diff', '--cached', '--name-only']).strip()
files = list(baseline['files']) + list(versions) + [str(base / n) for n in ('review-s3.md', 'cleanup-classification.png', 'cleanup-comparison.png', 'cleanup-mobile.png', 'verify_final_closeout.py')]
manifest = {'scope': 'M-P0-16 local verification handoff; human acceptance and inherited platform verification pending', 'head': baseline['head'], 'context': 'task047-final-closeout-1', 'files': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}}
(base / 'final-artifacts.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('PASS: 20 implementation hashes; 157+433 test cases; successful run/summary records; isolated PG cleanup; document versions/references; independent report; diff whitespace; no staged changes. Final manifest saved.')
