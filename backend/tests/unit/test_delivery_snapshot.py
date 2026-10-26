import difflib
import importlib.util
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("snapshot", ROOT / "scripts/delivery_snapshot.py")
assert spec and spec.loader
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def test_snapshot_reconstructs_empty_binary_and_text_files(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    files = {"versions/.gitkeep": b"", "data.bin": b"\x00\xff", "plain.txt": b"no newline"}
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Reproduce why the original text-only delivery patch lost the empty addition.
    assert "".join(difflib.unified_diff([], "".splitlines(True))) == ""
    output = tmp_path / "baseline"
    expected = snapshot.create_snapshot(root, list(files), output)
    with tarfile.open(output / "source.tar.gz") as archive:
        archive.extractall(tmp_path / "restored", filter="data")
    restored = tmp_path / "restored"
    assert {
        str(p.relative_to(restored)): p.read_bytes() for p in restored.rglob("*") if p.is_file()
    } == files
    assert snapshot.verify_snapshot(output) == expected
    with pytest.raises(FileExistsError):
        snapshot.create_snapshot(root, list(files), output)


@pytest.mark.parametrize("mutation", ["missing", "tampered", "extra"])
def test_snapshot_rejects_incomplete_or_inconsistent_manifest(tmp_path, mutation):
    (tmp_path / "empty").touch()
    output = tmp_path / "baseline"
    data = snapshot.create_snapshot(tmp_path, ["empty"], output)
    if mutation == "missing":
        del data["empty"]
    elif mutation == "tampered":
        data["empty"] = "wrong-hash"
    else:
        data["not-in-archive"] = snapshot.digest(b"")
    (output / "source-manifest.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="file set or SHA-256"):
        snapshot.verify_snapshot(output)
