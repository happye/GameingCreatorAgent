"""Saved hand-written subtitles are independent of source transcripts and edits."""

# ruff: noqa: F811

from fractions import Fraction

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401
from test_creation_subtitles import clip, speech

from gamingcreator.application.creation_subtitles import build_subtitles
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import serialize_srt
from gamingcreator.domain.errors import AppError
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.revision_jobs import load_chain


def save(jobs, req):
    job = jobs.submit("revision", req)["jobId"]
    result = finish(jobs, job)
    assert result["status"] == "completed", result
    return job, result["editor"]["subtitleOverrides"]


def test_snapshot_inherit_filter_reset_restart_and_changed_text(revisions):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    first_id = req["clips"][0]["clipId"]
    second_id = req["clips"][1]["clipId"]
    req["subtitleOverrides"] = [
        {"clipId": first_id, "text": "手写中文"},
        {"clipId": second_id, "text": ""},
    ]
    parent, texts = save(jobs, req)
    assert texts == req["subtitleOverrides"]
    assert jobs.submit("revision", req)["jobId"] == parent
    before = (jobs.directory(parent) / "result/receipt.json").read_bytes()
    inherited = payload(jobs, parent, "c")
    child, texts = save(jobs, inherited)
    assert texts == req["subtitleOverrides"]
    inherited = payload(jobs, child, "d")
    inherited["clips"] = [r for r in inherited["clips"] if r["clipId"] == first_id]
    deleted, texts = save(jobs, inherited)
    assert texts == [{"clipId": first_id, "text": "手写中文"}]
    reset = payload(jobs, deleted, "e")
    reset["subtitleOverrides"] = []
    reset_id, texts = save(jobs, reset)
    assert texts == []
    restarted = CreationJobs(jobs.repository)
    assert restarted.edit(parent, "hook-first")["subtitleOverrides"] == req["subtitleOverrides"]
    assert restarted.edit(reset_id, "hook-first")["subtitleOverrides"] == []
    changed = payload(jobs, parent, "f")
    changed["subtitleOverrides"] = [{"clipId": first_id, "text": "改写中文"}]
    changed_id, _ = save(jobs, changed)
    assert load_chain(jobs, changed_id).digest != load_chain(jobs, parent).digest
    assert (jobs.directory(parent) / "result/receipt.json").read_bytes() == before
    with pytest.raises(AppError):
        changed["requestId"] = req["requestId"]
        jobs.submit("revision", changed)


@pytest.mark.parametrize("bad", [None, {}, "text", [{"clipId": "unknown", "text": "x"}]])
def test_invalid_override_shapes_before_registration(revisions, bad):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    req["subtitleOverrides"] = bad
    with pytest.raises((ValueError, AppError)):
        jobs.submit("revision", req)
    assert not (jobs.root / (req["requestId"] + ".json")).exists()


@pytest.mark.parametrize(
    "text", [None, 1, True, "a" * 2001, "x\x00y", "x --> y", "\x01", "  ", "\x7f"]
)
def test_invalid_text_before_registration(revisions, text):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    req["subtitleOverrides"] = [{"clipId": req["clips"][0]["clipId"], "text": text}]
    with pytest.raises((ValueError, AppError)):
        jobs.submit("revision", req)


def test_deleted_and_duplicate_override_ids_rejected(revisions):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    item = {"clipId": req["clips"][-1]["clipId"], "text": "字幕"}
    req["subtitleOverrides"] = [item, item]
    with pytest.raises(ValueError):
        jobs.submit("revision", req)
    req["subtitleOverrides"] = [item]
    req["clips"] = req["clips"][:-1]
    with pytest.raises(ValueError):
        jobs.submit("revision", req)


@pytest.mark.parametrize("fps", [3, 30])
def test_override_clock_suppression_asr_fallback_and_original_immutable(fps):
    plan = RenderPlan(
        (clip(2_000_000, 2_666_667, 2), clip(0, 333_334, 1), clip(0, 333_334, 1)), fps
    )
    transcript = speech(0, 3_000_000, "原语音")
    cues = build_subtitles(plan, (transcript,), overrides=["手写", "", None])
    assert len(cues) == 2
    assert (cues[0].start, cues[0].end) == (Fraction(0), Fraction(2, fps))
    assert cues[0].uncertainty == "user-written"
    assert cues[1].start == Fraction(3, fps)
    assert cues[1].text == "原语音"
    assert transcript.text == "原语音" and transcript.source_range.start_us == 0
    assert "手写" in serialize_srt(cues)
    with pytest.raises(ValueError):
        build_subtitles(plan, (), overrides=[None])


def test_render_uses_saved_text_and_none_keeps_saved_text(revisions, monkeypatch):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    req["subtitleOverrides"] = [{"clipId": req["clips"][0]["clipId"], "text": "无语音手写"}]
    parent, _ = save(jobs, req)
    import gamingcreator.ui.revision_jobs as implementation

    captured = []
    real = implementation.build_subtitles

    def capture(*args, **kwargs):
        cues = real(*args, **kwargs)
        captured.extend(cues)
        return cues

    monkeypatch.setattr(implementation, "build_subtitles", capture)
    for token, mode in [("c", "sidecar"), ("d", "none")]:
        job = jobs.submit(
            "render",
            {
                "requestId": token * 32,
                "revisionJobId": parent,
                "width": 320,
                "height": 180,
                "subtitleMode": mode,
            },
        )["jobId"]
        result = finish(jobs, job)
        assert result["status"] == "completed", result
        assert result["artifact"].get("subtitleCueCount", 0) == (1 if mode == "sidecar" else 0)
    assert len(captured) == 1 and captured[0].text == "无语音手写"
    assert jobs.edit(parent, "hook-first")["subtitleOverrides"] == req["subtitleOverrides"]


@pytest.mark.parametrize("file", ["request.json", "result/revision.json"])
def test_saved_text_tampering_refuses_chain(revisions, file):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    req["subtitleOverrides"] = [{"clipId": req["clips"][0]["clipId"], "text": "原文"}]
    parent, _ = save(jobs, req)
    path = jobs.directory(parent) / file
    document = jobs.read(path)
    target = document["request"] if file == "request.json" else document
    target["subtitleOverrides"][0]["text"] = "篡改"
    jobs.save(path, document)
    with pytest.raises((ValueError, AppError)):
        jobs.edit(parent, "hook-first")
