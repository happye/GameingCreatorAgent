"""Pure refinement budget decisions. No HTTP, files, or SQLite."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.detail_refinement import (
    REFINEMENT_SCHEMA_VERSION,
    REFINEMENT_TEMPORAL_SCHEMA_VERSION,
    DetailRefinementRequest,
    request_hash,
)
from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import InvocationStatus, StoredInvocation
from gamingcreator.application.temporal_entity_projection import project_temporal_scene
from gamingcreator.application.temporal_scene_codec import scene_from_payload, scene_payload
from gamingcreator.domain.actor_details import (
    DETAIL_SCHEMA_VERSION,
    DETAIL_TEMPORAL_SCHEMA_VERSION,
    ActorDetail,
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    DetailAttribute,
    DetailEvidence,
    ShotDetail,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.time import SourceInstant, SourceRange

RESULT_SCHEMA_VERSION = "actor-detail-refinement-result-v1"


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _interval(value: SourceRange) -> dict[str, int]:
    return {"startUs": value.start_us, "endUs": value.end_us, "durationUs": value.duration_us}


def _range(value: object) -> SourceRange:
    if type(value) is not dict:
        raise ValueError("A detail interval must be an object.")
    return SourceRange(value["startUs"], value["endUs"], value["durationUs"])


def _attribute(value: object) -> DetailAttribute:
    if type(value) is not dict:
        raise ValueError("A detail attribute must be an object.")
    return DetailAttribute(
        value["partId"],
        AttributeKind(value["kind"]),
        value["value"],
        AttributeStatus(value["status"]),
        tuple(value["evidenceIds"]),
        _range(value["sourceRange"]),
    )


def canonical_detail_json(detail: CandidateDetail) -> str:
    """Stable typed payload. Callers store its SHA-256 beside the request hash."""
    if type(detail) is not CandidateDetail:
        raise ValueError("A typed candidate detail is required.")

    def evidence(item: DetailEvidence) -> dict[str, object]:
        return {
            "evidenceId": item.evidence_id,
            "sha256": item.image_sha256,
            "sourceUs": item.source_time.time_us,
            "durationUs": item.source_time.duration_us,
        }

    def attribute(item: DetailAttribute) -> dict[str, object]:
        return {
            "partId": item.part_id,
            "kind": item.kind.value,
            "value": item.value,
            "status": item.status.value,
            "evidenceIds": list(item.evidence_ids),
            "sourceRange": _interval(item.source_range),
        }

    def actor(item: ActorDetail) -> dict[str, object]:
        return {
            "shotId": item.shot_id,
            "actorId": item.actor_id,
            "description": item.description,
            "attributes": [attribute(entry) for entry in item.attributes],
        }

    def shot(item: ShotDetail) -> dict[str, object]:
        return {
            "shotId": item.shot_id,
            "sourceRange": _interval(item.source_range),
            "evidenceIds": list(item.evidence_ids),
            "environment": [attribute(entry) for entry in item.environment],
            "actors": [actor(entry) for entry in item.actors],
        }

    value: dict[str, object] = {
        "runId": detail.run_id,
        "mediaId": detail.media_id,
        "eventId": detail.event_id,
        "candidateId": detail.candidate_id,
        "eventFingerprint": detail.event_fingerprint,
        "mediaSha256": detail.media_sha256,
        "configurationHash": detail.configuration_hash,
        "pipelineVersion": detail.pipeline_version,
        "basePromptVersion": detail.base_prompt_version,
        "basePromptHash": detail.base_prompt_hash,
        "detailIdentityHash": detail.detail_identity_hash,
        "sourceRange": _interval(detail.source_range),
        "evidence": [evidence(item) for item in detail.evidence],
        "shots": [shot(item) for item in detail.shots],
        "notes": list(detail.notes),
        "schemaVersion": detail.schema_version,
        "vocabularyVersion": detail.vocabulary_version,
    }
    if detail.temporal_scene is not None:
        _validate_temporal_projection(detail)
        value["temporalScene"] = scene_payload(detail.temporal_scene)
    return _canonical(value)


def _validate_temporal_projection(detail: CandidateDetail) -> None:
    if detail.temporal_scene is not None:
        projection = project_temporal_scene(detail.temporal_scene)
        if detail.shots != projection.shots or detail.notes != projection.notes:
            raise ValueError("Temporal actor projection disagrees with its saved scene.")


def detail_from_canonical(payload: str) -> CandidateDetail:
    value = json.loads(payload)
    if type(value) is not dict:
        raise ValueError("A detail payload must be an object.")
    temporal_scene = None
    if value.get("schemaVersion") == DETAIL_TEMPORAL_SCHEMA_VERSION:
        temporal_scene = scene_from_payload(value["temporalScene"])
    elif "temporalScene" in value:
        raise ValueError("Legacy details cannot contain a temporal scene.")
    evidence = tuple(
        DetailEvidence(
            item["evidenceId"],
            item["sha256"],
            SourceInstant(item["sourceUs"], item["durationUs"]),
        )
        for item in value["evidence"]
    )
    shots = tuple(
        ShotDetail(
            item["shotId"],
            _range(item["sourceRange"]),
            tuple(item["evidenceIds"]),
            tuple(_attribute(entry) for entry in item["environment"]),
            tuple(
                ActorDetail(
                    actor["shotId"],
                    actor["actorId"],
                    actor["description"],
                    tuple(_attribute(entry) for entry in actor["attributes"]),
                )
                for actor in item["actors"]
            ),
        )
        for item in value["shots"]
    )
    detail = CandidateDetail(
        value["runId"],
        value["mediaId"],
        value["eventId"],
        value["candidateId"],
        value["eventFingerprint"],
        value["mediaSha256"],
        value["configurationHash"],
        value["pipelineVersion"],
        value["basePromptVersion"],
        value["basePromptHash"],
        value["detailIdentityHash"],
        _range(value["sourceRange"]),
        evidence,
        shots,
        tuple(value["notes"]),
        schema_version=value["schemaVersion"],
        vocabulary_version=value["vocabularyVersion"],
        temporal_scene=temporal_scene,
    )
    _validate_temporal_projection(detail)
    return detail


def detail_matches_request(detail: CandidateDetail, request: DetailRefinementRequest) -> bool:
    try:
        _validate_temporal_projection(detail)
    except ValueError:
        return False
    expected_schema = (
        DETAIL_TEMPORAL_SCHEMA_VERSION
        if request.identity.schema_version == REFINEMENT_TEMPORAL_SCHEMA_VERSION
        else DETAIL_SCHEMA_VERSION
    )
    return (
        request.identity.schema_version
        in {REFINEMENT_SCHEMA_VERSION, REFINEMENT_TEMPORAL_SCHEMA_VERSION}
        and detail.schema_version == expected_schema
        and detail.run_id == request.run_id
        and detail.event_id == request.event_id
        and detail.candidate_id == request.candidate_id
        and detail.event_fingerprint == request.event_fingerprint
        and detail.media_sha256 == request.media_sha256
        and detail.configuration_hash == request.configuration_hash
        and detail.pipeline_version == request.pipeline_version
        and detail.source_range == request.source_range
        and tuple(
            (item.evidence_id, item.image_sha256, item.source_time) for item in detail.evidence
        )
        == tuple(
            (item.evidence_id, item.image_sha256, item.source_time) for item in request.evidence
        )
        and detail.detail_identity_hash == request.identity.prompt_hash
        and detail.base_prompt_version == request.base_prompt_version
        and detail.base_prompt_hash == request.base_prompt_hash
    )


@dataclass(frozen=True, slots=True)
class BudgetCharge:
    budget_id: str
    attempt: int
    request_hash: str
    run_id: str
    reservation_cny: Decimal
    frames: int
    cost_cny: Decimal | None
    revision: str | None


def charge_invocation(charge: BudgetCharge) -> StoredInvocation:
    """One ledger line. Unknown cost stays unknown so restore keeps the reservation."""
    if (
        type(charge.attempt) is not int
        or charge.attempt < 1
        or type(charge.frames) is not int
        or charge.frames < 0
        or not isinstance(charge.reservation_cny, Decimal)
    ):
        raise ValueError("A budget charge needs an attempt, frames, and a Decimal reservation.")
    usage = ProviderUsage(
        original_cost=charge.cost_cny,
        currency=None if charge.cost_cny is None else "CNY",
        cost_cny=charge.cost_cny,
        cost_status=CostStatus.UNVERIFIED if charge.cost_cny is None else CostStatus.ESTIMATED,
    )
    metadata = InvocationMetadata(
        "deepseek",
        "deepseek-flash",
        None,
        charge.revision,
        "actor-detail-refinement-v1",
        "actor-detail-refinement-schema-v1",
        charge.attempt,
        usage,
        execution_details=json.dumps(
            {"inputFrames": charge.frames, "reservationCny": format(charge.reservation_cny, "f")},
            sort_keys=True,
        ),
    )
    return StoredInvocation(
        f"{charge.budget_id}:{charge.attempt}:{charge.request_hash}",
        charge.run_id,
        "detail-refinement",
        charge.request_hash,
        InvocationStatus.COMPLETED if charge.cost_cny is not None else InvocationStatus.FAILED,
        metadata,
        None if charge.cost_cny is not None else "budget.unknown",
    )


def reserve_attempt(
    ceiling: Decimal,
    charges: tuple[BudgetCharge, ...],
    frames: int,
    reservation: Decimal,
    *,
    max_requests: int = 10_000,
) -> BudgetLedger:
    """Restore every charge, then reserve. A new directory must pass the same charges."""
    if not isinstance(ceiling, Decimal) or not isinstance(reservation, Decimal):
        raise AppError("budget.estimate_invalid", "精分析预算必须是 Decimal。", ExitCode.BUDGET)
    ledger = BudgetLedger(ceiling, max_requests, max(1, max_requests * max(frames, 1)))
    ledger.restore(tuple(charge_invocation(item) for item in charges))
    ledger.reserve(frames, reservation)
    return ledger


def payload_hash(detail: CandidateDetail) -> str:
    return hashlib.sha256(canonical_detail_json(detail).encode("utf-8")).hexdigest()


def assert_same_request(request: DetailRefinementRequest, digest: str) -> None:
    if digest != request_hash(request):
        raise AppError(
            "refinement.hash_mismatch",
            "精分析请求哈希与冻结规范不一致。",
            ExitCode.STORAGE,
            request.run_id,
        )


REQUEST_DOCUMENT_SCHEMA_VERSION = 1
_HASH64 = re.compile(r"[0-9a-f]{64}\Z")

REFINEMENT_DOCUMENT_FORBIDDEN_CLAIM_KEYS = (
    "humanLabels",
    "qualityGate",
    "formalAcceptancePassed",
    "acceptanceStatus",
    "humanEvalPassed",
    "f006Passed",
    "f009Passed",
    "f010Passed",
)


def _refinement_contract_fail(message: str, run_id: str | None = None) -> AppError:
    return AppError("refinement.contract", message, ExitCode.STORAGE, run_id)


def assert_refinement_request_document_contract(document: dict[str, object]) -> None:
    """Refuse sidecar request.json that drifts hash, fingerprint, or claims acceptance."""
    if type(document) is not dict:
        raise _refinement_contract_fail("精分析请求投影必须是对象。")
    run_id = document.get("runId") if type(document.get("runId")) is str else None
    if document.get("schemaVersion") != REQUEST_DOCUMENT_SCHEMA_VERSION:
        raise _refinement_contract_fail("精分析请求 schemaVersion 无效。", run_id)
    digest = document.get("requestHash")
    if type(digest) is not str or not _HASH64.fullmatch(digest):
        raise _refinement_contract_fail("精分析请求 requestHash 无效。", run_id)
    if type(document.get("runId")) is not str or not document["runId"]:
        raise _refinement_contract_fail("精分析请求 runId 无效。", run_id)
    fingerprint = document.get("eventFingerprint")
    if type(fingerprint) is not str or not _HASH64.fullmatch(fingerprint):
        raise _refinement_contract_fail("精分析请求 eventFingerprint 无效。", run_id)
    canonical = document.get("canonicalJson")
    if type(canonical) is not str or not canonical:
        raise _refinement_contract_fail("精分析请求 canonicalJson 无效。", run_id)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != digest:
        raise _refinement_contract_fail("精分析请求哈希与 canonicalJson 不一致。", run_id)
    try:
        payload = json.loads(canonical)
    except (TypeError, ValueError, RecursionError):
        raise _refinement_contract_fail("精分析请求 canonicalJson 无法解析。", run_id) from None
    if type(payload) is not dict:
        raise _refinement_contract_fail("精分析请求 canonicalJson 必须是对象。", run_id)
    if payload.get("eventFingerprint") != fingerprint:
        raise _refinement_contract_fail("精分析请求指纹与规范载荷不一致。", run_id)
    if payload.get("baseRunId") != document.get("runId"):
        raise _refinement_contract_fail("精分析请求 runId 与规范载荷不一致。", run_id)
    if type(document.get("basePromptVersion")) is not str or not document["basePromptVersion"]:
        raise _refinement_contract_fail("精分析请求 basePromptVersion 无效。", run_id)
    prompt_hash = document.get("basePromptHash")
    if type(prompt_hash) is not str or not _HASH64.fullmatch(prompt_hash):
        raise _refinement_contract_fail("精分析请求 basePromptHash 无效。", run_id)
    for key in REFINEMENT_DOCUMENT_FORBIDDEN_CLAIM_KEYS:
        if key in document and document.get(key) is not None:
            raise _refinement_contract_fail(f"精分析请求不能声称 {key}。", run_id)
        if key in payload and payload.get(key) is not None:
            raise _refinement_contract_fail(f"精分析请求规范载荷不能声称 {key}。", run_id)
    candidate_id = payload.get("candidateId")
    if type(candidate_id) is not str or not candidate_id:
        raise _refinement_contract_fail("精分析请求 candidateId 无效。", run_id)
    media_sha = payload.get("mediaSha256")
    if type(media_sha) is not str or not _HASH64.fullmatch(media_sha):
        raise _refinement_contract_fail("精分析请求 mediaSha256 无效。", run_id)
    configuration_hash = payload.get("configurationHash")
    if type(configuration_hash) is not str or not _HASH64.fullmatch(configuration_hash):
        raise _refinement_contract_fail("精分析请求 configurationHash 无效。", run_id)
    interval = payload.get("interval")
    if type(interval) is not dict:
        raise _refinement_contract_fail("精分析请求 interval 无效。", run_id)
    start_us = interval.get("startUs")
    end_us = interval.get("endUs")
    duration_us = interval.get("durationUs")
    if type(start_us) is not int or type(end_us) is not int or type(duration_us) is not int:
        raise _refinement_contract_fail("精分析请求 interval 时间字段无效。", run_id)
    if not (0 <= start_us < end_us <= duration_us):
        raise _refinement_contract_fail("精分析请求 interval 时间范围无效。", run_id)
    evidence = payload.get("evidence")
    if type(evidence) is not list or not evidence:
        raise _refinement_contract_fail("精分析请求 evidence 无效。", run_id)


def assert_refinement_result_document_contract(document: dict[str, object]) -> None:
    """Refuse sidecar result.json that forges acceptance or breaks payload hashing."""
    if type(document) is not dict:
        raise _refinement_contract_fail("精分析结果投影必须是对象。")
    if document.get("schemaVersion") != RESULT_SCHEMA_VERSION:
        raise _refinement_contract_fail("精分析结果 schemaVersion 无效。")
    digest = document.get("requestHash")
    if type(digest) is not str or not _HASH64.fullmatch(digest):
        raise _refinement_contract_fail("精分析结果 requestHash 无效。")
    payload_json = document.get("payloadJson")
    if type(payload_json) is not str or not payload_json:
        raise _refinement_contract_fail("精分析结果 payloadJson 必须是规范字符串。")
    payload_digest = document.get("payloadHash")
    if type(payload_digest) is not str or not _HASH64.fullmatch(payload_digest):
        raise _refinement_contract_fail("精分析结果 payloadHash 无效。")
    if hashlib.sha256(payload_json.encode("utf-8")).hexdigest() != payload_digest:
        raise _refinement_contract_fail("精分析结果 payloadHash 与载荷不一致。")
    try:
        detail = detail_from_canonical(payload_json)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _refinement_contract_fail("精分析结果载荷不是有效主体结构。") from None
    if canonical_detail_json(detail) != payload_json:
        raise _refinement_contract_fail("精分析结果载荷不是冻结规范格式。")
    actual_model = document.get("actualModel")
    if actual_model is not None and type(actual_model) is not str:
        raise _refinement_contract_fail("精分析结果 actualModel 无效。")
    model_revision = document.get("modelRevision")
    if model_revision is not None and type(model_revision) is not str:
        raise _refinement_contract_fail("精分析结果 modelRevision 无效。")
    cost = document.get("costCny")
    if cost is not None and type(cost) is not str:
        raise _refinement_contract_fail("精分析结果 costCny 必须是十进制字符串或空。")
    if "metadata" in document and type(document.get("metadata")) is not dict:
        raise _refinement_contract_fail("精分析结果 metadata 必须是对象。")
    for key in REFINEMENT_DOCUMENT_FORBIDDEN_CLAIM_KEYS:
        if key in document and document.get(key) is not None:
            raise _refinement_contract_fail(f"精分析结果不能声称 {key}。")


def assert_refinement_sidecar_pair_contract(
    request_document: dict[str, object],
    result_document: dict[str, object] | None,
) -> None:
    """Readonly对照：request／result 同哈希，且结果主体挂回请求指纹与 run。"""
    assert_refinement_request_document_contract(request_document)
    if result_document is None:
        return
    assert_refinement_result_document_contract(result_document)
    run_id = request_document.get("runId") if type(request_document.get("runId")) is str else None
    if result_document.get("requestHash") != request_document.get("requestHash"):
        raise _refinement_contract_fail("精分析 request／result 的 requestHash 不一致。", run_id)
    payload_json = result_document["payloadJson"]
    assert type(payload_json) is str
    detail = detail_from_canonical(payload_json)
    if detail.run_id != request_document.get("runId"):
        raise _refinement_contract_fail("精分析结果 runId 与请求不一致。", run_id)
    if detail.event_fingerprint != request_document.get("eventFingerprint"):
        raise _refinement_contract_fail("精分析结果指纹与请求不一致。", run_id)
    canonical = request_document.get("canonicalJson")
    assert type(canonical) is str
    payload = json.loads(canonical)
    if detail.candidate_id != payload.get("candidateId"):
        raise _refinement_contract_fail("精分析结果 candidateId 与请求不一致。", run_id)
    if detail.media_sha256 != payload.get("mediaSha256"):
        raise _refinement_contract_fail("精分析结果 mediaSha256 与请求不一致。", run_id)
    if detail.configuration_hash != payload.get("configurationHash"):
        raise _refinement_contract_fail("精分析结果 configurationHash 与请求不一致。", run_id)
    interval = payload.get("interval")
    assert type(interval) is dict
    source_range = detail.source_range
    if (
        source_range.start_us != interval.get("startUs")
        or source_range.end_us != interval.get("endUs")
        or source_range.duration_us != interval.get("durationUs")
    ):
        raise _refinement_contract_fail("精分析结果时间范围与请求 interval 不一致。", run_id)
    if detail.base_prompt_hash != request_document.get("basePromptHash"):
        raise _refinement_contract_fail("精分析结果 basePromptHash 与请求不一致。", run_id)
    if detail.base_prompt_version != request_document.get("basePromptVersion"):
        raise _refinement_contract_fail("精分析结果 basePromptVersion 与请求不一致。", run_id)
    event_id = detail.event_id
    # Owned timelines use "{runId}:{mediaId}:..."; synthetic fixtures may use bare ids.
    if (
        type(event_id) is str
        and ":" in event_id
        and not event_id.startswith(f"{detail.run_id}:{detail.media_id}:")
    ):
        raise _refinement_contract_fail("精分析结果 eventId 不属于请求媒体。", run_id)


def refinement_sidecar_contract_gaps(
    request_document: dict[str, object],
    result_document: dict[str, object] | None = None,
) -> tuple[str, ...]:
    """List request／result contract gaps without raising. Empty means pair is clean."""
    gaps: list[str] = []
    try:
        assert_refinement_sidecar_pair_contract(request_document, result_document)
    except AppError as error:
        if error.code != "refinement.contract":
            gaps.append(f"unexpected:{error.code}")
        else:
            gaps.append(error.message)
    return tuple(gaps)
