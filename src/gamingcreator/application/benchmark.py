"""Human-label benchmark contracts; no model-generated judgment or file I/O."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from time import perf_counter
from typing import Literal, Protocol

MAX_SOURCE_US = (1 << 63) - 1
QueryKind = Literal["main", "sparse", "negative"]
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class BenchmarkMedia:
    media_id: str
    run_id: str
    sha256: str
    duration_us: int


@dataclass(frozen=True, slots=True)
class HumanEvent:
    human_event_id: str
    independence_group: str
    usable_ranges: tuple[tuple[int, int], ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CandidateLabel:
    event_id: str
    human_event_id: str | None
    start_us: int
    end_us: int
    grade: int
    reason: str


@dataclass(frozen=True, slots=True)
class BenchmarkQuery:
    query_id: str
    text: str
    kind: QueryKind
    media_id: str
    run_id: str
    reference_events: tuple[HumanEvent, ...]
    candidate_labels: tuple[CandidateLabel, ...]


@dataclass(frozen=True, slots=True)
class HumanLabels:
    confirmed: bool
    annotators: tuple[str, ...]
    reviewed: bool
    frozen_at: str | None
    independent_test_set: bool


@dataclass(frozen=True, slots=True)
class BenchmarkManifest:
    dataset_id: str
    label_version: str | None
    human_labels: HumanLabels
    media: tuple[BenchmarkMedia, ...]
    queries: tuple[BenchmarkQuery, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkHit:
    event_id: str
    start_us: int
    end_us: int
    rank: int

    def __post_init__(self) -> None:
        _text(self.event_id, "hit.eventId")
        _integer(self.start_us, "hit.startUs", minimum=0)
        _integer(self.end_us, "hit.endUs", minimum=1)
        _integer(self.rank, "hit.rank", minimum=1)
        if self.start_us >= self.end_us:
            raise ValueError("Hit interval must be nonempty.")


class SearchCallable(Protocol):
    async def __call__(self, query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]: ...


class MediaVerifier(Protocol):
    async def __call__(self, media: BenchmarkMedia) -> None:
        """Verify Completed run, media identity, duration, SHA and source integrity."""
        ...


@dataclass(frozen=True, slots=True)
class BenchmarkCosts:
    cold_cny: Decimal | None = None
    hot_cny: Decimal | None = None
    cost_status: Literal["unverified", "estimated", "confirmed"] = "unverified"
    attempts_complete: bool = False
    price_version: str | None = None

    def __post_init__(self) -> None:
        for value in (self.cold_cny, self.hot_cny):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value < 0
            ):
                raise ValueError("Cost must be a nonnegative finite Decimal or unknown.")
        if self.cost_status not in ("unverified", "estimated", "confirmed"):
            raise ValueError("Unknown cost status.")
        _boolean(self.attempts_complete, "cost.attemptsComplete")
        if self.price_version is not None:
            _text(self.price_version, "cost.priceVersion")


def _mapping(value: object, fields: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ValueError(f"{name} must be an object.")
    if set(value) != fields:
        raise ValueError(f"{name} has missing or unknown fields.")
    return value


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array.")
    return value


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 16_384:
        raise ValueError(f"{name} must be a nonempty bounded string.")
    return value


def _integer(value: object, name: str, *, minimum: int = 0, maximum: int = MAX_SOURCE_US) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in the permitted range.")
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean.")
    return value


def _unique(values: list[str], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique.")


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    result = _text(value, "humanLabels.frozenAt")
    try:
        parsed = datetime.fromisoformat(result)
    except ValueError as error:
        raise ValueError("frozenAt must be an ISO-8601 timestamp with timezone.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("frozenAt needs an explicit timezone.")
    return result


def _parse_human(value: object) -> HumanLabels:
    fields = {"confirmed", "annotators", "reviewed", "frozenAt", "independentTestSet"}
    item = _mapping(value, fields, "humanLabels")
    annotators = tuple(
        _text(annotator, "annotator") for annotator in _array(item["annotators"], "annotators")
    )
    _unique(list(annotators), "Annotators")
    result = HumanLabels(
        _boolean(item["confirmed"], "confirmed"),
        annotators,
        _boolean(item["reviewed"], "reviewed"),
        _timestamp(item["frozenAt"]),
        _boolean(item["independentTestSet"], "independentTestSet"),
    )
    if result.confirmed and (not result.annotators or result.frozen_at is None):
        raise ValueError("Confirmed human labels need annotators and a frozen timestamp.")
    return result


def _parse_media(value: object) -> BenchmarkMedia:
    item = _mapping(value, {"mediaId", "runId", "sha256", "durationUs"}, "media")
    sha = _text(item["sha256"], "media.sha256")
    if re.fullmatch(r"[0-9a-f]{64}", sha) is None:
        raise ValueError("Media SHA256 must be 64 lowercase hex digits.")
    return BenchmarkMedia(
        _text(item["mediaId"], "media.mediaId"),
        _text(item["runId"], "media.runId"),
        sha,
        _integer(item["durationUs"], "media.durationUs", minimum=1),
    )


def _parse_reference(value: object, duration_us: int) -> HumanEvent:
    fields = {"humanEventId", "independenceGroup", "usableRanges", "reason"}
    item = _mapping(value, fields, "referenceEvent")
    ranges: list[tuple[int, int]] = []
    for raw_range in _array(item["usableRanges"], "usableRanges"):
        interval = _mapping(raw_range, {"startUs", "endUs"}, "usableRange")
        start = _integer(interval["startUs"], "usableRange.startUs")
        end = _integer(interval["endUs"], "usableRange.endUs", minimum=1, maximum=duration_us)
        if start >= end:
            raise ValueError("Human usable ranges must be nonempty and inside the source.")
        ranges.append((start, end))
    if not ranges or len(set(ranges)) != len(ranges):
        raise ValueError("Human references need unique usable ranges.")
    return HumanEvent(
        _text(item["humanEventId"], "humanEventId"),
        _text(item["independenceGroup"], "independenceGroup"),
        tuple(ranges),
        _text(item["reason"], "referenceEvent.reason"),
    )


def _parse_label(value: object, references: set[str], duration_us: int) -> CandidateLabel:
    fields = {"eventId", "humanEventId", "startUs", "endUs", "grade", "reason"}
    item = _mapping(value, fields, "candidateLabel")
    human_id = None if item["humanEventId"] is None else _text(item["humanEventId"], "humanEventId")
    grade = _integer(item["grade"], "candidateLabel.grade", maximum=3)
    if human_id is not None and human_id not in references:
        raise ValueError("Candidate labels must map to a known human reference event.")
    if grade >= 2 and human_id is None:
        raise ValueError("Useful candidate labels require a human reference mapping.")
    start = _integer(item["startUs"], "candidateLabel.startUs")
    end = _integer(item["endUs"], "candidateLabel.endUs", minimum=1, maximum=duration_us)
    if start >= end:
        raise ValueError("Candidate judgments need a nonempty source interval.")
    return CandidateLabel(
        _text(item["eventId"], "candidateLabel.eventId"),
        human_id,
        start,
        end,
        grade,
        _text(item["reason"], "candidateLabel.reason"),
    )


def _parse_query(
    value: object, media: dict[tuple[str, str], BenchmarkMedia], human_confirmed: bool
) -> BenchmarkQuery:
    fields = {"id", "text", "kind", "mediaId", "runId", "referenceEvents", "candidateLabels"}
    item = _mapping(value, fields, "query")
    media_id = _text(item["mediaId"], "query.mediaId")
    run_id = _text(item["runId"], "query.runId")
    if (media_id, run_id) not in media:
        raise ValueError("Every query must reference a listed media/run pair.")
    kind = item["kind"]
    if kind not in ("main", "sparse", "negative"):
        raise ValueError("Query kind must be main, sparse or negative.")
    references = tuple(
        _parse_reference(raw, media[(media_id, run_id)].duration_us)
        for raw in _array(item["referenceEvents"], "referenceEvents")
    )
    _unique([reference.human_event_id for reference in references], "Human event IDs")
    _unique([reference.independence_group for reference in references], "Reference event groups")
    if kind == "negative" and references:
        raise ValueError("Negative queries cannot have useful reference events.")
    if human_confirmed:
        if kind == "main" and len(references) < 10:
            raise ValueError("Main queries need at least ten independent useful reference events.")
        if kind == "sparse" and not 1 <= len(references) <= 9:
            raise ValueError("Sparse queries need one to nine useful reference events.")
    labels = tuple(
        _parse_label(
            raw,
            {reference.human_event_id for reference in references},
            media[(media_id, run_id)].duration_us,
        )
        for raw in _array(item["candidateLabels"], "candidateLabels")
    )
    _unique([label.event_id for label in labels], "Candidate event labels")
    return BenchmarkQuery(
        _text(item["id"], "query.id"),
        _text(item["text"], "query.text"),
        kind,
        media_id,
        run_id,
        references,
        labels,
    )


def parse_manifest(value: object) -> BenchmarkManifest:
    """Reject coercion, unknown fields and fake main-group eligibility."""
    fields = {"schemaVersion", "datasetId", "labelVersion", "humanLabels", "media", "queries"}
    item = _mapping(value, fields, "benchmark")
    _integer(item["schemaVersion"], "schemaVersion", minimum=1, maximum=1)
    human = _parse_human(item["humanLabels"])
    label_version = (
        None if item["labelVersion"] is None else _text(item["labelVersion"], "labelVersion")
    )
    if human.confirmed and label_version is None:
        raise ValueError("Confirmed labels need a labelVersion.")
    media = tuple(_parse_media(raw) for raw in _array(item["media"], "media"))
    if not media:
        raise ValueError("The benchmark needs at least one source.")
    _unique([source.media_id for source in media], "Media IDs")
    # One source file cannot inflate the cost denominator via multiple runs/aliases.
    _unique([source.sha256 for source in media], "Source SHA256 values")
    index = {(source.media_id, source.run_id): source for source in media}
    queries = tuple(
        _parse_query(raw, index, human.confirmed) for raw in _array(item["queries"], "queries")
    )
    if not queries:
        raise ValueError("The benchmark needs at least one query.")
    _unique([query.query_id for query in queries], "Query IDs")
    return BenchmarkManifest(
        _text(item["datasetId"], "datasetId"), label_version, human, media, queries
    )


def loads_manifest(text: str) -> BenchmarkManifest:
    """Parse JSON without silently discarding duplicate keys or nonfinite literals."""

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object key.")
            result[key] = value
        return result

    def constant(value: str) -> object:
        raise ValueError("Nonfinite JSON literals are forbidden.")

    return parse_manifest(json.loads(text, object_pairs_hook=pairs, parse_constant=constant))


def _percentile90(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(9 * len(ordered) + 9) // 10 - 1]


def _score_query(
    query: BenchmarkQuery,
    hits: tuple[BenchmarkHit, ...],
    duration_us: int,
    labels_confirmed: bool,
) -> dict[str, JsonValue]:
    labels = {label.event_id: label for label in query.candidate_labels}
    references = {event.human_event_id: event for event in query.reference_events}
    seen_ids: set[str] = set()
    seen_groups: set[str] = set()
    useful_ids: set[str] = set()
    slots: list[JsonValue] = []
    duplicates = unjudged = out_of_bounds = 0
    start_errors: list[int] = []
    end_errors: list[int] = []
    for slot_number in range(1, 11):
        if slot_number > len(hits):
            slots.append({"slot": slot_number, "status": "missing", "useful": False})
            continue
        hit = hits[slot_number - 1]
        label = labels.get(hit.event_id) if labels_confirmed else None
        reference = references.get(label.human_event_id or "") if label is not None else None
        # A judgment belongs to the reviewed clip; changed clip boundaries need review.
        if label is not None and (label.start_us, label.end_us) != (hit.start_us, hit.end_us):
            label = None
        group = reference.independence_group if reference is not None else None
        duplicate = hit.event_id in seen_ids or (group is not None and group in seen_groups)
        seen_ids.add(hit.event_id)
        if group is not None:
            seen_groups.add(group)
        outside = hit.end_us > duration_us
        out_of_bounds += outside
        duplicates += duplicate
        unjudged += label is None and not duplicate
        useful = label is not None and label.grade >= 2 and not duplicate and not outside
        if useful and reference is not None:
            useful_ids.add(reference.human_event_id)
        start_error = end_error = None
        if label is not None and label.grade >= 2 and reference is not None:
            best_start, best_end = min(
                reference.usable_ranges,
                key=lambda interval: (
                    abs(hit.start_us - interval[0]) + abs(hit.end_us - interval[1])
                ),
            )
            start_error = abs(hit.start_us - best_start)
            end_error = abs(hit.end_us - best_end)
            if not duplicate:
                start_errors.append(start_error)
                end_errors.append(end_error)
        slots.append(
            {
                "slot": slot_number,
                "reportedRank": hit.rank,
                "eventId": hit.event_id,
                "humanEventId": label.human_event_id if label else None,
                "independenceGroup": group,
                "startUs": hit.start_us,
                "endUs": hit.end_us,
                "grade": label.grade if label else None,
                "reason": label.reason if label else None,
                "status": "duplicate" if duplicate else "judged" if label else "unjudged",
                "useful": False if duplicate or outside else useful if label else None,
                "outOfBounds": outside,
                "startErrorUs": start_error,
                "endErrorUs": end_error,
            }
        )
    measured = labels_confirmed and unjudged == 0
    u10 = len(useful_ids) / 10 if measured else None
    recall = len(useful_ids) / len(references) if measured and references else None
    return {
        "queryId": query.query_id,
        "text": query.text,
        "kind": query.kind,
        "mediaId": query.media_id,
        "runId": query.run_id,
        "status": "scored" if measured else "unverified_labels",
        "returnedTop10": min(10, len(hits)),
        "totalReturned": len(hits),
        "referenceIndependentEvents": len(references) if labels_confirmed else None,
        "slots": slots,
        "usefulIndependentEvents": len(useful_ids) if labels_confirmed else None,
        "duplicateSlots": duplicates,
        "duplicateRateAt10": duplicates / 10,
        "missingSlots": max(0, 10 - len(hits)),
        "unjudgedSlots": unjudged,
        "usefulRateAt10": u10,
        "mainMetricPassed": (u10 >= 0.7 if u10 is not None else None)
        if query.kind == "main"
        else None,
        "recallAt10": recall,
        "returnedPrecision": len(useful_ids) / min(10, len(hits)) if measured and hits else None,
        "missingHumanEventIds": [event_id for event_id in sorted(set(references) - useful_ids)]
        if measured
        else None,
        "negativeReturnedAny": bool(hits) if query.kind == "negative" else None,
        "timecodeErrors": {
            "startMedianUs": median(start_errors) if start_errors else None,
            "startP90Us": _percentile90(start_errors),
            "endMedianUs": median(end_errors) if end_errors else None,
            "endP90Us": _percentile90(end_errors),
            "outOfBoundsSlots": out_of_bounds,
        },
    }


def _cost_report(costs: BenchmarkCosts, duration_us: int) -> dict[str, JsonValue]:
    hours = Decimal(duration_us) / Decimal(3_600_000_000)
    cold_per_hour = None if costs.cold_cny is None else costs.cold_cny / hours
    hot_per_hour = None if costs.hot_cny is None else costs.hot_cny / hours
    verified = (
        costs.cost_status != "unverified"
        and costs.attempts_complete
        and costs.price_version is not None
        and cold_per_hour is not None
    )
    return {
        "status": costs.cost_status,
        "attemptsComplete": costs.attempts_complete,
        "priceVersion": costs.price_version,
        "coldCny": None if costs.cold_cny is None else str(costs.cold_cny),
        "hotCny": None if costs.hot_cny is None else str(costs.hot_cny),
        "coldCnyPerSourceHour": None if cold_per_hour is None else str(cold_per_hour),
        "hotCnyPerSourceHour": None if hot_per_hour is None else str(hot_per_hour),
        "coldCostGateUnder5CnyPerHour": bool(cold_per_hour < 5)
        if verified and cold_per_hour is not None
        else None,
        "hardwareCostCny": None,
    }


async def run_benchmark(
    manifest: BenchmarkManifest,
    search: SearchCallable,
    *,
    verify_media: MediaVerifier | None = None,
    runner_metadata: Mapping[str, JsonValue] | None = None,
    costs: BenchmarkCosts | None = None,
) -> dict[str, JsonValue]:
    """Run all frozen queries; a partial result cannot pass the quality gate.

    The caller supplies actual model/config identity and verifies each Completed
    run through the storage service. This function never calls a paid provider.
    """
    started_at = datetime.now(UTC)
    started = perf_counter()
    labels = manifest.human_labels
    # Keep the caller's provenance serializable without NaN or implicit string coercion.
    if runner_metadata is not None:
        json.dumps(dict(runner_metadata), allow_nan=False)
    if labels.frozen_at is not None and datetime.fromisoformat(labels.frozen_at) > started_at:
        raise ValueError("Human reference freezing cannot be after the benchmark run.")
    media_index = {(source.media_id, source.run_id): source for source in manifest.media}
    valid_sources: set[tuple[str, str]] = set()
    media_failures: list[JsonValue] = []
    if verify_media is not None:
        for source in manifest.media:
            try:
                await verify_media(source)
                valid_sources.add((source.media_id, source.run_id))
            except Exception:
                media_failures.append(
                    {
                        "mediaId": source.media_id,
                        "runId": source.run_id,
                        "code": "benchmark.media_identity_failed",
                    }
                )
    all_sources_verified = verify_media is not None and not media_failures
    results: list[dict[str, JsonValue]] = []
    for query in manifest.queries:
        began = perf_counter()
        try:
            if verify_media is not None and (query.media_id, query.run_id) not in valid_sources:
                raise ValueError("Source verification failed.")
            hits = await search(query)
            if not isinstance(hits, tuple) or any(
                not isinstance(hit, BenchmarkHit) for hit in hits
            ):
                raise ValueError("Search must return a tuple of BenchmarkHit.")
            result = _score_query(
                query,
                hits,
                media_index[(query.media_id, query.run_id)].duration_us,
                labels.confirmed,
            )
        except Exception:
            result = _score_query(
                query, (), media_index[(query.media_id, query.run_id)].duration_us, False
            )
            result["status"] = "failed"
            result["errorCode"] = "benchmark.search_failed"
        result["elapsedMs"] = round((perf_counter() - began) * 1000, 3)
        results.append(result)
    mains = [result for result in results if result["kind"] == "main"]
    scores = [result["usefulRateAt10"] for result in mains]
    eligible = (
        labels.confirmed
        and labels.independent_test_set
        and all_sources_verified
        and bool(mains)
        and all(result["status"] == "scored" for result in results)
    )
    gate = all(result["mainMetricPassed"] is True for result in mains) if eligible else None
    numeric_scores = [value for value in scores if isinstance(value, float)]
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    duration_us = sum(source.duration_us for source in manifest.media)
    cost_report = _cost_report(costs or BenchmarkCosts(), duration_us)
    if not all_sources_verified:
        cost_report["coldCostGateUnder5CnyPerHour"] = None
    return {
        "schemaVersion": 1,
        "datasetId": manifest.dataset_id,
        "labelVersion": manifest.label_version,
        "startedAt": started_at.isoformat(),
        "evidenceType": "human" if labels.confirmed else "unlabelled",
        "humanLabels": {
            "confirmed": labels.confirmed,
            "annotators": list(labels.annotators),
            "reviewed": labels.reviewed,
            "frozenAt": labels.frozen_at,
            "independentTestSet": labels.independent_test_set,
        },
        "mediaVerified": all_sources_verified,
        "media": [
            {
                "mediaId": source.media_id,
                "runId": source.run_id,
                "sha256": source.sha256,
                "durationUs": source.duration_us,
            }
            for source in manifest.media
        ],
        "mediaFailures": media_failures,
        "queries": list(results),
        "mainMacroUsefulRateAt10": sum(numeric_scores) / len(mains)
        if mains and len(numeric_scores) == len(mains)
        else None,
        "mainMinimumUsefulRateAt10": min(numeric_scores)
        if mains and len(numeric_scores) == len(mains)
        else None,
        "qualityGate": gate,
        "qualityStatus": "passed" if gate is True else "failed" if gate is False else "unverified",
        "negativeThresholdGate": None,
        "cost": cost_report,
        "elapsedMs": elapsed_ms,
        "sourceDurationUs": duration_us,
        "retrievalWallclockToSourceRatio": elapsed_ms * 1000 / duration_us,
        "runnerMetadata": dict(runner_metadata or {}),
        "humanSelectionTimeMs": None,
        "limitation": (
            "Human confirmation and test-set independence are declared by the annotators; "
            "this runner cannot authenticate them. Search timing excludes cold analysis. "
            "A metric fixture or an unlabelled demo does not establish Phase 0 acceptance."
        ),
    }
