"""Path containment helpers that stay correct while other threads create or delete files."""

import os
import stat
import sys
from pathlib import Path

LONG_PREFIX = "\\\\?\\"
UNC_PREFIX = "\\\\?\\UNC\\"


def _final_path(path: Path) -> Path:
    """Fully resolved path of an existing file or directory; raises if it is missing.

    On Windows, non-strict Path.resolve() asks the OS twice and keeps a \\\\?\\ prefix when
    the two answers differ, so a parent created or deleted concurrently makes an in-tree
    path look foreign (TD012). One final-path query has no such window.
    """
    if sys.platform != "win32":
        return path.resolve(strict=True)
    from nt import _getfinalpathname  # type: ignore[attr-defined]

    final = _getfinalpathname(str(path))
    if final.startswith(UNC_PREFIX):
        return Path("\\\\" + final[len(UNC_PREFIX) :])
    if (
        final.startswith(LONG_PREFIX)
        and final[len(LONG_PREFIX) + 1 : len(LONG_PREFIX) + 3] == ":\\"
    ):
        return Path(final[len(LONG_PREFIX) :])
    # Volume GUID and other device paths stay prefixed, so containment checks reject them.
    return Path(final)


def resolve_existing(path: Path) -> Path:
    """Resolve links in the longest existing part of an absolute path; append the rest.

    The missing tail is joined lexically after os.path.abspath has removed "..", so it
    cannot climb out of the resolved directory. Errors other than "not found" propagate
    to the caller. A directory caught mid-deletion may resolve under $Extend\\$Deleted,
    which containment checks reject, so that race fails closed rather than open.
    """
    current = Path(os.path.abspath(path))
    tail: list[str] = []
    while True:
        try:
            resolved = _final_path(current)
        except FileNotFoundError:
            if current.parent == current:
                raise
            # A link that cannot be resolved is dangling; treating it as a missing name would
            # keep a path that really leads elsewhere. (An ordinary folder created since the
            # query is not a link, so concurrent creation does not trip this.)
            if is_link(current):
                raise OSError(f"Unresolvable link: {current}") from None
            name = current.name
            # A drive-like ("G:foo"), stream ("x:s") or dot name in the missing tail would
            # be reinterpreted by joinpath, so refuse it rather than guess its meaning.
            if ":" in name or name in {"", ".", ".."}:
                raise OSError(f"Unsupported path component: {name!r}") from None
            tail.append(name)
            current = current.parent
        else:
            return resolved.joinpath(*reversed(tail))


def is_link(path: Path) -> bool:
    """Whether a directory entry is a symlink or other reparse point (e.g. a junction).

    lstat reads the entry without opening the target, so a file being released, replaced
    or deleted cannot turn this into a spurious answer; a missing entry is not a link and
    any other error is treated as one, so callers fail closed.
    """
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    attributes = getattr(status, "st_file_attributes", 0)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
