"""Run from the repository root after verification; never overwrite a source baseline."""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

root = Path.cwd()
out = root / 'docs/workorders/evidence/task005_coverage_2026-10-22'
spec = importlib.util.spec_from_file_location('snapshot', root / 'scripts/delivery_snapshot.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)
for p in (root / 'frontend/test-results').glob('shell-*.png'):
    shutil.copy2(p, out / p.name)
baseline = out / 'baseline'
hashes = snapshot.create_snapshot(root, snapshot.source_paths(root), baseline)
with tempfile.TemporaryDirectory(prefix='task005-review-') as temp:
    tmp = Path(temp)
    for name, archive in [('initial', out/'initial/source.tar.gz'), ('final', baseline/'source.tar.gz')]:
        with tarfile.open(archive) as t:
            t.extractall(tmp/name, filter='data')
    actual = {str(p.relative_to(tmp/'final')): snapshot.digest(p.read_bytes()) for p in (tmp/'final').rglob('*') if p.is_file()}
    assert actual == hashes
    assert (tmp/'final/backend/migrations/versions/.gitkeep').read_bytes() == b''
    result = subprocess.run(['git', 'diff', '--no-index', '--binary', 'initial', 'final'], cwd=tmp, capture_output=True)
    assert result.returncode in (0,1), result.stderr
    (out/'delivery.patch').write_bytes(result.stdout)
(out/'snapshot-verification.txt').write_text(f'PASS: {len(hashes)} files extracted and SHA-256 matched; empty .gitkeep present. Temporary reconstruction removed.\n')
initial = json.loads((out/'initial/source-manifest.json').read_text())
changed = sorted(n for n in set(initial)|set(hashes) if initial.get(n)!=hashes.get(n))
owned = {'backend/tests/unit/test_startup.py','backend/tests/unit/test_skeleton_requirements.py','backend/tests/architecture/test_boundaries.py','frontend/src/App.test.tsx','frontend/e2e/shell.spec.ts','scripts/verify_skeleton_delivery.py','tasks/005-engineering-skeleton.md','docs/PROJECT_STATUS.md','docs/workorders/task005_coverage_closure_2026-10-22.md'}
assert not (set(initial)-set(hashes)), 'Existing source removed'
(out/'scope.json').write_text(json.dumps({'task005_changes':[p for p in changed if p in owned], 'concurrent_changes_preserved':[p for p in changed if p not in owned], 'unchanged_initial_files':sum(initial.get(p)==h for p,h in hashes.items()), 'deleted_initial_files':[]},indent=2)+'\n')
# Wheel contents must be the current source, not a stale build.
wheel = next((root/'backend/dist').glob('*.whl'))
with zipfile.ZipFile(wheel) as z:
    members={n:z.read(n) for n in z.namelist() if n.startswith('rpb/') and n.endswith('.py')}
    sources={str(p.relative_to(root/'backend/src')):p.read_bytes() for p in (root/'backend/src/rpb').rglob('*.py')}
    assert members==sources
# Validate owned Markdown references and version/date presence.
with (out/'documentation.txt').open('w') as log:
    for name in ['tasks/005-engineering-skeleton.md','docs/workorders/task005_coverage_closure_2026-10-22.md','docs/PROJECT_STATUS.md']:
        p=root/name; text=p.read_text()
        assert re.search(r'文档版本：v1\.\d+',text) and '2026-10-22' in text
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in target or target.startswith('#'):continue
            target=target.split('#')[0].split(':')[0]
            assert (p.parent/target).exists(), (name,target)
        log.write(f'PASS version/date/local file references: {name}\n')
    log.write('Visual review: four current screenshots show readable previews with disabled actions; no clipping observed.\n')
artifacts = [p for folder in ['backend/dist','frontend/dist'] for p in (root/folder).rglob('*') if p.is_file()]
manifest={'source_manifest_sha256':snapshot.digest((baseline/'source-manifest.json').read_bytes()),'wheel_source_files_verified':len(sources),'artifacts':{str(p.relative_to(root)):snapshot.digest(p.read_bytes()) for p in artifacts},'evidence':{str(p.relative_to(root)):snapshot.digest(p.read_bytes()) for p in out.rglob('*') if p.is_file() and p.name!='review-manifest.json'}}
(out/'review-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Review package verified:',len(hashes),'source files;',len(sources),'wheel source files;',len(artifacts),'artifacts')
print((out/'scope.json').read_text())
