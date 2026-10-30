import hashlib
import json
import threading
import time

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.creation_jobs import CreationJobs


@pytest.fixture
def service(tmp_path, monkeypatch):
    import gamingcreator.ui.creation_jobs as implementation
    from gamingcreator.infrastructure.creation_files import write_creation

    (tmp_path / "artifacts/project").mkdir(parents=True)
    (tmp_path / "artifacts/project/timeline.sqlite3").touch()

    async def planner(project, runs, brief, output, events, fps, selection):
        report = {
            "schemaVersion": "creation-plan-v1",
            "fps": fps,
            "brief": json.loads(brief.read_text()),
            "plans": [
                {
                    "id": "chronological",
                    "structure": "chronological",
                    "ready": True,
                    "gaps": [],
                    "scriptStatus": "draft",
                    "segments": [{"sourcePath": "private", "startUs": 0, "runId": "run"}],
                }
            ],
        }
        report["plans"].append({**report["plans"][0], "id": "reverse"})
        write_creation(output, {"plans.json": report}, ())

    monkeypatch.setattr(implementation, "execute_plan_creation", planner)

    async def renderer(project, selection, output, tool, width, height, subtitle_mode="none"):
        output.mkdir()
        (output / "video.mp4").write_bytes(b"fixture-video")
        from gamingcreator.infrastructure.ffmpeg_media import hash_file

        receipt = {
            "schemaVersion": "creation-render-receipt-v1",
            "status": "completed",
            "width": width,
            "height": height,
            "creationReceiptSha256": hash_file(selection / "receipt.json"),
            "files": {"video.mp4": hash_file(output / "video.mp4")},
        }
        if subtitle_mode != "none":
            (output / "subtitles.srt").write_bytes(b"")
            receipt["files"]["subtitles.srt"] = hash_file(output / "subtitles.srt")
            receipt["subtitles"] = {"mode": subtitle_mode, "cueCount": 0}
        (output / "receipt.json").write_text(json.dumps(receipt))

    monkeypatch.setattr(implementation, "execute_render_creation", renderer)
    from types import SimpleNamespace

    from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

    async def load_run(run_id):
        return SimpleNamespace(asset=SimpleNamespace(source_path=tmp_path / "footage/source.mp4"))

    async def close():
        pass

    async def open_store(*args, **kwargs):
        return SimpleNamespace(load_run=load_run, close=close)

    monkeypatch.setattr(SqliteTimelineStore, "open", open_store)
    return CreationJobs(tmp_path)


def request():
    return {
        "requestId": "a" * 32,
        "projectId": "artifacts/project",
        "runIds": ["run"],
        "fps": 30,
        "brief": {
            "game": "g",
            "contentType": "guide",
            "platforms": ["bilibili"],
            "targetDuration": 3,
            "objective": "o",
            "audience": "a",
            "tone": "t",
            "mandatoryTopics": [],
            "exclude": [],
        },
    }


def finish(service, job_id):
    for _ in range(200):
        job = service.get(job_id)
        if job["status"] not in {"pending", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Job did not finish")


def test_idempotency_concurrent_and_restart_no_reexecution(service):
    results = []
    workers = [
        threading.Thread(target=lambda: results.append(service.submit("plan", request())))
        for _ in range(5)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert len(results) == 5
    assert len({result["jobId"] for result in results}) == 1
    job_id = results[0]["jobId"]
    job = finish(service, job_id)
    assert job["status"] == "completed"
    assert "sourcePath" not in job["plans"][0]["segments"][0]
    restarted = CreationJobs(service.repository)
    assert restarted.get(job_id)["status"] == "completed"
    assert not restarted.threads
    changed = request()
    changed["fps"] = 25
    with pytest.raises(AppError) as error:
        restarted.submit("plan", changed)
    assert error.value.code == "creation.conflict"


def test_active_lock_and_orphan_recovery(service):
    job_id = service.submit("plan", request())["jobId"]
    finish(service, job_id)
    directory = service.directory(job_id)
    state = service.read(directory / "status.json")
    state["status"] = "running"
    state.pop("resultReceiptSha256")
    service.save(directory / "status.json", state)
    owner = ProjectWriterLock(directory)
    owner.acquire()
    try:
        assert CreationJobs(service.repository).get(job_id)["status"] == "running"
    finally:
        owner.close()
    assert (
        service.get(job_id)["status"] == "completed"
    )  # valid result survives interrupted status write
    (directory / "result/receipt.json").unlink()
    service.save(directory / "status.json", state)
    assert service.get(job_id)["status"] == "interrupted"


def test_tampered_parent_and_failed_download(service):
    job_id = service.submit("plan", request())["jobId"]
    finish(service, job_id)
    (service.directory(job_id) / "result/plans.json").write_text("{}")
    assert service.get(job_id)["error"]["code"] == "creation.artifact_invalid"
    with pytest.raises(AppError):
        service.video(job_id)
    with pytest.raises(AppError):
        service.submit(
            "render",
            {
                "requestId": "b" * 32,
                "planJobId": job_id,
                "planId": "chronological",
                "width": 64,
                "height": 48,
            },
        )


def test_strict_input_and_paths(service):
    bad = request()
    bad["sourcePath"] = "outside"
    with pytest.raises(AppError):
        service.submit("plan", bad)
    with pytest.raises(AppError):
        service.get("../escape")
    bad = request()
    bad["projectId"] = "../outside"
    with pytest.raises(AppError):
        service.submit("plan", bad)


def test_lock_owned_by_second_process_is_not_interrupted(service):
    import subprocess
    import sys

    job_id = service.submit("plan", request())["jobId"]
    finish(service, job_id)
    directory = service.directory(job_id)
    state = service.read(directory / "status.json")
    state["status"] = "running"
    service.save(directory / "status.json", state)
    code = "from pathlib import Path; from gamingcreator.infrastructure.writer_lock import ProjectWriterLock; import sys; lock=ProjectWriterLock(Path(sys.argv[1])); lock.acquire(); print('locked',flush=True); sys.stdin.readline(); lock.close()"
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", code, str(directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"
        assert service.get(job_id)["status"] == "running"
    finally:
        process.communicate("\n", timeout=10)
    assert service.get(job_id)["status"] == "completed"


def test_completed_plan_rehashed_tamper_is_not_a_new_baseline(service):
    job_id = service.submit("plan", request())["jobId"]
    finish(service, job_id)
    directory = service.directory(job_id)
    assert service.read(directory / "status.json")["resultReceiptSha256"]
    report_path = directory / "result/plans.json"
    report = json.loads(report_path.read_text())
    report["plans"][0]["structure"] = "changed"
    report_path.write_text(json.dumps(report))
    receipt_path = directory / "result/receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["files"]["plans.json"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    assert service.get(job_id)["error"]["code"] == "creation.artifact_invalid"
    with pytest.raises(AppError):
        service.submit(
            "render",
            {
                "requestId": "c" * 32,
                "planJobId": job_id,
                "planId": "chronological",
                "width": 64,
                "height": 48,
            },
        )


def test_orphan_plan_rejects_other_requests_result(service):
    import shutil

    a = service.submit("plan", request())["jobId"]
    finish(service, a)
    other = request()
    other.update(requestId="d" * 32, fps=25)
    b = service.submit("plan", other)["jobId"]
    finish(service, b)
    directory = service.directory(b)
    for name in ("plans.json", "receipt.json"):
        shutil.copyfile(service.directory(a) / "result" / name, directory / "result" / name)
    state = service.read(directory / "status.json")
    state["status"] = "running"
    state.pop("resultReceiptSha256")
    service.save(directory / "status.json", state)
    assert service.get(b)["status"] == "interrupted"


def test_orphan_render_rejects_other_selection(service):
    import shutil

    parent = service.submit("plan", request())["jobId"]
    finish(service, parent)

    def render(req_id, plan):
        job = service.submit(
            "render",
            {
                "requestId": req_id * 32,
                "planJobId": parent,
                "planId": plan,
                "width": 64,
                "height": 48,
            },
        )["jobId"]
        assert finish(service, job)["status"] == "completed"
        return job

    a, b = render("e", "chronological"), render("f", "reverse")
    directory = service.directory(b)
    for folder in ("selection", "result"):
        for path in (service.directory(a) / folder).iterdir():
            shutil.copyfile(path, directory / folder / path.name)
    state = service.read(directory / "status.json")
    state["status"] = "running"
    state.pop("resultReceiptSha256")
    service.save(directory / "status.json", state)
    assert service.get(b)["status"] == "interrupted"
    with pytest.raises(AppError):
        service.video(b)


@pytest.mark.parametrize("layer", ["creations", "jobs"])
def test_linked_creation_root_rejected_before_external_write(tmp_path, layer):
    import os
    import subprocess

    outside = tmp_path / "outside"
    outside.mkdir()
    repository = tmp_path / "repo"
    (repository / ".cache/workspace").mkdir(parents=True)
    link = repository / ".cache/workspace/creations"
    if layer == "jobs":
        link.mkdir()
        link = link / "jobs"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(AppError):
            CreationJobs(repository)
        assert list(outside.iterdir()) == []
    finally:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()


def test_state_read_retries_windows_permission_without_native_code(service, monkeypatch):
    import os
    from pathlib import Path

    if os.name != "nt":
        pytest.skip("Windows CRT sharing error")
    target = service.root / "read-check.json"
    target.write_text('{"ok": true}', encoding="utf-8")
    original = Path.read_text
    calls = 0

    def read(path, *args, **kwargs):
        nonlocal calls
        if path == target:
            calls += 1
            if calls == 1:
                raise PermissionError(13, "transient sharing")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    assert service.read(target) == {"ok": True}
    assert calls == 2


@pytest.mark.parametrize("mode", ["none", "sidecar", "burn"])
def test_subtitle_selection_restart_and_idempotency(service, mode):
    parent = service.submit("plan", request())["jobId"]
    finish(service, parent)
    payload = {
        "requestId": "b" * 32,
        "planJobId": parent,
        "planId": "chronological",
        "width": 64,
        "height": 48,
        "subtitleMode": mode,
    }
    job_id = service.submit("render", payload)["jobId"]
    job = finish(service, job_id)
    assert job["status"] == "completed"
    restored = CreationJobs(service.repository)
    assert restored.get(job_id)["status"] == "completed"
    assert not restored.threads
    assert restored.submit("render", payload)["jobId"] == job_id
    with pytest.raises(AppError):
        restored.submit("render", {**payload, "subtitleMode": "burn" if mode != "burn" else "none"})
    if mode == "none":
        assert "subtitleUrl" not in job["artifact"]
        with pytest.raises(AppError):
            restored.subtitles(job_id)
    else:
        assert job["artifact"]["subtitleCueCount"] == 0
        assert job["artifact"]["subtitleMode"] == mode
        assert restored.subtitles(job_id).path.read_bytes() == b""
        (restored.directory(job_id) / "result/subtitles.srt").write_bytes(b"tampered")
        assert restored.get(job_id)["status"] == "failed"
        with pytest.raises(AppError):
            restored.subtitles(job_id)
        with pytest.raises(AppError):
            restored.video(job_id)


@pytest.mark.parametrize("value", ["invalid", None, [], {}, True])
def test_invalid_subtitle_choice_rejected_before_dispatch(service, value):
    with pytest.raises(AppError):
        service.submit(
            "render",
            {
                "requestId": "b" * 32,
                "planJobId": "c" * 32,
                "planId": "chronological",
                "width": 64,
                "height": 48,
                "subtitleMode": value,
            },
        )
    assert not service.threads


@pytest.mark.parametrize("change", ["mode", "files", "count"])
def test_orphan_rejects_inconsistent_subtitle_receipt(service, change):
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
    directory = service.directory(job_id)
    receipt = service.read(directory / "result/receipt.json")
    if change == "mode":
        receipt["subtitles"]["mode"] = "burn"
    elif change == "files":
        del receipt["files"]["subtitles.srt"]
    else:
        receipt["subtitles"]["cueCount"] = True
    service.save(directory / "result/receipt.json", receipt)
    state = service.read(directory / "status.json")
    state["status"] = "running"
    state.pop("resultReceiptSha256")
    service.save(directory / "status.json", state)
    assert CreationJobs(service.repository).get(job_id)["status"] == "interrupted"
