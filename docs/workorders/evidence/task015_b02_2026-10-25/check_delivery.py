"""Scoped B02 document/reference/version checks and exact source delta capture."""
import difflib
import hashlib
import json
import re
import tarfile
from pathlib import Path

root = Path.cwd()
evidence = root/'docs/workorders/evidence/task015_b02_2026-10-25'
old = json.loads((evidence/'before/source-manifest.json').read_text())
reviewed = json.loads((evidence/'s3-fix/source-manifest.json').read_text())
scoped = ['README.md', 'docs/PROJECT_STATUS.md', 'tasks/015-account-storage-migration.md',
          'backend/alembic.ini', 'backend/migrations/env.py', 'backend/pyproject.toml',
          'backend/migrations/versions/0001_account.py', 'backend/src/rpb/adapters/account.py',
          'backend/tests/conftest.py', 'backend/tests/integration/conftest.py',
          'backend/tests/integration/test_account_storage.py',
          'backend/tests/integration/test_fixture_cleanup.py',
          'scripts/engineering.py', 'scripts/run_storage_tests.py']
links = 0
for name in scoped[:3]:
    p = root/name
    body = p.read_text()
    assert re.search(r'文档版本：v1\.\d+', body), name
    assert '更新日期：2026-10-25' in body, name
    for target in re.findall(r'\]\(([^)]+)\)', body):
        if '://' in target or target.startswith('#'):
            continue
        assert (p.parent/target.split('#')[0]).exists(), (name, target)
        links += 1
source_drift = [p for p in scoped[3:]
                if hashlib.sha256((root/p).read_bytes()).hexdigest() != reviewed[p]]
assert not source_drift, source_drift
patch = []
with tarfile.open(evidence/'before/source.tar.gz') as archive:
    for name in scoped:
        previous = archive.extractfile(name).read().decode() if name in old else ''
        current = (root/name).read_text()
        if name in scoped[:2]:
            ov = int(re.search(r'文档版本：v1\.(\d+)', previous)[1])
            nv = int(re.search(r'文档版本：v1\.(\d+)', current)[1])
            assert nv > ov
        patch.extend(difflib.unified_diff(previous.splitlines(True), current.splitlines(True),
                                       fromfile='before/'+name, tofile='after/'+name))
(evidence/'changes.patch').write_text(''.join(patch))
result = dict(scoped_files=len(scoped), local_references=links,
              reviewed_source_unchanged=True, versions_dates=True,
              parallel_workflow_changes='Excluded; preserved in snapshots; status merged')
(evidence/'document-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
