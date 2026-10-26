from pathlib import Path
import tempfile
import shutil
import os
import subprocess
import signal

root = Path('/Users/qingyue/projects/ResearchPaperBase_codex')
python = str(root / 'backend/.venv/bin/python')
with tempfile.TemporaryDirectory(prefix='rpb-review-coverage-') as tmp:
    directory = Path(tmp)
    shutil.copytree(root / 'backend/src/rpb', directory / 'rpb')
    shutil.copyfile(root / 'backend/tests/unit/test_startup.py', directory / 'test_startup.py')
    shutil.copyfile(root / 'backend/tests/unit/process_support.py', directory / 'process_support.py')
    env = {key: value for key, value in os.environ.items() if not key.startswith('RPB_')}
    env['PYTHONPATH'] = str(directory)
    health = directory / 'rpb/api/health.py'
    original = health.read_text()
    assert '@router.get("/health/live")' in original
    health.write_text(original.replace('@router.get("/health/live")', '@router.get("/health/live", status_code=201)'))
    result = subprocess.run(
        [python, '-m', 'pytest', '-p', 'no:cacheprovider', '-q',
         str(directory / 'test_startup.py') + '::test_probes_and_no_business_routes'],
        cwd=directory, env=env, capture_output=True, text=True, timeout=15,
    )
    print('LIVE_STATUS_201_MUTANT exit:', result.returncode)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 1 and 'assert 201 == 200' in result.stdout, '201 mutation must be rejected'

    worker = directory / 'rpb/bootstrap/worker.py'
    original = worker.read_text()
    target = 'print("Worker skeleton alive; task execution disabled; not ready.", flush=True)'
    assert target in original
    worker.write_text(original.replace(target, 'pass  # simulate startup stuck before ready output'))
    process = subprocess.Popen(
        [python, '-m', 'pytest', '-p', 'no:cacheprovider', '-q',
         str(directory / 'test_startup.py') + '::test_worker_idle_lifecycle'],
        cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=15)
        print('WORKER_STUCK: bounded failure', process.returncode, output)
        assert process.returncode == 1 and 'handshake timed out' in output
        print('Silent worker correctly rejected within external 15s limit; test cleanup completed.')
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
