"""Production CLI assembly for the read-only local shot-boundary report."""

from collections.abc import Callable
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.shot_boundaries import (
    ShotDetector,
    build_shot_report,
    shot_summary,
)
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.cli.local_reports import (
    load_saved_timeline,
    publish_new_report,
    refuse_report_output,
    require_unchanged_source,
)
from gamingcreator.domain.time import SourceInstant

_SOURCE_CHANGED = "原片已不在原位置或内容已改变，未生成镜头报告。"


def saved_frames(timeline: StoredTimeline) -> tuple[tuple[str, int], ...]:
    """The run's saved images as (evidence id, source instant)."""
    return tuple(
        (item.evidence_id, item.source_time.time_us)
        for item in timeline.evidence
        if item.kind == "image" and isinstance(item.source_time, SourceInstant)
    )


async def build_run_shot_report(
    project: Path,
    run_id: str,
    detector: ShotDetector,
    *,
    before_scan: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    """Scan the run's original footage locally; reads the project read-only, writes nothing.

    ``before_scan`` receives the source path once the run is loaded, before any decoding.
    """
    timeline = await load_saved_timeline(project, run_id)
    asset = timeline.run.asset
    if before_scan is not None:
        before_scan(asset.source_path)
    context = CancellationContext("detect-shots", 600 + 2 * asset.duration_us / 1_000_000)
    await require_unchanged_source(asset, context, _SOURCE_CHANGED)
    version = await detector.tool_version(context)
    samples = await detector.samples(asset, context)
    await require_unchanged_source(asset, context, _SOURCE_CHANGED)
    return build_shot_report(
        timeline.run,
        timeline.events,
        samples,
        detector.identity,
        version,
        frames=saved_frames(timeline),
        checkpoints=timeline.checkpoints,
    )


async def execute_detect_shots(
    project: Path, run_id: str, output: Path, detector: ShotDetector
) -> dict[str, object]:
    """CLI: scan the run's footage and save the report to one new file."""
    report = await build_run_shot_report(
        project,
        run_id,
        detector,
        before_scan=lambda source: refuse_report_output(output, project, source),
    )
    target = publish_new_report(output, report)
    for line in shot_summary(report):
        print(line)
    print(f"报告已保存：{target}")
    return report
