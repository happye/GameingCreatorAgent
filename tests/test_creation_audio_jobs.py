"""Audio snapshots keep version identity without requiring a renderer."""

# ruff: noqa: F811
import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401

from gamingcreator.domain.creation_audio import AudioMix
from gamingcreator.infrastructure.music_library import MusicLibrary, MusicTrack
from gamingcreator.ui.creation_jobs import CreationJobs


def test_audio_inheritance_clear_and_subtitles(revisions, monkeypatch):
    jobs, root, _ = revisions
    track = MusicTrack(
        "1" * 32,
        "测试",
        jobs.repository / "tone.wav",
        "2" * 64,
        "3" * 64,
        1000000,
        "test_only",
        "test",
    )

    def resolve(self, identity, receipt):
        if identity != track.track_id or receipt != track.receipt_sha256:
            raise ValueError("Music changed")
        return track

    monkeypatch.setattr(MusicLibrary, "resolve", resolve)
    req = payload(jobs, root)
    req["audioMix"] = {
        "bgm": {
            "trackId": track.track_id,
            "trackReceiptSha256": track.receipt_sha256,
            "gainDb": -12,
        },
        "sourceGainDb": -6,
        "ducking": "source-v1",
    }
    req["subtitleOverrides"] = [{"clipId": req["clips"][0]["clipId"], "text": "字幕"}]
    parent = jobs.submit("revision", req)["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    child = jobs.submit("revision", payload(jobs, parent, "c"))["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    snapshot = CreationJobs(jobs.repository).edit(child, "hook-first")
    assert snapshot["audioMix"] == req["audioMix"]
    assert snapshot["subtitleOverrides"] == req["subtitleOverrides"]
    assert jobs.edit(root, "hook-first")["audioMix"] == AudioMix().to_json()
    reset = payload(jobs, child, "d")
    reset["audioMix"] = AudioMix().to_json()
    cleared = jobs.submit("revision", reset)["jobId"]
    assert finish(jobs, cleared)["status"] == "completed"
    assert jobs.edit(cleared, "hook-first")["audioMix"]["bgm"] is None
    assert jobs.edit(parent, "hook-first")["audioMix"] == req["audioMix"]
    for key, value in [("trackId", "4" * 32), ("trackReceiptSha256", "5" * 64)]:
        invalid = payload(jobs, root, "e")
        invalid["audioMix"] = {**req["audioMix"], "bgm": {**req["audioMix"]["bgm"], key: value}}
        with pytest.raises(ValueError):
            jobs.submit("revision", invalid)


def test_render_checks_effective_audio_receipt(revisions, monkeypatch):
    import json

    from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer

    jobs, root, _ = revisions
    original = FfmpegCreationRenderer.render

    async def render(self, *args, audio_mix, music, **kwargs):
        await original(self, *args, **kwargs)
        path = args[1] / "receipt.json"
        value = json.loads(path.read_text())
        value.update(audioMix=audio_mix.to_json(), music=None if music is None else music.public())
        path.write_text(json.dumps(value))

    monkeypatch.setattr(FfmpegCreationRenderer, "render", render)
    req = payload(jobs, root)
    req["audioMix"] = {"bgm": None, "sourceGainDb": -6, "ducking": "off"}
    parent = jobs.submit("revision", req)["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    job = jobs.submit(
        "render", {"requestId": "f" * 32, "revisionJobId": parent, "width": 320, "height": 180}
    )["jobId"]
    assert finish(jobs, job)["status"] == "completed"
    assert jobs.get(job)["artifact"]["mediaType"] == "video/mp4"
