"""Verified registered media and bounded single-range HTTP responses."""

import hashlib
import os
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from gamingcreator.domain.errors import AppError, ExitCode


@dataclass(frozen=True, slots=True)
class MediaResource:
    path: Path
    sha256: str
    content_type: str


def byte_range(header: str | None, size: int) -> tuple[int, int, bool]:
    """Return offset, length, partial; reject unsupported or unsatisfiable ranges."""
    if header is None:
        return 0, size, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if match is None or size <= 0 or not any(match.groups()):
        raise ValueError("Invalid range")
    left, right = match.groups()
    if not left:
        suffix = int(right)
        if suffix <= 0:
            raise ValueError("Invalid suffix")
        start, end = max(0, size - suffix), size - 1
    else:
        start, end = int(left), int(right) if right else size - 1
        if start >= size or end < start:
            raise ValueError("Unsatisfiable range")
        end = min(end, size - 1)
    return start, end - start + 1, True


class VerifiedMediaCache:
    """Bounded file identities, never video bytes; stat-check on every open."""

    def __init__(self) -> None:
        self._verified: OrderedDict[Path, tuple[tuple[int, ...], str]] = OrderedDict()
        self._lock = threading.Lock()

    def open(self, resource: MediaResource) -> BinaryIO:
        stream = resource.path.open("rb")
        try:
            with self._lock:
                # Windows CRT fstat timestamps can lose subsecond precision.
                # Path.stat supplies the file-system precision needed to detect
                # a same-size replacement within one second.
                before = resource.path.stat()
                handle = os.fstat(stream.fileno())
                if (before.st_dev, before.st_ino, before.st_size) != (
                    handle.st_dev,
                    handle.st_ino,
                    handle.st_size,
                ):
                    raise AppError(
                        "storage.integrity", "媒体已更改，请检查原文件。", ExitCode.STORAGE
                    )
                signature = (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                identity = signature, resource.sha256
                if self._verified.get(resource.path) != identity:
                    digest = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                    after = resource.path.stat()
                    unchanged = (
                        before.st_dev,
                        before.st_ino,
                        before.st_size,
                        before.st_mtime_ns,
                        before.st_ctime_ns,
                    ) == (
                        after.st_dev,
                        after.st_ino,
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    )
                    if digest.hexdigest() != resource.sha256 or not unchanged:
                        raise AppError(
                            "storage.integrity", "媒体已更改，请检查原文件。", ExitCode.STORAGE
                        )
                    self._verified[resource.path] = identity
                    if len(self._verified) > 128:
                        self._verified.popitem(last=False)
                self._verified.move_to_end(resource.path)
            stream.seek(0)
            return stream
        except BaseException:
            stream.close()
            raise
