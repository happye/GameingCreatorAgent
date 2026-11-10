"""Every job state the backend writes has a Chinese label in Studio (no raw English status)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_backend_job_states_are_labelled():
    backend = (ROOT / "src/gamingcreator/ui/creation_jobs.py").read_text(encoding="utf-8")
    states = set(re.findall(r'"status"\s*[:=]\s*"([a-z_]+)"|status="([a-z_]+)"', backend))
    states = {a or b for a, b in states} | {"pending", "running", "completed", "failed"}
    api = (ROOT / "src/gamingcreator/ui/static/studio/api.js").read_text(encoding="utf-8")
    table = re.search(r"export const JOB_STATUS = \{([^}]*)\}", api).group(1)
    labelled = set(re.findall(r"(\w+):", table))
    assert states <= labelled, states - labelled
