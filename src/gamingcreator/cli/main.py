import argparse
import asyncio
import json
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Never, cast
from uuid import uuid4

from gamingcreator import __version__
from gamingcreator.application.analysis import (
    AnalysisPorts,
    AnalyzeOutcome,
    prepare_media,
    resume_analysis,
    run_new_analysis,
)
from gamingcreator.application.asr import LocalAsrSettings, ModelFile
from gamingcreator.application.benchmark import (
    BenchmarkHit,
    BenchmarkMedia,
    BenchmarkQuery,
    JsonValue,
    loads_manifest,
    run_benchmark,
)
from gamingcreator.application.benchmark_analysis_costs import benchmark_analysis_costs
from gamingcreator.application.benchmark_preparation import (
    bind_manifest,
    freeze_document,
    loads_plan,
)
from gamingcreator.application.budget import BudgetLedger, InvocationRecorder
from gamingcreator.application.detail_query import MAX_MANIFEST_BYTES, loads_constraint
from gamingcreator.application.inputs import (
    AnalysisConfig,
    AnalyzeInput,
    PreparedAnalyze,
    prepare_analyze,
)
from gamingcreator.application.media_batch import (
    MediaBatchItem,
    MediaBatchPlan,
    loads_batch_input,
    run_media_batch,
)
from gamingcreator.application.observation_text import (
    FACTS_PROJECTION_VERSION,
    clean_observation_text,
    display_facts,
)
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.project_detail_query import match_project_details
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.retrieval import (
    RETRIEVAL_VERSION,
    RetrievalMode,
    SearchResult,
    search_timeline,
    search_timelines,
)
from gamingcreator.application.search_detail_query import match_search_details
from gamingcreator.application.storage import RunStatus
from gamingcreator.application.tasks import tasks_payload
from gamingcreator.domain.errors import AppError, ExitCode, invalid_config
from gamingcreator.infrastructure.benchmark_preparation_files import (
    read_bounded,
    read_freeze,
    validate_bound_manifest,
    write_binding,
    write_freeze,
)
from gamingcreator.infrastructure.deepseek_vision import (
    MAX_IMAGE_WIDTH_V5,
    MODEL,
    DeepSeekVisionProvider,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.detail_query_sidecar import match_refinement
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.http_transport import HttpxVisionTransport
from gamingcreator.infrastructure.local_asr import LocalAsrProvider
from gamingcreator.infrastructure.local_embeddings import LocalEmbeddingProvider
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.media_batch_files import MediaBatchFiles, read_batch_bytes
from gamingcreator.infrastructure.project_search_files import (
    read_project_search,
    write_project_search,
)
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
    prepare = commands.add_parser("prepare-media", help="离线准备素材，保存后等待显式分析")
    prepare.add_argument("video", type=Path)
    prepare.add_argument("--project", type=Path, required=True)
    prepare.add_argument("--config", type=Path)
    prepare.add_argument("--max-cost-cny", help="保存后续分析的费用上限；准备不会调用模型")
    prepare.add_argument("--resume", help="按原配置续准备，只接受尚未开始模型分析的任务")
    prepare.add_argument("--timeout-seconds", type=float, default=3600)
    batch = commands.add_parser(
        "prepare-media-batch", help="一次清单逐素材离线准备，支持原批次续跑"
    )
    batch.add_argument("--project", type=Path, required=True)
    batch.add_argument("--input", type=Path, help="media-batch-input-v1素材清单")
    batch.add_argument("--config", type=Path)
    batch.add_argument("--max-cost-cny", help="保存每个任务后续上限，准备不预留费用")
    batch.add_argument("--resume", help="按原批次ID续准备，不能覆盖清单／配置／限额")
    batch.add_argument("--timeout-seconds", type=float, help="每素材期限；续跑默认保留原值")
    tasks = commands.add_parser("tasks", help="查看已保存素材任务、阶段、原配置和费用")
    tasks.add_argument("--project", type=Path, required=True)
    tasks.add_argument("--run", help="只查看一个任务")
    tasks.add_argument("--limit", type=int, default=100)
    tasks.add_argument("--offset", type=int, default=0)
    freeze = commands.add_parser("freeze-benchmark", help="本地登记原素材并冻结验收查询，不分析")
    freeze.add_argument("--input", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    bind = commands.add_parser("bind-benchmark", help="把冻结验收素材绑定到已完成运行，不检索")
    bind.add_argument("--freeze", type=Path, required=True)
    bind.add_argument("--project", type=Path, required=True)
    bind.add_argument("--runs", type=Path, required=True)
    bind.add_argument("--partition", choices=("development", "test"), default="test")
    bind.add_argument("--output", type=Path, required=True)
    search = commands.add_parser("search", help="用自然语言检索已完成的时间线")
    search.add_argument("query")
    search.add_argument("--project", type=Path, required=True)
    search.add_argument("--run", required=True)
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--format", choices=("json",), default="json")
    search.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="hybrid")
    search.add_argument("--min-similarity", type=float, default=0.80)
    project_search = commands.add_parser("search-project", help="一次需求联合检索多个已完成录像")
    project_search.add_argument("query")
    project_search.add_argument("--project", type=Path, required=True)
    project_search.add_argument(
        "--run", action="append", required=True, help="明确选择任务，可重复参数"
    )
    project_search.add_argument("--top-k", type=int, default=10)
    project_search.add_argument(
        "--mode", choices=("lexical", "semantic", "hybrid"), default="hybrid"
    )
    project_search.add_argument("--min-similarity", type=float, default=0.80)
    benchmark = commands.add_parser("benchmark", help="执行冻结人工标签评测")
    benchmark.add_argument("--input", type=Path, required=True)
    benchmark.add_argument("--project", type=Path, required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    benchmark.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="hybrid")
    benchmark.add_argument("--min-similarity", type=float, default=0.80)
    benchmark.add_argument(
        "--binding", type=Path, help="复核冻结绑定，只允许追加候选人评与复核状态"
    )
    detail = commands.add_parser("match-details", help="离线匹配同主体属性条件清单")
    detail.add_argument("--project", type=Path, required=True)
    detail.add_argument("--run", required=True)
    detail.add_argument("--event", required=True)
    detail.add_argument("--input", type=Path, required=True)
    detail.add_argument("--profile", choices=("v1", "v2", "v3", "v4"), default="v2")
    detail.add_argument(
        "--save-match", action="store_true", help="在已发布精分析旁保存独立匹配记录"
    )
    project_detail = commands.add_parser(
        "match-project-details", help="按明确复合条件核对多段录像的已保存精结果"
    )
    project_detail.add_argument("--project", type=Path, required=True)
    project_detail.add_argument("--run", action="append", required=True)
    project_detail.add_argument("--input", type=Path, required=True)
    project_detail.add_argument("--profile", choices=("v1", "v2", "v3", "v4"), default="v2")
    project_detail.add_argument(
        "--status", choices=("all", "full", "partial", "no_match", "unverified"), default="all"
    )
    project_detail.add_argument("--limit", type=int, default=20)
    project_detail.add_argument("--offset", type=int, default=0)
    project_detail.add_argument("--snapshot", help="沿用上页结果身份；变化时拒绝")
    search_detail = commands.add_parser(
        "match-search-details", help="为已保存原排名补明确条件依据，不再搜索"
    )
    search_detail.add_argument("--project", type=Path, required=True)
    search_detail.add_argument("--search", required=True)
    search_detail.add_argument("--search-sha256", required=True)
    search_detail.add_argument("--input", type=Path, required=True)
    search_detail.add_argument("--profile", choices=("v1", "v2", "v3", "v4"), default="v2")
    return parser


def _timecode(microseconds: int) -> str:
    milliseconds = microseconds // 1000
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def _search_document(
    result: SearchResult,
    elapsed_ms: int,
    event_uncertainty: dict[str, str | None] | None = None,
) -> dict[str, object]:
    doubts = event_uncertainty or {}
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
                "uncertainty": doubts.get(item.event_id or ""),
                "displayUncertainty": clean_observation_text(doubts.get(item.event_id or "") or "")
                or None,
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
        document = _search_document(
            result,
            round((perf_counter() - started) * 1000),
            {event.event_id: event.uncertainty for event in timeline.events},
        )
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


async def execute_project_search(
    project: Path,
    run_ids: Sequence[str],
    query: str,
    repository: Path,
    *,
    top_k: int = 10,
    mode: RetrievalMode = "hybrid",
    min_similarity: float = 0.80,
) -> dict[str, object]:
    if (
        not 1 <= len(run_ids) <= 100
        or any(
            type(identifier) is not str or not identifier.strip() or len(identifier) > 256
            for identifier in run_ids
        )
        or len(set(run_ids)) != len(run_ids)
        or type(query) is not str
        or not query.strip()
        or len(query) > 4096
        or type(top_k) is not int
        or not 1 <= top_k <= 100
        or mode not in ("lexical", "semantic", "hybrid")
        or type(min_similarity) not in (int, float)
        or not isfinite(min_similarity)
        or not -1 <= min_similarity <= 1
    ):
        raise AppError(
            "input.project_search", "请选择不同任务、有效查询和检索参数。", ExitCode.INPUT
        )
    project = project.resolve()
    _require_project(project)
    started_at = datetime.now(UTC).isoformat()
    began = perf_counter()
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timelines = tuple(
            [await store.load_completed_timeline(identifier) for identifier in sorted(run_ids)]
        )
        if len({timeline.run.asset.sha256 for timeline in timelines}) != len(timelines) or len(
            {timeline.run.asset.media_id for timeline in timelines}
        ) != len(timelines):
            raise AppError("retrieval.scope", "同一原录像请只选择一个分析版本。", ExitCode.INPUT)
        validation_ms = round((perf_counter() - began) * 1000)
        provider = LocalEmbeddingProvider.from_manifest(repository) if mode != "lexical" else None
        result = await search_timelines(
            timelines,
            query,
            top_k=top_k,
            mode=mode,
            embedding_provider=provider,
            min_similarity=min_similarity,
        )
        details: dict[str, dict[str, object]] = {}
        for timeline in timelines:
            subset = SearchResult(
                timeline.run.run_id,
                result.query,
                mode,
                tuple(
                    item.clip for item in result.candidates if item.run_id == timeline.run.run_id
                ),
            )
            rows = cast(
                list[dict[str, object]],
                _search_document(
                    subset, 0, {event.event_id: event.uncertainty for event in timeline.events}
                )["candidates"],
            )
            details.update((cast(str, row["candidateId"]), row) for row in rows)
        sources = [
            {
                "runId": run.run_id,
                "mediaId": run.asset.media_id,
                "sourceName": run.asset.source_path.name,
                "sourcePath": str(run.asset.source_path),
                "sourceSha256": run.asset.sha256,
                "durationUs": run.asset.duration_us,
                "configHash": run.config_hash,
                "pipelineVersion": run.configuration.pipeline_version,
                "pipelineHash": run.configuration.pipeline_hash,
                "analysisConfiguration": asdict(run.configuration.analysis),
            }
            for run in result.sources
        ]
        source_by_run = {cast(str, source["runId"]): source for source in sources}
        search_id = uuid4().hex
        document: dict[str, object] = {
            "schemaVersion": "project-search-v1",
            "searchId": search_id,
            "scopeId": result.scope_id,
            "query": result.query,
            "mode": result.mode,
            "topK": top_k,
            "retrievalVersion": result.retrieval_version,
            "factsProjectionVersion": FACTS_PROJECTION_VERSION,
            "minSimilarity": result.min_similarity,
            "minSemanticMargin": result.min_semantic_margin,
            "abstentionReason": result.abstention_reason,
            "startedAt": started_at,
            "elapsedMs": round((perf_counter() - began) * 1000),
            "sourceValidationMs": validation_ms,
            "scoreIsProbability": False,
            "qualityGate": None,
            "modelAnalysisCalls": 0,
            "newReservations": 0,
            "embedding": json.loads(json.dumps(asdict(result.embedding_metadata), default=str))
            if result.embedding_metadata
            else None,
            "sources": sources,
            "candidates": [
                details[item.clip.candidate_id]
                | {
                    "rank": rank,
                    "runId": item.run_id,
                    "sourceName": source_by_run[item.run_id]["sourceName"],
                    "sourceSha256": source_by_run[item.run_id]["sourceSha256"],
                }
                for rank, item in enumerate(result.candidates, 1)
            ],
            "recordPath": str(project / "project-searches" / search_id / "result.json"),
        }
        write_project_search(project, document)
        return document
    finally:
        await store.close()


async def execute_search_detail_match(
    project: Path,
    search_id: str,
    search_sha256: str,
    manifest: str,
    *,
    profile: str,
) -> dict[str, object]:
    _require_project(project)
    try:
        constraint = loads_constraint(manifest)
    except ValueError:
        raise AppError("input.detail_query", "复合条件格式或词表无效。", ExitCode.INPUT) from None
    document = read_project_search(project, search_id)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await match_search_details(
            store,
            document,
            search_sha256,
            constraint,
            profile,
            lambda timeline, event_id, query: match_refinement(
                project,
                timeline,
                event_id,
                query,
                profile=profile,
                save=False,
            ),
        )
    finally:
        await store.close()


async def execute_project_detail_match(
    project: Path,
    run_ids: Sequence[str],
    manifest: str,
    *,
    profile: str,
    limit: int = 20,
    offset: int = 0,
    status: str = "all",
    snapshot: str | None = None,
) -> dict[str, object]:
    _require_project(project)
    try:
        constraint = loads_constraint(manifest)
    except ValueError:
        raise AppError("input.detail_query", "复合条件格式或词表无效。", ExitCode.INPUT) from None
    from gamingcreator.infrastructure.detail_query_sidecar import refinement_identity_for_profile

    refinement_identity_for_profile(profile)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await match_project_details(
            store,
            run_ids,
            constraint,
            profile,
            lambda timeline, event_id, query: match_refinement(
                project, timeline, event_id, query, profile=profile, save=False
            ),
            limit=limit,
            offset=offset,
            status=status,
            expected_snapshot=snapshot,
        )
    finally:
        await store.close()


async def execute_detail_match(
    project: Path,
    run_id: str,
    event_id: str,
    input_path: Path,
    *,
    profile: str = "v2",
    save: bool = False,
) -> dict[str, object]:
    _require_project(project)
    try:
        with input_path.open("rb") as source:
            content = source.read(MAX_MANIFEST_BYTES + 1)
        if len(content) > MAX_MANIFEST_BYTES:
            raise ValueError("Oversized query.")
        constraint = loads_constraint(content.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise AppError(
            "input.detail_query", "属性条件清单无效或超过1MiB。", ExitCode.INPUT
        ) from None
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_completed_timeline(run_id)
        return match_refinement(project, timeline, event_id, constraint, profile=profile, save=save)
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
    binding_path: Path | None = None,
) -> dict[str, JsonValue]:
    _require_project(project)
    try:
        if binding_path is not None:
            input_bytes = read_bounded(input_path)
            validate_bound_manifest(binding_path, input_bytes)
            manifest = loads_manifest(input_bytes.decode("utf-8-sig"))
        else:
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

        retrieval_ids: dict[str, str] = {}

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
            retrieval_ids[query.query_id] = await store.persist_search(
                result,
                _search_document(
                    result,
                    elapsed,
                    {event.event_id: event.uncertainty for event in timeline.events},
                ),
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

        cost_timelines = []
        provenance: list[JsonValue] = []
        for source in manifest.media:
            try:
                timeline = await store.load_completed_timeline(source.run_id)
                cost_timelines.append(timeline)
                provenance.append(
                    {
                        "runId": source.run_id,
                        "pipelineVersion": timeline.run.configuration.pipeline_version,
                        "configHash": timeline.run.config_hash,
                    }
                )
            except AppError:
                pass
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
            costs=benchmark_analysis_costs(
                cost_timelines, all_runs_loaded=len(cost_timelines) == len(manifest.media)
            ),
        )
        for row in cast(list[dict[str, JsonValue]], report["queries"]):
            row["retrievalId"] = retrieval_ids.get(cast(str, row["queryId"]))
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


async def execute_freeze_benchmark(
    input_path: Path, output: Path, repository: Path
) -> dict[str, object]:
    try:
        data = read_bounded(input_path)
        plan = loads_plan(data.decode("utf-8-sig"))
        processor = FfmpegMediaProcessor(repository)
        assets = {}
        for source in plan.sources:
            path = Path(source.path)
            if not path.is_absolute():
                path = input_path.parent / path
            assets[source.source_id] = await processor.probe(
                path.resolve(), CancellationContext("benchmark-freeze", timeout_seconds=300)
            )
        frozen = freeze_document(plan, assets, datetime.now(UTC).isoformat())
        hashes = write_freeze(input_path, data, frozen, output)
        return {
            "schemaVersion": "benchmark-preparation-result-v1",
            "output": str(output.resolve()),
            "files": hashes,
            "frozenAt": frozen["frozenAt"],
            "preparation": frozen["preparation"],
            "qualityGate": None,
            "paidRequestsSent": 0,
        }
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        raise AppError(
            "input.benchmark_preparation",
            "验收计划／来源／新输出目录无效，未开始分析。",
            ExitCode.INPUT,
        ) from None


async def execute_bind_benchmark(
    directory: Path, project: Path, runs_path: Path, partition: str, output: Path
) -> dict[str, object]:
    _require_project(project)
    try:
        frozen, freeze_sha = read_freeze(directory)

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("运行映射含重复字段。")
                result[key] = value
            return result

        runs = json.loads(read_bounded(runs_path).decode("utf-8-sig"), object_pairs_hook=pairs)
        if (
            type(runs) is not dict
            or not runs
            or any(type(value) is not str or not value.strip() for value in runs.values())
            or len(set(runs.values())) != len(runs)
        ):
            raise ValueError("运行映射无效。")
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            timelines = {
                key: await store.load_completed_timeline(value) for key, value in runs.items()
            }
            manifest = bind_manifest(frozen, timelines, partition)
            provenance = {
                "schemaVersion": "benchmark-binding-v1",
                "freezeSha256": freeze_sha,
                "frozenAt": frozen["frozenAt"],
                "partition": partition,
                "runs": [
                    {
                        "sourceId": key,
                        "runId": value.run.run_id,
                        "configHash": value.run.config_hash,
                        "pipelineVersion": value.run.configuration.pipeline_version,
                    }
                    for key, value in timelines.items()
                ],
                "preparation": frozen["preparation"],
                "qualityGate": None,
                "humanCandidateLabels": None,
                "paidRequestsSent": 0,
            }
            hashes = write_binding(
                directory=directory,
                freeze_sha256=freeze_sha,
                output=output,
                project=project,
                manifest=manifest,
                provenance=provenance,
            )
            return {
                "schemaVersion": "benchmark-preparation-result-v1",
                "output": str(output.resolve()),
                "files": hashes,
                "preparation": frozen["preparation"],
                "qualityGate": None,
                "paidRequestsSent": 0,
            }
        finally:
            await store.close()
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        raise AppError(
            "input.benchmark_binding",
            "冻结资料／运行映射／来源身份／新输出目录无效，未检索。",
            ExitCode.INPUT,
        ) from None


async def execute_tasks(
    project: Path, *, limit: int = 100, offset: int = 0, run_id: str | None = None
) -> dict[str, object]:
    _require_project(project)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        document = await tasks_payload(store, limit=limit, offset=offset, run_id=run_id)
        document["project"] = str(project.resolve())
        rows = cast(list[dict[str, object]], document["tasks"])
        for row in rows:
            row["nextCommand"] = None
            if row["nextAction"] is not None and not row["continuationBlockers"]:
                run = await store.load_run(cast(str, row["runId"]))
                row["nextCommand"] = [
                    "gamingcreator",
                    "prepare-media" if row["nextAction"] == "prepare_media" else "analyze",
                    str(run.asset.source_path),
                    "--project",
                    str(project.resolve()),
                    "--resume",
                    run.run_id,
                ]
        return document
    finally:
        await store.close()


def _media_preparation_config(config: AnalysisConfig | None) -> AnalysisConfig:
    if (
        config is None
        or config.schema_version != 2
        or config.provider != "deepseek"
        or config.model != MODEL
        or config.price_version != DEEPSEEK_FLASH_20261004.version
        or (
            config.vision_prompt_hash is not None
            and config.vision_prompt_hash != vision_prompt_fingerprint(config.vision_prompt_version)
        )
    ):
        raise invalid_config()
    return config


async def execute_prepare_media_batch(
    project: Path,
    repository: Path,
    *,
    input_path: Path | None = None,
    config_path: Path | None = None,
    max_cost_cny: str | None = None,
    resume: str | None = None,
    timeout_seconds: float | None = None,
    on_progress: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    if timeout_seconds is not None and (not isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise AppError("input.media_batch", "每素材期限须为有限正数。", ExitCode.INPUT)
    project = project.resolve()
    files = None
    try:
        if resume is not None:
            if input_path is not None or config_path is not None or max_cost_cny is not None:
                raise ValueError("续批次不能覆盖清单／配置／限额。")
            _require_project(project)
            files = MediaBatchFiles(project, resume)
        else:
            if input_path is None or config_path is None or max_cost_cny is None:
                raise ValueError("新批次需要清单／配置／每任务后续上限。")
            input_path = input_path.resolve()
            source_bytes = read_batch_bytes(input_path)
            config_bytes = read_batch_bytes(config_path)
            config = _media_preparation_config(LocalInputReader().load_config(config_path))
            budget = Decimal(max_cost_cny)
            if not budget.is_finite() or budget <= 0:
                raise ValueError("每任务后续上限须为有限正数。")
            inputs = loads_batch_input(source_bytes)
            items = tuple(
                MediaBatchItem(
                    identifier,
                    (
                        Path(path) if Path(path).is_absolute() else input_path.parent / path
                    ).resolve(),
                    uuid4().hex,
                )
                for identifier, path in inputs
            )
            if len({item.video for item in items}) != len(items):
                raise ValueError("清单不能重复同一本地路径。")
            _require_space(project)
            plan = MediaBatchPlan(
                uuid4().hex, project, config, budget, timeout_seconds or 3600, items
            )
            files = MediaBatchFiles(project, plan.batch_id)
            files.create(plan, input_path.parent, source_bytes, config_bytes)
        files.acquire()
        plan, state, digest = files.load()
        _media_preparation_config(plan.config)
        _require_space(project)
        media = FfmpegMediaProcessor(repository)
        store = await SqliteTimelineStore.open(project)
        try:

            def checkpoint(document: dict[str, object]) -> None:
                files.save(document, plan, digest)
                if on_progress is not None:
                    on_progress(document)
                    return
                rows = cast(list[dict[str, object]], document["items"])
                print(
                    json.dumps(
                        {
                            "schemaVersion": "media-batch-progress-v1",
                            "batchId": plan.batch_id,
                            "status": document["status"],
                            "finishedItems": sum(
                                row["verifiedThisInvocation"] is True for row in rows
                            ),
                            "totalItems": len(rows),
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )

            return await run_media_batch(
                plan, state, media, store, checkpoint, timeout_seconds=timeout_seconds
            )
        finally:
            await store.close()
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, ArithmeticError):
        raise AppError(
            "input.media_batch",
            "批次清单／配置／状态不符，请保留原资料并检查对应批次。",
            ExitCode.INPUT,
        ) from None
    finally:
        if files is not None:
            files.close()


async def execute_prepare_media(
    prepared: PreparedAnalyze, repository: Path, *, timeout_seconds: float = 3600
) -> dict[str, object]:
    if not isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise AppError("input.prepare", "素材准备期限必须是有限正数。", ExitCode.INPUT)
    project = prepared.project.resolve()
    _require_space(project)
    media = FfmpegMediaProcessor(repository)
    started = perf_counter()
    asset = None
    if prepared.resume is None:
        config = prepared.config
    else:
        _require_project(project)
        preview = await SqliteTimelineStore.open(project, read_only=True)
        try:
            config = (await preview.load_run(prepared.resume)).configuration.analysis
        finally:
            await preview.close()
    config = _media_preparation_config(config)
    if prepared.resume is None:
        asset = await media.probe(
            prepared.video, CancellationContext("probe", min(120, timeout_seconds))
        )
    remaining = timeout_seconds - (perf_counter() - started)
    if remaining <= 0:
        raise AppError("media.timeout", "素材准备达到时间上限。", ExitCode.INPUT)
    store = await SqliteTimelineStore.open(project)
    try:
        result = await prepare_media(
            prepared,
            media,
            store,
            project,
            run_id=prepared.resume or uuid4().hex,
            asset=asset,
            max_image_width=MAX_IMAGE_WIDTH_V5,
            timeout_seconds=remaining,
        )
        stored = await store.load_run(result.run_id)
        return {
            "schemaVersion": 1,
            "runId": result.run_id,
            "mediaId": result.media_id,
            "status": "media_prepared",
            "runStatus": str(stored.status),
            "sourceSha256": stored.asset.sha256,
            "durationUs": stored.asset.duration_us,
            "samplingIntervalMs": config.sampling_interval_ms,
            "imageCount": result.image_count,
            "audioAvailable": result.audio_available,
            "plannedWindows": result.window_count,
            "plannedUploadFrames": result.upload_frame_count,
            "coverageFits": result.coverage_fits,
            "maxRequests": config.max_requests,
            "maxInputFrames": config.max_input_frames,
            "savedMaxCostCny": str(stored.configuration.max_cost_cny),
            "modelInvocations": 0,
            "message": "素材已准备，等待显式分析。"
            if result.coverage_fits
            else "素材已准备，但原配置无法覆盖全部窗口；尚未调用模型。请调整配置后准备新任务。",
            "nextCommand": [
                "gamingcreator",
                "analyze",
                str(prepared.video),
                "--project",
                str(project),
                "--resume",
                result.run_id,
            ]
            if result.coverage_fits
            else None,
        }
    finally:
        await store.close()


def _dispatch(args: argparse.Namespace) -> AnalyzeOutcome | dict[str, object] | None:
    if args.command == "search-project":
        return asyncio.run(
            execute_project_search(
                args.project,
                args.run,
                args.query,
                Path.cwd(),
                top_k=args.top_k,
                mode=args.mode,
                min_similarity=args.min_similarity,
            )
        )
    if args.command == "prepare-media-batch":
        return asyncio.run(
            execute_prepare_media_batch(
                args.project,
                Path.cwd(),
                input_path=args.input,
                config_path=args.config,
                max_cost_cny=args.max_cost_cny,
                resume=args.resume,
                timeout_seconds=args.timeout_seconds,
            )
        )
    if args.command == "freeze-benchmark":
        return asyncio.run(
            execute_freeze_benchmark(args.input.resolve(), args.output.resolve(), Path.cwd())
        )
    if args.command == "bind-benchmark":
        return asyncio.run(
            execute_bind_benchmark(
                args.freeze.resolve(),
                args.project.resolve(),
                args.runs.resolve(),
                args.partition,
                args.output.resolve(),
            )
        )
    if args.command == "tasks":
        return asyncio.run(
            execute_tasks(
                args.project.resolve(), limit=args.limit, offset=args.offset, run_id=args.run
            )
        )
    if args.command == "match-search-details":
        return asyncio.run(
            execute_search_detail_match(
                args.project.resolve(),
                args.search,
                args.search_sha256,
                read_bounded(args.input).decode("utf-8-sig"),
                profile=args.profile,
            )
        )
    if args.command == "match-project-details":
        return asyncio.run(
            execute_project_detail_match(
                args.project.resolve(),
                args.run,
                read_bounded(args.input).decode("utf-8-sig"),
                profile=args.profile,
                limit=args.limit,
                offset=args.offset,
                status=args.status,
                snapshot=args.snapshot,
            )
        )
    if args.command == "match-details":
        return asyncio.run(
            execute_detail_match(
                args.project.resolve(),
                args.run,
                args.event,
                args.input,
                profile=args.profile,
                save=args.save_match,
            )
        )
    if args.command in ("analyze", "prepare-media"):
        prepared = prepare_analyze(
            AnalyzeInput(
                args.video,
                args.project,
                args.config,
                args.max_cost_cny,
                args.resume,
                args.retry_uncertain if args.command == "analyze" else False,
            ),
            LocalInputReader(),
        )
        if args.command == "prepare-media":
            return asyncio.run(
                execute_prepare_media(prepared, Path.cwd(), timeout_seconds=args.timeout_seconds)
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
                binding_path=args.binding.resolve() if args.binding is not None else None,
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
            if args.command == "prepare-media-batch":
                return int(cast(int, outcome["exitCode"]))
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
