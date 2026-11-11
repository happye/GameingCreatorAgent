import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_creation_jobs import finish, request, service  # noqa: F401

from gamingcreator.ui.server import create_server


def test_http_registered_jobs_and_conflict(service):  # noqa: F811
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(payload):
        return urlopen(
            Request(
                base + "/api/creation/plans",
                json.dumps(payload).encode(),
                {"Content-Type": "application/json", "Origin": base},
            ),
            timeout=10,
        )

    try:
        with post(request()) as response:
            assert response.status == 202
            result = json.load(response)
        job = finish(server.creation_jobs, result["jobId"])
        assert job["status"] == "completed"
        with urlopen(base + "/api/creation/jobs?projectId=artifacts%2Fproject") as response:
            assert len(json.load(response)["jobs"]) == 1
        changed = request()
        changed["fps"] = 25
        try:
            with post(changed):
                raise AssertionError("Expected conflict")
        except HTTPError as error:
            try:
                assert error.code == 409
            finally:
                error.close()
        with urlopen(base + "/api/creation/jobs/" + result["jobId"]) as response:
            assert json.load(response)["status"] == "completed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_subtitle_http_get_head_and_fixed_path(service):  # noqa: F811
    import pytest

    parent = service.submit("plan", request())["jobId"]
    finish(service, parent)
    job_id = service.submit(
        "render",
        {
            "requestId": "b" * 32,
            "planJobId": parent,
            "planId": "chronological",
            "width": 64,
            "height": 48,
            "subtitleMode": "sidecar",
        },
    )["jobId"]
    assert finish(service, job_id)["status"] == "completed"
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    path = f"/api/creation/jobs/{job_id}/subtitles"
    try:
        for method in ("GET", "HEAD"):
            with urlopen(Request(base + path, method=method)) as response:
                assert response.status == 200
                assert response.headers["Content-Type"] == "application/x-subrip; charset=utf-8"
                assert (
                    response.headers["Content-Disposition"]
                    == 'attachment; filename="subtitles.srt"'
                )
                assert response.read() == b""
        for suffix in ("?path=outside.srt", "/../request.json"):
            with pytest.raises(HTTPError) as error:
                urlopen(base + path + suffix)
            try:
                assert error.value.code in (400, 404)
            finally:
                error.value.close()
        (service.directory(job_id) / "result/subtitles.srt").write_bytes(b"changed")
        with pytest.raises(HTTPError) as error:
            urlopen(base + path)
        try:
            assert error.value.code == 409
        finally:
            error.value.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_work_name_labels_a_job_in_the_list(service):  # noqa: F811
    """J1 2026-11-11: a work gets a name at export; the list shows it; empty clears it."""
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path, payload):
        return urlopen(
            Request(
                base + path,
                json.dumps(payload).encode(),
                {"Content-Type": "application/json", "Origin": base},
            ),
            timeout=10,
        )

    def listed():
        with urlopen(base + "/api/creation/jobs?projectId=artifacts%2Fproject") as response:
            return json.load(response)["jobs"][0]

    try:
        with post("/api/creation/plans", request()) as response:
            job_id = json.load(response)["jobId"]
        finish(server.creation_jobs, job_id)
        assert "name" not in listed()
        with post("/api/creation/job-name", {"jobId": job_id, "name": " 漫画群星\x07新手向 "}) as r:
            assert json.load(r) == {"jobId": job_id, "name": "漫画群星新手向"}
        assert listed()["name"] == "漫画群星新手向"
        for bad in (
            {"jobId": job_id},
            {"jobId": job_id, "name": "x" * 61},
            {"jobId": "../x", "name": "a"},
        ):
            try:
                with post("/api/creation/job-name", bad):
                    raise AssertionError("Expected refusal")
            except HTTPError as error:
                assert error.code == 400
                error.close()
        with post("/api/creation/job-name", {"jobId": job_id, "name": ""}):
            pass
        assert "name" not in listed()
        # The label lives beside the job, never inside its verified result.
        assert server.creation_jobs.get(job_id)["status"] == "completed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
