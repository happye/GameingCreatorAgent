import argparse
import asyncio
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never, cast
from uuid import uuid4

from gamingcreator import __version__
from gamingcreator.application.analysis import (
    AnalysisPorts,
    AnalyzeOutcome,
    resume_analysis,
    run_new_analysis,
)
from gamingcreator.application.asr import LocalAsrSettings, ModelFile
from gamingcreator.application.budget import BudgetLedger, InvocationRecorder
from gamingcreator.application.inputs import AnalyzeInput, PreparedAnalyze, prepare_analyze
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError, ExitCode, invalid_config
from gamingcreator.infrastructure.deepseek_vision import MODEL, DeepSeekVisionProvider
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.http_transport import HttpxVisionTransport
from gamingcreator.infrastructure.local_asr import LocalAsrProvider
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


class CliParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise AppError("input.arguments", "参数格式错误，请使用 --help 查看命令。", ExitCode.INPUT)


def _parser() -> CliParser:
    parser = CliParser(prog="gamingcreator", description="本地游戏素材分析与检索开发工具")
    parser.add_argument("--version", action="version", version=f"gamingcreator {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="分析本地视频")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--project", type=Path, required=True)
    analyze.add_argument("--config", type=Path)
    analyze.add_argument("--max-cost-cny")
    analyze.add_argument("--resume")
    search = commands.add_parser("search", help="查询时间线（检索链路待实现）")
    search.add_argument("query")
    search.add_argument("--project", type=Path, required=True)
    search.add_argument("--run", required=True)
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--format", choices=("json",), default="json")
    benchmark = commands.add_parser("benchmark", help="执行人工标签评测（待实现）")
    benchmark.add_argument("--input", type=Path, required=True)
    benchmark.add_argument("--project", type=Path, required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    return parser


def _require_space(project: Path) -> None:
    anchor = project
    while not anchor.exists():
        parent = anchor.parent
        if parent == anchor:
            break
        anchor = parent
    try:
        free = shutil.disk_usage(anchor).free
    except OSError:
        raise AppError(
            "environment.disk", "无法检查项目所在磁盘的可用空间。", ExitCode.ENVIRONMENT
        ) from None
    if free <= 0:
        raise AppError("environment.disk", "项目所在磁盘没有可用空间。", ExitCode.ENVIRONMENT)


def _pinned_asr_settings(repository: Path) -> LocalAsrSettings:
    repository = repository.resolve()
    try:
        pin_raw: object = json.loads(
            (repository / "docs/references/asr-models.json").read_text(encoding="utf-8")
        )
        native_raw: object = json.loads(
            (repository / "docs/references/asr-native-toolchain.json").read_text(encoding="utf-8")
        )
        if not isinstance(pin_raw, dict) or not isinstance(native_raw, dict):
            raise ValueError
        pin = cast(dict[str, object], pin_raw)
        native = cast(dict[str, object], native_raw)
        file_rows, library_rows = pin["files"], native["files"]
        version, model, revision = native["version"], pin["model"], pin["revision"]
        if (
            not isinstance(file_rows, list)
            or not isinstance(library_rows, dict)
            or not isinstance(version, str)
            or not isinstance(model, str)
            or not isinstance(revision, str)
        ):
            raise ValueError
        model_files: list[ModelFile] = []
        for item in file_rows:
            if not isinstance(item, dict):
                raise ValueError
            row = cast(dict[str, object], item)
            name, size, digest = row["name"], row["size"], row["sha256"]
            if not isinstance(name, str) or type(size) is not int or not isinstance(digest, str):
                raise ValueError
            model_files.append(ModelFile(name, size, digest))
        native_directory = repository / ".tools" / "native" / "msvc" / version
        libraries: list[ModelFile] = []
        for name, digest in cast(dict[object, object], library_rows).items():
            if not isinstance(name, str) or not isinstance(digest, str):
                raise ValueError
            libraries.append(ModelFile(name, (native_directory / name).stat().st_size, digest))
        return LocalAsrSettings(
            repository / ".cache" / "models" / "faster-whisper" / "tiny" / revision,
            model,
            revision,
            tuple(model_files),
            native_directory,
            native_library_files=tuple(libraries),
        )
    except (OSError, ValueError, KeyError, TypeError):
        raise AppError(
            "environment.asr", "本地 ASR 模型清单不可用。", ExitCode.ENVIRONMENT
        ) from None


def vision_for_run(recorder: InvocationRecorder, budget: BudgetLedger) -> DeepSeekVisionProvider:
    # No price snapshot is configured. The ledger refuses the reservation before HTTP.
    return DeepSeekVisionProvider(HttpxVisionTransport(), budget, None, recorder)


async def execute_analyze(prepared: PreparedAnalyze, repository: Path) -> AnalyzeOutcome:
    project = prepared.project.resolve()
    _require_space(project)
    if prepared.resume is not None:
        if not (project / "timeline.sqlite3").is_file():
            raise AppError("input.resume", "找不到可续跑的项目。", ExitCode.INPUT)
        store = await SqliteTimelineStore.open(project)
        try:
            try:
                stored = await store.load_run(prepared.resume)
            except AppError as error:
                raise AppError(
                    error.code, error.message, error.exit_code, prepared.resume
                ) from error
            ports = None
            if stored.status in (RunStatus.PENDING, RunStatus.RUNNING):
                if stored.asset.source_path.resolve() != prepared.video.resolve():
                    raise AppError(
                        "input.resume", "续跑视频与原运行不一致。", ExitCode.INPUT, prepared.resume
                    )
                stored_config = stored.configuration.analysis
                if stored_config.provider != "deepseek" or stored_config.model != MODEL:
                    raise invalid_config()
                ledger = BudgetLedger(
                    stored.configuration.max_cost_cny,
                    stored_config.max_requests,
                    stored_config.max_input_frames,
                )
                ports = AnalysisPorts(
                    FfmpegMediaProcessor(repository),
                    LocalAsrProvider(repository, _pinned_asr_settings(repository)),
                    vision_for_run(store, ledger),
                    store,
                )
            return await resume_analysis(prepared, store, project, ports)
        finally:
            await store.close()
    config, budget = prepared.config, prepared.max_cost_cny
    if config is None or budget is None or config.provider != "deepseek" or config.model != MODEL:
        raise invalid_config()
    asset = await FfmpegMediaProcessor(repository).probe(
        prepared.video, CancellationContext("probe", 120)
    )
    asr_settings = _pinned_asr_settings(repository)
    store = await SqliteTimelineStore.open(project)
    try:
        ledger = BudgetLedger(budget, config.max_requests, config.max_input_frames)
        ports = AnalysisPorts(
            FfmpegMediaProcessor(repository),
            LocalAsrProvider(repository, asr_settings),
            vision_for_run(store, ledger),
            store,
        )
        return await run_new_analysis(prepared, ports, asset, project, run_id=uuid4().hex)
    finally:
        await store.close()


def _dispatch(args: argparse.Namespace) -> AnalyzeOutcome | None:
    if args.command == "analyze":
        prepared = prepare_analyze(
            AnalyzeInput(args.video, args.project, args.config, args.max_cost_cny, args.resume),
            LocalInputReader(),
        )
        return asyncio.run(execute_analyze(prepared, Path.cwd()))
    if args.command == "search" and (
        not args.query.strip() or not args.run.strip() or args.top_k <= 0
    ):
        raise AppError("input.search", "查询、运行 ID 与正数 top-k 均为必需。", ExitCode.INPUT)
    raise AppError("feature.not_implemented", "检索与评测链路尚未实现。", ExitCode.ENVIRONMENT)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        outcome = _dispatch(args)
    except SystemExit as error:
        return int(error.code) if isinstance(error.code, int) else int(ExitCode.INPUT)
    except KeyboardInterrupt:
        failure = AppError("operation.cancelled", "操作已取消。", ExitCode.CANCELLED)
    except AppError as error:
        failure = error
    except Exception:
        failure = AppError(
            "environment.unexpected", "无法完成操作，请检查本地运行环境。", ExitCode.ENVIRONMENT
        )
    else:
        if outcome is not None:
            print(
                json.dumps(
                    {
                        "runId": outcome.run_id,
                        "status": "completed",
                        "mediaId": outcome.media_id,
                        "eventCount": outcome.event_count,
                        "transcriptCount": outcome.transcript_count,
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    print(
        json.dumps(
            {
                "code": failure.code,
                "runId": failure.run_id,
                "retryable": False,
                "message": failure.message,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return int(failure.exit_code)
