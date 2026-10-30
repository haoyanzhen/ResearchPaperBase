import json, subprocess, sys, os
from pathlib import Path
base=Path(__file__).resolve().parent
name=sys.argv[1]; cmd=sys.argv[2:]
junit = bool(cmd and cmd[0] == '--junit')
if junit:
    cmd = cmd[1:]
    os.environ['PYTEST_ADDOPTS'] = os.environ.get('PYTEST_ADDOPTS', '') + ' --junitxml=' + str(base/(name+'-tests.xml'))
with (base/(name+'.log')).open('x') as f:
    r=subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
(base/(name+'-run.json')).write_text(json.dumps({'command':cmd,'exit_code':r.returncode,'pytest_addopts':os.environ.get('PYTEST_ADDOPTS')},indent=2))
args=[sys.executable,'scripts/delivery_summary.py',str(base/(name+'-tests.xml' if junit else name+'.log'))]
if not junit: args+=['--log']
s=subprocess.run(args+['--exit-code',str(r.returncode),'--chars','3500'],capture_output=True,text=True)
(base/(name+'-summary.json')).write_text(s.stdout)
print(s.stdout)
if s.stderr: print(s.stderr)
sys.exit(r.returncode or s.returncode)
