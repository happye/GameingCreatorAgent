import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.ui.server import create_server


def test_http_edit_revision_render_roundtrip(revisions):  # noqa: F811
    jobs, root, calls = revisions
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(route, value):
        return urlopen(
            Request(
                base + route,
                json.dumps(value).encode(),
                {"Content-Type": "application/json", "Origin": base},
            ),
            timeout=30,
        )

    def get(route):
        with urlopen(base + route, timeout=30) as response:
            return json.load(response)

    try:
        before = {p: p.read_bytes() for p in jobs.directory(root).rglob("*") if p.is_file()}
        snap = get(f"/api/creation/jobs/{root}/edit?planId=hook-first")
        assert snap["parentJobId"] == root
        assert all(p.read_bytes() == value for p, value in before.items())
        payload = {k: snap[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
        payload.update(
            requestId="b" * 32,
            clips=[
                {k: r[k] for k in ("clipId", "startUs", "outputFrames")}
                for r in reversed(snap["clips"])
            ],
        )
        for clip in payload["clips"]:
            clip["outputFrames"] = 5
        with post("/api/creation/revisions", payload) as response:
            assert response.status == 202
            revision = json.load(response)["jobId"]
        assert finish(server.creation_jobs, revision)["status"] == "completed"
        revised = get(f"/api/creation/jobs/{revision}")
        assert revised["editor"]["parentJobId"] == revision
        assert revised["editor"]["planId"] == "hook-first"
        assert revised["editor"] == get(f"/api/creation/jobs/{revision}/edit?planId=hook-first")
        with post(
            "/api/creation/renders",
            {"requestId": "c" * 32, "revisionJobId": revision, "width": 320, "height": 180},
        ) as response:
            rendered = json.load(response)["jobId"]
        assert finish(server.creation_jobs, rendered)["status"] == "completed"
        assert calls[-1].frames == 5 * len(payload["clips"])
        for suffix in ("", "?planId=hook-first&path=outside"):
            with pytest.raises(HTTPError):
                get(f"/api/creation/jobs/{root}/edit" + suffix)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
