import json
import os
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[4]
label = sys.argv[1]
folder = Path(__file__).resolve().parent / label
folder.mkdir(exist_ok=False)
command = sys.argv[2:]
with (folder / 'output.log').open('x') as stream:
    result = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
(folder / 'run.json').write_text(json.dumps({'command':command,'exit_code':result.returncode,'pytest_addopts':os.environ.get('PYTEST_ADDOPTS'),'baseline':os.environ.get('DELIVERY_BASELINE', 's2-snapshot; later changes recorded in task checkpoint')}))
summary = subprocess.run([sys.executable, str(root/'scripts/delivery_summary.py'), str(folder/'output.log'), '--log', '--exit-code', str(result.returncode), '--chars','3000'],capture_output=True,text=True)
(folder/'summary.json').write_text(summary.stdout)
print(summary.stdout)
print(summary.stderr)
raise SystemExit(result.returncode or summary.returncode)
