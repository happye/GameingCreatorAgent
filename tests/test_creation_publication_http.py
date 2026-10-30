import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_publication import payload, rendered  # noqa: F401

from gamingcreator.ui.server import create_server


def test_publication_http_files_head_queries_and_version(rendered):  # noqa: F811
    jobs, render = rendered
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + f"/api/creation/jobs/{render}/publication") as response:
            assert json.load(response)["frames"] == 4
        with urlopen(
            Request(
                base + "/api/creation/publications",
                json.dumps(payload(jobs, render)).encode(),
                {"Content-Type": "application/json", "Origin": base},
            )
        ) as response:
            assert response.status == 202
            job_id = json.load(response)["jobId"]
        assert finish(server.creation_jobs, job_id)["status"] == "completed"
        for name in ("cover.png", "title.txt", "description.txt", "tags.json", "publication.json"):
            path = base + f"/api/creation/jobs/{job_id}/publication-files/{name}"
            for method in ("GET", "HEAD"):
                with urlopen(Request(path, method=method)) as response:
                    assert response.status == 200
                    assert int(response.headers["Content-Length"]) > 0
                    if name == "cover.png":
                        assert response.headers.get("Content-Type") == "image/png"
                        assert response.headers.get("Content-Disposition") is None
                    else:
                        assert response.headers["Content-Disposition"].startswith("attachment")
                    if method == "HEAD":
                        assert response.read() == b""
            with urlopen(path + "?download=1") as response:
                assert response.headers["Content-Disposition"].startswith("attachment")
        for suffix in (
            "cover.png?path=elsewhere",
            "../request.json",
            "receipt.json",
            "cover.png?download=0",
        ):
            with pytest.raises(HTTPError) as error:
                urlopen(base + f"/api/creation/jobs/{job_id}/publication-files/" + suffix)
            assert error.value.code in (400, 404)
        with urlopen(base + f"/api/creation/jobs/{job_id}/publication") as response:
            assert json.load(response)["draft"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
