"""Run the two reviewed defects in a disposable source copy, never edit working sources."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path.cwd()
evidence = root / 'docs/workorders/evidence/task015_b02_2026-10-25'
with tempfile.TemporaryDirectory(prefix='rpb-b02-regression-') as tmp:
    clone = Path(tmp)
    shutil.copytree(root / 'backend', clone / 'backend', ignore=shutil.ignore_patterns(
        '.venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'dist'))
    (clone / 'scripts').mkdir()
    runner = clone / 'scripts/run_storage_tests.py'
    shutil.copy2(root / 'scripts/run_storage_tests.py', runner)
    migration = clone / 'backend/migrations/versions/0001_account.py'
    migration.write_text(migration.read_text().replace(
        '    op.execute("LOCK TABLE accounts IN ACCESS EXCLUSIVE MODE")\n', ''))
    runner.write_text(runner.read_text().replace(
        '        password_file.unlink()  # Never expose fixture administrator credentials to child tests.\n', ''
    ).replace('        if password_file.exists():\n            raise RuntimeError("Fixture administrator credential cleanup failed")\n', ''))
    result = subprocess.run([str(root/'backend/.venv/bin/python'), str(runner), '--postgres-bin',
                             '/opt/homebrew/opt/postgresql@17/bin'], cwd=clone,
                            capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    (evidence / 'regression-mutations.log').write_text(output)
    assert result.returncode == 1, output
    assert 'FAILED tests/integration/test_account_storage.py::test_ac06_concurrent_committing_writer_prevents_downgrade' in output
    assert 'FAILED tests/integration/test_fixture_cleanup.py::test_ac11_child_has_only_test_role_credentials' in output
    assert '"server_stopped": true, "root_removed": true' in output
print(json.dumps(dict(defects_detected=['R01', 'R02'], source_copy_removed=True)))
