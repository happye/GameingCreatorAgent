"""Evidence-bound observed attributes as optional ranking text; no human quality claims."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from gamingcreator.application.detail_refinement import (
    DetailRefinementRequest,
    RefinementIdentity,
    RefinementSettings,
    prepare_refinement,
    refinement_settings_hash,
    request_hash,
)
from gamingcreator.application.detail_refinement_budget import detail_matches_request, payload_hash
from gamingcreator.application.retrieval import CandidateText, RetrievalSupplement, SemanticFacet
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.actor_details import (
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    DetailAttribute,
    attribute_value_options,
    values_are_exclusive,
)
from gamingcreator.domain.errors import AppError, ExitCode

LEGACY_VERSION = "saved-detail-text-v1"
VERSION = "saved-detail-text-v2"
MAX_EVENTS = 20_000
MAX_FACETS = 20_000
MAX_BYTES = 8 * 1024 * 1024
SavedReader = Callable[
    [StoredTimeline, str], tuple[DetailRefinementRequest | None, CandidateDetail | None]
]


@dataclass(frozen=True, slots=True)
class SavedDetailCorpus:
    supplement: RetrievalSupplement
    manifest: dict[str, object]
    evidence: dict[str, dict[str, object]]


def _fail(message: str) -> AppError:
    return AppError("retrieval.detail_source", message, ExitCode.STORAGE)


def attribute_search_text(attribute: DetailAttribute) -> str:
    """A fixed bilingual vocabulary, never the model's free description."""
    value = attribute.value
    label = dict(attribute_value_options(attribute.kind))[value]
    if attribute.kind == AttributeKind.HAIR_COLOR:
        color = label if label.endswith("色") else label + "色"
        return f"{color}头发 {label}发 {value} hair"
    if attribute.kind == AttributeKind.CLOTHING_COLOR:
        color = label if label.endswith("色") else label + "色"
        return f"{color}衣服 {label}衣 {value} clothing"
    if attribute.kind == AttributeKind.HELD_CLASS and value == "staff":
        return "手持权杖 手持法杖 staff"
    prefixes = {
        AttributeKind.CLOTHING_SHAPE: "衣物形状",
        AttributeKind.HELD_SHAPE: "手持物形状",
        AttributeKind.HELD_CLASS: "手持物类别",
        AttributeKind.ACTION: "动作",
        AttributeKind.EFFECT: "可见效果",
        AttributeKind.ENVIRONMENT: "环境",
    }
    return f"{prefixes[attribute.kind]} {label} {value.replace('_', ' ')}"


def _indexable(attributes: tuple[DetailAttribute, ...]) -> tuple[DetailAttribute, ...]:
    observed = tuple(row for row in attributes if row.status == AttributeStatus.OBSERVED)
    return tuple(
        row
        for row in observed
        if not any(
            other.part_id == row.part_id
            and other.kind == row.kind
            and max(row.source_range.start_us, other.source_range.start_us)
            < min(row.source_range.end_us, other.source_range.end_us)
            and values_are_exclusive(row.kind, row.value, other.value)
            for other in observed
        )
    )


def build_saved_detail_corpus(
    timelines: tuple[StoredTimeline, ...],
    reader: SavedReader,
    *,
    profile: str,
    identity: RefinementIdentity,
    settings: RefinementSettings,
    version: str = VERSION,
) -> SavedDetailCorpus:
    total = sum(len(row.events) for row in timelines)
    if (
        profile not in {"v1", "v2", "v3", "v4"}
        or version not in {LEGACY_VERSION, VERSION}
        or not 1 <= len(timelines) <= 100
        or total > MAX_EVENTS
        or any(row.run.status != RunStatus.COMPLETED for row in timelines)
        or len({row.run.run_id for row in timelines}) != len(timelines)
        or len({row.run.asset.sha256 for row in timelines}) != len(timelines)
        or len({row.run.asset.media_id for row in timelines}) != len(timelines)
    ):
        raise _fail("请选择准确的Completed版本，最多100个不同来源及20,000事件。")
    evidence: dict[str, dict[str, object]] = {}
    texts, records = [], []
    facets: list[SemanticFacet] = []
    facet_records: list[dict[str, object]] = []
    for timeline in sorted(timelines, key=lambda row: row.run.run_id):
        for event in sorted(timeline.events, key=lambda row: row.event_id):
            request, detail = reader(timeline, event.event_id)
            if detail is None:
                continue
            expected = prepare_refinement(
                timeline, event.event_id, settings=settings, identity=identity
            ).request
            if (
                request is None
                or request != expected
                or not detail_matches_request(detail, request)
            ):
                raise _fail("已有细节与原事件、帧或所选精分析版本不一致。")
            entries: list[dict[str, object]] = []
            for shot in detail.shots:
                groups = [(None, shot.environment)] + [
                    (actor.actor_id, actor.attributes) for actor in shot.actors
                ]
                for actor_id, attributes in groups:
                    first = len(entries)
                    for attribute in _indexable(attributes):
                        entries.append(
                            {
                                "shotId": shot.shot_id,
                                "actorId": actor_id,
                                "partId": attribute.part_id,
                                "kind": attribute.kind.value,
                                "value": attribute.value,
                                "status": "observed",
                                "text": attribute_search_text(attribute),
                                "evidenceIds": list(attribute.evidence_ids),
                                "startUs": attribute.source_range.start_us,
                                "endUs": attribute.source_range.end_us,
                            }
                        )
                    if version == VERSION and len(entries) > first:
                        if len(facets) >= MAX_FACETS:
                            raise _fail("人物细节超过20,000组，请明确缩小来源范围。")
                        facet_id = (
                            "facet-"
                            + hashlib.sha256(
                                json.dumps([detail.candidate_id, shot.shot_id, actor_id]).encode()
                            ).hexdigest()[:24]
                        )
                        facts = tuple(dict.fromkeys(str(row["text"]) for row in entries[first:]))
                        if len("\n".join(facts)) > 8192 - len("passage: "):
                            raise _fail("单组人物细节文字过长，请明确缩小来源范围。")
                        facets.append(SemanticFacet(facet_id, detail.candidate_id, facts))
                        facet_records.append(
                            {
                                "facetId": facet_id,
                                "candidateId": detail.candidate_id,
                                "runId": timeline.run.run_id,
                                "eventId": event.event_id,
                                "shotId": shot.shot_id,
                                "actorId": actor_id,
                                "attributeIndexes": list(range(first, len(entries))),
                                "facts": list(facts),
                            }
                        )
            record: dict[str, object] = {
                "runId": timeline.run.run_id,
                "eventId": event.event_id,
                "candidateId": detail.candidate_id,
                "requestHash": request_hash(request),
                "payloadHash": payload_hash(detail),
                "attributes": entries,
            }
            records.append(record)
            if entries:
                evidence[detail.candidate_id] = record
                texts.append(
                    CandidateText(
                        detail.candidate_id,
                        tuple(dict.fromkeys(str(row["text"]) for row in entries)),
                    )
                )
    manifest: dict[str, object] = {
        "version": version,
        "profile": profile,
        "promptHash": identity.prompt_hash,
        "settingsHash": refinement_settings_hash(settings),
        "sources": [
            {
                "runId": row.run.run_id,
                "mediaId": row.run.asset.media_id,
                "sourceSha256": row.run.asset.sha256,
                "durationUs": row.run.asset.duration_us,
                "configHash": row.run.config_hash,
                "pipelineHash": row.run.configuration.pipeline_hash,
                "pipelineVersion": row.run.configuration.pipeline_version,
            }
            for row in sorted(timelines, key=lambda row: row.run.run_id)
        ],
        "totalVisualEvents": total,
        "publishedRefinements": len(records),
        "indexedEvents": len(texts),
        "refinements": records,
        "humanLabels": None,
        "qualityGate": None,
    }
    if version == VERSION:
        manifest["semanticFacetCount"] = len(facets)
        manifest["semanticFacets"] = facet_records
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise _fail("已有细节语料超过8MiB，请明确缩小来源范围。")
    digest = hashlib.sha256(raw).hexdigest()
    manifest["snapshotSha256"] = digest
    return SavedDetailCorpus(
        RetrievalSupplement(digest, tuple(texts), version, tuple(facets)), manifest, evidence
    )
