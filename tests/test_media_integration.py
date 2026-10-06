import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.media import MediaProcessor, SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.cli import main as cli
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


def test_preparation_cli_uses_real_ffmpeg_without_model_or_network_construction(
    make_video: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = make_video("中文 本地准备.mp4", video_shift="5", audio_shift="5.1", vfr=True)
    project = tmp_path / "prepared-project"

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline preparation constructed a model, transport, or cost port")

    for name in (
        "_pinned_asr_settings",
        "LocalAsrProvider",
        "vision_for_run",
        "BudgetLedger",
        "HttpxVisionTransport",
    ):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    arguments = [
        "prepare-media",
        str(source),
        "--project",
        str(project),
        "--config",
        str(REPOSITORY / "config.example.json"),
        "--max-cost-cny",
        "5",
        "--timeout-seconds",
        "30",
    ]
    assert cli.main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "media_prepared" and result["runStatus"] == "pending"
    assert result["imageCount"] == 2 and result["audioAvailable"] is True
    assert result["modelInvocations"] == 0 and result["coverageFits"] is True
    run_id = result["runId"]
    assert not (project / "runs" / run_id / "semantic_timeline.json").exists()
    manifest = project / "runs" / run_id / "media" / "media-manifest.json"
    before = manifest.read_bytes()
    assert (
        cli.main(["prepare-media", str(source), "--project", str(project), "--resume", run_id]) == 0
    )
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["runId"] == run_id and manifest.read_bytes() == before
    second = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import asyncio,json,sys; from pathlib import Path; from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore\nasync def read():\n s=await SqliteTimelineStore.open(Path(sys.argv[1]),read_only=True)\n try:\n  r=await s.load_run(sys.argv[2]); b=await s.load_media_bundle(sys.argv[2]); i=await s.load_invocations(sys.argv[2]); print(json.dumps({'status':str(r.status),'frames':len(b.images),'invocations':len(i),'sourceSha256':b.asset.sha256,'origin':str(b.asset.origin_seconds)}))\n finally: await s.close()\nasyncio.run(read())",
            str(project),
            run_id,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert second.returncode == 0, second.stderr
    restored = json.loads(second.stdout)
    assert restored == {
        "status": "pending",
        "frames": 2,
        "invocations": 0,
        "sourceSha256": hash_file(source),
        "origin": "5",
    }


def test_preparation_script_with_no_api_key_preserves_pending_run_and_returns_id(
    make_video: Callable[..., Path],
    tmp_path: Path,
) -> None:
    source = make_video("中文 准备脚本.mp4", audio=False)
    project = tmp_path / "prepared-script-project"
    environment = os.environ.copy()
    environment.pop("DEEPSEEK_API_KEY", None)
    result = subprocess.run(
        [
            shutil.which("pwsh") or "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPOSITORY / "scripts/prepare-media.ps1"),
            "-Video",
            str(source),
            "-Project",
            str(project),
            "-Config",
            str(REPOSITORY / "config.example.json"),
            "-MaxCostCny",
            "5",
            "-TimeoutSeconds",
            "30",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "media_prepared" and report["runStatus"] == "pending"
    assert report["audioAvailable"] is False and report["imageCount"] == 2
    assert report["modelInvocations"] == 0
    assert report["nextCommand"][-2:] == ["--resume", report["runId"]]


def test_preparation_reports_insufficient_window_coverage_before_analysis(
    make_video: Callable[..., Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Coverage planning must not construct a vision provider")

    monkeypatch.setattr(cli, "vision_for_run", forbidden)
    source = make_video("coverage.mp4", audio=False)
    config = json.loads((REPOSITORY / "config.example.json").read_text(encoding="utf-8"))
    config["sampling"]["intervalMs"] = 200
    config["limits"] = {"maxRequests": 1, "maxInputFrames": 20}
    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert (
        cli.main(
            [
                "prepare-media",
                str(source),
                "--project",
                str(tmp_path / "coverage-project"),
                "--config",
                str(config_path),
                "--max-cost-cny",
                "5",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "media_prepared" and result["runStatus"] == "pending"
    assert result["coverageFits"] is False and result["nextCommand"] is None
    assert result["plannedWindows"] > result["maxRequests"] and result["modelInvocations"] == 0
