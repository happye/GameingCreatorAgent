"""Local shot boundaries: pure rules, log mapping, real FFmpeg and the read-only CLI."""

from __future__ import annotations

import asyncio
import json
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest
from test_detail_query import snapshot
from test_material_tasks import CONFIG, seed_tasks

from gamingcreator.application.analysis import window_input_hash, window_slices
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.shot_boundaries import (
    SHOT_REPORT_VERSION,
    ShotDetectorIdentity,
    ShotSamples,
    build_shot_report,
    shot_summary,
)
from gamingcreator.application.storage import (
    RunStatus,
    StageCheckpoint,
    StageStatus,
    StoredRun,
)
from gamingcreator.cli.main import main
from gamingcreator.cli.shot_boundaries import execute_detect_shots
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.shot_boundaries import (
    BlackTransition,
    CutCandidate,
    ShotParameters,
    black_intervals,
    detect_shot_boundaries,
    frames_span_cut,
    span_report,
)
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_shots import IDENTITY, FfmpegShotDetector, ShotLogParser

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
SECOND = 1_000_000


def asset(duration_us: int = 10 * SECOND, origin: Fraction = Fraction(0)) -> MediaAsset:
    ticks = int((Fraction(duration_us, SECOND)) * 1000)
    start = int(origin * 1000)
    return MediaAsset(
        "media-1",
        Path("C:/footage/demo.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1000), start, ticks),),
        origin,
        duration_us,
        "fixture",
    )


def test_black_intervals_pair_transitions_and_keep_long_runs_only() -> None:
    transitions = [
        BlackTransition(1 * SECOND, True),
        BlackTransition(1 * SECOND + 100_000, False),  # too short
        BlackTransition(3 * SECOND, True),
        BlackTransition(4 * SECOND, False),
        BlackTransition(4 * SECOND + 500_000, False),  # end without start
        BlackTransition(9 * SECOND, True),  # runs to the end
    ]
    ranges = black_intervals(transitions, 10 * SECOND, 200_000)
    assert [(item.start_us, item.end_us) for item in ranges] == [
        (3 * SECOND, 4 * SECOND),
        (9 * SECOND, 10 * SECOND),
    ]


def test_flashes_close_cuts_and_black_edges_are_not_counted_as_cuts() -> None:
    candidates = [
        CutCandidate(2 * SECOND, 30.0),
        CutCandidate(2 * SECOND + 300_000, 12.0),  # closer than min shot to the last cut
        CutCandidate(5 * SECOND, 40.0),  # flash in ...
        CutCandidate(5 * SECOND + 40_000, 40.0),  # ... and out
        CutCandidate(6 * SECOND, 50.0),  # into black, covered by the black edge
        CutCandidate(8 * SECOND, 20.0),
        CutCandidate(0, 99.0),  # first frame is never a cut
    ]
    transitions = [BlackTransition(6 * SECOND, True), BlackTransition(7 * SECOND, False)]
    result = detect_shot_boundaries(candidates, transitions, 10 * SECOND)
    assert [item.time_us for item in result.cuts] == [2 * SECOND, 8 * SECOND]
    assert result.flashes_dropped == 2 and result.close_cuts_dropped == 1
    assert [(item.start_us, item.end_us) for item in result.black] == [(6 * SECOND, 7 * SECOND)]
    assert [(item.start_us, item.end_us) for item in result.shots] == [
        (0, 2 * SECOND),
        (2 * SECOND, 6 * SECOND),
        (7 * SECOND, 8 * SECOND),
        (8 * SECOND, 10 * SECOND),
    ]


def test_span_report_counts_inner_cuts_black_overlap_and_touched_shots() -> None:
    result = detect_shot_boundaries(
        [CutCandidate(2 * SECOND, 30.0), CutCandidate(8 * SECOND, 20.0)],
        [BlackTransition(6 * SECOND, True), BlackTransition(7 * SECOND, False)],
        10 * SECOND,
    )
    inside = span_report(SourceRange(1 * SECOND, 9 * SECOND, 10 * SECOND), result)
    assert (inside.cuts_inside, inside.black_overlap_us, inside.shots_touched) == (2, SECOND, 4)
    # A cut exactly on the range edge starts or ends it; it is not inside.
    edge = span_report(SourceRange(2 * SECOND, 3 * SECOND, 10 * SECOND), result)
    assert (edge.cuts_inside, edge.black_overlap_us, edge.shots_touched) == (0, 0, 1)
    # Rounding leaves an event end one microsecond past the cut frame: still not inside.
    rounded = span_report(SourceRange(SECOND, 2 * SECOND + 1, 10 * SECOND), result)
    assert rounded.cuts_inside == 0
    assert frames_span_cut(SECOND, 2 * SECOND, result) == 1
    assert frames_span_cut(2 * SECOND, 3 * SECOND, result) == 0


def test_window_slices_match_the_vision_window_stride() -> None:
    assert window_slices(0, CONFIG.analysis) == ()
    assert window_slices(5, CONFIG.analysis) == (slice(0, 5),)
    assert window_slices(9, CONFIG.analysis) == (slice(0, 5), slice(4, 9))
    assert window_slices(10, CONFIG.analysis) == (slice(0, 5), slice(4, 9), slice(8, 13))


def test_parameters_and_duration_are_validated() -> None:
    with pytest.raises(ValueError):
        ShotParameters(min_shot_us=-1)
    with pytest.raises(ValueError):
        detect_shot_boundaries([], [], 0)


def header(pts: int, seconds: str, index: int = 3) -> str:
    return f"[Parsed_metadata_{index} @ 0000] frame:7    pts:{pts}  pts_time:{seconds}\r\n"


def test_log_parser_maps_pts_to_the_source_origin_and_skips_outside_frames() -> None:
    parser = ShotLogParser(asset(5 * SECOND, origin=Fraction(1)))
    lines = [
        "[Parsed_scdet_1 @ 0000] unrelated diagnostic\n",
        header(500, "0.5"),  # before the media origin
        "[Parsed_metadata_3 @ 0000] lavfi.scd.score=40.0\n",
        header(2500, "2.5"),
        "[Parsed_metadata_3 @ 0000] lavfi.scd.score=12.5\n",
        header(3000, "3", 4),
        "[Parsed_metadata_4 @ 0000] lavfi.black_start=3\n",
        header(4000, "4", 5),
        "[Parsed_metadata_5 @ 0000] lavfi.black_end=4\n",
    ]
    consumed = [parser.consume(line) for line in lines]
    assert consumed == [False, True, True, True, True, True, True, True, True]
    samples = parser.finish()
    assert samples.cuts == (CutCandidate(1_500_000, 12.5),)
    assert samples.transitions == (
        BlackTransition(2 * SECOND, True),
        BlackTransition(3 * SECOND, False),
    )
    assert samples.frames_outside_media == 1


def test_log_parser_refuses_a_clock_mismatch_or_an_unpaired_header() -> None:
    parser = ShotLogParser(asset())
    with pytest.raises(AppError) as mismatch:
        parser.consume(header(2000, "4"))  # 1/1000 says 2 s
    assert mismatch.value.code == "media.shot_mapping"
    lonely = ShotLogParser(asset())
    lonely.consume(header(2000, "2"))
    with pytest.raises(AppError):
        lonely.finish()
    orphan = ShotLogParser(asset())
    with pytest.raises(AppError):
        orphan.consume("[Parsed_metadata_3 @ 0000] lavfi.scd.score=40\n")


IDENTITY_FIXTURE = ShotDetectorIdentity("fixture-detector", "scdet", 10, "0.10")


def stored_run(media: MediaAsset) -> StoredRun:
    return StoredRun("run-1", media, CONFIG, "hash", RunStatus.COMPLETED, None)


def event(event_id: str, start: int, end: int, duration: int) -> SemanticEvent:
    return SemanticEvent(
        event_id,
        "media-1",
        "run-1",
        SourceRange(start, end, duration),
        ("fact",),
        (),
        (),
        "visual",
        None,
    )


def test_report_marks_events_that_cross_cuts_and_stays_inert() -> None:
    media = asset()
    samples = ShotSamples(
        (CutCandidate(2 * SECOND, 30.0), CutCandidate(8 * SECOND, 20.0)),
        (BlackTransition(6 * SECOND, True), BlackTransition(7 * SECOND, False)),
        0,
    )
    events = (
        event("late", 7 * SECOND + 500_000, 9 * SECOND, media.duration_us),
        event("early", 0, 1 * SECOND, media.duration_us),
        event("dark", 5 * SECOND, 6 * SECOND + 500_000, media.duration_us),
    )
    report = build_shot_report(stored_run(media), events, samples, IDENTITY_FIXTURE, "ffmpeg x")
    assert report["schemaVersion"] == SHOT_REPORT_VERSION
    assert report["readOnly"] is True and report["paidRequests"] == 0
    assert report["humanReviewed"] is False
    rows = report["events"]
    assert [row["eventId"] for row in rows] == ["early", "dark", "late"]
    assert [row["crossesCut"] for row in rows] == [False, False, True]
    assert rows[1]["blackOverlapUs"] == 500_000
    summary = report["summary"]
    assert summary["cuts"] == 2 and summary["shots"] == 4
    assert summary["eventsCrossingCut"] == 1 and summary["eventsWithBlack"] == 1
    assert summary["medianShotUs"] == 2 * SECOND
    assert summary["windows"] == 0 and report["windowsSpanningCut"] == []
    lines = shot_summary(report)
    assert any("1 个跨越镜头切换" in line for line in lines)
    json.dumps(report, ensure_ascii=False)


def test_report_rebuilds_vision_windows_from_saved_frames() -> None:
    media = asset()
    samples = ShotSamples(
        (CutCandidate(2 * SECOND, 30.0), CutCandidate(8 * SECOND, 20.0)),
        (BlackTransition(6 * SECOND, True), BlackTransition(7 * SECOND, False)),
        0,
    )
    frames = tuple((f"image-{second}", second * SECOND) for second in reversed(range(10)))
    sent = window_input_hash([f"image-{second}" for second in range(5)])
    checkpoints = (
        StageCheckpoint("run-1", "vision-000000", StageStatus.COMPLETED, sent, "o", 1, None),
        StageCheckpoint("run-1", "vision-000001", StageStatus.FAILED, "x" * 64, None, 1, "e"),
    )
    report = build_shot_report(
        stored_run(media),
        (),
        samples,
        IDENTITY_FIXTURE,
        "ffmpeg x",
        frames=frames,
        checkpoints=checkpoints,
    )
    summary = report["summary"]
    assert (summary["windows"], summary["windowsSpanningCut"]) == (3, 2)
    assert summary["windowsWithBlackFrames"] == 1
    assert (summary["windowsStarted"], summary["windowInputMismatches"]) == (2, 1)
    first, second = report["windowsSpanningCut"]
    assert (first["stageStatus"], first["inputMatchesStage"]) == ("completed", True)
    assert (second["stageStatus"], second["inputMatchesStage"]) == ("failed", False)
    assert any("1 个窗口与保存的分析输入不一致" in line for line in shot_summary(report))
    # The fingerprint follows the saved analysis, not the scan.
    later = build_shot_report(
        stored_run(media), (), samples, IDENTITY_FIXTURE, "ffmpeg x", frames=frames
    )
    assert later["timelineDigest"] != report["timelineDigest"]
    assert [
        (row["window"], row["firstFrameUs"], row["lastFrameUs"])
        for row in report["windowsSpanningCut"]
    ] == [(0, 0, 4 * SECOND), (1, 4 * SECOND, 8 * SECOND)]
    assert any("2 个的画面来自不同镜头" in line for line in shot_summary(report))


def make_color_video(destination: Path) -> None:
    graph = (
        "color=c=red:s=320x180:r=25:d=1.2[a];color=c=blue:s=320x180:r=25:d=1.2[b];"
        "color=c=black:s=320x180:r=25:d=1[c];color=c=green:s=320x180:r=25:d=1.2[d];"
        "[a][b][c][d]concat=n=4:v=1:a=0[v]"
    )
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@pytest.mark.skipif(not FFMPEG.is_file(), reason="project-local FFmpeg is not installed")
def test_real_ffmpeg_finds_the_hard_cut_and_the_black_gap(tmp_path: Path) -> None:
    source = tmp_path / "colors.mp4"
    make_color_video(source)

    async def run() -> tuple[MediaAsset, ShotSamples]:
        context = CancellationContext("test-shots", 120)
        media = await FfmpegMediaProcessor(ROOT).probe(source, context)
        return media, await FfmpegShotDetector(ROOT).samples(media, context)

    media, samples = asyncio.run(run())
    result = detect_shot_boundaries(samples.cuts, samples.transitions, media.duration_us)
    frame = 40_000
    assert len(result.cuts) == 1 and abs(result.cuts[0].time_us - 1_200_000) <= frame
    assert len(result.black) == 1
    assert abs(result.black[0].start_us - 2_400_000) <= frame
    assert abs(result.black[0].end_us - 3_400_000) <= frame
    assert len(result.shots) == 3
    assert IDENTITY.scene_threshold == 10


class FakeDetector:
    identity = IDENTITY_FIXTURE

    def __init__(self, change: Path | None = None) -> None:
        self.change = change
        self.calls = 0

    async def tool_version(self, context: CancellationContext) -> str:
        return "ffmpeg fixture"

    async def samples(self, media: MediaAsset, context: CancellationContext) -> ShotSamples:
        self.calls += 1
        if self.change is not None:
            self.change.write_bytes(b"changed while scanning")
        return ShotSamples((CutCandidate(1_500_000, 20.0),), (), 0)


def test_cli_writes_a_new_report_without_touching_the_project(tmp_path) -> None:
    project, bundles = seed_tasks(tmp_path / "artifacts", 1)
    before = snapshot(project)
    output = tmp_path / "reports" / "shots.json"
    report = asyncio.run(execute_detect_shots(project, "run-000", output, FakeDetector()))
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == report and saved["runId"] == "run-000"
    assert saved["sourceSha256"] == bundles[0].asset.sha256
    assert saved["summary"]["cuts"] == 1 and saved["events"] == []
    assert snapshot(project) == before
    with pytest.raises(AppError, match="新的文件"):
        asyncio.run(execute_detect_shots(project, "run-000", output, FakeDetector()))
    with pytest.raises(AppError, match="项目目录"):
        asyncio.run(
            execute_detect_shots(project, "run-000", project / "shots.json", FakeDetector())
        )
    footage = bundles[0].asset.source_path.parent
    with pytest.raises(AppError, match="原片所在目录"):
        asyncio.run(
            execute_detect_shots(
                project, "run-000", footage / "reports" / "shots.json", FakeDetector()
            )
        )


def test_cli_refuses_a_source_that_changed_before_or_during_the_scan(tmp_path) -> None:
    project, bundles = seed_tasks(tmp_path / "artifacts", 1)
    source = bundles[0].asset.source_path
    during = FakeDetector(change=source)
    with pytest.raises(AppError) as changed:
        asyncio.run(execute_detect_shots(project, "run-000", tmp_path / "a.json", during))
    assert changed.value.code == "input.source_changed" and during.calls == 1
    assert not (tmp_path / "a.json").exists()
    before = FakeDetector()
    with pytest.raises(AppError):
        asyncio.run(execute_detect_shots(project, "run-000", tmp_path / "b.json", before))
    assert before.calls == 0


def test_cli_command_is_registered(capsys) -> None:
    assert main(["detect-shots", "--help"]) == 0
    assert "--run" in capsys.readouterr().out
