import hashlib, json, importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('snap','scripts/delivery_snapshot.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=Path.cwd(); evidence=root/'docs/workorders/evidence/task005_coverage_2026-10-22'
hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in m.source_paths(root) if n.startswith(('backend/','frontend/','scripts/','contracts/'))}
p=evidence/'verification-inputs.json'
if not p.exists():p.write_text(json.dumps(hashes,indent=2)+'\n')
else:
 old=json.loads(p.read_text());changed=[n for n in set(old)|set(hashes) if old.get(n)!=hashes.get(n)]
 print('Verification input changes:',changed)
 if changed:raise SystemExit(1)
