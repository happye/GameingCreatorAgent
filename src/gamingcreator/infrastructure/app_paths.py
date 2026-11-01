"""Where bundled helper scripts live, in a source checkout or a packaged app folder."""

import sys
from pathlib import Path


def scripts_directory() -> Path:
    """The repository's scripts/ when run from source, else the app folder's scripts/.

    A packaged app installs the code into its own runtime (site-packages), so the checkout
    layout no longer applies; there the app root is the parent of the runtime prefix.
    """
    candidates = (
        Path(__file__).resolve().parents[3] / "scripts",
        Path(sys.prefix).resolve().parent / "scripts",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])
