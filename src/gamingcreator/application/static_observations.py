"""Pure static declaration identity verification, support matching, and result documents."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Protocol

from gamingcreator.application.retrieval import refuse_unsearchable_run
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.actor_details import (
    AttributeConstraint,
    AttributeStatus,
    values_are_exclusive,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.static_observations import (
    MAX_STATIC_PACKAGE_BYTES,
    STATIC_IMPORT_RESULT_SCHEMA_VERSION,
    STATIC_KIND,
    STATIC_QUERY_SCHEMA_VERSION,
    STATIC_SEARCH_RESULT_SCHEMA_VERSION,
    StaticActor,
    StaticAttribute,
    StaticAttributeSupport,
    StaticObservation,
    StaticObservationMatch,
    StaticObservationPackage,
    StaticQuery,
    canonical_observation_json,
    canonical_package_json,
    canonical_query_json,
    observation_id,
    package_sha256,
    query_sha256,
    sorted_supports,
    static_source_range,
)
from gamingcreator.domain.time import SourceInstant, SourceRange

PublishStatus = Literal["created", "unchanged"]

_CLAIM_MEANING = (
    "只说明导入的本地静态声明在同一个注册帧、同一主体与部件上支持这些条件；"
    "真实外观未验证，不是自动识别、提供方核实或验收结论。"
)


@dataclass(frozen=True, slots=True)
class StaticObservationRecord:
    observation_id: str
    local_observation_id: str
    evidence_id: str
    source_time_us: int
    image_sha256: str
    artifact_path: str
    source_path: str
    observation_json: str


@dataclass(frozen=True, slots=True)
class StoredStaticCollection:
    run_id: str
    collection_id: str
    package_sha256: str
    canonical_payload: str
    package: StaticObservationPackage
    records: tuple[StaticObservationRecord, ...]


@dataclass(frozen=True, slots=True)
class StaticCollectionArtifact:
    package: StaticObservationPackage
    package_sha256: str
    canonical_payload: str
    records: tuple[StaticObservationRecord, ...]


@dataclass(frozen=True, slots=True)
class RegisteredFrame:
    observation: StaticObservation
    evidence_id: str
    image_sha256: str
    artifact_path: str
    source_path: str
    source_time_us: int
    source_range: SourceRange


class StaticObservationStore(Protocol):
    def load_collection(self, run_id: str, collection_id: str) -> StoredStaticCollection: ...

    def publish(self, artifact: StaticCollectionArtifact) -> PublishStatus: ...


def _identity_error() -> AppError:
    return AppError(
        "static.identity",
        "静态声明与当前已完成任务、媒体、配置或注册证据不一致。",
        ExitCode.STORAGE,
    )


def _integrity_error() -> AppError:
    return AppError(
        "static.integrity",
        "静态观察库的声明、哈希或存储投影不一致。",
        ExitCode.STORAGE,
    )


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        raise _identity_error() from None
    return digest.hexdigest()


def _image_evidence(evidence: EvidenceReference) -> SourceInstant:
    if evidence.kind != "image" or type(evidence.source_time) is not SourceInstant:
        raise _identity_error()
    return evidence.source_time


def verify_package_against_timeline(
    package: StaticObservationPackage, timeline: StoredTimeline
) -> tuple[RegisteredFrame, ...]:
    """Recheck Completed/coverage eligibility and exact registered identity and files."""
    run = timeline.run
    refuse_unsearchable_run(run)
    if run.status is not RunStatus.COMPLETED:
        raise _identity_error()
    if (
        package.run_id != run.run_id
        or package.media_id != run.asset.media_id
        or package.source_sha256 != run.asset.sha256
        or package.config_hash != run.config_hash
        or package.pipeline_version != run.configuration.pipeline_version
        or (
            package.pipeline_hash is not None
            and package.pipeline_hash != run.configuration.pipeline_hash
        )
    ):
        raise _identity_error()
    if not run.asset.source_path.is_file():
        raise _identity_error()
    evidence_by_id: dict[str, EvidenceReference] = {}
    for evidence in timeline.evidence:
        if evidence.evidence_id in evidence_by_id:
            raise _identity_error()
        evidence_by_id[evidence.evidence_id] = evidence
    frames: list[RegisteredFrame] = []
    for observation in package.observations:
        registered = evidence_by_id.get(observation.evidence_id)
        if registered is None:
            raise _identity_error()
        instant = _image_evidence(registered)
        if (
            registered.media_id != package.media_id
            or registered.source_time.duration_us != run.asset.duration_us
            or not registered.evidence_id.startswith(f"{package.run_id}:")
            or len(registered.sha256) != 64
        ):
            raise _identity_error()
        if _hash_file(str(registered.artifact_path)) != registered.sha256:
            raise _identity_error()
        frames.append(
            RegisteredFrame(
                observation,
                registered.evidence_id,
                registered.sha256,
                str(registered.artifact_path),
                str(run.asset.source_path),
                instant.time_us,
                static_source_range(instant),
            )
        )
    return tuple(frames)


def build_static_collection_artifact(
    package: StaticObservationPackage, timeline: StoredTimeline
) -> StaticCollectionArtifact:
    """Bind the declared package to current registered frames before one atomic publish."""
    frames = verify_package_against_timeline(package, timeline)
    canonical_payload = canonical_package_json(package)
    if len(canonical_payload.encode("utf-8")) > MAX_STATIC_PACKAGE_BYTES:
        raise AppError(
            "static.input",
            "静态声明规范化后超过1MiB。",
            ExitCode.INPUT,
        )
    records = tuple(
        StaticObservationRecord(
            observation_id(package, frame.observation),
            frame.observation.local_observation_id,
            frame.evidence_id,
            frame.source_time_us,
            frame.image_sha256,
            frame.artifact_path,
            frame.source_path,
            canonical_observation_json(frame.observation),
        )
        for frame in frames
    )
    return StaticCollectionArtifact(
        package,
        package_sha256(package),
        canonical_payload,
        records,
    )


def verify_stored_collection(
    stored: StoredStaticCollection, timeline: StoredTimeline
) -> StaticCollectionArtifact:
    """Rebuild the exact projection from the payload and current timeline; no stale rows."""
    if (
        stored.package.run_id != stored.run_id
        or stored.package.collection_id != stored.collection_id
    ):
        raise _integrity_error()
    expected = build_static_collection_artifact(stored.package, timeline)
    if (
        stored.package_sha256 != expected.package_sha256
        or stored.canonical_payload != expected.canonical_payload
    ):
        raise _integrity_error()
    actual_by_id: dict[str, StaticObservationRecord] = {}
    for record in stored.records:
        if record.observation_id in actual_by_id:
            raise _integrity_error()
        actual_by_id[record.observation_id] = record
    for record in expected.records:
        if actual_by_id.pop(record.observation_id, None) != record:
            raise _integrity_error()
    if actual_by_id:
        raise _integrity_error()
    return expected


def _has_part_conflict(attributes: tuple[StaticAttribute, ...], part_id: str) -> bool:
    """Mutually exclusive observed values on one real part block support.

    Source ``part_group`` is declaration metadata. The query's ``part_group`` is a
    query-local variable, so conflicts must be checked across every source group that
    contains the chosen real ``part_id``.
    """
    values = tuple(
        attribute
        for attribute in attributes
        if attribute.status is AttributeStatus.OBSERVED and attribute.part_id == part_id
    )
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            if left.kind == right.kind and values_are_exclusive(left.kind, left.value, right.value):
                return True
    return False


def _support_for_actor(
    actor: StaticActor,
    conditions: tuple[AttributeConstraint, ...],
    evidence_id: str,
    source_range: SourceRange,
) -> tuple[StaticAttributeSupport, ...] | None:
    """Support one actor by binding each query-local group to one real part id.

    Query ``part_group`` values only group conditions; they are not compared with the
    source attribute's declaration ``part_group``. Conditions in one query group must
    bind to the same real ``part_id``; separate query groups may bind separately.
    """
    observed = tuple(
        attribute for attribute in actor.attributes if attribute.status is AttributeStatus.OBSERVED
    )
    uncertain = {
        (attribute.kind, attribute.value)
        for attribute in actor.attributes
        if attribute.status is AttributeStatus.UNCERTAIN
    }
    if any((condition.kind, condition.value) in uncertain for condition in conditions):
        return None
    grouped: dict[str, list[AttributeConstraint]] = {}
    for condition in conditions:
        grouped.setdefault(condition.part_group, []).append(condition)
    bindings: dict[str, str] = {}
    for query_group in sorted(grouped):
        candidates: set[str] | None = None
        for condition in grouped[query_group]:
            parts = {
                attribute.part_id
                for attribute in observed
                if attribute.kind == condition.kind and attribute.value == condition.value
            }
            if not parts:
                return None
            candidates = parts if candidates is None else candidates & parts
            if not candidates:
                return None
        assert candidates is not None
        for part_id in sorted(candidates):
            if not _has_part_conflict(observed, part_id):
                bindings[query_group] = part_id
                break
        else:
            return None
    return tuple(
        StaticAttributeSupport(
            condition,
            bindings[condition.part_group],
            evidence_id,
            source_range,
        )
        for condition in conditions
    )


def match_static_observations(
    artifact: StaticCollectionArtifact,
    query: StaticQuery,
    duration_us: int,
) -> tuple[StaticObservationMatch, ...]:
    """Match all conditions on one actor of one registered frame, never pooled elsewhere."""
    package = artifact.package
    if query.run_id != package.run_id or query.collection_id != package.collection_id:
        raise _identity_error()
    records_by_observation = {record.observation_id: record for record in artifact.records}
    matches: list[StaticObservationMatch] = []
    for observation in package.observations:
        record = records_by_observation.get(observation_id(package, observation))
        if record is None or record.source_time_us >= duration_us:
            raise _integrity_error()
        source_range = SourceRange(record.source_time_us, record.source_time_us + 1, duration_us)
        for actor in observation.actors:
            supported = _support_for_actor(
                actor,
                query.constraint.actor_all,
                record.evidence_id,
                source_range,
            )
            if supported is None:
                continue
            matches.append(
                StaticObservationMatch(
                    record.observation_id,
                    observation.local_observation_id,
                    actor.actor_id,
                    record.evidence_id,
                    record.image_sha256,
                    record.artifact_path,
                    record.source_path,
                    source_range,
                    sorted_supports(supported),
                )
            )
    matches.sort(
        key=lambda match: (match.source_range.start_us, match.observation_id, match.actor_id)
    )
    return tuple(matches)


def _range_document(source_range: SourceRange) -> dict[str, int]:
    return {
        "startUs": source_range.start_us,
        "endUs": source_range.end_us,
        "durationUs": source_range.duration_us,
    }


def _provenance_document(package: StaticObservationPackage) -> dict[str, str]:
    return {
        "sourceNote": package.provenance.source_note,
        "sourcePayloadSha256": package.provenance.source_payload_sha256,
        "sourcePayloadVersion": package.provenance.source_payload_version,
    }


def _support_document(support: StaticAttributeSupport) -> dict[str, object]:
    return {
        "kind": support.condition.kind.value,
        "value": support.condition.value,
        "partGroup": support.condition.part_group,
        "partId": support.part_id,
        "evidenceId": support.evidence_id,
        "sourceRange": _range_document(support.source_range),
    }


def _match_document(match: StaticObservationMatch, media_id: str) -> dict[str, object]:
    return {
        "kind": STATIC_KIND,
        "observationId": match.observation_id,
        "localObservationId": match.local_observation_id,
        "actorId": match.actor_id,
        "mediaId": media_id,
        "sourceTimeUs": match.source_range.start_us,
        "sourceUs": match.source_range.start_us,
        "startUs": match.source_range.start_us,
        "endUs": match.source_range.end_us,
        "durationUs": match.source_range.duration_us,
        "sourceRange": _range_document(match.source_range),
        "evidenceId": match.evidence_id,
        "evidenceIds": [match.evidence_id],
        "imageSha256": match.image_sha256,
        "artifactPath": match.artifact_path,
        "sourcePath": match.source_path,
        "supportedAttributes": [_support_document(support) for support in match.supported],
        "claim": "imported_local_declaration_only",
    }


def _query_document(query: StaticQuery) -> dict[str, object]:
    parsed = json.loads(canonical_query_json(query))
    if type(parsed) is not dict:
        raise _integrity_error()
    return parsed


def _local_flags() -> dict[str, object]:
    return {
        "claim": "imported_local_declaration_only",
        "claimMeaning": _CLAIM_MEANING,
        "paidRequestsSent": 0,
        "paidRequestsSentScope": "local_operation_only",
        "localPaidRequestsSent": 0,
        "sourceCostCny": None,
        "sourceCostStatus": "unknown",
        "providerVerified": False,
        "billingVerified": False,
        "visualVerified": None,
        "humanLabels": None,
        "qualityGate": None,
        "f006Passed": False,
        "f009Passed": False,
        "f010Passed": False,
        "modelInvocations": 0,
    }


def build_static_import_result(
    artifact: StaticCollectionArtifact, status: PublishStatus
) -> dict[str, object]:
    package = artifact.package
    document: dict[str, object] = {
        "schemaVersion": STATIC_IMPORT_RESULT_SCHEMA_VERSION,
        "status": status,
        "runId": package.run_id,
        "collectionId": package.collection_id,
        "mediaId": package.media_id,
        "collectionSha256": artifact.package_sha256,
        "packageSha256": artifact.package_sha256,
        "observationCount": len(package.observations),
        "actorCount": sum(len(observation.actors) for observation in package.observations),
        "provenance": _provenance_document(package),
        "sourcePath": artifact.records[0].source_path,
        "sourceSha256": package.source_sha256,
    }
    document.update(_local_flags())
    return document


def build_static_search_report(
    stored: StoredStaticCollection, query: StaticQuery, timeline: StoredTimeline
) -> dict[str, object]:
    if (
        query.run_id != stored.run_id
        or query.collection_id != stored.collection_id
        or query.run_id != stored.package.run_id
        or query.collection_id != stored.package.collection_id
    ):
        raise _identity_error()
    artifact = verify_stored_collection(stored, timeline)
    duration_us = timeline.run.asset.duration_us
    matches = match_static_observations(artifact, query, duration_us)
    package = artifact.package
    document: dict[str, object] = {
        "schemaVersion": STATIC_SEARCH_RESULT_SCHEMA_VERSION,
        "runId": package.run_id,
        "collectionId": package.collection_id,
        "mediaId": package.media_id,
        "collectionSha256": artifact.package_sha256,
        "packageSha256": artifact.package_sha256,
        "querySchemaVersion": STATIC_QUERY_SCHEMA_VERSION,
        "querySha256": query_sha256(query),
        "query": _query_document(query),
        "matchCount": len(matches),
        "matches": [_match_document(match, package.media_id) for match in matches],
        "provenance": _provenance_document(package),
        "sourcePath": str(timeline.run.asset.source_path),
        "sourceSha256": package.source_sha256,
        "durationUs": duration_us,
    }
    document.update(_local_flags())
    return document
