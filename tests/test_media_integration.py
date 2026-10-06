import asyncio
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.media import MediaProcessor, SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import ffmpeg_media
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor, hash_file
from gamingcreator.infrastructure.media_process import ProcessOutput, run_media_process

REPOSITORY = Path(__file__).resolve().parents[1]
FFMPEG = REPOSITORY / ".tools/ffmpeg/bin/ffmpeg.exe"
pytestmark = [
    pytest.mark.media,
    pytest.mark.skipif(not FFMPEG.exists(), reason="Project-local FFmpeg not prepared"),
]


@pytest.fixture
def make_video(tmp_path: Path) -> Callable[..., Path]:
    def make(
        name: str,
        *,
        audio: bool = True,
        video_shift: str = "0",
        audio_shift: str = "0",
        vfr: bool = False,
        audio_gap: bool = False,
    ) -> Path:
        path = tmp_path / name
        arguments = [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x96:rate=30:duration=2",
        ]
        if audio:
            arguments += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=2"]
        selection = "select='not(mod(n,2))+eq(mod(n,5),0)'," if vfr else ""
        filters = f"[0:v]{selection}setpts=PTS+({video_shift})/TB[v]"
        if audio:
            gap = "+if(gte(T,0.5),0.2,0)/TB" if audio_gap else ""
            filters += f";[1:a]asetpts='PTS+({audio_shift})/TB{gap}'[a]"
        arguments += ["-filter_complex", filters, "-map", "[v]"]
        if audio:
            arguments += ["-map", "[a]", "-c:a", "aac"]
        arguments += [
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-fps_mode",
            "vfr",
            "-avoid_negative_ts",
            "disabled",
            str(path),
        ]
        subprocess.run(
            arguments,
            capture_output=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return path

    return make


def test_vfr_nonzero_start_and_delayed_audio_are_traceable(
    make_video: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_video("中文 空格 & input.mp4", video_shift="5", audio_shift="5.1", vfr=True)
    processor: MediaProcessor = FfmpegMediaProcessor(REPOSITORY)
    result = asyncio.run(
        processor.preprocess(
            source,
            tmp_path / "evidence",
            SamplingParameters(Fraction(1, 5)),
            CancellationContext("run", 15),
        )
    )
    assert result.asset.origin_seconds >= 5
    assert result.images[0].source_time.time_us == 0
    assert len(result.images) > 5 and result.audio is not None
    audio = result.audio
    mapped = audio.map_interval(0, min(1600, audio.sample_count), result.asset)
    assert mapped.source_range.start_us > 50_000
    assert (
        audio.decoded_sample_count is not None and audio.decoded_sample_count >= audio.sample_count
    )
    assert hash_file(audio.path) == audio.sha256
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "completed" and manifest["audio"]["frames"]
    for image in result.images:
        expected = (
            (image.pts * image.time_base - result.asset.origin_seconds) * 1_000_000
        ).__floor__()
        assert image.source_time.time_us == expected and hash_file(image.path) == image.sha256


def test_audio_before_video_uses_a_common_origin(
    make_video: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_video("early-audio.mp4", video_shift="5.2", audio_shift="5")
    result = asyncio.run(
        FfmpegMediaProcessor(REPOSITORY).preprocess(
            source, tmp_path / "evidence", SamplingParameters(), CancellationContext("run", 15)
        )
    )
    assert result.images[0].source_time.time_us >= 150_000
    assert result.audio is not None
    assert result.audio.map_interval(0, 100, result.asset).source_range.start_us < 1000


def test_absent_audio_keeps_visual_evidence(
    make_video: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_video("no-audio.mp4", audio=False)
    result = asyncio.run(
        FfmpegMediaProcessor(REPOSITORY).preprocess(
            source, tmp_path / "evidence", SamplingParameters(), CancellationContext("run", 15)
        )
    )
    assert result.images and result.audio is None
    assert json.loads(result.manifest_path.read_text())["audio"] is None


def test_audio_timestamp_gap_is_recorded(make_video: Callable[..., Path], tmp_path: Path) -> None:
    source = make_video("audio-gap.mp4", audio_gap=True)
    result = asyncio.run(
        FfmpegMediaProcessor(REPOSITORY).preprocess(
            source, tmp_path / "evidence", SamplingParameters(), CancellationContext("run", 15)
        )
    )
    assert result.audio is not None
    frames = result.audio.frames
    assert any(
        current.pts - previous.pts - previous.sample_count > 1600
        for previous, current in zip(frames, frames[1:], strict=False)
    )
    assert result.audio.map_interval(0, result.audio.sample_count, result.asset).uncertain


def test_malformed_input_does_not_create_evidence(tmp_path: Path) -> None:
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"private-invalid-video")
    output = tmp_path / "evidence"
    with pytest.raises(AppError) as error:
        asyncio.run(
            FfmpegMediaProcessor(REPOSITORY).preprocess(
                source, output, SamplingParameters(), CancellationContext("run", 15)
            )
        )
    assert not output.exists() and "private-invalid-video" not in str(error.value)


def test_sampling_limit_leaves_no_completed_manifest(
    make_video: Callable[..., Path], tmp_path: Path
) -> None:
    source = make_video("limit.mp4")
    output = tmp_path / "evidence"
    with pytest.raises(AppError) as error:
        asyncio.run(
            FfmpegMediaProcessor(REPOSITORY).preprocess(
                source,
                output,
                SamplingParameters(Fraction(1, 10), max_frames=1),
                CancellationContext("run", 15),
            )
        )
    assert error.value.code == "media.frame_limit"
    assert not (output / "media-manifest.json").exists()


def test_source_change_prevents_manifest_publication(
    make_video: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_video("change.mp4")
    original = ffmpeg_media.hash_source
    calls = 0

    async def mutate_second_hash(path: Path, context: CancellationContext) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            with path.open("ab") as destination:
                destination.write(b"changed")
        return await original(path, context)

    monkeypatch.setattr(ffmpeg_media, "hash_source", mutate_second_hash)
    output = tmp_path / "evidence"
    with pytest.raises(AppError) as error:
        asyncio.run(
            FfmpegMediaProcessor(REPOSITORY).preprocess(
                source, output, SamplingParameters(), CancellationContext("run", 15)
            )
        )
    assert error.value.code == "media.source_changed"
    assert not (output / "media-manifest.json").exists()


def test_cancellation_after_frames_never_publishes_manifest(
    make_video: Callable[..., Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_video("cancel.mp4")
    original = run_media_process
    context = CancellationContext("run", 15)

    async def cancel_after_frames(
        arguments: list[str],
        active: CancellationContext,
        *,
        stderr_line_consumer: Callable[[str], bool] | None = None,
    ) -> ProcessOutput:
        result = await original(arguments, active, stderr_line_consumer=stderr_line_consumer)
        if any("frame-%06d.jpg" in argument for argument in arguments):
            active.cancelled.set()
        return result

    monkeypatch.setattr(ffmpeg_media, "run_media_process", cancel_after_frames)
    output = tmp_path / "evidence"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            FfmpegMediaProcessor(REPOSITORY).preprocess(
                source, output, SamplingParameters(), context
            )
        )
    assert not (output / "media-manifest.json").exists()


def test_cancellation_after_final_hash_never_publishes_manifest(
    make_video: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_video("late-cancel.mp4")
    original = ffmpeg_media.hash_source
    calls = 0

    async def cancel_after_final_hash(path: Path, context: CancellationContext) -> str:
        nonlocal calls
        digest = await original(path, context)
        calls += 1
        if calls == 2:
            context.cancelled.set()
        return digest

    monkeypatch.setattr(ffmpeg_media, "hash_source", cancel_after_final_hash)
    output = tmp_path / "evidence"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            FfmpegMediaProcessor(REPOSITORY).preprocess(
                source,
                output,
                SamplingParameters(),
                CancellationContext("run", 15),
            )
        )
    assert not (output / "media-manifest.json").exists()


def test_offline_media_entry_point_uses_explicit_sampling_and_limits(
    make_video: Callable[..., Path],
) -> None:
    source = make_video("中文 显式采样.mp4")
    result = subprocess.run(
        [
            shutil.which("pwsh") or "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPOSITORY / "scripts/test-media.ps1"),
            "-SourcePath",
            str(source),
            "-MaxFrames",
            "20",
            "-SamplingIntervalMs",
            "200",
            "-TimeoutSeconds",
            "30",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    report_path = Path(rows[-1]["report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["samplingIntervalMs"] == 200 and report["maxFrames"] == 20
    assert report["timeoutSeconds"] == 30
    assert 2 < report["cases"][0]["images"] <= 20
    assert report["cases"][0]["sourceSha256"] == hash_file(source)
    assert Path(report["cases"][0]["source"]).name == source.name
