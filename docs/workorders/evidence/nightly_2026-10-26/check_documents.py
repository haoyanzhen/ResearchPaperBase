from pathlib import Path
import re,json,subprocess,hashlib,tarfile,difflib
root=Path.cwd(); ev=root/'docs/workorders/evidence/nightly_2026-10-26'
files=(ev/'changed-files.txt').read_text().splitlines()+['docs/workorders/nightly_maintenance_2026-10-26.md']
errors=[];links=0;anchors=0
# GitHub heading IDs for these documents, including Unicode and duplicate headings.
def ids(s):
 out=set();counts={}
 for h in re.findall(r'^#{1,6}\s+(.+)$',s,re.M):
  h=re.sub(r'\[([^]]+)\]\([^)]*\)',r'\1',h)
  h=re.sub(r'[^\w\-\s]','',h.lower()).replace(' ','-')
  n=counts.get(h,0);counts[h]=n+1;out.add(h+(f'-{n}' if n else ''))
 return out
for n in files:
 p=root/n;s=p.read_text()
 if not re.search(r'文档版本：v1\.\d+',s) or '更新日期：2026-10-26' not in s: errors.append(n+': version/date')
 for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',s):
  if '://' in target:continue
  name,_,anchor=target.partition('#'); q=(p.parent/name).resolve() if name else p
  links+=1
  # Output evidence is produced by this check/finalization after validation.
  if q in [ev/'validation.json',ev/'success.json',ev/'after/source-manifest.json',ev/'input-output-hashes.json',ev/'maintenance.patch']:continue
  if not q.exists():errors.append(f'{n}: missing {target}');continue
  if anchor:
   anchors+=1
   if anchor not in ids(q.read_text()):errors.append(f'{n}: anchor {target}')
 for i,l in enumerate(s.splitlines(),1):
  if l.endswith((' ','\t')) and not l.endswith('  '):errors.append(f'{n}:{i}: trailing whitespace')
plan=(root/'docs/workorders/preimplementation_design_tasks_2026-10-21.md').read_text()
coverage=plan.split('### 10.1')[1].split('### 10.2')[0]
fr=re.findall(r'^#### (FR-\d+) ',(root/'docs/design/01_functional_requirements.md').read_text(),re.M)
for id in fr:
 # Count only the FR-range column, not discussion cross-references.
 count=sum(id in l.split('|')[2] for l in coverage.splitlines() if l.startswith('|') and len(l.split('|'))>=5)
 if count!=1:errors.append(f'{id}: primary assignments {count}')
status=(root/'docs/PROJECT_STATUS.md').read_text()
tracks=re.findall(r'^\| (TRACK-[\da-z]+) \|',status,re.M)
trackmap=plan.split('### 10.2')[1].split('### 10.3')[0]
for id in tracks:
 count=sum(id in re.findall(r'TRACK-[\da-z]+',l.split('|')[1]) for l in trackmap.splitlines() if l.startswith('|'))
 if count!=1:errors.append(f'{id}: assignments {count}')
for prefix,total in [('A',10),('B',8),('H',3)]:
 for i in range(1,total+1):
  id=f'{prefix}{i:02}'
  pattern=rf'^### {id} ' if prefix=='A' else rf'^\| {id}[ ，]'
  if len(re.findall(pattern,plan,re.M))!=1:errors.append(f'{id}: definition count')
# Hard edges in A definitions; A06 mutual alignment is deliberately not an edge.
edges={'A01':[],'A02':['A01'],'A03':['A01'],'A04':['A01'],'A05':['A01','A04'],'A06':['A01'],'A07':['A01','A04'],'A08':['A04','A05','A06','A07'],'A09':['A01','A02','A06'],'A10':['A03']}
def walk(n,stack):
 if n in stack:errors.append('dependency cycle '+str(stack+[n]));return
 for d in edges[n]:walk(d,stack+[n])
for n in edges:walk(n,[])
r=subprocess.run(['git','diff','--check','--',*files],capture_output=True,text=True)
if r.returncode:errors.append(r.stdout+r.stderr)
with tarfile.open(ev/'before/source.tar.gz') as t:
 old={m.name:t.extractfile(m).read() for m in t if m.isfile()}

# Verify version increment and task identifier uniqueness, including untracked task files.
for n in files:
 before=old.get(n,b'').decode(); after=(root/n).read_text()
 v=re.search(r'文档版本：v1\.(\d+)',before); w=re.search(r'文档版本：v1\.(\d+)',after)
 if int(w[1])!=(int(v[1])+1 if v else 0):errors.append(n+': version increment')
taskids={}
for p in (root/'tasks').glob('*.md'):
 m=re.match(r'(\d+)-',p.name)
 if m:
  if m[1] in taskids:errors.append('duplicate task '+m[1])
  taskids[m[1]]=str(p)
hp=(root/'tasks/013-human-content-protection-plan.md').read_text()
if len(re.findall(r'^\| HP-E\d{2} ',hp,re.M))!=11:errors.append('HP content rows')
diff='' 
for n in files:
 diff+=''.join(difflib.unified_diff(old.get(n,b'').decode().splitlines(True),(root/n).read_text().splitlines(True),fromfile='before/'+n,tofile='after/'+n))
(ev/'maintenance.patch').write_text(diff)
result={'files':files,'local_links':links,'anchors':anchors,'FR_primary_assignments':len(fr),'open_TRACK_assignments':len(tracks),'A_B_H_definitions':21,'hard_dependency_cycle_check':'passed' if not errors else 'see errors','git_diff_check_exit':r.returncode,'errors':errors,'scope':'document structure and coverage routing; semantic self-review recorded in report; no business tests rerun'}
(ev/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(errors))
