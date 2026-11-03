"""Real local files: atomic installation, project isolation and integrity failures."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from rpb.adapters.immutable_files import FileIntegrityError, ImmutableFileStore


def test_same_identity_is_idempotent_and_conflicting_write_cannot_overwrite(tmp_path):
    store = ImmutableFileStore(tmp_path)
    project, attempt, identity = uuid4(), uuid4(), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        digests = list(
            pool.map(lambda _: store.write(project, attempt, identity, b"original"), range(2))
        )
    assert digests[0] == digests[1]
    with pytest.raises(FileIntegrityError):
        store.write(project, attempt, identity, b"different")
    assert store.read(project, attempt, identity, digests[0]) == b"original"
    with pytest.raises(FileNotFoundError):
        store.read(uuid4(), attempt, identity, digests[0])
    path = tmp_path / str(project) / str(attempt) / str(identity)
    path.chmod(0o600)
    path.write_bytes(b"tampered")
    with pytest.raises(FileIntegrityError):
        store.read(project, attempt, identity, digests[0])


def test_symlinked_scope_cannot_escape_the_root(tmp_path):
    project, attempt = uuid4(), uuid4()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / str(project)).symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        ImmutableFileStore(tmp_path).write(project, attempt, uuid4(), b"data")
    assert list(outside.iterdir()) == []
    with pytest.raises(FileIntegrityError):
        ImmutableFileStore(tmp_path).write("../outside", attempt, uuid4(), b"data")


def test_fifo_object_is_rejected_without_waiting_for_a_writer(tmp_path):
    project, attempt, identity = uuid4(), uuid4(), uuid4()
    directory = tmp_path / str(project) / str(attempt)
    directory.mkdir(parents=True)
    os.mkfifo(directory / str(identity))
    with pytest.raises(FileIntegrityError):
        ImmutableFileStore(tmp_path).read(project, attempt, identity, "not-a-digest")


def test_discard_cannot_follow_symlink_and_repeated_missing_is_safe(tmp_path):
    store = ImmutableFileStore(tmp_path)
    project, attempt, identity = uuid4(), uuid4(), uuid4()
    target = tmp_path / "unrelated"
    target.write_bytes(b"keep")
    scoped = tmp_path / str(project) / str(attempt)
    scoped.mkdir(parents=True)
    (scoped / str(identity)).symlink_to(target)
    store.discard(project, attempt, identity)
    store.discard(project, attempt, identity)
    assert target.read_bytes() == b"keep"
    scoped.rmdir()
    scoped.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        store.discard(project, attempt, identity)
    assert target.read_bytes() == b"keep"
