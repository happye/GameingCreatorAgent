"""Bounded Windows file-sharing waits around individual state-file operations."""

import os
import time
from collections.abc import Callable
from errno import EACCES


def retry_file_sharing[IOResult](
    operation: Callable[[], IOResult], *, reading: bool = False
) -> IOResult:
    """Wait briefly for Windows file sharing; never retry the workflow operation."""
    deadline = time.monotonic() + 1.0
    while True:
        try:
            return operation()
        except OSError as error:
            remaining = deadline - time.monotonic()
            winerror = getattr(error, "winerror", None)
            # Windows CRT open() drops the native sharing code and exposes EACCES.
            read_access_denied = (
                reading
                and os.name == "nt"
                and isinstance(error, PermissionError)
                and error.errno == EACCES
                and winerror is None
            )
            if (winerror not in {5, 32, 33} and not read_access_denied) or remaining <= 0:
                raise
            time.sleep(min(0.05, remaining))
