"""Create and verify a complete source snapshot, including empty and binary files."""

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_paths(root: Path) -> list[str]:
    paths = (
        subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    # The existing repository ignores .gitignore files themselves.
    paths += [
        str(p.relative_to(root))
        for p in [
            root / ".gitignore",
            root / "backend/.gitignore",
            root / "frontend/.gitignore",
        ]
        if p.is_file()
    ]
    return sorted(
        {
            p
            for p in paths
            if p and (root / p).is_file() and not p.startswith("docs/workorders/evidence/")
        }
    )


def safe_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name or not path.parts:
        raise ValueError(f"Unsafe snapshot path: {name}")


def create_snapshot(root: Path, paths: list[str], output: Path) -> dict[str, str]:
    # A new directory is mandatory: never overwrite a previously reviewed baseline.
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    with tarfile.open(output / "source.tar.gz", "w:gz") as archive:
        for name in sorted(set(paths)):
            safe_path(name)
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Expected regular source file: {name}")
            hashes[name] = digest(path.read_bytes())
            archive.add(path, arcname=name, recursive=False)
    (output / "source-manifest.json").write_text(json.dumps(hashes, indent=2) + "\n")
    verify_snapshot(output)
    return hashes


def verify_snapshot(output: Path) -> dict[str, str]:
    """Check complete reconstructed file bytes without unsafe filesystem extraction."""
    expected = json.loads((output / "source-manifest.json").read_text())
    actual = {}
    with tarfile.open(output / "source.tar.gz", "r:gz") as archive:
        for member in archive:
            safe_path(member.name)
            if not member.isfile() or member.name in actual:
                raise ValueError("Non-regular or duplicate snapshot member")
            content = archive.extractfile(member)
            if content is None:
                raise ValueError("Missing snapshot member bytes")
            actual[member.name] = digest(content.read())
    if actual != expected:
        raise ValueError("Reconstructed file set or SHA-256 differs from manifest")
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify"])
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "create":
        root = Path(__file__).resolve().parents[1]
        result = create_snapshot(root, source_paths(root), args.directory)
    else:
        result = verify_snapshot(args.directory)
    print(f"Verified complete snapshot: {len(result)} files, including empty files.")


if __name__ == "__main__":
    main()
