import os, subprocess, sys
from pathlib import Path
root=Path.cwd()
evidence=root/'docs/workorders/evidence/task005_coverage_2026-10-22'
env=os.environ.copy();env['PATH']='/tmp/rpb-skeleton-tools/node_modules/.bin:'+env['PATH']
commands={
 'check':['python3','scripts/engineering.py','check'],
 'build':['python3','scripts/engineering.py','build'],
 'e2e':['python3','scripts/engineering.py','e2e'],
 'migration-history':['python3','scripts/engineering.py','migration-history'],
 'clean-delivery':['python3','scripts/verify_skeleton_delivery.py'],
}
for name in sys.argv[1:]:
 with (evidence/(name+'.txt')).open('w') as log:
  log.write('COMMAND: '+' '.join(commands[name])+'\n');log.flush()
  result=subprocess.run(commands[name],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
  log.write(f'\nEXIT: {result.returncode}\n')
 print(name, result.returncode, flush=True)
 if result.returncode:
  print((evidence/(name+'.txt')).read_text()[-8000:]);sys.exit(result.returncode)
