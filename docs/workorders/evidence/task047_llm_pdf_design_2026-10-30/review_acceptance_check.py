import hashlib, json, subprocess
from pathlib import Path
r=Path.cwd(); old=r/'docs/workorders/evidence/task046_processing_gate_2026-10-29'; a=json.loads((r/'docs/workorders/evidence/task046_acceptance_2026-10-30/accepted-baseline.json').read_text())
m=json.loads((old/'delivery-artifacts.json').read_text());m.update(json.loads((old/'platform-artifacts.json').read_text()))
allowed={'tasks/046-paper-processing-gate.md','docs/PROJECT_STATUS.md'}
old_diff=[f for f,h in m.items() if a['scope_hashes'].get(f)!=h]
now_diff=[f for f,h in a['scope_hashes'].items() if hashlib.sha256((r/f).read_bytes()).hexdigest()!=h]
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
staged=subprocess.check_output(['git','diff','--cached','--name-only'],text=True)
print(json.dumps({'accepted_at':a['accepted_at'],'user_statement':a['user_statement'],'head':head,'accepted_head':a['head'],'manifest_count':len(m),'accepted_count':len(a['scope_hashes']),'old_manifest_to_acceptance_changed':old_diff,'acceptance_to_current_changed':now_diff,'known_gaps':a['known_gaps'],'commit':a['commit'],'current_staged':staged,'accepted_staged':a['staged_status']},ensure_ascii=False,indent=2))
assert set(m)==set(a['scope_hashes'])
assert set(old_diff)<=allowed and set(now_diff)<=allowed
assert head==a['head'] and not staged and not a['staged_status']
