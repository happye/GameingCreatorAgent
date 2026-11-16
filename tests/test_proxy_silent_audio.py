"""B11: 无声代理可播放，声音状态诚实；缺音轨不伪造波形，也不改原片音频。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_inspection_http import get, workspace
from test_sqlite_store import CONFIG, event_fixture, sha

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.media import MediaPreprocessingResult, VisualEvidence
from gamingcreator.infrastructure.audio_peaks import audio_peaks
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor, write_manifest
from gamingcreator.infrastructure.proxy_media import SETTINGS, make_proxy, proxy_directory
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.server import InspectionHandler

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
FFPROBE = FFMPEG.with_name("ffprobe.exe")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG.exists(), reason="project FFmpeg missing")


def use_project_ffmpeg(monkeypatch) -> None:
    """Workspace tmp dirs have no .tools; decode peaks with the project FFmpeg, still from the given source path."""
    import gamingcreator.ui.server as server_module

    def peaks(repository, source, start, end, buckets):
        return audio_peaks(ROOT, source, start, end, buckets)

    monkeypatch.setattr(server_module, "audio_peaks", peaks)


def encode(path: Path, *args: str) -> Path:
    subprocess.run(
        [str(FFMPEG), "-v", "error", "-y", *args, str(path)], check=True, capture_output=True
    )
    return path


def stream_kinds(path: Path) -> list[str]:
    result = subprocess.run(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_source(path: Path):
    return asyncio.run(FfmpegMediaProcessor(ROOT).probe(path, CancellationContext("b11-audio", 60)))


def build_proxy(repo: Path, source: Path, sha256: str, duration_us: int):
    return asyncio.run(
        make_proxy(
            repo, source, sha256, duration_us, CancellationContext("proxy", 120), FFMPEG.parent
        )
    )


def seed_from_video(root: Path, video: Path):
    source_root = root / "artifacts"
    source_root.mkdir(parents=True, exist_ok=True)
    source = source_root / "source.mp4"
    if source.resolve() != video.resolve():
        source.write_bytes(video.read_bytes())
    asset = probe_source(source)
    project = source_root / "project"
    directory = project / "runs" / "run-1" / "media"
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / "frame.png"
    image_path.write_bytes(b"not a real image: storage fixture")
    video_stream = next(stream for stream in asset.streams if stream.kind == "video")
    image = VisualEvidence(
        f"run-1:{asset.media_id}:image:000000",
        image_path,
        sha(image_path),
        video_stream.start_pts,
        video_stream.time_base,
        asset.instant(video_stream.start_pts, video_stream.time_base),
    )
    bundle = MediaPreprocessingResult(
        asset, (image,), None, directory / "media-manifest.json", "fixture-v1", "fixture-processor"
    )
    write_manifest(bundle, SamplingParameters())
    event = replace(
        event_fixture(
            bundle, run_id="run-1", event_id=f"run-1:{bundle.asset.media_id}:event:" + "ab" * 12
        ),
        observable_facts=("画面左侧有白色头发的主体。",),
        modality="visual",
    )

    async def create():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-1", bundle.asset, CONFIG)
            await store.begin_stage("run-1", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-1", bundle)
            await store.begin_stage("run-1", "vision", "a" * 64)
            await store.persist_timeline("run-1", "vision", (event,), (), "b" * 64)
            await store.complete_run("run-1")
            return await store.load_timeline("run-1", require_completed=True)
        finally:
            await store.close()

    return project, bundle, asyncio.run(create())


def plant_proxy(repository: Path, source_sha256: str, source_duration_us: int, body: bytes) -> None:
    directory = proxy_directory(repository, source_sha256)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "proxy.mp4").write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    (directory / "receipt.json").write_text(
        json.dumps(
            {
                "schemaVersion": "editing-proxy-receipt-v1",
                "sourceSha256": source_sha256,
                "sourceDurationUs": source_duration_us,
                "settings": SETTINGS,
                "bytes": len(body),
                "budgetBytes": len(body) + 1,
                "durationUs": source_duration_us,
                "proxySha256": digest,
                "use": "preview-only; renders read the original source",
            }
        ),
        encoding="utf-8",
    )


@needs_ffmpeg
def test_video_only_proxy_is_playable_and_does_not_invent_audio(tmp_path):
    source = encode(
        tmp_path / "silent.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-an",
        "-c:v",
        "libx264",
    )
    before = source.read_bytes()
    sha256 = hashlib.sha256(before).hexdigest()
    receipt = build_proxy(tmp_path, source, sha256, 2_000_000)
    proxy = Path(receipt["path"])
    assert receipt["reused"] is False
    assert receipt["sourceHasAudio"] is False
    assert receipt["proxyHasAudio"] is False
    assert stream_kinds(proxy) == ["video"]
    assert abs(receipt["durationUs"] - 2_000_000) <= 500_000
    assert source.read_bytes() == before
    # A frame can be decoded from the proxy (playable, not a broken stub).
    frame = tmp_path / "frame.png"
    subprocess.run(
        [str(FFMPEG), "-v", "error", "-y", "-i", str(proxy), "-frames:v", "1", str(frame)],
        check=True,
        capture_output=True,
    )
    assert frame.stat().st_size > 0


@needs_ffmpeg
def test_silent_audio_track_is_kept_and_source_is_unchanged(tmp_path):
    source = encode(
        tmp_path / "quiet.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=mono:d=2",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
    )
    before = source.read_bytes()
    sha256 = hashlib.sha256(before).hexdigest()
    receipt = build_proxy(tmp_path, source, sha256, 2_000_000)
    assert receipt["sourceHasAudio"] is True
    assert receipt["proxyHasAudio"] is True
    assert stream_kinds(Path(receipt["path"])) == ["video", "audio"]
    assert source.read_bytes() == before


@needs_ffmpeg
def test_inspect_and_waveform_stay_honest_when_proxy_audio_differs(tmp_path, monkeypatch):
    silent = encode(
        tmp_path / "video-only.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-an",
        "-c:v",
        "libx264",
    )
    loud = encode(
        tmp_path / "loud.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=48000:duration=2",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
    )
    use_project_ffmpeg(monkeypatch)
    project, bundle, _timeline = seed_from_video(tmp_path, silent)
    original = tmp_path / "artifacts" / "source.mp4"
    before = original.read_bytes()
    plant_proxy(tmp_path, bundle.asset.sha256, bundle.asset.duration_us, loud.read_bytes())
    InspectionHandler.waveform_cache.clear()
    try:
        with workspace(tmp_path) as base:
            query = urlencode({"project": "artifacts/project", "run": "run-1"})
            status, _headers, body = get(base, "/api/inspect?" + query)
            assert status == 200
            media = json.loads(body.decode("utf-8"))["media"]
            assert media["sourceHasAudio"] is False
            assert media["proxyUrl"] and "proxy=1" in media["proxyUrl"]
            wave = urlencode(
                {
                    "project": "artifacts/project",
                    "run": "run-1",
                    "startUs": "0",
                    "endUs": "1000000",
                    "buckets": "8",
                }
            )
            status, _headers, body = get(base, "/api/waveform?" + wave)
            assert status == 200
            payload = json.loads(body.decode("utf-8"))
            assert payload == {"audio": False, "peaks": []}
            status, headers, body = get(base, "/api/media?" + query + "&proxy=1")
            assert status == 200
            assert "video/mp4" in headers.get("Content-Type", "")
            assert body == loud.read_bytes()
            runs_status, _h, runs_body = get(
                base, "/api/runs?" + urlencode({"project": "artifacts/project"})
            )
            assert runs_status == 200
            row = next(
                item
                for item in json.loads(runs_body.decode("utf-8"))["runs"]
                if item["id"] == "run-1"
            )
            assert row["sourceHasAudio"] is False
    finally:
        InspectionHandler.waveform_cache.clear()
    assert original.read_bytes() == before
    assert audio_peaks(ROOT, original, 0, 1_000_000, 8) is None


@needs_ffmpeg
def test_waveform_keeps_original_tone_when_proxy_has_no_audio(tmp_path, monkeypatch):
    tone = encode(
        tmp_path / "tone.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
    )
    silent_proxy = encode(
        tmp_path / "proxy-silent.mp4",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
        "-an",
        "-c:v",
        "libx264",
    )
    use_project_ffmpeg(monkeypatch)
    project, bundle, _timeline = seed_from_video(tmp_path, tone)
    original = tmp_path / "artifacts" / "source.mp4"
    before = original.read_bytes()
    expected = audio_peaks(ROOT, original, 0, 1_000_000, 8)
    assert expected is not None and max(expected) > 0.05
    plant_proxy(tmp_path, bundle.asset.sha256, bundle.asset.duration_us, silent_proxy.read_bytes())
    InspectionHandler.waveform_cache.clear()
    try:
        with workspace(tmp_path) as base:
            status, _headers, body = get(
                base,
                "/api/inspect?" + urlencode({"project": "artifacts/project", "run": "run-1"}),
            )
            assert status == 200
            media = json.loads(body.decode("utf-8"))["media"]
            assert media["sourceHasAudio"] is True
            status, _headers, body = get(
                base,
                "/api/waveform?"
                + urlencode(
                    {
                        "project": "artifacts/project",
                        "run": "run-1",
                        "startUs": "0",
                        "endUs": "1000000",
                        "buckets": "8",
                    }
                ),
            )
            assert status == 200
            payload = json.loads(body.decode("utf-8"))
            assert payload["audio"] is True
            assert payload["peaks"] == expected
    finally:
        InspectionHandler.waveform_cache.clear()
    assert original.read_bytes() == before
