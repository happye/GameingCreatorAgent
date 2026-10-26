"""Existing runs of the same video bytes and analysis settings (master plan section 52).

Within one project, a paid analysis of a recording that already has a run with identical
analysis settings would pay again for the same output. Callers look here before any
provider or budget ledger exists and stop unless the person explicitly asks for a fresh
run. The guidance follows the same continuation rules as the task list.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.storage import (
    RunConfiguration,
    RunStatus,
    StoredInvocation,
    TimelineStore,
)
from gamingcreator.application.tasks import task_payload
from gamingcreator.domain.errors import AppError, ExitCode

REUSE_REPORT_VERSION = "analysis-reuse-check-v1"
# Spending caps decide how far a run may go, not what it produces.
_CAP_FIELDS = ("max_requests", "max_input_frames")
_BLOCKERS = {
    "coverage_gap": "有覆盖缺口，等你决定如何处理（工作台“覆盖缺口”）",
    "material_integrity": "保存的素材完整性校验失败",
    "explicit_retry_required": "有费用未确认的调用，续跑须显式 --retry-uncertain",
    "legacy_stopped": "旧版任务已停止，不会重放",
    "coverage_limit": "保存的请求或帧上限不够覆盖全部窗口（续跑沿用原上限）",
    "unsupported_cli_provider": "任务使用的模型提供方命令行不支持续跑",
    "budget_exhausted": "费用上限已用完（续跑沿用原上限）",
}


def analysis_identity(
    analysis: AnalysisConfig, pipeline_hash: str, required_stages: Sequence[str]
) -> dict[str, object]:
    """Everything that shapes a run's output, without its spending caps or budget."""
    settings = asdict(analysis)
    for field in _CAP_FIELDS:
        settings.pop(field)
    if analysis.vision_prompt_version == "phase0-vision-v1":
        # The first runs predate prompt pinning and stored no hash for this fixed prompt.
        settings.pop("vision_prompt_hash")
    return {
        "analysis": settings,
        "pipelineHash": pipeline_hash,
        "requiredStages": list(required_stages),
    }


def paid_calls(invocations: Sequence[StoredInvocation]) -> int:
    """Remote model calls; local speech recognition never charges."""
    return sum(1 for item in invocations if item.metadata.provider == "deepseek")


def stored_identity(configuration: RunConfiguration) -> dict[str, object]:
    return analysis_identity(
        configuration.analysis, configuration.pipeline_hash, configuration.required_stages
    )


@dataclass(frozen=True, slots=True)
class ReuseMatch:
    run_id: str
    status: RunStatus
    same_settings: bool
    source_path: Path | None = None
    resumable: bool = False
    blockers: tuple[str, ...] = ()
    model_calls: int = 0
    error_code: str | None = None


async def find_matches(
    store: TimelineStore,
    source_sha256: str,
    wanted: dict[str, object],
    *,
    exclude: str | None = None,
) -> tuple[ReuseMatch, ...]:
    """Runs of the same source bytes, with settings match and continuation state.

    A run that cannot be read stops the caller: without it nobody can say whether the
    result was already paid for.
    """
    matches = []
    for run_id, _ in await store.list_runs():
        if run_id == exclude:
            continue
        try:
            run = await store.load_run(run_id)
            if run.asset.sha256 != source_sha256:
                continue
            page = await store.load_task_page(limit=1, run_id=run_id)
        except AppError as error:
            raise AppError(
                error.code,
                f"项目里的任务 {run_id} 无法读取（{error.message}），无法确认是否已付费分析过，"
                "已停止。修复后再试；确认不需要比对时加 --allow-reanalysis。",
                error.exit_code,
                run_id,
            ) from error
        snapshot = page.tasks[0]
        payload = task_payload(snapshot)
        blockers = tuple(str(item) for item in payload["continuationBlockers"])  # type: ignore[attr-defined]
        if run.error_code is not None and run.error_code.startswith("budget."):
            # Resume keeps the saved budget, so a run stopped by it stops again at once.
            blockers = (*blockers, "budget_exhausted")
        matches.append(
            ReuseMatch(
                run.run_id,
                run.status,
                stored_identity(run.configuration) == wanted,
                run.asset.source_path,
                payload["nextAction"] is not None and not blockers,
                blockers,
                paid_calls(snapshot.invocations),
                run.error_code,
            )
        )
    return tuple(sorted(matches, key=lambda item: item.run_id))


def _reasons(match: ReuseMatch) -> str:
    reasons = [_BLOCKERS.get(item, item) for item in match.blockers]
    if not reasons:
        reasons.append(f"状态为{match.status}，没有可续跑的下一步")
    return "；".join(reasons)


def refuse_duplicate_analysis(matches: Sequence[ReuseMatch], video: Path) -> None:
    """Stop a new paid run when one with the same bytes and settings already exists.

    A completed run is the result already paid for. An unfinished one is continued with
    ``--resume`` only when the task list says it can be; otherwise the reason is given.
    ``--allow-reanalysis`` skips this check.
    """
    same = [match for match in matches if match.same_settings]
    completed = [match for match in same if match.status == RunStatus.COMPLETED]
    if completed:
        raise AppError(
            "analysis.already_completed",
            f"这段录像已用相同设置分析完成（任务 {completed[0].run_id}），重新分析会再次付费。"
            "请直接检索这个任务；确实需要重新付费分析时加 --allow-reanalysis。",
            ExitCode.INPUT,
            completed[0].run_id,
        )
    # Runs that already paid for model work come first: advice never sends the person to
    # a free duplicate that the resume check would then refuse. Without any paid run, a
    # blocked free run (for example caps too small) is no reason to stop a new one.
    paid = [match for match in same if match.model_calls]
    same = paid or [match for match in same if match.resumable]
    if not same:
        return
    target = video.resolve()
    resumable = [match for match in same if match.resumable]
    here = [match for match in resumable if match.source_path == target]
    if here:
        raise AppError(
            "analysis.already_started",
            f"这段录像已有相同设置的未完成任务 {here[0].run_id}（{here[0].status}）。"
            f"请用 --resume {here[0].run_id} 续跑，已完成的部分不会重复付费；"
            "确实需要另起一次付费分析时加 --allow-reanalysis。",
            ExitCode.INPUT,
            here[0].run_id,
        )
    if resumable:
        raise AppError(
            "analysis.already_started",
            f"这段录像已有相同设置的未完成任务 {resumable[0].run_id}，但它记录的是另一路径的同一文件"
            f"（{resumable[0].source_path}）。把文件放回原位置后用 --resume {resumable[0].run_id} 续跑；"
            "确实需要另起一次付费分析时加 --allow-reanalysis。",
            ExitCode.INPUT,
            resumable[0].run_id,
        )
    raise AppError(
        "analysis.existing_unfinished",
        f"这段录像已有相同设置的任务 {same[0].run_id}，但不能直接续跑：{_reasons(same[0])}。"
        "请先在工作台“查看素材任务”看它的状态和待决定事项；确实要为全部窗口重新付费另起任务时加"
        " --allow-reanalysis。",
        ExitCode.INPUT,
        same[0].run_id,
    )


def refuse_resuming_duplicate(matches: Sequence[ReuseMatch], resume: str) -> None:
    """Stop a prepared run that has not paid for anything yet from repeating a paid result.

    Preparation is free and may create a second run of the same recording; continuing it
    would pay again when another run with the same settings already paid for model work.
    """
    paid = [
        match
        for match in matches
        if match.same_settings and (match.status == RunStatus.COMPLETED or match.model_calls)
    ]
    if paid:
        raise AppError(
            "analysis.duplicate_of_existing",
            f"这段录像已用相同设置在任务 {paid[0].run_id}（{paid[0].status}）里付费分析过；"
            f"继续尚未付费的任务 {resume} 会为同样的结果再付一次钱。请改用任务 {paid[0].run_id}；"
            "确实需要时加 --allow-reanalysis。",
            ExitCode.INPUT,
            resume,
        )


def reuse_report(
    source_name: str,
    source_sha256: str,
    video: Path,
    matches: Sequence[ReuseMatch],
) -> dict[str, object]:
    """Read-only answer to "would analyze stop, and which runs already exist?"."""
    try:
        refuse_duplicate_analysis(matches, video)
    except AppError as error:
        verdict: dict[str, object] = {
            "wouldStop": True,
            "code": error.code,
            "message": error.message,
        }
    else:
        verdict = {"wouldStop": False, "code": None, "message": "没有相同录像与相同设置的任务。"}

    def row(match: ReuseMatch) -> dict[str, object]:
        return {
            "runId": match.run_id,
            "status": str(match.status),
            "resumable": match.resumable,
            "continuationBlockers": list(match.blockers),
            "modelCalls": match.model_calls,
        }

    return {
        "schemaVersion": REUSE_REPORT_VERSION,
        "sourceName": source_name,
        "sourceSha256": source_sha256,
        "sameSettings": [row(match) for match in matches if match.same_settings],
        "otherSettings": [row(match) for match in matches if not match.same_settings],
        **verdict,
        "scope": "this project only",
        "readOnly": True,
        "paidRequests": 0,
    }
