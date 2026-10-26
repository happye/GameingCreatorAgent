"""Production CLI assembly for the read-only local on-screen text report."""

import shutil
from collections.abc import Callable, Sequence
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from gamingcreator.application.ocr_frames import (
    DEFAULT_LANGUAGES,
    FullResolutionFrames,
    OcrEngine,
    build_ocr_report,
    matched_frames,
    ocr_summary,
)
from gamingcreator.application.providers import CancellationContext
from gamingcreator.cli.local_reports import (
    load_saved_timeline,
    publish_new_report,
    refuse_report_output,
    require_unchanged_source,
)
from gamingcreator.cli.shot_boundaries import saved_frames
from gamingcreator.domain.errors import AppError, ExitCode

_SOURCE_CHANGED = "原片已不在原位置或内容已改变，未生成文字识别报告。"
MAX_EVERY = 1000


async def build_run_ocr_report(
    project: Path,
    run_id: str,
    frames: FullResolutionFrames,
    engine: OcrEngine,
    scratch: Path,
    *,
    every: int = 1,
    languages: Sequence[str] = DEFAULT_LANGUAGES,
    before_scan: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    """Re-extract the run's sampled frames at native resolution and read their text locally.

    The project is opened read-only; images live only in a scratch directory that is
    removed afterwards. Re-extracted instants must equal the saved evidence instants.
    """
    if type(every) is not int or not 1 <= every <= MAX_EVERY:
        raise AppError("input.ocr", f"--every须为1–{MAX_EVERY}的整数。", ExitCode.INPUT)
    if not languages or len({item.casefold() for item in languages}) != len(languages):
        raise AppError("input.ocr", "识别语言须至少一个且不重复。", ExitCode.INPUT)
    timeline = await load_saved_timeline(project, run_id)
    asset = timeline.run.asset
    saved = saved_frames(timeline)
    if not saved:
        raise AppError("input.ocr", "该任务没有保存的取帧，无法识别文字。", ExitCode.INPUT)
    if before_scan is not None:
        before_scan(asset.source_path)
    work = scratch.resolve()
    if project.resolve() in (work, *work.parents) or asset.source_path.resolve().parent in (
        work,
        *work.parents,
    ):
        raise AppError(
            "input.ocr", "临时画面目录不能放在项目目录或原片所在目录里。", ExitCode.INPUT
        )
    interval = Fraction(timeline.run.configuration.analysis.sampling_interval_ms, 1000)
    context = CancellationContext("ocr-frames", 900 + 2 * len(saved))
    workspace = scratch / f"ocr-frames-{uuid4().hex}"
    seconds: dict[str, float] = {}
    try:
        started = perf_counter()
        await require_unchanged_source(asset, context, _SOURCE_CHANGED)
        extracted = await frames.extract(asset, interval, len(saved), workspace, context)
        await require_unchanged_source(asset, context, _SOURCE_CHANGED)
        paired = matched_frames(asset, saved, extracted)[::every]
        seconds["extract"] = round(perf_counter() - started, 3)
        started = perf_counter()
        batch = await engine.recognize([image for _, _, image in paired], languages, context)
        # Windows matches language tags without case; report them as Windows spells them.
        spelled = {item.casefold(): item for item in batch.available_languages}
        languages = tuple(spelled.get(item.casefold(), item) for item in languages)
        seconds["recognize"] = round(perf_counter() - started, 3)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    if not any(language in batch.available_languages for language in languages):
        raise AppError(
            "environment.ocr_unavailable",
            "本机没有所选语言的文字识别能力（不会自动下载或安装）。",
            ExitCode.ENVIRONMENT,
        )
    return build_ocr_report(
        timeline.run,
        [(evidence, time) for evidence, time, _ in paired],
        batch,
        engine.identity(),
        languages,
        every=every,
        seconds=seconds,
    )


async def execute_ocr_frames(
    project: Path,
    run_id: str,
    output: Path,
    frames: FullResolutionFrames,
    engine: OcrEngine,
    scratch: Path,
    *,
    every: int = 1,
    languages: Sequence[str] = DEFAULT_LANGUAGES,
) -> dict[str, object]:
    """CLI: read on-screen text of the run's frames and save the report to one new file."""
    report = await build_run_ocr_report(
        project,
        run_id,
        frames,
        engine,
        scratch,
        every=every,
        languages=languages,
        before_scan=lambda source: refuse_report_output(output, project, source),
    )
    target = publish_new_report(output, report)
    for line in ocr_summary(report):
        print(line)
    print(f"报告已保存：{target}")
    return report
