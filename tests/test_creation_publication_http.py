import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_publication import payload, rendered  # noqa: F401

from gamingcreator.domain.platform_profile import validate_profile
from gamingcreator.ui import package_jobs
from gamingcreator.ui.server import create_server


def test_package_batch_http_accepts_four_full_length_cjk_copies(tmp_path, monkeypatch):
    server = create_server("127.0.0.1", 0, tmp_path)
    profiles = package_jobs.profiles()["profiles"]
    for profile in profiles:
        profile["Fields"]["publicationCopy"] = {
            "title": "攻略" * 100,
            "description": "关" * 5000,
            "tags": ["标" * 48 + f"{i:02}" for i in range(20)],
        }
    body = json.dumps({"profiles": profiles}).encode()
    assert len(body) > 65_536

    def submit(request):
        assert [validate_profile(profile) for profile in request["profiles"]] == profiles
        return {"batchId": "d" * 32}

    monkeypatch.setattr(server.creation_jobs.package_batches, "submit", submit)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(
            Request(
                base + "/api/creation/package-batches",
                body,
                {"Content-Type": "application/json", "Origin": base},
            )
        ) as response:
            assert response.status == 202 and json.load(response)["batchId"] == "d" * 32
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


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
            try:
                assert error.value.code in (400, 404)
            finally:
                error.value.close()
        with urlopen(base + f"/api/creation/jobs/{job_id}/publication") as response:
            assert json.load(response)["draft"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
