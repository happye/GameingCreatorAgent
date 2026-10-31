import json
import re
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_clip_replacement_jobs import replacements  # noqa: F401
from test_creation_jobs import service  # noqa: F401

from gamingcreator.ui.server import create_server


def test_candidate_range_head_and_no_worker(replacements):  # noqa: F811
    jobs, root, _ = replacements
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    before = sorted(jobs.jobs.iterdir())
    try:
        with urlopen(base + "/creation") as response:
            scripts = re.findall(r'<script src="([^"]+)"', response.read().decode("utf-8"))
        assert "/assets/source-clock.js" in scripts
        for script in scripts:
            with urlopen(base + script) as response:
                assert response.status == 200
                assert response.headers["Content-Type"].startswith("text/javascript")
        route = f"/api/creation/jobs/{root}/candidates?planId=hook-first"
        with urlopen(base + route) as response:
            catalog = json.load(response)
        candidate = next(c for c in catalog["candidates"] if c["runId"] == "B")
        assert candidate["sourceName"] and not any(c in candidate["sourceName"] for c in "/\\")
        with urlopen(
            Request(base + candidate["previewUrl"], headers={"Range": "bytes=0-3"})
        ) as response:
            assert response.status == 206
            assert response.read() == b"sour"
        with urlopen(Request(base + candidate["previewUrl"], method="HEAD")) as response:
            assert response.status == 200
            assert response.read() == b""
        for url in (
            route + "&path=x",
            candidate["previewUrl"] + "&path=x",
            candidate["previewUrl"].replace(candidate["candidateId"], "0" * 64),
        ):
            with pytest.raises(HTTPError):
                urlopen(base + url)
        assert before == sorted(jobs.jobs.iterdir())
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
