"""Real fixed-tool rendering and receipt/source rejection checks."""

import asyncio
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_creation_planner import brief, clips

from gamingcreator.application.creative_planner import plan_creation
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan, validate_render_plan
from gamingcreator.cli.creation_render import read_creation
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"


def decision():
    material = clips()
    report = plan_creation(brief(), material, 30)
    report["brief"] = {"targetDuration": 6}
    edl = select_edit_decision(report, "hook-first")
    timeline = SimpleNamespace(
        run=SimpleNamespace(run_id="run", asset=material[0].asset),
        events=tuple(clip.event for clip in material),
    )
    return edl, report, (timeline,)


@pytest.mark.parametrize("fault", ["range", "sha", "path", "frames", "unknown", "mismatch"])
def test_reject_forged_decisions(fault):
    edl, report, timelines = decision()
    segment = edl["segments"][0]
    if fault == "range":
        segment["endUs"] = 31_000_000
    elif fault == "sha":
        segment["sourceSha256"] = "b" * 64
    elif fault == "path":
        segment["sourcePath"] = "foreign.mp4"
    elif fault == "frames":
        segment["outputFrames"] = True
    elif fault == "unknown":
        segment["eventId"] = "unknown"
    else:
        edl["segments"] = list(reversed(edl["segments"]))
    with pytest.raises(ValueError):
        validate_render_plan(edl, report, timelines)


def test_receipt_rejects_tampering(tmp_path):
    edl, report, _ = decision()
    directory = tmp_path / "creation"
    write_creation(directory, {"plans.json": report, "edit-decision.json": edl}, ())
    assert read_creation(directory)[0] == edl
    (directory / "edit-decision.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        read_creation(directory)


def run_tool(arguments):
    return subprocess.run(
        [str(FFMPEG), "-v", "error", "-nostdin", "-n", *arguments], check=True, capture_output=True
    ).stdout


@pytest.mark.parametrize("mode", ["silent", "audio", "offset", "vfr"])
def test_real_render_order_clocks_audio_and_immutable_source(tmp_path, mode):
    source = tmp_path / "source.mp4"
    graph = "color=c=red:s=64x48:r=10:d=1[r];color=c=blue:s=64x48:r=10:d=1[b];color=c=green:s=64x48:r=10:d=1[g];[r][b][g]concat=n=3:v=1:a=0"
    arguments = ["-f", "lavfi", "-i", graph]
    if mode != "silent":
        arguments += [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=48000:duration=3",
            "-af",
            "volume=enable='lt(t,2)':volume=0",
            "-c:a",
            "aac",
        ]
    if mode == "offset":
        arguments += ["-output_ts_offset", "5"]
    if mode == "vfr":
        arguments += ["-vf", "select='lt(n,10)+not(mod(n,2))'", "-fps_mode", "vfr"]
    arguments += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)]
    run_tool(arguments)
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    async def scenario():
        context = CancellationContext("test-render", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        # Green first, then red: deliberately not source chronology.
        plan = RenderPlan(
            tuple(
                RenderClip(asset, SourceRange(start, start + 500_000, asset.duration_us), 5)
                for start in (2_000_000, 0)
            ),
            10,
        )
        output = tmp_path / "rendered"
        renderer = FfmpegCreationRenderer(ROOT)
        result = await renderer.render(plan, output, (source,), context, 64, 48)
        assert result["frames"] == 10
        assert result["videoDuration"] == "1"
        assert result["audioStartSeconds"] == "0.000000"
        pixels = run_tool(
            [
                "-i",
                str(output / "video.mp4"),
                "-vf",
                "scale=1:1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "-",
            ]
        )
        assert len(pixels) == 30
        assert pixels[1] > pixels[0] + 30  # first frame green
        assert pixels[15] > pixels[16] + 30  # sixth frame red
        pcm = run_tool(
            ["-i", str(output / "video.mp4"), "-vn", "-ar", "48000", "-ac", "1", "-f", "s16le", "-"]
        )
        import array

        samples = array.array("h", pcm)

        def energy(values):
            return sum(abs(value) for value in values) / len(values)

        if mode == "silent":
            assert max(abs(value) for value in samples) == 0
        else:
            assert energy(samples[2400:12000]) > 100
            assert energy(samples[30000:40000]) < 20
            # First quiet 10 ms block measures the source cut's audio position.
            quiet = next(
                index
                for index in range(4800, min(len(samples), 40000), 480)
                if energy(samples[index : index + 480]) < 20
            )
            assert abs(quiet / 48000 - 0.5) <= 0.1
        receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
        assert (
            receipt["files"]["video.mp4"]
            == hashlib.sha256((output / "video.mp4").read_bytes()).hexdigest()
        )
        with pytest.raises(FileExistsError):
            await renderer.render(plan, output, (), context, 64, 48)
        cancelled = CancellationContext("cancelled", 60)
        cancelled.cancelled.set()
        with pytest.raises(asyncio.CancelledError):
            await renderer.render(plan, tmp_path / "cancelled", (), cancelled, 64, 48)
        assert not (tmp_path / "cancelled" / "receipt.json").exists()

    asyncio.run(scenario())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_source_tamper_rejected_by_real_read_only_store_before_render(tmp_path):
    from test_sqlite_store import HASH, bundle_fixture, event_fixture, media_ready

    from gamingcreator.cli.creation_render import execute_render_creation
    from gamingcreator.domain.errors import AppError
    from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

    async def scenario():
        bundle = bundle_fixture(tmp_path)
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            events = tuple(
                replace(
                    event_fixture(bundle),
                    event_id=f"event{i}",
                    source_range=SourceRange(i * 500_000, (i + 1) * 500_000, 2_000_000),
                )
                for i in range(3)
            )
            await store.persist_timeline("run-1", "vision", events, (), HASH)
            await store.complete_run("run-1")
            timeline = await store.load_completed_timeline("run-1")
        finally:
            await store.close()
        from gamingcreator.application.creative_planner import candidates

        report = plan_creation(brief(), candidates((timeline,), ()), 30)
        report["brief"] = {"targetDuration": 6}
        edl = select_edit_decision(report, "hook-first")
        creation = tmp_path / "creation"
        write_creation(creation, {"plans.json": report, "edit-decision.json": edl}, ())
        bundle.asset.source_path.write_bytes(b"changed source")
        with pytest.raises(AppError) as rejected:
            await execute_render_creation(
                tmp_path / "project",
                creation,
                tmp_path / "output",
                FfmpegCreationRenderer(ROOT),
                64,
                48,
            )
        assert rejected.value.code == "storage.integrity"
        assert not (tmp_path / "output").exists()

    asyncio.run(scenario())


def test_decoder_failure_has_no_completed_receipt(tmp_path):
    from gamingcreator.domain.errors import AppError

    source = tmp_path / "broken.mp4"
    source.write_bytes(b"invalid codec input")
    asset = replace(
        clips()[0].asset, source_path=source, sha256=hashlib.sha256(source.read_bytes()).hexdigest()
    )
    plan = RenderPlan((RenderClip(asset, SourceRange(0, 500_000, asset.duration_us), 5),), 10)

    async def scenario():
        with pytest.raises(AppError):
            await FfmpegCreationRenderer(ROOT).render(
                plan, tmp_path / "failed", (), CancellationContext("failed", 30), 64, 48
            )
        assert not (tmp_path / "failed" / "receipt.json").exists()

    asyncio.run(scenario())


def test_same_hash_different_path_each_rechecked_before_completion(tmp_path, monkeypatch):
    import gamingcreator.infrastructure.ffmpeg_render as implementation

    source = tmp_path / "a.mp4"
    other = tmp_path / "b.mp4"
    run_tool(["-f", "lavfi", "-i", "color=c=red:s=64x48:r=10:d=1", "-c:v", "libx264", str(source)])
    other.write_bytes(source.read_bytes())
    original_process = implementation.run_media_process

    async def mutate_after_decoding(arguments, context):
        result = await original_process(arguments, context)
        if "-xerror" in arguments:
            source.write_bytes(b"source A changed while B stayed the same")
        return result

    monkeypatch.setattr(implementation, "run_media_process", mutate_after_decoding)

    async def scenario():
        context = CancellationContext("two-paths", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = RenderPlan(
            (
                RenderClip(asset, SourceRange(0, 500_000, asset.duration_us), 5),
                RenderClip(
                    replace(asset, source_path=other),
                    SourceRange(500_000, 1_000_000, asset.duration_us),
                    5,
                ),
            ),
            10,
        )
        with pytest.raises(ValueError, match="Source changed"):
            await FfmpegCreationRenderer(ROOT).render(
                plan, tmp_path / "rendered", (), context, 64, 48
            )
        assert not (tmp_path / "rendered" / "receipt.json").exists()

    asyncio.run(scenario())


def test_audio_relative_delay_preserves_sample_alignment(tmp_path):
    import array

    source = tmp_path / "delayed.mov"
    run_tool(
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x48:r=10:d=1",
            "-itsoffset",
            "0.25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=997:sample_rate=48000:duration=0.05",
            "-c:v",
            "libx264",
            "-c:a",
            "pcm_s16le",
            str(source),
        ]
    )

    async def scenario():
        context = CancellationContext("audio-delay", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        assert (
            next(s for s in asset.streams if s.kind == "audio").start_seconds - asset.origin_seconds
            == 1 / 4
        )
        plan = RenderPlan((RenderClip(asset, SourceRange(0, 500_000, asset.duration_us), 5),), 10)
        output = tmp_path / "delayed-render"
        await FfmpegCreationRenderer(ROOT).render(plan, output, (), context, 64, 48)
        decoded = array.array(
            "h",
            run_tool(
                [
                    "-i",
                    str(output / "video.mp4"),
                    "-vn",
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    "-f",
                    "s16le",
                    "-",
                ]
            ),
        )
        reference = array.array(
            "h",
            run_tool(
                [
                    "-i",
                    str(source),
                    "-vn",
                    "-af",
                    "aresample=48000:async=1:first_pts=0",
                    "-ac",
                    "1",
                    "-f",
                    "s16le",
                    "-",
                ]
            ),
        )
        # AAC can ring around an impulse; measure waveform alignment inside the pulse,
        # independently of its low-amplitude leading coding noise.
        lag = max(
            range(-24, 25),
            key=lambda shift: sum(
                reference[index] * decoded[index + shift] for index in range(12240, 13920)
            ),
        )
        assert abs(lag) <= 1  # one 48 kHz output sample
        assert max(abs(value) for value in decoded[:11520]) < 20  # first 240 ms silent
        onset = next(index for index, value in enumerate(decoded) if abs(value) > 500)
        assert abs(onset - 12000) <= 48  # threshold onset within 1 ms of 250 ms

    asyncio.run(scenario())
