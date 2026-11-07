"""Shared escaping for local filenames embedded in FFmpeg filter expressions."""

from pathlib import Path


def filter_path(path: Path) -> str:
    value = path.as_posix()
    value = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return "".join("\\" + char if char in "\\'[],;" else char for char in value)
