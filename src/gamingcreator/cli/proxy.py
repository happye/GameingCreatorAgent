"""make-proxy: build (or reuse) low-resolution editing proxies for one or many runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.proxy_batch import make_proxies_for_runs
from gamingcreator.infrastructure.proxy_media import make_proxy
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def execute_make_proxy(project: Path, run_id: str, repository: Path) -> None:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        asset = (await store.load_run(run_id)).asset
    finally:
        await store.close()
    try:
        receipt = await make_proxy(
            repository,
            asset.source_path,
            asset.sha256,
            asset.duration_us,
            CancellationContext(f"proxy-{run_id}", 6 * 3600),
        )
    except ValueError as error:
        # e.g. byte budget reached or source bytes changed: say which, not a generic failure.
        raise AppError("proxy.failed", f"代理预览未生成：{error}", ExitCode.INPUT) from error
    except OSError as error:
        raise AppError(
            "proxy.failed",
            f"代理预览未生成：读不到登记的原录像（{error}）",
            ExitCode.INPUT,
        ) from error
    sys.stdout.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")


async def execute_make_proxy_batch(
    project: Path,
    repository: Path,
    runs: list[str] | None,
    *,
    all_eligible: bool,
) -> None:
    if all_eligible and runs:
        raise AppError(
            "input.proxy_batch",
            "不能同时指定 --run 与 --all-eligible。",
            ExitCode.INPUT,
        )
    if not all_eligible and not runs:
        raise AppError(
            "input.proxy_batch",
            "请提供至少一个 --run，或使用 --all-eligible。",
            ExitCode.INPUT,
        )
    run_ids: list[str] | None = None if all_eligible else list(runs or [])
    report = await make_proxies_for_runs(project, repository, run_ids)
    if not report["items"]:
        raise AppError(
            "input.proxy_batch",
            "没有可生成编辑代理的任务（项目里没有合格的已准备／已分析录像）。",
            ExitCode.INPUT,
        )
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    failed = int(report["summary"]["failed"])
    if failed and failed == len(report["items"]):
        raise AppError(
            "proxy.failed",
            f"批量代理全部失败（{failed} 条）。",
            ExitCode.INPUT,
        )