import hashlib
import json
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_render import decision

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.revision_jobs import load_chain


@pytest.fixture
def revisions(service, monkeypatch):  # noqa: F811
    from dataclasses import replace

    import gamingcreator.ui.creation_jobs as implementation
    from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
    from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

    edl, report, timelines = decision()
    asset = replace(timelines[0].run.asset, source_path=service.repository / "footage/source.mp4")
    timelines[0].run.asset = asset
    for plan in report["plans"]:
        for row in plan["segments"]:
            row["sourcePath"] = str(asset.source_path)

    async def planner(project, runs, brief, output, events, fps, selection):
        report["brief"] = json.loads(brief.read_text())
        write_creation(output, {"plans.json": report}, ())

    async def load_run(run_id):
        return timelines[0].run

    async def load_completed(run_id):
        return SimpleNamespace(**timelines[0].__dict__, transcripts=())

    async def close():
        pass

    async def open_store(*args, **kwargs):
        return SimpleNamespace(
            load_run=load_run, load_completed_timeline=load_completed, close=close
        )

    calls = []

    async def render(
        self,
        plan,
        output,
        protected,
        context,
        width,
        height,
        digest,
        cues,
        mode,
        *,
        audio_mix=None,
        music=None,
    ):
        from gamingcreator.domain.creation_audio import AudioMix

        calls.append(plan)
        output.mkdir()
        (output / "video.mp4").write_bytes(b"revised-video")
        files = {"video.mp4": hash_file(output / "video.mp4")}
        if mode != "none":
            (output / "subtitles.srt").write_bytes(b"")
            files["subtitles.srt"] = hash_file(output / "subtitles.srt")
        (output / "receipt.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "creation-render-receipt-v1",
                    "status": "completed",
                    "files": files,
                    "creationReceiptSha256": digest,
                    "width": width,
                    "height": height,
                    "frames": plan.frames,
                    "subtitles": {"mode": mode, "cueCount": len(cues)},
                    "audioMix": (audio_mix or AudioMix()).to_json(),
                    "music": None if music is None else music.public(),
                }
            )
        )

    monkeypatch.setattr(implementation, "execute_plan_creation", planner)
    monkeypatch.setattr(SqliteTimelineStore, "open", open_store)
    monkeypatch.setattr(FfmpegCreationRenderer, "render", render)
    req = request()
    req["brief"]["targetDuration"] = 6
    root = service.submit("plan", req)["jobId"]
    assert finish(service, root)["status"] == "completed"
    return service, root, calls


def payload(jobs, parent, token="b"):
    snapshot = jobs.edit(parent, "hook-first")
    return {
        "requestId": token * 32,
        "parentJobId": parent,
        "planId": snapshot["planId"],
        "expectedParentReceiptSha256": snapshot["expectedParentReceiptSha256"],
        "clips": [
            {
                "clipId": row["clipId"],
                "startUs": row["startUs"],
                "outputFrames": min(7, row["outputFrames"]),
            }
            for row in reversed(snapshot["clips"])
        ],
    }


def test_revision_trim_order_restore_restart_and_source_immutability(revisions):
    jobs, root, calls = revisions
    original = {p: p.read_bytes() for p in jobs.directory(root).rglob("*") if p.is_file()}
    snapshot = jobs.edit(root, "hook-first")
    assert "sourcePath" not in snapshot["clips"][0]
    assert snapshot["ancestry"] == []
    assert all(p.read_bytes() == data for p, data in original.items())
    req = payload(jobs, root)
    revision = jobs.submit("revision", req)["jobId"]
    result = finish(jobs, revision)
    assert result["status"] == "completed", result
    assert result["editor"]["ancestry"] == [{"jobId": root, "planId": "hook-first", "kind": "plan"}]
    assert [r["clipId"] for r in result["editor"]["clips"]] == [r["clipId"] for r in req["clips"]]
    assert jobs.submit("revision", req)["jobId"] == revision
    child_req = payload(jobs, revision, "c")
    child_req["clips"] = child_req["clips"][:1]
    child = jobs.submit("revision", child_req)["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    restored = jobs.submit("revision", payload(jobs, root, "d"))["jobId"]
    assert finish(jobs, restored)["status"] == "completed"
    restarted = CreationJobs(jobs.repository)
    assert restarted.get(child)["status"] == "completed"
    assert len(restarted.edit(child, "hook-first")["ancestry"]) == 2
    assert not restarted.threads
    rendered = restarted.submit(
        "render",
        {
            "requestId": "e" * 32,
            "revisionJobId": child,
            "width": 320,
            "height": 180,
            "subtitleMode": "sidecar",
        },
    )["jobId"]
    result = finish(restarted, rendered)
    assert result["status"] == "completed", result
    assert calls[-1].frames == 7
    assert result["artifact"]["subtitleCueCount"] == 0
    assert restarted.get(rendered)["status"] == "completed"
    assert all(p.read_bytes() == data for p, data in original.items())


@pytest.mark.parametrize("fault", ["expected", "empty", "duplicate", "foreign", "extra", "bool"])
def test_reject_invalid_revision_before_registration(revisions, fault):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    if fault == "expected":
        req["expectedParentReceiptSha256"] = "0" * 64
    if fault == "empty":
        req["clips"] = []
    if fault == "duplicate":
        req["clips"].append(req["clips"][0])
    if fault == "foreign":
        req["clips"][0]["clipId"] = "unknown"
    if fault == "extra":
        req["path"] = "outside"
    if fault == "bool":
        req["clips"][0]["outputFrames"] = True
    with pytest.raises((ValueError, AppError)):
        jobs.submit("revision", req)
    assert not (jobs.root / (req["requestId"] + ".json")).exists()


@pytest.mark.parametrize("target", ["root", "metadata", "edl", "request", "parent"])
def test_revision_tamper_refuses_editor_and_completed_render(revisions, target):
    jobs, root, _ = revisions
    parent = jobs.submit("revision", payload(jobs, root))["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    child = jobs.submit("revision", payload(jobs, parent, "c"))["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    rendered = jobs.submit(
        "render", {"requestId": "d" * 32, "revisionJobId": child, "width": 320, "height": 180}
    )["jobId"]
    assert finish(jobs, rendered)["status"] == "completed"
    location, name = {
        "root": (root, "result/plans.json"),
        "metadata": (parent, "result/revision.json"),
        "edl": (child, "result/edit-decision.json"),
        "request": (child, "request.json"),
        "parent": (parent, "result/receipt.json"),
    }[target]
    path = jobs.directory(location) / name
    if target == "request":
        stored = jobs.read(path)
        stored["request"]["clips"][0]["outputFrames"] = 1
        jobs.save(path, stored)
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ValueError, AppError)):
        jobs.edit(child, "hook-first")
    assert jobs.get(child)["status"] == "failed"
    assert "editor" not in jobs.get(child)
    assert jobs.get(rendered)["status"] == "failed"


def test_mutually_exclusive_render_parents(revisions):
    jobs, root, _ = revisions
    with pytest.raises((ValueError, AppError)):
        jobs.submit(
            "render",
            {
                "requestId": "e" * 32,
                "revisionJobId": root,
                "planJobId": root,
                "planId": "hook-first",
                "width": 320,
                "height": 180,
            },
        )


def test_chain_depth_and_cycle_rejected(revisions):
    jobs, root, _ = revisions
    # Cycle is rejected before any source read, even if status/request digests were rewritten.
    parent = jobs.submit("revision", payload(jobs, root))["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    directory = jobs.directory(parent)
    stored = jobs.read(directory / "request.json")
    stored["request"]["parentJobId"] = parent
    stored["digest"] = hashlib.sha256(
        json.dumps(
            {"kind": "revision", "request": stored["request"]}, sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()
    jobs.save(directory / "request.json", stored)
    state = jobs.read(directory / "status.json")
    state["parentJobId"] = parent
    receipt = jobs.read(directory / "result/receipt.json")
    receipt["requestDigest"] = stored["digest"]
    jobs.save(directory / "result/receipt.json", receipt)
    state["resultReceiptSha256"] = hash_file(directory / "result/receipt.json")
    jobs.save(directory / "status.json", state)
    with pytest.raises(ValueError, match="cycle"):
        load_chain(jobs, parent, "hook-first")


def test_depth_limit_stops_before_loading_sources(monkeypatch):
    import gamingcreator.ui.revision_jobs as implementation

    def record(jobs, job_id, **kwargs):
        index = int(job_id, 16)
        return (
            {"kind": "revision", "parentJobId": f"{index + 1:032x}"},
            {"request": {"parentJobId": f"{index + 1:032x}", "planId": "hook-first"}},
            "a" * 64,
        )

    monkeypatch.setattr(implementation, "_record", record)
    with pytest.raises(ValueError, match="exceeds 64"):
        load_chain(None, "0" * 32, "hook-first")


def test_revision_orphan_receipt_recovery_does_not_execute(revisions):
    jobs, root, calls = revisions
    revision = jobs.submit("revision", payload(jobs, root))["jobId"]
    assert finish(jobs, revision)["status"] == "completed"
    directory = jobs.directory(revision)
    state = jobs.read(directory / "status.json")
    state["status"] = "running"
    state.pop("resultReceiptSha256")
    jobs.save(directory / "status.json", state)
    restarted = CreationJobs(jobs.repository)
    recovered = restarted.get(revision)
    assert recovered["status"] == "completed"
    assert recovered["editor"]["parentJobId"] == revision
    assert not restarted.threads and not calls


def test_revision_worker_failure_is_saved_and_not_reexecuted(revisions, monkeypatch):
    jobs, root, _ = revisions
    import gamingcreator.ui.creation_jobs as implementation

    def fail_write(*args):
        raise ValueError("unwritable revision")

    monkeypatch.setattr(implementation, "save_revision", fail_write)
    revision = jobs.submit("revision", payload(jobs, root))["jobId"]
    result = finish(jobs, revision)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "creation.execution_failed"
    assert not (jobs.directory(revision) / "result/receipt.json").exists()
    restarted = CreationJobs(jobs.repository)
    assert restarted.get(revision)["status"] == "failed"
    assert not restarted.threads


def test_speed_revisions_reload_render_and_restore_without_rewriting_old_files(revisions):
    from fractions import Fraction

    jobs, root, calls = revisions
    old = jobs.submit("revision", payload(jobs, root))["jobId"]
    assert finish(jobs, old)["status"] == "completed"
    original = {
        p: p.read_bytes()
        for key in (root, old)
        for p in jobs.directory(key).rglob("*")
        if p.is_file()
    }

    def speed_request(parent, token, numerator, denominator):
        snapshot = jobs.edit(parent, "hook-first")
        req = payload(jobs, parent, token)
        req["clips"] = [
            {
                "clipId": row["clipId"],
                "startUs": row["startUs"],
                "endUs": row["endUs"],
                "speed": {"numerator": numerator, "denominator": denominator},
            }
            for row in snapshot["clips"]
        ]
        return req

    slow = jobs.submit("revision", speed_request(old, "c", 1, 2))["jobId"]
    result = finish(jobs, slow)
    assert result["status"] == "completed", result
    assert result["editor"]["targetDuration"] == 6
    assert result["editor"]["actualDuration"] == load_chain(jobs, slow).plan.frames / 30
    assert result["editor"]["clips"][0]["speed"] == {"numerator": 1, "denominator": 2}
    fast = jobs.submit("revision", speed_request(slow, "d", 2, 1))["jobId"]
    assert finish(jobs, fast)["status"] == "completed"
    with pytest.raises(ValueError, match="requires v2"):
        jobs.submit("revision", payload(jobs, fast, "f"))
    restarted = CreationJobs(jobs.repository)
    assert restarted.get(fast)["status"] == "completed"
    assert len(restarted.edit(fast, "hook-first")["ancestry"]) == 3
    assert not restarted.threads
    rendered = restarted.submit(
        "render", {"requestId": "e" * 32, "revisionJobId": fast, "width": 320, "height": 180}
    )["jobId"]
    assert finish(restarted, rendered)["status"] == "completed"
    assert all(clip.speed == Fraction(2) for clip in calls[-1].clips)
    restored = jobs.submit("revision", speed_request(slow, "9", 1, 2))["jobId"]
    assert finish(jobs, restored)["status"] == "completed"
    assert load_chain(jobs, restored).plan.frames == load_chain(jobs, slow).plan.frames
    assert all(p.read_bytes() == data for p, data in original.items())
