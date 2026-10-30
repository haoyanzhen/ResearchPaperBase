import hashlib,json,re
from pathlib import Path
files=['tasks/047-llm-pdf-extraction-design.md','docs/PROJECT_STATUS.md']
result={}
for f in files:
 p=Path(f); text=p.read_text(); assert '2026-10-30' in text
 assert re.search(r'版本[：:]\s*v1\.\d+',text)
 missing=[]
 for target in re.findall(r'\]\(([^)]+)\)',text):
  if '://' in target or target.startswith('#'):continue
  dest=(p.parent/target.split('#')[0]);
  if not dest.exists(): missing.append(target)
 assert not missing,(f,missing)
 result[f]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'local_file_links':'exist','version_date':'present'}
print(json.dumps(result,ensure_ascii=False,indent=2))
