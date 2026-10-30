import hashlib,json,re,subprocess
from pathlib import Path
base=Path('docs/workorders/evidence/task047_acceptance_2026-10-30')
d=json.loads((base/'accepted-baseline.json').read_text())
records={'tasks/046-paper-processing-gate.md':'v1.11','tasks/047-llm-pdf-extraction-design.md':'v1.5','docs/PROJECT_STATUS.md':'v1.117'}
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==d['head']
prior=set(subprocess.check_output(['git','diff','--cached','--name-only'],text=True).splitlines())
allowed=set(json.loads((base/'candidate-files.json').read_text())) | {str(base/'candidate-files.json')}
assert prior <= allowed
for p,h in d['files'].items():
 if p not in records: assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
for p,v in records.items():
 s=Path(p).read_text();assert v in s and '2026-10-30' in s
 for t in re.findall(r'\]\(([^)]+)\)',s):
  if '://' not in t and not t.startswith('#'):assert (Path(p).parent/t.split('#')[0]).exists(),(p,t)
assert 'TRACK-023' in Path('docs/PROJECT_STATUS.md').read_text()
subprocess.run(['git','diff','--check'],check=True)
files=set(d['files'])
for name in ['task046_processing_gate_2026-10-29','task046_acceptance_2026-10-30','task047_llm_pdf_design_2026-10-30']:
 folder=base.parent/name
 for p in folder.iterdir():
  if not p.is_file():continue
  if name!='task046_processing_gate_2026-10-29' or p.suffix=='.md' or p.name in ['delivery-artifacts.json','platform-artifacts.json','run_check.py'] or p.name.startswith(('cleanup-db-final1','cleanup-unit-final','cleanup-types-final','cleanup-lint-final','cleanup-format-final','cleanup-contract-tests1','cleanup-contract2','cleanup-frontend2','cleanup-closeout1','capacity-storage2','platform-unit3','lint4','types3','contracts2','architecture1','review-runtime4','accepted-platform-image1')):files.add(str(p))
files.update(str(p) for p in base.iterdir() if p.is_file() and p.name != 'candidate-files.json')
files={p for p in files if not p.endswith('.log') and p != str(base/'candidate-files.json')}
# Freeze candidate bytes before staging. Logs for this check are generated outside the list.
manifest={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(files)}
(base/'candidate-files.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
files.add(str(base/'candidate-files.json'))
subprocess.run(['git','add','--',*sorted(files)],check=True)
actual=set(subprocess.check_output(['git','diff','--cached','--name-only'],text=True).splitlines())
assert actual==files, (actual-files,files-actual)
for p,h in manifest.items():assert hashlib.sha256(subprocess.check_output(['git','show',':'+p])).hexdigest()==h,p
subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)docs/workorders/evidence/**/*.xml'],check=True)
print('PASS: accepted code unchanged; versions/references/deferred decision verified; precise staged files:',len(actual))
