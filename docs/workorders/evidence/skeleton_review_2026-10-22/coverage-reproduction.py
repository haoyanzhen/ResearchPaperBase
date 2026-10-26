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
    assert result.returncode == 0, 'The expected missing-assertion reproduction did not succeed'

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
        output, _ = process.communicate(timeout=4)
        print('WORKER_STUCK: unexpectedly completed', process.returncode, output)
        raise AssertionError('The expected unbounded-read reproduction did not succeed')
    except subprocess.TimeoutExpired:
        print('WORKER_STUCK: external 4s deadline hit; pytest is blocked before communicate(timeout=10).')
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        print('Isolated pytest/worker process group killed; temporary files removed on exit.')
