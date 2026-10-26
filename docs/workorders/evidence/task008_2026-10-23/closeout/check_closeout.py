"""Verify task008 record-only closeout against the accepted delivery; no app tests."""
from pathlib import Path
import ast,hashlib,json,re,tarfile,unicodedata,difflib,sys
root=Path(__file__).resolve().parents[5]
b=root/'docs/workorders/evidence/task008_2026-10-23'; out=b/'closeout'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
# Reuse only the already reviewed pure link functions, never its output-writing main.
tree=ast.parse((b/'check_docs.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('anchors','links')],type_ignores=[]),'<pure-link-checks>','exec'))
changed=['tasks/008-material-policy-internal-contracts.md','docs/PROJECT_STATUS.md','docs/workorders/task008_internal_contract_review_2026-10-23.md']
design=['docs/design/'+n for n in ['05_application_use_cases.md','05-01_internal_module_contracts.md','06_agent_knowledge_services.md','07_data_persistence.md','09_quality_observability.md']]
manifest=json.loads((b/'delivery/source-manifest.json').read_text()); entry=json.loads((out/'entry.json').read_text());errors=[]
assert sha(b/'delivery/source-manifest.json')==entry['accepted_manifest_sha256']
old={}
with tarfile.open(b/'delivery/source.tar.gz') as t:
 for m in t:old[m.name]=t.extractfile(m).read()
if {n:hashlib.sha256(v).hexdigest() for n,v in old.items()}!=manifest:errors.append('accepted archive mismatch')
actual=[n for n,h in manifest.items() if not (root/n).is_file() or sha(root/n)!=h]
if set(actual)!=set(changed):errors.append(['unexpected diff',actual])
patch=[]
for n in changed+design:
 s=(root/n).read_text();prev=old[n].decode();errors.extend([[n,*err] for err in links(n,s)])
 v=int(re.search(r'文档版本：v1\.(\d+)',s)[1]);ov=int(re.search(r'文档版本：v1\.(\d+)',prev)[1])
 if v!=ov+(1 if n in changed else 0):errors.append([n,'version'])
 if '更新日期：2026-10-23' not in s:errors.append([n,'date'])
 if n in changed:
  patch.extend(difflib.unified_diff(prev.splitlines(True),s.splitlines(True),fromfile='accepted/'+n,tofile='closeout/'+n))
  for i,line in enumerate(s.splitlines(),1):
   if line.rstrip()!=line and line not in prev.splitlines():errors.append([n,'whitespace',i])
for i in range(1,13):
 for n in [changed[0],design[-1],changed[2]]:
  if not re.search(r'^\| IC-'+f'{i:02}'+r' /|^\| IC-'+f'{i:02}'+r' \|',(root/n).read_text(),re.M):errors.append([n,'trace missing',i])
for n,h in entry['existing_evidence'].items():
 if not (b/n).is_file() or sha(b/n)!=h:errors.append(['historical evidence changed',n])
result={'errors':errors,'checked_documents':8,'trace_scenarios':12,'accepted_snapshot_files':len(manifest),'unchanged_design_files':5,'record_only_changes':actual,'preserved_existing_evidence_files':len(entry['existing_evidence']),'level':'documentation and snapshot verification only; business runtime untested'}
(out/'record-changes.patch').write_text(''.join(patch))
(out/'s7-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(bool(errors))
