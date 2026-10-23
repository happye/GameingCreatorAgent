"""Persistent step ownership, immutable outputs and existing acceptance boundaries."""

import hashlib
import json
import threading
import time
from urllib.parse import urlencode

import pytest
from test_benchmark_reference_browser import (
    reference_page,  # noqa: F401 - shared real media fixture
)
from test_inspection_http import get, workspace

from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.benchmark_workflow import BenchmarkWorkflows


def completed(manager, identifier):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = manager.get(identifier)
        if not value["busy"]:
            return value
        time.sleep(0.02)
    raise AssertionError("Acceptance step did not finish")


def submit(manager, identifier, action, fields):
    manager.submit({"workflow": identifier, "action": action, "fields": fields})
    return completed(manager, identifier)


def test_registration_saves_exact_inputs_reload_and_no_overwrite(tmp_path):
    manager = BenchmarkWorkflows(tmp_path)
    value = manager.create({"name": "素材 <script>保留文字</script>"})
    identifier = value["id"]
    value = submit(manager, identifier, "register", {"inputText": ""})
    row = value["attempts"][-1]
    assert row["status"] == "finished" and row["exitCode"] == 0
    assert set(row["files"]) == {"edit.html", "draft.json", "receipt.json"}
    assert json.loads(manager.file(identifier, row["attemptId"], "draft.json"))["sources"] == []
    before = {name: manager.file(identifier, row["attemptId"], name) for name in row["files"]}
    second = BenchmarkWorkflows(tmp_path)
    assert second.get(identifier) == value
    assert second.catalog()["workflows"][0]["id"] == identifier
    assert "attempts" not in second.catalog()["workflows"][0]
    value = submit(second, identifier, "register", {"inputText": before["draft.json"].decode()})
    assert len(value["attempts"]) == 2 and value["attempts"][1]["attemptId"] != row["attemptId"]
    assert {
        name: second.file(identifier, row["attemptId"], name) for name in row["files"]
    } == before
    assert value["qualityGate"] is None and value["paidRequestsSent"] == 0
    manager.close()
    second.close()


@pytest.mark.parametrize(
    "change",
    [
        {"action": "analyze"},
        {"action": "freeze"},
        {"fields": {"inputText": "", "extra": ""}},
        {"fields": {"inputText": '{"schemaVersion":1,"schemaVersion":2}'}},
        {"workflow": "../outside"},
        {"fields": {"inputText": '{"value":NaN}'}},
        {"fields": {"inputText": 1}},
    ],
)
def test_bad_steps_rejected_before_any_attempt(tmp_path, change):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "invalid-input"})["id"]
    document = {"workflow": identifier, "action": "register", "fields": {"inputText": ""}}
    document.update(change)
    with pytest.raises((AppError, ValueError)):
        manager.submit(document)
    assert manager.get(identifier)["attempts"] == []


def test_actual_os_lock_blocks_duplicate_and_released_ownership_is_interrupted(
    tmp_path, monkeypatch
):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "ownership"})["id"]
    entered, release = threading.Event(), threading.Event()
    original = manager._execute

    def delayed(*arguments):
        entered.set()
        assert release.wait(10)
        return original(*arguments)

    monkeypatch.setattr(manager, "_execute", delayed)
    document = {"workflow": identifier, "action": "register", "fields": {"inputText": ""}}
    manager.submit(document)
    assert entered.wait(5)
    second = BenchmarkWorkflows(tmp_path)
    value = second.get(identifier)
    assert value["busy"] is True and value["attempts"][-1]["status"] == "running"
    with pytest.raises(AppError, match="已有写入"):
        second.submit(document)
    release.set()
    value = completed(manager, identifier)
    row = value["attempts"][-1]
    path = manager.directory(identifier) / row["attemptId"] / "status.json"
    row["status"] = "running"
    path.write_bytes(canonical_json(row))
    value = second.get(identifier)
    assert value["busy"] is False and value["attempts"][-1]["status"] == "interrupted"
    assert json.loads(path.read_bytes())["status"] == "running"  # read does not rewrite history
    value = submit(second, identifier, "register", {"inputText": ""})
    assert len(value["attempts"]) == 2
    manager.close()


def persist_running_attempt(manager, identifier, attempt="000001-" + "a" * 32):
    """Persist one running attempt exactly like submit does before its worker finishes."""
    parent = manager.directory(identifier) / attempt
    parent.mkdir()
    request = canonical_json(
        {"action": "register", "fields": {"inputText": ""}, "dependencies": {}}
    )
    (parent / "request.json").write_bytes(request)
    row = {
        "attemptId": attempt,
        "action": "register",
        "startedAt": "2026-10-23T00:00:00+00:00",
        "status": "running",
        "exitCode": None,
        "files": {},
        "error": None,
        "project": None,
        "qualityGate": None,
        "elapsedMs": None,
        "dependencies": {},
    }
    status = parent / "status.json"
    status.write_bytes(canonical_json(row))
    return parent, status, row, request


@pytest.mark.parametrize(
    ("terminal", "exit_code", "error"),
    [
        ("finished", 0, None),
        ("failed", 2, "资料读取或保存失败；保留已有文件，检查后明确重试。"),
    ],
)
def test_terminal_status_between_running_read_and_lock_observation_is_returned(
    tmp_path, monkeypatch, terminal, exit_code, error
):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "terminal-interleave"})["id"]
    parent, status, row, request = persist_running_attempt(manager, identifier)
    ownership = ProjectWriterLock(manager.directory(identifier))
    ownership.acquire()  # a worker that has not persisted its terminal status yet
    real_acquire = ProjectWriterLock.acquire
    persisted = []

    def acquire_after_terminal(self_lock):
        if not persisted:
            terminal_row = {
                **row,
                "status": terminal,
                "exitCode": exit_code,
                "error": error,
                "elapsedMs": 1.5,
            }
            if terminal == "finished":
                output = parent / "output"
                output.mkdir()
                (output / "draft.json").write_bytes(b"registered")
                terminal_row["files"] = {"draft.json": hashlib.sha256(b"registered").hexdigest()}
            status.write_bytes(canonical_json(terminal_row))
            persisted.append(terminal_row)
            ownership.close()
        return real_acquire(self_lock)

    monkeypatch.setattr(ProjectWriterLock, "acquire", acquire_after_terminal)
    value = manager.get(identifier)

    assert persisted, "get did not read the old running snapshot before the lock observation"
    assert value["busy"] is False and value["qualityGate"] is None
    current = value["attempts"][-1]
    assert current["status"] == terminal and current["exitCode"] == exit_code
    assert current["error"] == error
    assert current["files"] == persisted[0]["files"]
    # The query only projects; it never rewrites the persisted status/input/output history.
    assert status.read_bytes() == canonical_json(persisted[0])
    assert (parent / "request.json").read_bytes() == request
    if terminal == "finished":
        assert manager.file(identifier, row["attemptId"], "draft.json") == b"registered"
    else:
        with pytest.raises(AppError):
            manager.file(identifier, row["attemptId"], "draft.json")
    monkeypatch.setattr(ProjectWriterLock, "acquire", real_acquire)
    probe = ProjectWriterLock(manager.directory(identifier))
    probe.acquire()  # a leaked observation lock would make this raise storage.writer_busy
    probe.close()
    assert manager.get(identifier)["attempts"][-1]["status"] == terminal


def test_fresh_snapshot_error_closes_the_observation_lock(tmp_path, monkeypatch):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "read-error"})["id"]
    persist_running_attempt(manager, identifier)
    original = manager._attempts
    calls = []

    def flaky(workflow):
        calls.append(workflow)
        if len(calls) == 2:
            raise AppError("input.benchmark_workflow", "验收资料已改变。", ExitCode.INPUT)
        return original(workflow)

    monkeypatch.setattr(manager, "_attempts", flaky)
    with pytest.raises(AppError) as caught:
        manager.get(identifier)
    assert caught.value.code == "input.benchmark_workflow" and len(calls) == 2
    monkeypatch.undo()
    probe = ProjectWriterLock(manager.directory(identifier))
    probe.acquire()  # the failed fresh read must already have released the lock it held
    probe.close()
    value = manager.get(identifier)
    assert value["busy"] is False and value["attempts"][-1]["status"] == "interrupted"


def test_writer_lock_error_is_not_reported_as_busy_or_interrupted(tmp_path, monkeypatch):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "lock-error"})["id"]
    persist_running_attempt(manager, identifier)

    def broken(self_lock):
        raise AppError("storage.writer_lock", "无法获取项目写入锁。", ExitCode.STORAGE)

    monkeypatch.setattr(ProjectWriterLock, "acquire", broken)
    with pytest.raises(AppError) as caught:
        manager.get(identifier)
    assert caught.value.code == "storage.writer_lock"


def test_failed_attempt_retains_input_and_explicit_retry_uses_new_directory(tmp_path):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "failure"})["id"]
    value = submit(manager, identifier, "register", {"inputText": '{"invalid":true}'})
    row = value["attempts"][0]
    assert row["status"] == "failed" and row["files"] == {}
    parent = manager.directory(identifier) / row["attemptId"]
    assert (parent / "input.json").read_text() == '{"invalid":true}'
    assert value["qualityGate"] is None
    value = submit(manager, identifier, "register", {"inputText": ""})
    assert value["attempts"][-1]["status"] == "finished"
    assert (parent / "input.json").read_text() == '{"invalid":true}'


def test_downstream_locks_earlier_steps_and_tampered_outputs_block_reuse(tmp_path, monkeypatch):
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "immutable"})["id"]
    value = submit(manager, identifier, "register", {"inputText": ""})
    row = value["attempts"][0]
    original = manager._execute

    def fake_step(identifier, current, fields, rows):
        if current["action"] == "references":
            publish_review_bundle(manager._output(identifier, current), {"context.json": b"{}"}, [])
            return 0, None
        return original(identifier, current, fields, rows)

    monkeypatch.setattr(manager, "_execute", fake_step)
    # A complete, absolute-path plan is still required before executing the reference step.
    from test_benchmark_plan_draft import complete_draft

    from gamingcreator.application.benchmark_plan_draft import draft_to_plan

    plan = draft_to_plan(complete_draft()).document
    submit(manager, identifier, "references", {"inputText": json.dumps(plan)})
    with pytest.raises(AppError, match="后续资料"):
        manager.submit({"workflow": identifier, "action": "register", "fields": {"inputText": ""}})
    (manager._output(identifier, row) / "draft.json").write_bytes(b"{}")
    with pytest.raises(AppError, match="已改变"):
        manager.file(identifier, row["attemptId"], "draft.json")
    with pytest.raises(AppError):
        manager.submit(
            {"workflow": identifier, "action": "references-import", "fields": {"inputText": "{}"}}
        )
    with pytest.raises(AppError):
        manager.file(identifier, row["attemptId"], "../request.json")


def test_http_registered_source_range_csp_and_reference_import(tmp_path, request):
    _, context, template, assets = request.getfixturevalue("reference_page")
    with workspace(tmp_path) as base:

        def post(path, value):
            code, headers, body = get(
                base,
                path,
                method="POST",
                data=json.dumps(value).encode(),
                headers={"Content-Type": "application/json"},
            )
            return code, json.loads(body)

        code, value = post("/api/benchmark-workflows", {"name": "原片 HTTP"})
        assert code == 201
        identifier = value["id"]
        code, value = post(
            "/api/benchmark-step",
            {
                "workflow": identifier,
                "action": "references",
                "fields": {"inputText": json.dumps(context["plan"])},
            },
        )
        assert code == 202
        deadline = time.monotonic() + 20
        while value["busy"] and time.monotonic() < deadline:
            time.sleep(0.03)
            _, _, body = get(base, "/api/benchmark-workflow?" + urlencode({"workflow": identifier}))
            value = json.loads(body)
        row = value["attempts"][-1]
        assert row["status"] == "finished", row
        prefix = {"workflow": identifier, "attempt": row["attemptId"]}
        path = "/api/benchmark-file?" + urlencode({**prefix, "file": "review.html"})
        code, headers, body = get(base, path)
        assert code == 200 and "script-src 'sha256-" in headers["Content-Security-Policy"]
        assert b"/api/benchmark-source?" in body or b"const source=" in body
        assert "media-src 'self'" in headers["Content-Security-Policy"]
        path = "/api/benchmark-source?" + urlencode({**prefix, "source": "source-0"})
        code, headers, body = get(base, path, headers={"Range": "bytes=0-15"})
        assert code == 206 and body == assets["source-0"].source_path.read_bytes()[:16]
        assert headers["Content-Range"].startswith("bytes 0-15/")
        assert get(base, path, method="HEAD")[2] == b""
        assert get(base, path + "&path=G:/secret.json")[0] == 400
        # Use this newly prepared step's own context, never an old context hash.
        _, _, data = get(
            base, "/api/benchmark-file?" + urlencode({**prefix, "file": "record-template.json"})
        )
        record = json.loads(data)
        code, value = post(
            "/api/benchmark-step",
            {
                "workflow": identifier,
                "action": "references-import",
                "fields": {"inputText": json.dumps(record)},
            },
        )
        assert code == 202
        deadline = time.monotonic() + 20
        while value["busy"] and time.monotonic() < deadline:
            time.sleep(0.03)
            _, _, data = get(base, "/api/benchmark-workflow?" + urlencode({"workflow": identifier}))
            value = json.loads(data)
        row = value["attempts"][-1]
        assert row["status"] == "finished", row
        _, _, data = get(
            base,
            "/api/benchmark-file?"
            + urlencode(
                {"workflow": identifier, "attempt": row["attemptId"], "file": "benchmark-plan.json"}
            ),
        )
        plan = json.loads(data)
        assert plan["humanReferences"]["confirmed"] is False
        assert plan["queries"][0]["referenceEvents"] == []
        asset = assets["source-0"]
        asset.source_path.write_bytes(b"changed")
        assert get(base, path)[0] == 409


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/benchmark-workflows", None),
        ("POST", "/api/benchmark-workflows", b'{"name":"cross-site"}'),
        ("GET", "/api/benchmark-file?workflow=../outside&attempt=x&file=secret.json", None),
    ],
)
def test_http_cross_origin_and_path_boundaries(tmp_path, method, path, body):
    with workspace(tmp_path) as base:
        headers = {"Origin": "https://outside.invalid", "Content-Type": "application/json"}
        assert get(base, path, method=method, data=body, headers=headers)[0] == 403
        if method == "GET" and "benchmark-file" in path:
            assert get(base, path)[0] == 400
