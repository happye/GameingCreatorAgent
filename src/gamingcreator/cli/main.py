import argparse
import asyncio
import json
import shutil
import sys
from collections.abc import Sequence
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from time import perf_counter
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
from gamingcreator.application.benchmark import (
    BenchmarkCosts,
    BenchmarkHit,
    BenchmarkMedia,
    BenchmarkQuery,
    JsonValue,
    loads_manifest,
    run_benchmark,
)
from gamingcreator.application.budget import BudgetLedger, InvocationRecorder
from gamingcreator.application.inputs import AnalyzeInput, PreparedAnalyze, prepare_analyze
from gamingcreator.application.observation_text import FACTS_PROJECTION_VERSION, display_facts
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, CostStatus
from gamingcreator.application.retrieval import (
    RETRIEVAL_VERSION,
    RetrievalMode,
    SearchResult,
    search_timeline,
)
from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError, ExitCode, invalid_config
from gamingcreator.infrastructure.deepseek_vision import (
    MODEL,
    DeepSeekVisionProvider,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.http_transport import HttpxVisionTransport
from gamingcreator.infrastructure.local_asr import LocalAsrProvider
from gamingcreator.infrastructure.local_embeddings import LocalEmbeddingProvider
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
    analyze.add_argument(
        "--retry-uncertain",
        action="store_true",
        help="显式允许重试费用未确认的未完成窗口，预留费用继续计入原预算",
    )
    search = commands.add_parser("search", help="用自然语言检索已完成的时间线")
    search.add_argument("query")
    search.add_argument("--project", type=Path, required=True)
    search.add_argument("--run", required=True)
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--format", choices=("json",), default="json")
    search.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="hybrid")
    search.add_argument("--min-similarity", type=float, default=0.80)
    benchmark = commands.add_parser("benchmark", help="执行冻结人工标签评测")
    benchmark.add_argument("--input", type=Path, required=True)
    benchmark.add_argument("--project", type=Path, required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    benchmark.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="hybrid")
    benchmark.add_argument("--min-similarity", type=float, default=0.80)
    return parser


def _timecode(microseconds: int) -> str:
    milliseconds = microseconds // 1000
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def _search_document(result: SearchResult, elapsed_ms: int) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "runId": result.run_id,
        "query": result.query,
        "mode": result.mode,
        "retrievalVersion": result.retrieval_version,
        "factsProjectionVersion": FACTS_PROJECTION_VERSION,
        "minSimilarity": result.min_similarity,
        "minSemanticMargin": result.min_semantic_margin,
        "abstentionReason": result.abstention_reason,
        "elapsedMs": elapsed_ms,
        "scoreIsProbability": False,
        "embedding": json.loads(json.dumps(asdict(result.embedding_metadata), default=str))
        if result.embedding_metadata
        else None,
        "candidates": [
            {
                "rank": rank,
                "candidateId": item.candidate_id,
                "eventId": item.event_id,
                "mediaId": item.media_id,
                "startUs": item.source_range.start_us,
                "endUs": item.source_range.end_us,
                "startTimecode": _timecode(item.source_range.start_us),
                "endTimecode": _timecode(item.source_range.end_us),
                "score": item.score,
                "scoreKind": item.score_kind,
                "evidenceIds": list(item.evidence_ids),
                "observableFacts": list(item.observable_facts),
                "displayFacts": list(display_facts(item.observable_facts)),
                "why": item.why,
            }
            for rank, item in enumerate(result.candidates, 1)
        ],
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _require_project(project: Path) -> None:
    if not (project / "timeline.sqlite3").is_file():
        raise AppError("input.project", "找不到已分析的项目数据库。", ExitCode.INPUT)


async def execute_search(
    project: Path,
    run_id: str,
    query: str,
    repository: Path,
    *,
    top_k: int = 10,
    mode: RetrievalMode = "hybrid",
    min_similarity: float = 0.80,
) -> dict[str, object]:
    _require_project(project)
    store = await SqliteTimelineStore.open(project)
    try:
        timeline = await store.load_completed_timeline(run_id)
        provider = LocalEmbeddingProvider.from_manifest(repository) if mode != "lexical" else None
        started = perf_counter()
        result = await search_timeline(
            timeline,
            query,
            top_k=top_k,
            mode=mode,
            embedding_provider=provider,
            min_similarity=min_similarity,
        )
        document = _search_document(result, round((perf_counter() - started) * 1000))
        document["retrievalId"] = await store.persist_search(
            result,
            document,
            elapsed_ms=cast(int, document["elapsedMs"]),
            top_k=top_k,
            embedding_space=provider.space if provider else None,
        )
        _write_json(project / "runs" / run_id / "searches" / (uuid4().hex + ".json"), document)
        return document
    finally:
        await store.close()


async def execute_benchmark(
    project: Path,
    input_path: Path,
    output_path: Path,
    repository: Path,
    *,
    mode: RetrievalMode = "hybrid",
    min_similarity: float = 0.80,
) -> dict[str, JsonValue]:
    _require_project(project)
    try:
        manifest = loads_manifest(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise AppError("input.benchmark", "评测清单不符合冻结标签合同。", ExitCode.INPUT) from None
    store = await SqliteTimelineStore.open(project)
    try:
        provider = LocalEmbeddingProvider.from_manifest(repository) if mode != "lexical" else None

        async def verify(media: BenchmarkMedia) -> None:
            source = media
            timeline = await store.load_completed_timeline(source.run_id)
            asset = timeline.run.asset
            if (asset.media_id, asset.sha256, asset.duration_us) != (
                source.media_id,
                source.sha256,
                source.duration_us,
            ):
                raise ValueError("Benchmark source mismatch.")

        async def search(query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]:
            timeline = await store.load_completed_timeline(query.run_id)
            began = perf_counter()
            result = await search_timeline(
                timeline,
                query.text,
                mode=mode,
                embedding_provider=provider,
                min_similarity=min_similarity,
            )
            elapsed = round((perf_counter() - began) * 1000)
            await store.persist_search(
                result,
                _search_document(result, elapsed),
                elapsed_ms=elapsed,
                top_k=10,
                embedding_space=provider.space if provider else None,
            )
            return tuple(
                BenchmarkHit(
                    item.event_id or item.candidate_id,
                    item.source_range.start_us,
                    item.source_range.end_us,
                    rank,
                )
                for rank, item in enumerate(result.candidates, 1)
            )

        cold = Decimal(0)
        known = True
        versions: set[str] = set()
        provenance: list[JsonValue] = []
        for source in manifest.media:
            try:
                timeline = await store.load_completed_timeline(source.run_id)
                provenance.append(
                    {
                        "runId": source.run_id,
                        "pipelineVersion": timeline.run.configuration.pipeline_version,
                        "configHash": timeline.run.config_hash,
                    }
                )
                for attempt in timeline.invocations:
                    usage = attempt.metadata.usage
                    if usage.cost_cny is None or usage.cost_status == CostStatus.UNVERIFIED:
                        known = False
                    else:
                        cold += usage.cost_cny
                    if attempt.metadata.provider == "deepseek" and attempt.metadata.price_version:
                        versions.add(attempt.metadata.price_version)
                    elif attempt.metadata.provider == "deepseek":
                        known = False
            except AppError:
                known = False
        report = await run_benchmark(
            manifest,
            search,
            verify_media=verify,
            runner_metadata={
                "retrievalMode": mode,
                "retrievalVersion": RETRIEVAL_VERSION,
                "minSimilarity": min_similarity,
                "minSemanticMargin": 0.02,
                "runs": provenance,
                "embeddingRevision": provider.space.revision_scope if provider else None,
            },
            costs=BenchmarkCosts(
                cold if known else None,
                Decimal(0),
                "estimated" if known else "unverified",
                known,
                next(iter(versions)) if len(versions) == 1 else None,
            ),
        )
        _write_json(output_path, report)
        return report
    finally:
        await store.close()


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


def vision_for_run(
    recorder: InvocationRecorder, budget: BudgetLedger, price_version: str | None = None
) -> DeepSeekVisionProvider:
    if price_version is not None and price_version != DEEPSEEK_FLASH_20261004.version:
        raise invalid_config()
    return DeepSeekVisionProvider(
        HttpxVisionTransport(),
        budget,
        None,
        recorder,
        price_snapshot=DEEPSEEK_FLASH_20261004 if price_version else None,
    )


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
            if stored.status != RunStatus.COMPLETED:
                if stored.asset.source_path.resolve() != prepared.video.resolve():
                    raise AppError(
                        "input.resume", "续跑视频与原运行不一致。", ExitCode.INPUT, prepared.resume
                    )
                stored_config = stored.configuration.analysis
                if (
                    stored_config.vision_prompt_hash is not None
                    and stored_config.vision_prompt_hash
                    != vision_prompt_fingerprint(stored_config.vision_prompt_version)
                ):
                    raise invalid_config()
                if stored_config.provider != "deepseek" or stored_config.model != MODEL:
                    raise invalid_config()
                ledger = BudgetLedger(
                    stored.configuration.max_cost_cny,
                    stored_config.max_requests,
                    stored_config.max_input_frames,
                )
                if stored_config.schema_version == 2:
                    ledger.restore(await store.load_invocations(prepared.resume))
                asr_provider = LocalAsrProvider(repository, _pinned_asr_settings(repository))
                ports = AnalysisPorts(
                    FfmpegMediaProcessor(repository),
                    asr_provider,
                    vision_for_run(store, ledger, stored_config.price_version),
                    store,
                    asr_provider.describe_request,
                )
            return await resume_analysis(prepared, store, project, ports)
        finally:
            await store.close()
    config, budget = prepared.config, prepared.max_cost_cny
    if config is None or budget is None or config.provider != "deepseek" or config.model != MODEL:
        raise invalid_config()
    if (
        config.vision_prompt_hash is not None
        and config.vision_prompt_hash != vision_prompt_fingerprint(config.vision_prompt_version)
    ):
        raise invalid_config()
    asset = await FfmpegMediaProcessor(repository).probe(
        prepared.video, CancellationContext("probe", 120)
    )
    asr_settings = _pinned_asr_settings(repository)
    store = await SqliteTimelineStore.open(project)
    try:
        ledger = BudgetLedger(budget, config.max_requests, config.max_input_frames)
        asr_provider = LocalAsrProvider(repository, asr_settings)
        ports = AnalysisPorts(
            FfmpegMediaProcessor(repository),
            asr_provider,
            vision_for_run(store, ledger, config.price_version),
            store,
            asr_provider.describe_request,
        )
        return await run_new_analysis(prepared, ports, asset, project, run_id=uuid4().hex)
    finally:
        await store.close()


def _dispatch(args: argparse.Namespace) -> AnalyzeOutcome | dict[str, object] | None:
    if args.command == "analyze":
        prepared = prepare_analyze(
            AnalyzeInput(
                args.video,
                args.project,
                args.config,
                args.max_cost_cny,
                args.resume,
                args.retry_uncertain,
            ),
            LocalInputReader(),
        )
        return asyncio.run(execute_analyze(prepared, Path.cwd()))
    if args.command == "search" and (
        not args.query.strip() or not args.run.strip() or args.top_k <= 0
    ):
        raise AppError("input.search", "查询、运行 ID 与正数 top-k 均为必需。", ExitCode.INPUT)
    if args.command == "search":
        return asyncio.run(
            execute_search(
                args.project.resolve(),
                args.run,
                args.query,
                Path.cwd(),
                top_k=args.top_k,
                mode=args.mode,
                min_similarity=args.min_similarity,
            )
        )
    return cast(
        dict[str, object],
        asyncio.run(
            execute_benchmark(
                args.project.resolve(),
                args.input,
                args.output,
                Path.cwd(),
                mode=args.mode,
                min_similarity=args.min_similarity,
            )
        ),
    )


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
        if isinstance(outcome, dict):
            print(json.dumps(outcome, ensure_ascii=False, default=str))
            if args.command == "benchmark" and outcome.get("qualityGate") is not True:
                return int(ExitCode.BENCHMARK)
        elif outcome is not None:
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
