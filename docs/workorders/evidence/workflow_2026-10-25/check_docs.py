from pathlib import Path
import re,json,hashlib,subprocess,difflib
root=Path(__file__).resolve().parents[4]
base=Path(__file__).resolve().parent
files=['AGENTS.md','docs/IMPLEMENTATION_ENTRY.md','.agents/skills/project-delivery/SKILL.md','tasks/example.md','docs/PROJECT_STATUS.md','docs/workorders/workflow_autonomy_2026-10-25.md']
errors=[]; links=0; patch=[]
for f in files:
 p=root/f;s=p.read_text();before=base/'before'/f
 if '2026-10-25' not in s: errors.append(f+': date')
 v=re.search(r'(?:文档版本：|Document version: )v1\.(\d+)',s)
 if not v: errors.append(f+': version missing')
 if before.exists():
  old=before.read_text();ov=re.search(r'(?:文档版本：|Document version: )v1\.(\d+)',old)
  if int(v[1])!=int(ov[1])+1: errors.append(f+': minor increment')
  patch.extend(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='before/'+f,tofile='after/'+f))
 for label,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',s):
  if '://' in target: continue
  path,_,anchor=target.partition('#');dest=p.parent/path if path else p
  if not dest.exists(): errors.append(f+': missing '+target);continue
  links+=1
  if anchor and dest.is_file():
   heads=re.findall(r'^#+\s+(.+)$',dest.read_text(),re.M)
   slugs=[re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-') for h in heads]
   if anchor not in slugs: errors.append(f+': missing anchor '+target)
entry=(root/files[1]).read_text();template=(root/files[3]).read_text()
rows=lambda s:re.findall(r'^\| (S\d [^|]+?) \|',s,re.M)
if rows(entry)!=rows(template): errors.append('stage tables differ')
(base/'changes.patch').write_text(''.join(patch))
r=subprocess.run(['git','diff','--check','--',*files],cwd=root,capture_output=True,text=True)
if r.returncode: errors.append(r.stdout+r.stderr)
validator=subprocess.run([str(root/'contracts/.venv/bin/python'),'/Users/qingyue/.codex/skills/.system/skill-creator/scripts/quick_validate.py',str(root/'.agents/skills/project-delivery')],capture_output=True,text=True)
if validator.returncode: errors.append(validator.stdout+validator.stderr)
result={'errors':errors,'files':files,'local_links_checked':links,'stage_tables_match':rows(entry)==rows(template),'scoped_diff_check_exit':r.returncode,'skill_validator':{'exit':validator.returncode,'stdout':validator.stdout,'stderr':validator.stderr},'sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files},'scope':'documentation only; no application tests or business execution'}
(base/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(errors))
