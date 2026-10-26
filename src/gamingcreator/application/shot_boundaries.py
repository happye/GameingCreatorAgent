"""Read-only shot-boundary report for one saved run; never changes analysis or ranking."""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from typing import Protocol

from gamingcreator.application.analysis import window_input_hash, window_slices
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import StageCheckpoint, StoredRun
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.shot_boundaries import (
    BlackTransition,
    CutCandidate,
    ShotBoundaries,
    ShotParameters,
    detect_shot_boundaries,
    frames_span_cut,
    span_report,
)

SHOT_REPORT_VERSION = "shot-boundaries-v1"


@dataclass(frozen=True, slots=True)
class ShotDetectorIdentity:
    detector: str
    filter_graph: str
    scene_threshold: int
    black_pixel_threshold: str


@dataclass(frozen=True, slots=True)
class ShotSamples:
    cuts: tuple[CutCandidate, ...]
    transitions: tuple[BlackTransition, ...]
    frames_outside_media: int


class ShotDetector(Protocol):
    identity: ShotDetectorIdentity

    async def tool_version(self, context: CancellationContext) -> str: ...

    async def samples(self, asset: MediaAsset, context: CancellationContext) -> ShotSamples: ...


def _window_rows(
    run: StoredRun,
    frames: tuple[tuple[str, int], ...],
    checkpoints: tuple[StageCheckpoint, ...],
    boundaries: ShotBoundaries,
) -> list[dict[str, object]] | None:
    """Vision windows rebuilt from the saved frames, or None for a run without windows.

    Each row carries its saved stage status, and whether the rebuilt frame list hashes to
    the input the stage recorded (so a rebuilt window provably is the window that was sent).
    """
    config = run.configuration.analysis
    if config.schema_version != 2:
        return None
    ordered = sorted(frames, key=lambda item: (item[1], item[0]))
    stages = {item.stage_id: item for item in checkpoints}
    rows: list[dict[str, object]] = []
    for index, window in enumerate(window_slices(len(ordered), config)):
        selected = ordered[window]
        times = [time for _, time in selected]
        stage_id = f"vision-{index:06d}"
        stage = stages.get(stage_id)
        rows.append(
            {
                "window": index,
                "stageId": stage_id,
                "stageStatus": None if stage is None else str(stage.status),
                "inputMatchesStage": None
                if stage is None
                else stage.input_hash == window_input_hash([key for key, _ in selected]),
                "firstFrameUs": times[0],
                "lastFrameUs": times[-1],
                "frames": len(times),
                "cutsBetweenFrames": frames_span_cut(times[0], times[-1], boundaries),
                "blackFrames": sum(
                    1
                    for time in times
                    if any(item.start_us <= time < item.end_us for item in boundaries.black)
                ),
            }
        )
    return rows


def shot_timeline_digest(
    run: StoredRun,
    events: tuple[SemanticEvent, ...],
    frames: tuple[tuple[str, int], ...],
    checkpoints: tuple[StageCheckpoint, ...],
) -> str:
    """Identity of the saved analysis a report describes; it changes when analysis moves on."""
    payload = {
        "status": str(run.status),
        "events": sorted(
            (item.event_id, item.source_range.start_us, item.source_range.end_us) for item in events
        ),
        "frames": sorted(frames),
        "stages": sorted(
            (item.stage_id, str(item.status), item.input_hash) for item in checkpoints
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def build_shot_report(
    run: StoredRun,
    events: tuple[SemanticEvent, ...],
    samples: ShotSamples,
    identity: ShotDetectorIdentity,
    tool_version: str,
    parameters: ShotParameters | None = None,
    *,
    frames: tuple[tuple[str, int], ...] = (),
    checkpoints: tuple[StageCheckpoint, ...] = (),
) -> dict[str, object]:
    """Cuts, black intervals and shots on the source clock, plus each saved event's span.

    ``frames`` are the run's saved images as (evidence id, source instant); vision windows
    are rebuilt from them with the run's own window settings and matched to ``checkpoints``.
    """
    settings = parameters or ShotParameters()
    asset = run.asset
    boundaries = detect_shot_boundaries(
        samples.cuts, samples.transitions, asset.duration_us, settings
    )
    rows: list[dict[str, object]] = []
    for event in sorted(events, key=lambda item: (item.source_range.start_us, item.event_id)):
        span = span_report(event.source_range, boundaries)
        rows.append(
            {
                "eventId": event.event_id,
                "startUs": event.source_range.start_us,
                "endUs": event.source_range.end_us,
                "cutsInside": span.cuts_inside,
                "shotsTouched": span.shots_touched,
                "blackOverlapUs": span.black_overlap_us,
                "crossesCut": span.cuts_inside > 0,
            }
        )
    windows = _window_rows(run, frames, checkpoints, boundaries)
    spanning = [row for row in windows or [] if row["cutsBetweenFrames"]]
    shot_lengths = [item.end_us - item.start_us for item in boundaries.shots]
    black_total = sum(item.end_us - item.start_us for item in boundaries.black)
    return {
        "schemaVersion": SHOT_REPORT_VERSION,
        "runId": run.run_id,
        "runStatus": str(run.status),
        "mediaId": asset.media_id,
        "sourceName": asset.source_path.name,
        "sourceSha256": asset.sha256,
        "durationUs": asset.duration_us,
        "detector": {
            "name": identity.detector,
            "tool": tool_version,
            "filterGraph": identity.filter_graph,
            "sceneThreshold": identity.scene_threshold,
            "blackPixelThreshold": identity.black_pixel_threshold,
            "minShotUs": settings.min_shot_us,
            "flashUs": settings.flash_us,
            "minBlackUs": settings.min_black_us,
        },
        "summary": {
            "cutCandidates": len(samples.cuts),
            "cuts": len(boundaries.cuts),
            "flashCandidatesDropped": boundaries.flashes_dropped,
            "closeCutsDropped": boundaries.close_cuts_dropped,
            "shots": len(boundaries.shots),
            "medianShotUs": int(statistics.median(shot_lengths)) if shot_lengths else None,
            "blackIntervals": len(boundaries.black),
            "blackTotalUs": black_total,
            "framesOutsideMedia": samples.frames_outside_media,
            "events": len(rows),
            "eventsCrossingCut": sum(1 for row in rows if row["crossesCut"]),
            "eventsWithBlack": sum(1 for row in rows if row["blackOverlapUs"]),
            "windows": None if windows is None else len(windows),
            "windowsStarted": None
            if windows is None
            else sum(1 for row in windows if row["stageStatus"] is not None),
            "windowInputMismatches": None
            if windows is None
            else sum(1 for row in windows if row["inputMatchesStage"] is False),
            "windowsSpanningCut": None if windows is None else len(spanning),
            "windowsWithBlackFrames": None
            if windows is None
            else sum(1 for row in windows if row["blackFrames"]),
        },
        "cuts": [{"timeUs": item.time_us, "score": item.score} for item in boundaries.cuts],
        "blackIntervals": [
            {"startUs": item.start_us, "endUs": item.end_us} for item in boundaries.black
        ],
        "shots": [{"startUs": item.start_us, "endUs": item.end_us} for item in boundaries.shots],
        "events": rows,
        "windowsSpanningCut": spanning,
        "timelineDigest": shot_timeline_digest(run, events, frames, checkpoints),
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
        "notes": (
            "本地画面变化启发式（FFmpeg镜头切换分数与黑屏检测），未经人工核对；"
            "只读原片与已保存事件，不改变分析结果、检索排名或验收结论。"
        ),
    }


def shot_summary(report: dict[str, object]) -> list[str]:
    """Plain-language lines for the console."""
    summary, duration = report["summary"], report["durationUs"]
    assert isinstance(summary, dict) and type(duration) is int
    lines = [
        f"素材：{report['sourceName']}（{duration / 1_000_000:.1f}秒）",
        f"镜头切换 {summary['cuts']} 处，镜头 {summary['shots']} 段，"
        f"黑屏 {summary['blackIntervals']} 段共 {int(summary['blackTotalUs']) / 1_000_000:.1f}秒",
    ]
    if summary["events"]:
        lines.append(
            f"已保存事件 {summary['events']} 个：其中 {summary['eventsCrossingCut']} 个跨越镜头切换，"
            f"{summary['eventsWithBlack']} 个含黑屏"
        )
    else:
        lines.append("该任务没有已保存事件，只给出镜头切分。")
    if summary["windows"] is not None:
        lines.append(
            f"多帧分析窗口 {summary['windows']} 个（已开始分析 {summary['windowsStarted']} 个）："
            f"其中 {summary['windowsSpanningCut']} 个的画面来自不同镜头，"
            f"{summary['windowsWithBlackFrames']} 个含黑屏帧"
        )
        if summary["windowInputMismatches"]:
            lines.append(
                f"注意：{summary['windowInputMismatches']} 个窗口与保存的分析输入不一致，"
                "这些窗口的跨镜头判断不可靠。"
            )
    lines.append("这是本地启发式结果，未经人工核对；不改变分析、排名或验收。")
    return lines
