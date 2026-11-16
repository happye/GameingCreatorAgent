"""E14：逐词识别入口接已有本机任务机制，显式开始、状态、取消和失败可见。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_asr_audio import DURATION_US
from test_asr_models import MODEL
from test_asr_words_cli import FakeWords, _seed
from test_asr_words_http import _query
from test_inspection_http import get, workspace

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words import transcribe_project_words


def post(base, path, value, **headers):
    return get(
        base,
        path,
        data=json.dumps(value, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )


def _status_path(project_id: str, task_id: str) -> str:
    return "/api/asr-words?" + urlencode({"projectId": project_id, "taskId": task_id})


def _wait(base, project_id: str, task_id: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    payload = {}
    while time.monotonic() < deadline:
        status, _, body = get(base, _status_path(project_id, task_id))
        payload = json.loads(body.decode("utf-8"))
        assert status == 200
        if payload["status"] in {"finished", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"任务未在时限内结束: {payload}")


def _install_fake(monkeypatch, provider=None):
    real = transcribe_project_words
    chosen = provider or FakeWords()

    async def wrapped(
        project, run_id, model, repository, *, provider=None, context=None, timeout_seconds=600
    ):
        return await real(
            project,
            run_id,
            model,
            repository,
            provider=chosen,
            context=context,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr("gamingcreator.ui.asr_words_jobs.transcribe_project_words", wrapped)
    return chosen


def test_http_start_status_and_result_are_server_generated(tmp_path, monkeypatch):
    repository, project, bundle = _seed(tmp_path)
    _install_fake(monkeypatch)
    with workspace(repository) as base:
        status, _, body = post(
            base,
            "/api/asr-words",
            {"projectId": "project", "runId": "run-1", "model": MODEL},
        )
        payload = json.loads(body.decode("utf-8"))
        assert status == 202
        assert payload["schemaVersion"] == "asr-words-job-v1"
        assert payload["status"] in {"queued", "running", "finished"}
        assert payload["projectId"] == "project"
        assert payload["runId"] == "run-1"
        assert payload["model"] == MODEL
        task_id = payload["taskId"]
        assert len(task_id) == 32 and set(task_id) <= set("0123456789abcdef")
        finished = _wait(base, "project", task_id)
        assert finished["status"] == "finished"
        assert finished["error"] is None
        assert finished["taskId"] == task_id
        result = finished["result"]
        assert result["wordCount"] == 1
        assert result["resultHash"]
        assert result["resultPath"]
        read_status, _, read_body = get(base, _query("project", "run-1", result["resultHash"]))
        document = json.loads(read_body.decode("utf-8"))
        assert read_status == 200
        assert document["words"][0]["text"] == "你好"
        billing = repository / "artifacts" / "billing"
        entitlement = repository / ".cache" / "workspace" / "creations" / "entitlement.json"
        assert not billing.exists()
        assert not entitlement.exists()


def test_http_rejects_extra_start_fields_and_missing_task(tmp_path, monkeypatch):
    repository, _, _ = _seed(tmp_path)
    _install_fake(monkeypatch)
    with workspace(repository) as base:
        extra_status, _, extra_body = post(
            base,
            "/api/asr-words",
            {
                "projectId": "project",
                "runId": "run-1",
                "model": MODEL,
                "output": "out",
            },
        )
        audio_status, _, audio_body = post(
            base,
            "/api/asr-words",
            {
                "projectId": "project",
                "runId": "run-1",
                "model": MODEL,
                "audioUrl": "http://example/audio.wav",
            },
        )
        missing_status, _, missing_body = get(base, _status_path("project", "a" * 32))
        cancel_status, _, cancel_body = post(
            base,
            "/api/asr-words-cancel",
            {"projectId": "project", "taskId": "a" * 32},
        )
    assert extra_status == 400
    assert json.loads(extra_body.decode("utf-8"))["code"] == "asr.task_input"
    assert json.loads(extra_body.decode("utf-8"))["message"] == "请填写项目、任务和本机识别模型。"
    assert audio_status == 400
    assert json.loads(audio_body.decode("utf-8"))["code"] == "asr.task_input"
    assert missing_status == 404
    assert json.loads(missing_body.decode("utf-8"))["code"] == "asr.task_not_found"
    assert json.loads(missing_body.decode("utf-8"))["message"] == "找不到这个逐词识别任务。"
    assert cancel_status == 404
    assert json.loads(cancel_body.decode("utf-8"))["code"] == "asr.task_not_found"


def test_http_failure_is_visible_on_status(tmp_path, monkeypatch):
    repository, _, _ = _seed(tmp_path)
    _install_fake(monkeypatch)
    with workspace(repository) as base:
        status, _, body = post(
            base,
            "/api/asr-words",
            {"projectId": "project", "runId": "run-missing", "model": MODEL},
        )
        payload = json.loads(body.decode("utf-8"))
        assert status == 202
        finished = _wait(base, "project", payload["taskId"])
    assert finished["status"] == "failed"
    assert finished["result"] is None
    assert finished["error"]["code"] == "asr.run_missing"
    assert finished["error"]["message"] == "找不到这个任务的已准备音频。"


def test_http_cancel_stops_this_task_and_keeps_the_other(tmp_path, monkeypatch):
    repository, project, bundle = _seed(tmp_path)
    started = []

    class SlowWords(FakeWords):
        async def transcribe_words(self, request, context):
            started.append(request.run_id if hasattr(request, "run_id") else "run")
            for _ in range(400):
                context.check_cancelled()
                await asyncio.sleep(0.05)
            return await super().transcribe_words(request, context)

    slow = SlowWords()
    real = transcribe_project_words

    async def wrapped(
        project_path, run_id, model, repo, *, provider=None, context=None, timeout_seconds=600
    ):
        chosen = (
            slow if run_id == "run-1" and not getattr(wrapped, "second", False) else FakeWords()
        )
        return await real(
            project_path,
            run_id,
            model,
            repo,
            provider=chosen,
            context=context,
            timeout_seconds=timeout_seconds,
        )

    # Two jobs on the same run: first uses SlowWords, second should still be able to finish
    # after we mark the first as the slow one by task start order.
    providers = {"count": 0}

    async def dispatch(
        project_path, run_id, model, repo, *, provider=None, context=None, timeout_seconds=600
    ):
        providers["count"] += 1
        chosen = (
            slow
            if providers["count"] == 1
            else FakeWords(
                (
                    AsrWord(
                        bundle.asset.media_id, SourceRange(200_000, 500_000, DURATION_US), "第二份"
                    ),
                )
            )
        )
        return await real(
            project_path,
            run_id,
            model,
            repo,
            provider=chosen,
            context=context,
            timeout_seconds=timeout_seconds,
        )

    monkeypatch.setattr("gamingcreator.ui.asr_words_jobs.transcribe_project_words", dispatch)
    with workspace(repository) as base:
        first_status, _, first_body = post(
            base,
            "/api/asr-words",
            {"projectId": "project", "runId": "run-1", "model": MODEL},
        )
        first = json.loads(first_body.decode("utf-8"))
        assert first_status == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not started:
            time.sleep(0.05)
        assert started, "第一个任务没有进入识别"
        second_status, _, second_body = post(
            base,
            "/api/asr-words",
            {"projectId": "project", "runId": "run-1", "model": MODEL},
        )
        second = json.loads(second_body.decode("utf-8"))
        assert second_status == 202
        assert second["taskId"] != first["taskId"]
        cancel_status, _, cancel_body = post(
            base,
            "/api/asr-words-cancel",
            {"projectId": "project", "taskId": first["taskId"]},
        )
        cancelled = json.loads(cancel_body.decode("utf-8"))
        assert cancel_status == 200
        assert cancelled["cancellationRequested"] is True
        first_done = _wait(base, "project", first["taskId"])
        second_done = _wait(base, "project", second["taskId"])
    assert first_done["status"] == "cancelled"
    assert first_done["error"]["code"] == "asr.cancelled"
    assert first_done["error"]["message"] == "逐词识别已取消。"
    assert first_done["result"] is None
    assert second_done["status"] == "finished"
    assert second_done["result"]["wordCount"] == 1
    assert "第二份" in Path(second_done["result"]["resultPath"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("failure", ["permission", "disk_full", "unexpected"])
def test_job_write_and_unexpected_errors_are_terminal(tmp_path, monkeypatch, failure):
    repository, _, _ = _seed(tmp_path)
    _install_fake(monkeypatch)
    if failure == "unexpected":

        async def broken(*args, **kwargs):
            raise RuntimeError("worker crashed")

        monkeypatch.setattr("gamingcreator.ui.asr_words_jobs.transcribe_project_words", broken)
    else:
        original_open = Path.open

        def failing_open(path, *args, **kwargs):
            if path.name == "words.json" and args and args[0] == "xb":
                if failure == "permission":
                    raise PermissionError(13, "denied")
                raise OSError(28, "disk full")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", failing_open)
    with workspace(repository) as base:
        status, _, body = post(
            base,
            "/api/asr-words",
            {
                "projectId": "project",
                "runId": "run-1",
                "model": MODEL,
            },
        )
        assert status == 202
        finished = _wait(base, "project", json.loads(body)["taskId"])
    assert finished["status"] == "failed"
    assert finished["result"] is None
    assert finished["error"]["code"] == (
        "asr.task_failed" if failure == "unexpected" else "asr.words_write"
    )
    assert finished["error"]["message"]
