"""Project/attempt-scoped immutable files, atomically installed before publication."""

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4


class FileIntegrityError(ValueError):
    pass


class ImmutableFileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @contextmanager
    def _attempt_dir(self, project: UUID, attempt: UUID, create: bool) -> Iterator[int]:
        if not isinstance(project, UUID) or not isinstance(attempt, UUID):
            raise FileIntegrityError("invalid scope")
        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors = [root_fd]
        try:
            for name in (str(project), str(attempt)):
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=descriptors[-1])
                        os.fsync(descriptors[-1])
                    except FileExistsError:
                        pass
                descriptors.append(
                    os.open(
                        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptors[-1]
                    )
                )
            yield descriptors[-1]
        finally:
            for fd in reversed(descriptors):
                os.close(fd)

    def stamp(self, project: UUID, attempt: UUID, object_id: UUID) -> list[int]:
        """Identify an immutable file without loading its bytes at commit."""
        if not isinstance(object_id, UUID):
            raise FileIntegrityError("invalid object identity")
        with self._attempt_dir(project, attempt, False) as directory:
            info = os.stat(str(object_id), dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise FileIntegrityError("invalid object")
        return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]

    def read(self, project: UUID, attempt: UUID, object_id: UUID, expected_digest: str) -> bytes:
        if not isinstance(object_id, UUID):
            raise FileIntegrityError("invalid object identity")
        with self._attempt_dir(project, attempt, False) as directory:
            fd = os.open(
                str(object_id), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 52_428_800:
                    raise FileIntegrityError("invalid object")
                data = stream.read(52_428_801)
                if len(data) > 52_428_800:
                    raise FileIntegrityError("invalid object")
        if hashlib.sha256(data).hexdigest() != expected_digest:
            raise FileIntegrityError("object digest mismatch")
        return data

    def write(self, project: UUID, attempt: UUID, object_id: UUID, data: bytes) -> str:
        if not isinstance(object_id, UUID) or not isinstance(data, bytes) or len(data) > 52_428_800:
            raise FileIntegrityError("invalid object")
        digest = hashlib.sha256(data).hexdigest()
        with self._attempt_dir(project, attempt, True) as directory:
            temporary = "." + str(uuid4())
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o400)
                    os.fsync(stream.fileno())
                try:
                    os.link(
                        temporary,
                        str(object_id),
                        src_dir_fd=directory,
                        dst_dir_fd=directory,
                        follow_symlinks=False,
                    )
                    os.fsync(directory)
                except FileExistsError:
                    # Repeated delivery can only reuse the same immutable bytes.
                    if self.read(project, attempt, object_id, digest) != data:
                        raise FileIntegrityError("object identity conflict")
            finally:
                os.unlink(temporary, dir_fd=directory)
        return digest
