"""Offline refinement identity. A Completed timeline recheck is not a quality label."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.detail_refinement import (
    DetailRefinementProvider,
    DetailRefinementResult,
    DetailRefinementStore,
    RefinementIdentity,
    StoredRefinementRequest,
    canonical_request_json,
    default_refinement_identity,
    event_fingerprint,
    prepare_refinement,
    request_hash,
)
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.inspection import inspection_view
from gamingcreator.application.providers import CancellationContext, ProviderResult
from gamingcreator.application.retrieval import search_timeline
from gamingcreator.application.storage import RunConfiguration, RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.actor_details import CandidateDetail, MatchStatus
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.deepseek_vision import (
    PROMPT_VERSION_V5,
    PROMPT_VERSION_V6,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

RUN = "run-1"
MEDIA = "media-1"
EVENT = f"{RUN}:{MEDIA}:event:" + "ab" * 12
DURATION = 54_743_220
COMPLETED = "f601fb9b3e734d5ea188fc15c790acbb"
TARGET_SUFFIX = "0b8be73b204cceb6f0e37c7d"
PROJECT = Path(__file__).resolve().parents[1] / "artifacts" / "demo-phase0"


def _asset() -> MediaAsset:
    return MediaAsset(
        MEDIA,
        Path("fixture-source.mp4"),
        "b" * 64,
        (MediaStream(0, "video", Fraction(1, 1_000_000), 0, DURATION),),
        Fraction(0),
        DURATION,
        "engineering-fixture",
    )


def _timeline(
    events: tuple[SemanticEvent, ...], evidence: tuple[EvidenceReference, ...]
) -> StoredTimeline:
    configuration = RunConfiguration(
        AnalysisConfig(
            "deepseek",
            "deepseek-flash",
            10,
            10,
            schema_version=2,
            vision_prompt_version="phase0-vision-v6",
            vision_prompt_hash="c" * 64,
        ),
        Decimal("1"),
        "phase0-analyze-detailed-v2",
        "d" * 64,
    )
    run = StoredRun(RUN, _asset(), configuration, "e" * 64, RunStatus.COMPLETED, None)
    return StoredTimeline(run, (), evidence, (), events, ())


def _image(index: int, time_us: int, digest: str) -> EvidenceReference:
    return EvidenceReference(
        f"{RUN}:{MEDIA}:image:{index:06d}",
        MEDIA,
        "image",
        SourceInstant(time_us, DURATION),
        Path(f"frame-{index}.jpg"),
        digest,
        "fixture-transform-v1",
    )


def _visual_timeline() -> tuple[StoredTimeline, SemanticEvent]:
    images = (
        _image(0, 28_000_000, "1" * 64),
        _image(1, 28_500_000, "2" * 64),
        _image(2, 29_000_000, "3" * 64),
    )
    event = SemanticEvent(
        EVENT,
        MEDIA,
        RUN,
        SourceRange(28_000_000, 29_000_001, DURATION),
        ("画面左侧有白色头发的角色。",),
        ("pending",),
        tuple(item.evidence_id for item in images),
        "visual",
        "具体武器名称无法确认。",
    )
    return _timeline((event,), images), event


def test_identical_requests_share_a_hash_and_leave_base_prompt_separate() -> None:
    timeline, event = _visual_timeline()
    first = prepare_refinement(timeline, event.event_id)
    second = prepare_refinement(timeline, event.event_id)
    assert first.request is not None and second.request is not None
    assert first.request_hash == second.request_hash == request_hash(first.request)
    payload = json.loads(canonical_request_json(first.request))
    assert "basePromptVersion" not in payload and "basePromptHash" not in payload
    assert first.request.base_prompt_version == "phase0-vision-v6"
    assert first.request.base_prompt_hash == "c" * 64
    identity = default_refinement_identity()
    assert first.request.identity.prompt_hash == identity.prompt_hash
    assert identity.prompt_hash not in {
        vision_prompt_fingerprint(PROMPT_VERSION_V5),
        vision_prompt_fingerprint(PROMPT_VERSION_V6),
        first.request.base_prompt_hash,
    }
    assert payload["promptVersion"] == identity.prompt_version
    assert payload["interval"] == {
        "startUs": 28_000_000,
        "endUs": 29_000_001,
        "durationUs": DURATION,
    }
    assert [item["sourceUs"] for item in payload["evidence"]] == [
        28_000_000,
        28_500_000,
        29_000_000,
    ]
    assert all(type(item["sourceUs"]) is int for item in payload["evidence"])
    assert first.shots == () and first.status == MatchStatus.UNVERIFIED


def test_interval_or_evidence_hash_changes_the_request_hash() -> None:
    timeline, event = _visual_timeline()
    original = prepare_refinement(timeline, event.event_id)
    assert original.request is not None
    moved = replace(
        event,
        source_range=SourceRange(
            event.source_range.start_us, event.source_range.end_us + 1, DURATION
        ),
    )
    moved_timeline = replace(timeline, events=(moved,))
    moved_result = prepare_refinement(moved_timeline, event.event_id)
    assert moved_result.request is not None
    assert moved_result.request_hash != original.request_hash
    assert event_fingerprint(moved) != event_fingerprint(event)
    changed_images = tuple(
        replace(item, sha256="4" * 64) if item.evidence_id.endswith("000001") else item
        for item in timeline.evidence
    )
    changed = prepare_refinement(replace(timeline, evidence=changed_images), event.event_id)
    assert changed.request is not None
    assert changed.request_hash != original.request_hash
    assert changed.event_fingerprint == original.event_fingerprint
    assert changed.request.evidence[1].image_sha256 == "4" * 64


def test_fixture_candidate_keeps_interval_evidence_and_retrieval_identity() -> None:
    timeline, event = _visual_timeline()
    prepared = prepare_refinement(timeline, event.event_id)
    assert prepared.request is not None
    assert prepared.request.source_range == event.source_range
    assert tuple(item.evidence_id for item in prepared.request.evidence) == event.evidence_ids
    stored = {item.evidence_id: item for item in timeline.evidence}
    for item in prepared.request.evidence:
        source = stored[item.evidence_id]
        assert isinstance(source.source_time, SourceInstant)
        assert item.image_sha256 == source.sha256
        assert item.source_time.time_us == source.source_time.time_us
        assert type(item.source_time.time_us) is int
    found = asyncio.run(search_timeline(timeline, "白色", mode="lexical"))
    assert len(found.candidates) == 1
    assert prepared.request.candidate_id == found.candidates[0].candidate_id
    assert prepared.request.event_id == event.event_id


def test_nonvisual_candidate_is_unverified_without_invented_attributes() -> None:
    timeline, visual = _visual_timeline()
    audio = SemanticEvent(
        f"{RUN}:{MEDIA}:event:" + "cd" * 12,
        MEDIA,
        RUN,
        SourceRange(1_000_000, 2_000_000, DURATION),
        ("旁白说了一句话。",),
        (),
        (),
        "audio",
        None,
    )
    combined = replace(timeline, events=(visual, audio))
    before = visual.observable_facts
    result = prepare_refinement(combined, audio.event_id)
    assert result.status == MatchStatus.UNVERIFIED
    assert result.request is None and result.request_hash is None and result.shots == ()
    assert result.event_fingerprint == event_fingerprint(audio)
    assert combined.events[0].observable_facts == before
    view = inspection_view(combined, (), "fixture")
    original = next(row for row in view.timeline if row.event_id == visual.event_id)
    assert original.facts == before
    assert (original.start_us, original.end_us) == (
        visual.source_range.start_us,
        visual.source_range.end_us,
    )


def test_provider_port_is_not_used_by_preparation() -> None:
    class RejectingProvider:
        async def refine(
            self, request: object, context: CancellationContext
        ) -> ProviderResult[CandidateDetail]:
            raise AssertionError("preparation must not call the provider")

    class MemoryStore:
        def __init__(self) -> None:
            self.rows: dict[tuple[str, str], StoredRefinementRequest] = {}

        async def load_request(
            self, run_id: str, request_hash: str
        ) -> StoredRefinementRequest | None:
            return self.rows.get((run_id, request_hash))

        async def save_request(self, record: StoredRefinementRequest) -> None:
            self.rows[(record.run_id, record.request_hash)] = record

    provider = RejectingProvider()
    store = MemoryStore()
    assert isinstance(provider, DetailRefinementProvider)
    assert isinstance(store, DetailRefinementStore)
    timeline, event = _visual_timeline()
    prepared = prepare_refinement(timeline, event.event_id)
    assert prepared.request is not None and prepared.request_hash is not None
    record = StoredRefinementRequest(
        prepared.request.run_id,
        prepared.request_hash,
        canonical_request_json(prepared.request),
    )

    async def round_trip() -> str | None:
        await store.save_request(record)
        loaded = await store.load_request(record.run_id, record.request_hash)
        return None if loaded is None else loaded.canonical_json

    assert asyncio.run(round_trip()) == canonical_request_json(prepared.request)
    with pytest.raises(ValueError, match="separate"):
        RefinementIdentity(
            "phase0-vision-v6",
            vision_prompt_fingerprint(PROMPT_VERSION_V6),
            "actor-detail-refinement-schema-v1",
            "deepseek",
            "deepseek-flash",
        )
    assert DetailRefinementResult(MatchStatus.UNVERIFIED, event_fingerprint(event)).shots == ()


def test_completed_timeline_keeps_registered_source_clock() -> None:
    database = PROJECT / "timeline.sqlite3"
    if not database.is_file():
        pytest.skip("Completed timeline database is absent")

    async def load() -> StoredTimeline:
        store = await SqliteTimelineStore.open(PROJECT, read_only=True)
        try:
            return await store.load_timeline(COMPLETED)
        finally:
            await store.close()

    timeline = asyncio.run(load())
    event = next(item for item in timeline.events if item.event_id.endswith(TARGET_SUFFIX))
    prepared = prepare_refinement(timeline, event.event_id)
    assert prepared.request is not None and prepared.shots == ()
    assert prepared.request.source_range == event.source_range
    assert (
        prepared.request.base_prompt_version
        == timeline.run.configuration.analysis.vision_prompt_version
    )
    assert (
        prepared.request.base_prompt_hash == timeline.run.configuration.analysis.vision_prompt_hash
    )
    assert prepared.request.identity.prompt_hash != prepared.request.base_prompt_hash
    stored = {item.evidence_id: item for item in timeline.evidence}
    assert tuple(item.evidence_id for item in prepared.request.evidence) == tuple(
        sorted(
            (
                evidence_id
                for evidence_id in event.evidence_ids
                if stored[evidence_id].kind == "image"
            ),
            key=lambda evidence_id: (stored[evidence_id].source_time.time_us, evidence_id),
        )
    )
    for item in prepared.request.evidence:
        source = stored[item.evidence_id]
        assert isinstance(source.source_time, SourceInstant)
        assert item.image_sha256 == source.sha256
        assert item.source_time == source.source_time
        assert type(item.source_time.time_us) is int
    solo = replace(timeline, events=(event,), transcripts=())
    found = asyncio.run(search_timeline(solo, event.observable_facts[0], mode="lexical", top_k=5))
    assert prepared.request.candidate_id == found.candidates[0].candidate_id
    view = inspection_view(timeline, (), "demo-phase0")
    original = next(row for row in view.timeline if row.event_id == event.event_id)
    assert original.facts == event.observable_facts
    assert (original.start_us, original.end_us) == (
        event.source_range.start_us,
        event.source_range.end_us,
    )
