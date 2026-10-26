"""Task012 scoped documentation checks; not a business test."""
from pathlib import Path
import hashlib,json,re,subprocess,tarfile,unicodedata,difflib,sys
root=Path(__file__).resolve().parents[5]
e=root/'docs/workorders/evidence/task012_a09_2026-10-23/closeout'
paths=['tasks/012-graph-rag-technical-design.md', 'docs/workorders/task012_a09_review_2026-10-23.md', 'docs/PROJECT_STATUS.md', 'docs/IMPLEMENTATION_ENTRY.md']
old={}
with tarfile.open(e/'before/source.tar.gz') as t:
 for m in t:
  old[m.name]=t.extractfile(m).read()
def anchors(s):
 found=set(re.findall(r'<a\s+id="([^"]+)"',s)); counts={}
 for line in s.splitlines():
  if re.match(r'^#{1,6} ',line):
   h=re.sub(r'^#+\s+','',line).lower()
   h=''.join(c for c in h if c in '-_ ' or unicodedata.category(c)[0] in 'LN')
   h=h.replace(' ','-'); n=counts.get(h,0);counts[h]=n+1
   found.add(h+(f'-{n}' if n else ''))
 return found
def links(name,s):
 errors=[]
 for dest in re.findall(r'\]\(([^\s)]+)\)',s):
  if '://' in dest or dest.startswith('mailto:'):continue
  file,_,anchor=dest.partition('#'); target=(root/name).parent/file if file else root/name
  if not target.exists():errors.append((dest,'missing file'))
  elif anchor and target.is_file() and target.suffix=='.md' and anchor not in anchors(target.read_text()):errors.append((dest,'missing anchor'))
 return errors
errors=[];preexisting=[];patch=[]
for name in paths:
 s=(root/name).read_text(); previous=old.get(name,b'').decode()
 for err in links(name,s):
  if err in links(name,previous):preexisting.append((name,*err))
  else:errors.append((name,*err))
 v=re.search(r'文档版本：v1\.(\d+)',s);ov=re.search(r'文档版本：v1\.(\d+)',previous)
 if not v or (ov and int(v[1])!=int(ov[1])+1) or (not ov and v[1]!='0'):errors.append((name,'minor version'))
 if '更新日期：2026-10-24' not in s:errors.append((name,'date'))
 for i,l in enumerate(s.splitlines(),1):
  if l.rstrip()!=l and l not in previous.splitlines():errors.append((name,f'new trailing whitespace {i}'))
 patch.extend(difflib.unified_diff(previous.splitlines(True),s.splitlines(True),fromfile='before/'+name,tofile='after/'+name))
for n in range(1,19):
 sid=f'KG-{n:02}'
 for name in ['tasks/012-graph-rag-technical-design.md','docs/workorders/task012_a09_review_2026-10-23.md']:
  if sid not in (root/name).read_text():errors.append((name,sid,'missing trace row'))
# Every pre-existing file outside the authorized doc scope must stay byte-identical.
changes=[n for n,b in old.items() if n not in paths and (not (root/n).exists() or (root/n).read_bytes()!=b)]
if changes:errors.append(('outside_scope_changes',changes))
patch.extend(difflib.unified_diff(old['contracts/p0.coverage.json'].decode().splitlines(True),(root/'contracts/p0.coverage.json').read_text().splitlines(True),fromfile='before/contracts/p0.coverage.json',tofile='after/contracts/p0.coverage.json'))
(e/'delivery.patch').write_text(''.join(patch))
(e/'reviewed-sha256.json').write_text(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths},indent=2)+'\n')
result={'errors':errors,'preexisting_link_findings':preexisting,'checked_files':len(paths),'trace_rows':18,'outside_scope_changes':changes,'level':'documentation only; no business execution'}
print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(bool(errors))
