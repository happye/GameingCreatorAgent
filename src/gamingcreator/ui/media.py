"""Verified registered media and bounded single-range HTTP responses."""

import re

from gamingcreator.infrastructure.verified_media import MediaResource, VerifiedMediaCache

__all__ = ["MediaResource", "VerifiedMediaCache", "byte_range"]


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
