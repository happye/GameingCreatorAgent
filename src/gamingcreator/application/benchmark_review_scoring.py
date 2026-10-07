"""Score the verified saved ten positions, without executing another retrieval."""

import hashlib
from datetime import UTC, datetime
from math import isfinite
from typing import cast

from gamingcreator.application.benchmark import (
    BenchmarkCosts,
    BenchmarkHit,
    BenchmarkMedia,
    BenchmarkQuery,
    JsonValue,
    parse_manifest,
    run_benchmark,
)
from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.application.benchmark_review import decode_object, judged_manifest


def _timing(value: object) -> int | float:
    if type(value) not in (int, float):
        raise ValueError("原检索耗时必须为非负有限数字。")
    numeric = cast(int | float, value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError("原检索耗时必须为非负有限数字。")
    return numeric


async def score_saved_review(
    context: dict[str, object],
    record: dict[str, object],
    original_report: bytes,
    *,
    costs: BenchmarkCosts,
) -> dict[str, JsonValue]:
    """The caller freshly verifies context/ranking/source through read-only storage.

    Actual analysis costs come from those same stored timelines, never from the
    downloaded human record or editable original report's claimed cost fields.
    """
    if hashlib.sha256(original_report).hexdigest() != context["reportSha256"]:
        raise ValueError("原报告与人工记录依据不同。")
    original = decode_object(original_report)
    manifest = parse_manifest(judged_manifest(context, record))
    began = datetime.fromisoformat(cast(str, original["startedAt"]))
    if began.tzinfo is None or began.utcoffset() is None or began > datetime.now(UTC):
        raise ValueError("原检索时间须有时区，不能在未来。")
    frozen = manifest.human_labels.frozen_at
    if frozen is not None and datetime.fromisoformat(frozen) > began:
        raise ValueError("原检索不能早于人工参考冻结。")
    duration = sum(source.duration_us for source in manifest.media)
    if type(original["sourceDurationUs"]) is not int or original["sourceDurationUs"] != duration:
        raise ValueError("原报告素材时长不同。")
    elapsed = _timing(original["elapsedMs"])
    ratio = _timing(original["retrievalWallclockToSourceRatio"])
    if ratio != elapsed * 1000 / duration:
        raise ValueError("原检索耗时比例不同。")
    queries = cast(list[dict[str, object]], context["queries"])
    original_queries = cast(list[dict[str, object]], original["queries"])
    if len(queries) != len(manifest.queries) or len(original_queries) != len(queries):
        raise ValueError("原查询不完整。")
    for query in original_queries:
        _timing(query["elapsedMs"])
    by_id = {cast(str, row["queryId"]): row for row in queries}
    sources = {(source.media_id, source.run_id): source for source in manifest.media}

    async def saved_hits(query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]:
        row = by_id[query.query_id]
        if row["status"] == "failed":
            raise ValueError("原查询失败，不能改成成功。")
        return tuple(
            BenchmarkHit(
                cast(str, slot["eventId"]),
                cast(int, slot["startUs"]),
                cast(int, slot["endUs"]),
                cast(int, slot["reportedRank"]),
            )
            for slot in cast(list[dict[str, object]], row["slots"])
            if slot["state"] != "missing"
        )

    async def already_verified(media: BenchmarkMedia) -> None:
        if sources.get((media.media_id, media.run_id)) != media:
            raise ValueError("已核对素材身份不同。")

    report = await run_benchmark(
        manifest,
        saved_hits,
        verify_media=already_verified,
        runner_metadata=cast(dict[str, JsonValue], original["runnerMetadata"]),
        costs=costs,
    )
    # The existing runner's timer here measures scoring, not search or analysis.
    report["scoredAt"] = report["startedAt"]
    report["scoringElapsedMs"] = report["elapsedMs"]
    report["startedAt"] = cast(str, original["startedAt"])
    report["elapsedMs"] = elapsed
    report["retrievalWallclockToSourceRatio"] = ratio
    scored_queries = cast(list[dict[str, JsonValue]], report["queries"])
    for result, previous, fixed in zip(scored_queries, original_queries, queries, strict=True):
        if result["queryId"] != previous["queryId"] or result["queryId"] != fixed["queryId"]:
            raise ValueError("原查询身份或顺序不同。")
        result["scoringElapsedMs"] = result["elapsedMs"]
        result["elapsedMs"] = cast(int | float, previous["elapsedMs"])
        result["totalReturned"] = cast(int, previous["totalReturned"])
        result["retrievalId"] = cast(str | None, fixed["retrievalId"])
    report["scoring"] = {
        "schemaVersion": "benchmark-fixed-scoring-v1",
        "basisSha256": cast(str, cast(dict[str, object], context["template"])["basisSha256"]),
        "originalReportSha256": context["reportSha256"],
        "bindingSha256": cast(str, context["bindingSha256"]),
        "reviewRecordSha256": hashlib.sha256(canonical_json(record)).hexdigest(),
        "ordinarySearches": 0,
        "paidRequestsSent": 0,
    }
    report["limitation"] = (
        cast(str, report["limitation"])
        + " This report scores the original saved ranking; elapsedMs and retrieval ratio "
        "retain original retrieval timings. scoringElapsedMs measures scoring only. "
        "Base-analysis costs are recomputed from the freshly verified original attempts."
    )
    return report
