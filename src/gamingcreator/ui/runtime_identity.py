"""Stable source identity for one workspace server process (stdlib only)."""

import argparse
import hashlib
import json
import os
from pathlib import Path

SOURCE_SUFFIXES = frozenset({".py", ".js", ".css", ".html", ".json", ".txt", ".svg"})


def runtime_identity(package_root: Path) -> dict[str, str]:
    """Hash sorted package source paths and bytes, excluding caches and user files."""
    root = package_root.resolve(strict=True)
    digest = hashlib.sha256()
    sources: list[Path] = []
    for directory, children, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        children[:] = [
            name
            for name in children
            if not name.startswith(".")
            and name != "__pycache__"
            and not (parent / name).is_symlink()
            and not (parent / name).is_junction()
            and (parent / name).resolve().is_relative_to(root)
        ]
        sources.extend(
            parent / name
            for name in files
            if not name.startswith(".") and Path(name).suffix in SOURCE_SUFFIXES
        )
    for path in sorted(sources, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return {
        "version": "workspace-runtime-v1",
        "packageRoot": str(root),
        "sha256": digest.hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", required=True, type=Path)
    print(json.dumps(runtime_identity(parser.parse_args().package_root)))
