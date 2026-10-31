"""Reclaim only explicitly owned pytest media, never source trees or user outputs."""

import argparse
import ctypes
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath

MEDIA = {".nut", ".mp4", ".mkv", ".webm", ".wav", ".pcm", ".avi", ".mov"}
LIMIT = 1024 * 1024
PROTECTED = {
    "workspace",
    "models",
    "artifacts",
    "GameVideos",
    ".git",
    ".tools",
    ".venv",
    "worktrees",
    ".worktrees",
    "downloads",
    "huggingface",
}
PROTECTED_FOLDED = {name.casefold() for name in PROTECTED}


def linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 1024)


def safe_root(root: Path, cache: Path, fixture_base: Path | None = None) -> bool:
    root, cache = root.absolute(), cache.absolute()
    try:
        relative = root.relative_to(cache)
        if (
            not relative.parts
            or any(p in (".", "..") for p in relative.parts)
            or any(p.casefold() in PROTECTED_FOLDED for p in relative.parts)
            or not root.name.startswith("test_")
        ):
            return False
        if fixture_base is None:
            # Manual callers may only target the established managed pytest layout.
            if (
                len(relative.parts) != 4
                or relative.parts[0] != "pytest-runs"
                or relative.parts[2] != "tmp"
            ):
                return False
        elif root.parent != fixture_base.absolute() or fixture_base.absolute() == cache:
            return False
        return cache.name == ".cache" and not any(linked(p) for p in (root, *root.parents))
    except (ValueError, OSError):
        return False


def _delete_exclusive(path: Path) -> bool:
    if os.name != "nt":
        path.unlink()
        return True
    # A native exclusive handle avoids starting PowerShell for every media file.
    # DELETE_ON_CLOSE unlinks this file while the exclusive handle is still held.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x04200000, None)
    if handle == ctypes.c_void_p(-1).value:
        return False
    return bool(kernel.CloseHandle(handle))


def _record(path: Path, root: Path, failed: bool, apply: bool) -> dict:
    record = {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "failed_test": failed,
        "deleted": False,
    }
    audit = root / "media-reclamation.jsonl"
    try:
        if audit.exists() and (linked(audit) or audit.stat().st_nlink != 1):
            raise ValueError("Audit path cannot be a link")
        if any(linked(p) for p in (path, *path.parents)):
            raise ValueError("Media path cannot traverse links")
        with path.open("rb") as stream:
            record["prefix_sha256"] = hashlib.sha256(stream.read(4096)).hexdigest()
        with audit.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        if apply:
            if path.stat().st_size != record["bytes"]:
                record["skipped"] = "file changed"
            else:
                record["deleted"] = _delete_exclusive(path)
            with audit.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        record["skipped"] = "file or audit unavailable"
    return record


def reclaim(
    root: Path, cache: Path, *, failed: bool, apply: bool = False, fixture_base: Path | None = None
) -> list[dict]:
    if os.environ.get("GC_KEEP_TEST_MEDIA") == "1" or not safe_root(root, cache, fixture_base):
        return []
    root = root.absolute()
    records = []
    stack = [root]
    while stack:
        for path in stack.pop().iterdir():
            if linked(path) or path.name.casefold() in PROTECTED_FOLDED:
                continue
            if path.is_dir():
                stack.append(path)
            elif path.suffix.lower() in MEDIA and (not failed or path.stat().st_size >= LIMIT):
                records.append(_record(path, root, failed, apply))
    return records


def manual_files(
    cache: Path, relatives: list[str], *, apply: bool = False, minimum_age_hours: int = 24
) -> list[dict]:
    import time

    cache = cache.absolute()
    records = []
    for relative in relatives:
        parts = PurePosixPath(relative.replace("\\", "/")).parts
        if (
            len(parts) < 5
            or parts[0] != "pytest-runs"
            or parts[2] != "tmp"
            or any(p in (".", "..") or ":" in p for p in parts)
            or not parts[3].startswith("test_")
            or any(p.casefold() in PROTECTED_FOLDED for p in parts)
        ):
            raise ValueError("Only explicit managed pytest media paths are allowed")
        root = cache.joinpath(*parts[:4])
        path = cache.joinpath(*parts)
        if not safe_root(root, cache) or path.suffix.lower() not in MEDIA or not path.is_file():
            raise ValueError("Not an eligible generated test-media file")
        if time.time() - path.stat().st_mtime < max(24, minimum_age_hours) * 3600:
            raise ValueError("Recent test media is protected")
        records.append(_record(path, root, True, apply))
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relative-file", nargs="+", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--minimum-age-hours", type=int, default=24)
    args = parser.parse_args()
    print(
        json.dumps(
            manual_files(
                Path(__file__).resolve().parents[1] / ".cache",
                args.relative_file,
                apply=args.apply,
                minimum_age_hours=args.minimum_age_hours,
            ),
            ensure_ascii=False,
        )
    )
