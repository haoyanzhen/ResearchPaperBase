"""Verify R01 documentation delivery, not application behavior. Run from any cwd."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
sha = lambda data: hashlib.sha256(data).hexdigest()
m = json.loads((BASE / 'manifest.json').read_text())
inputs = json.loads((BASE / 'input.json').read_text())
for name, digest in m['evidence_sha256'].items():
    assert sha((BASE / name).read_bytes()) == digest, name
for name, rec in m['files'].items():
    assert sha(inputs[name].encode()) == rec['input_sha256'], name
    assert sha((ROOT / name).read_bytes()) == rec['output_sha256'], name
with tempfile.TemporaryDirectory(prefix='rpb-r01-docs-') as tmp:
    for name, content in inputs.items():
        p = Path(tmp) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    subprocess.run(['git', 'apply', '--check', str(BASE / 'changes.patch')], cwd=tmp, check=True)
    subprocess.run(['git', 'apply', str(BASE / 'changes.patch')], cwd=tmp, check=True)
    for name, rec in m['files'].items():
        assert sha((Path(tmp) / name).read_bytes()) == rec['output_sha256'], name
print('PASS: three-file input/output hashes and patch reconstruction')
links = 0
for name, rec in m['files'].items():
    p = ROOT / name
    text = p.read_text()
    assert f"文档版本：{rec['version']}" in text
    assert '更新日期：2026-10-22' in text
    columns = None
    for line in text.splitlines():
        if line.startswith('|'):
            size = len(line.split('|'))
            if columns is None:
                columns = size
            assert size == columns, (name, 'table column mismatch', line)
        else:
            columns = None
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if '://' in target:
            continue
        path, _, anchor = target.partition('#')
        dest = p.parent / path if path else p
        assert dest.exists(), (name, target)
        if anchor:
            headings = [re.sub(r'\s', '-', re.sub(r'[^\w\-\s]', '', line.lstrip('#').strip().lower()))
                        for line in dest.read_text().splitlines() if line.startswith('#')]
            assert anchor in headings, (name, target)
        links += 1
print(f'PASS: {links} local references/anchors and versions/dates')
s = (ROOT / 'tasks/004-project-create-idempotency-example.md').read_text()
scenarios = re.findall(r'^\| (T\d{2}) /', s, re.M)
assert scenarios == [f'T{i:02}' for i in range(1, 11)], scenarios
rows = re.findall(r'^\| (R\d{2})：([^\n]+)', s, re.M)
assert [r[0] for r in rows] == [f'R{i:02}' for i in range(1, 14)]
used = set()
for rid, row in rows:
    refs = re.findall(r'\bT\d{2}\b', row)
    assert refs and set(refs) <= set(scenarios), rid
    assert 'V02未执行' in row and '待建立' in row, rid
    used.update(refs)
assert used == set(scenarios)
for number in range(4):
    assert len(re.findall(rf'^\| V0{number} ', s, re.M)) == 1
for token in ['t0+24h−ε', 'meta.idempotency_expires_at', 'E≥t0+24h', 'E=t0+48h', '非null',
              '24小时是最小保留下界，不是强制删除时刻', '不要求每次重放自动续24h']:
    assert token in s, token
print('PASS: T01-T10, R01-R13 traceability and explicit unexecuted business tests')
for name, digest in m['unchanged_sha256'].items():
    assert sha((ROOT / name).read_bytes()) == digest, name
for name in ['backend', 'frontend', 'e2e']:
    assert not (ROOT / name).exists(), name
print('PASS: protected source/evidence unchanged; no application directories created')
