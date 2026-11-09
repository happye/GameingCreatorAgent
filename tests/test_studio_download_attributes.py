"""Studio htm templates must name every download.

A bare `download` attribute becomes download="true" in htm/preact, so a browser
that does not take the server's Content-Disposition saves the file as "true"
(J1 fourth trial: platform package arrived as true.txt).
"""

from __future__ import annotations

import re
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1] / "src" / "gamingcreator" / "ui" / "static" / "studio"
BARE = re.compile(r"\sdownload(?=[\s>/])")


def test_studio_templates_have_no_bare_download_attribute() -> None:
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(STUDIO.glob("*.js"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if BARE.search(line)
    ]
    assert offenders == []
