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


def test_http_waveform_is_exact_cached_and_reports_silence(service, monkeypatch):  # noqa: F811
    """Stage C waveform lane: registered run only, exact query, one FFmpeg pass per range."""
    from pathlib import Path

    import gamingcreator.ui.server as server_module
    from gamingcreator.ui.media import MediaResource

    calls = []

    async def media(project, run_id, evidence_id=None):
        return MediaResource(
            Path("source.mp4"), ("s" if run_id == "run" else "q") * 64, "video/mp4"
        )

    def peaks(repository, source, start, end, buckets):
        calls.append((start, end, buckets))
        return None if start == 7 else [0.5] * buckets

    monkeypatch.setattr(server_module, "registered_media", media)
    monkeypatch.setattr(server_module, "audio_peaks", peaks)
    server_module.InspectionHandler.waveform_cache.clear()
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/api/waveform?project=artifacts%2Fproject"
    try:
        url = base + "&run=run&startUs=0&endUs=1000000&buckets=4"
        for _ in range(2):
            with urlopen(url) as response:
                assert json.load(response) == {"audio": True, "peaks": [0.5] * 4}
        assert calls == [(0, 1_000_000, 4)]
        with urlopen(base + "&run=run&startUs=7&endUs=9&buckets=2") as response:
            assert json.load(response) == {"audio": False, "peaks": []}
        try:
            with urlopen(base + "&run=run&startUs=0&endUs=1"):
                raise AssertionError("Expected refusal")
        except HTTPError as error:
            assert error.code == 400
            error.close()
    finally:
        server_module.InspectionHandler.waveform_cache.clear()
        server.shutdown()
        server.server_close()
        thread.join()
