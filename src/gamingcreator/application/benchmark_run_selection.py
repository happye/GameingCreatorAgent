"""Read-only metadata choices for an existing frozen benchmark; no media verification."""

from collections.abc import Sequence
from pathlib import PureWindowsPath
from typing import cast

from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.storage import RunStatus, StoredRun

VERSION = "benchmark-bind-options-v1"
LABELS = {
    "phase0-vision-v1": "画面观察 V1",
    "phase0-vision-v2": "画面观察 V2",
    "phase0-vision-v3": "连续动作 V3",
    "phase0-vision-v4": "连续动作 V4",
    "phase0-vision-v5": "主体细节 V5",
    "phase0-vision-v6": "主体细节与动作 V6",
}


def binding_choices(
    frozen: dict[str, object], runs: Sequence[StoredRun], partition: str
) -> list[dict[str, object]]:
    """Only queried sources in the declared partition, with explicit version choices."""
    if partition not in {"development", "test"}:
        raise ValueError("请明确选择这次评估用途。")
    plan = loads_plan(canonical_json(frozen["plan"]).decode())
    queried = {row["sourceId"] for row in cast(list[dict[str, object]], plan.document["queries"])}
    selected = [
        source
        for source in plan.sources
        if source.partition == partition and source.source_id in queried
    ]
    if not selected:
        raise ValueError("这个用途没有已冻结的事前查询，不会自动改录像用途。")
    sources = {
        cast(str, row["id"]): row for row in cast(list[dict[str, object]], frozen["sources"])
    }
    hashes = [sources[source.source_id]["sha256"] for source in selected]
    rows = []
    for source in selected:
        original = sources[source.source_id]
        duplicate = hashes.count(original["sha256"]) > 1
        candidates = []
        for run in sorted(runs, key=lambda run: run.run_id):
            if run.asset.sha256 != original["sha256"]:
                continue
            complete = run.status == RunStatus.COMPLETED
            duration_matches = run.asset.duration_us == original["durationUs"]
            reason = (
                "同一录像在所选用途里重复登记，请先核对计划。"
                if duplicate
                else "分析尚未完成，不能用于检索验收。"
                if not complete
                else "保存时长与冻结原片不同，不能关联。"
                if not duration_matches
                else None
            )
            config = run.configuration.analysis
            candidates.append(
                {
                    "runId": run.run_id,
                    "status": str(run.status),
                    "selectable": reason is None,
                    "reason": reason,
                    "analysisLabel": LABELS.get(config.vision_prompt_version, "其他已保存分析"),
                    "model": config.model,
                    "promptVersion": config.vision_prompt_version,
                    "configHash": run.config_hash,
                    "pipelineVersion": run.configuration.pipeline_version,
                    "durationUs": run.asset.duration_us,
                }
            )
        rows.append(
            {
                "sourceId": source.source_id,
                "sourceName": PureWindowsPath(cast(str, original["path"])).name,
                "sourceSha256": original["sha256"],
                "durationUs": original["durationUs"],
                "recordingGroup": source.recording_group,
                "modelResultsViewed": source.results_viewed,
                "candidates": candidates,
                "duplicateSource": duplicate,
            }
        )
    return rows
