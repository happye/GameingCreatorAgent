"""Premiere dry narration handoff through real saved jobs and HTTP."""

# ruff: noqa: F811
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from test_clip_replacement_jobs import replacement_request, replacements  # noqa: F401
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import revisions  # noqa: F401
from test_narration_jobs import choice, done, engine, narrated, revise  # noqa: F401
from test_timeline_export import EDL

from gamingcreator.application.timeline_export import ExportNarration, to_xmeml
from gamingcreator.ui.server import create_server


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_saved_narration_http_read_only(narrated, monkeypatch):  # noqa: F811
    monkeypatch.setattr("test_narration_jobs.SECONDS_PER_CHAR", 2206 / 22050)
    jobs = narrated.jobs
    state = done(jobs, "旁")  # 2206 samples = 4 frames, real WAV bytes
    child = revise(jobs, narrated.root, "b", narration=choice(state, start=7))
    assert child["status"] == "completed"
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        before = snapshot(jobs.repository)
        url = f"http://127.0.0.1:{server.server_port}/api/creation/jobs/{child['jobId']}/timeline?planId=hook-first&format=xmeml"
        with urllib.request.urlopen(url) as response:
            xml = ET.fromstring(response.read())
            assert "-premiere.xml" in response.headers["Content-Disposition"]
        tracks = xml.findall("./sequence/media/audio/track")
        assert len(tracks) == 2
        clip = tracks[1].find("clipitem")
        assert [clip.findtext(k) for k in ("start", "end", "in", "out")] == ["7", "11", "0", "4"]
        file = clip.find("file")
        assert file.findtext("./media/audio/samplecharacteristics/samplerate") == "22050"
        assert file.findtext("./media/audio/samplecharacteristics/depth") == "16"
        uri = urlparse(file.findtext("pathurl"))
        path = Path(urllib.request.url2pathname(unquote(uri.path)))
        assert path.read_bytes()[:4] == b"RIFF"
        assert before == snapshot(jobs.repository)
        assert narrated.engine.synthesized == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_narration_ceil_and_legacy_bytes(tmp_path):
    baseline = to_xmeml(EDL, "legacy", include_audio_track=True)
    assert baseline == to_xmeml(EDL, "legacy", include_audio_track=True, narration=None)
    narration = ExportNarration(str(tmp_path / "voice.wav"), 4, 22050, 2, 3, 2206)
    root = ET.fromstring(to_xmeml(EDL, "test", narration=narration))
    clip = root.find("./sequence/media/audio/track/clipitem")
    assert clip.findtext("end") == "8"
    assert clip.findtext("./file/media/audio/channelcount") == "2"
    assert clip.findtext("./file/media/audio/samplecharacteristics/depth") == "24"
    with pytest.raises(ValueError):
        to_xmeml(EDL, "too long", narration=ExportNarration("x", 0, 1, 1, 2, 999999))


@pytest.mark.parametrize("damage", ["project", "status", "wav", "receipt", "missing"])
def test_bad_dependency_is_read_only(narrated, damage):  # noqa: F811
    import json

    jobs = narrated.jobs
    state = done(jobs)
    child = revise(jobs, narrated.root, "b", narration=choice(state))
    assert child["status"] == "completed"
    directory = jobs.directory(state["jobId"])
    if damage in ("project", "status"):
        path = directory / "status.json"
        value = json.loads(path.read_text())
        value["projectId" if damage == "project" else "status"] = (
            "artifacts/other" if damage == "project" else "running"
        )
        path.write_text(json.dumps(value))
    else:
        path = (
            directory
            / "result"
            / ("narration.wav" if damage in ("wav", "missing") else "receipt.json")
        )
        if damage == "missing":
            path.unlink()
        else:
            path.write_bytes(b"corrupt")
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        before = snapshot(jobs.repository)
        url = f"http://127.0.0.1:{server.server_port}/api/creation/jobs/{child['jobId']}/timeline?planId=hook-first&format=xmeml"
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(url)
        with caught.value as response:
            assert response.code in (400, 409)
            assert "json" in response.headers["Content-Type"]
            assert json.loads(response.read())["message"]
        assert before == snapshot(jobs.repository)
        assert narrated.engine.synthesized == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def nonzero_asset(target):
    import asyncio
    import subprocess

    from gamingcreator.application.providers import CancellationContext
    from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor

    target.unlink()  # fixture B only, never a user file
    repository = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            str(repository / ".tools/ffmpeg/bin/ffmpeg.exe"),
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=64x48:r=30:d=30",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-output_ts_offset",
            "2.5",
            str(target),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return asyncio.run(
        FfmpegMediaProcessor(repository).probe(target, CancellationContext("clock-test", 30))
    )


def test_saved_replacement_speed_transition_nonzero_clock_with_narration(
    replacements, engine, monkeypatch
):  # noqa: F811
    from dataclasses import replace
    from fractions import Fraction

    from gamingcreator.ui.revision_jobs import load_chain

    jobs, root, other = replacements
    target = other.run.asset.source_path
    asset = nonzero_asset(target)
    assert asset.origin_seconds == Fraction(5, 2)
    assert asset.duration_us == other.run.asset.duration_us
    other.run.asset = replace(asset, media_id="B")
    monkeypatch.setattr("test_narration_jobs.SECONDS_PER_CHAR", 2206 / 22050)
    narration = done(jobs, "旁")
    request = replacement_request(jobs, root)
    request["narration"] = choice(narration, start=7)
    replaced = finish(jobs, jobs.submit("revision", request)["jobId"])
    assert replaced["status"] == "completed", replaced
    editor = jobs.edit(replaced["jobId"], "hook-first")
    descendant = {
        "requestId": "c" * 32,
        "parentJobId": replaced["jobId"],
        "planId": "hook-first",
        "expectedParentReceiptSha256": editor["expectedParentReceiptSha256"],
        "candidateManifestSha256": request["candidateManifestSha256"],
        "replacements": [],
        "clips": [
            {k: row[k] for k in ("clipId", "startUs", "endUs", "speed", "transitionIn")}
            for row in editor["clips"]
        ],
    }
    descendant["clips"][0]["speed"] = {"numerator": 2, "denominator": 1}
    descendant["clips"][1]["transitionIn"] = {"type": "crossfade", "frames": 3}
    child = finish(jobs, jobs.submit("revision", descendant)["jobId"])
    assert child["status"] == "completed", child
    chain = load_chain(jobs, child["jobId"], "hook-first", read_only=True)
    assert chain.edl["segments"][0]["runId"] == "B"
    assert chain.timelines[0].run.asset.origin_seconds != asset.origin_seconds
    before = snapshot(jobs.repository)
    xml = ET.fromstring(jobs.timeline_export(child["jobId"], "hook-first", "xmeml")[0])
    video = xml.findall("./sequence/media/video/track/clipitem")
    assert video[0].findtext("./file/pathurl") == target.resolve().as_uri()
    # Normalized source seconds, with 2.5s absolute container origin excluded.
    assert int(video[0].findtext("in")) == request["clips"][0]["startUs"] * 30 // 1_000_000
    assert video[0].findtext('./filter/effect/parameter[parameterid="speed"]/value') == "200"
    assert xml.find("./sequence/media/video/track/transitionitem") is not None
    voice = xml.findall("./sequence/media/audio/track")[-1].find("clipitem")
    assert (voice.findtext("start"), voice.findtext("end")) == ("7", "11")
    assert before == snapshot(jobs.repository)
