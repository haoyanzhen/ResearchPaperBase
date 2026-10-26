from pathlib import Path
import hashlib,json,tarfile,tempfile,subprocess,zipfile
root=Path('/Users/qingyue/projects/ResearchPaperBase_codex'); base=root/'docs/workorders/evidence/skeleton_2026-10-22'
f=json.loads((base/'final.json').read_text()); initial=json.loads((base/'initial.json').read_text()); report={}
for group in ('source_sha256','artifact_sha256','evidence_sha256'):
 report[group]={'count':len(f[group]),'mismatches':[p for p,h in f[group].items() if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=h]}
with tarfile.open(base/'initial-files.tar.gz') as t:
 report['initial_snapshot']={'count':len(initial['sha256']),'mismatches':[p for p,h in initial['sha256'].items() if hashlib.sha256(t.extractfile(p).read()).hexdigest()!=h]}
 with tempfile.TemporaryDirectory(prefix='rpb-evidence-review-') as tmp:
  t.extractall(tmp,filter='data')
  apply=subprocess.run(['git','apply',str(base/'delivery.patch')],cwd=tmp,capture_output=True,text=True)
  report['reconstruction']={'apply_exit':apply.returncode,'stderr':apply.stderr,'mismatches':[p for p,h in f['source_sha256'].items() if not (Path(tmp)/p).is_file() or hashlib.sha256((Path(tmp)/p).read_bytes()).hexdigest()!=h]}
  history=subprocess.run([str(root/'backend/.venv/bin/python'),'-m','alembic','-c',str(Path(tmp)/'backend/alembic.ini'),'history'],cwd=tmp,capture_output=True,text=True)
  report['reconstructed_migration_history']={'exit':history.returncode,'stdout':history.stdout,'stderr':history.stderr}
with zipfile.ZipFile(next((root/'backend/dist').glob('*.whl'))) as z:
 names=[n for n in z.namelist() if n.startswith('rpb/') and n.endswith('.py')]
 report['wheel_sources']={'count':len(names),'mismatches':[n for n in names if z.read(n)!=(root/'backend/src'/n).read_bytes()]}
print(json.dumps(report,indent=2))
