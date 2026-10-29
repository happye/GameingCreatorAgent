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
            post(changed)
            raise AssertionError("Expected conflict")
        except HTTPError as error:
            assert error.code == 409
        with urlopen(base + "/api/creation/jobs/" + result["jobId"]) as response:
            assert json.load(response)["status"] == "completed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
