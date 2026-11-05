import json
import threading
from http.client import HTTPConnection

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_proposals import output
from test_creation_reasoning_service import Transport
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.application.creation_proposals import create_snapshot
from gamingcreator.ui import server as module
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.revision_jobs import load_chain


@pytest.fixture
def http(revisions, monkeypatch):  # noqa: F811
    jobs, job, _ = revisions
    chain = load_chain(jobs, job, "hook-first")
    snapshot = create_snapshot(job, chain.plan_id, chain.digest, chain.root_sha, chain.edl)
    transport = Transport(output(snapshot))

    def factory(created_jobs, **kwargs):
        return CreationReasoningService(created_jobs, transport=transport, **kwargs)

    monkeypatch.setattr(module, "CreationReasoningService", factory)
    server = module.create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(value=None, path="/api/creation/reasoning", origin=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        body = None if value is None else json.dumps(value)
        connection.request("GET" if value is None else "POST", path, body, headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    yield request, transport, job, chain.digest
    server.shutdown()
    server.server_close()
    thread.join()


def prepare(http):
    request, _, job, _ = http
    status, prepared = request(
        {"action": "prepare", "jobId": job, "planId": "hook-first", "instruction": "调整节奏"}
    )
    assert status == 200, prepared
    return prepared


def test_reasoning_http_confirm_execute_validate_and_replay(http):
    request, transport, job, digest = http
    prepared = prepare(http)
    assert not transport.calls
    assert set(prepared["payloadPreview"]) == {"system", "user"}
    assert "sourcePath" not in json.dumps(prepared)
    execute = {
        "action": "execute",
        "preparedHash": prepared["preparedHash"],
        "snapshotFingerprint": prepared["snapshotFingerprint"],
        "confirmedMaxCny": prepared["maxCostCny"],
    }
    status, result = request(execute)
    assert status == 200 and result["status"] == "completed", result
    assert request(execute) == (status, result)
    assert request({"action": "result", "preparedHash": prepared["preparedHash"]}) == (200, result)
    assert len(transport.calls) == 1
    validate = {
        "action": "validate",
        "preparedHash": prepared["preparedHash"],
        "jobId": job,
        "planId": "hook-first",
        "expectedParentReceiptSha256": digest,
    }
    status, rows = request(validate)
    assert status == 200, rows
    assert set(rows) == {"clips", "preparedHash", "jobId", "planId", "expectedParentReceiptSha256"}
    assert "sourcePath" not in json.dumps(rows)
    assert set(rows["clips"][0]) == {"clipId", "startUs", "endUs", "speed", "transitionIn"}
    for key in ("jobId", "planId", "expectedParentReceiptSha256"):
        status, error = request({**validate, key: "wrong"})
        assert status == 400 and error["code"] == "input.request"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("amount", [None, 1, "NaN", "Infinity", "bogus", "0"])
def test_reasoning_http_requires_string_finite_confirmation(http, amount):
    request, transport, _, _ = http
    prepared = prepare(http)
    value = {
        "action": "execute",
        "preparedHash": prepared["preparedHash"],
        "snapshotFingerprint": prepared["snapshotFingerprint"],
    }
    if amount is not None:
        value["confirmedMaxCny"] = amount
    assert request(value)[0] == 400
    assert not transport.calls


def test_reasoning_http_config_origin_and_exact_fields(http, monkeypatch):
    request, transport, job, _ = http
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = "/api/creation/reasoning/config"
    status, config = request(path=path)
    assert status == 200 and config["available"] is False
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-test")
    assert request(path=path)[1]["available"] is True
    assert "secret-test" not in json.dumps(request(path=path))
    assert request(path=path + "?unexpected=1")[0] == 400
    value = {"action": "prepare", "jobId": job, "planId": "hook-first", "instruction": "调整"}
    assert request(value, origin="https://evil.invalid")[0] == 403
    assert request({**value, "clips": []})[0] == 400
    assert request({"action": "result", "preparedHash": "a" * 64, "extra": "x"})[0] == 400
    assert request({**value, "action": "unknown"})[0] == 400
    assert not transport.calls
