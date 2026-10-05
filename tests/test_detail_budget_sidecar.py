"""Sidecar and shared budget rules. No provider HTTP and no gameplay label."""

import asyncio
import json
import os
import subprocess
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.detail_refinement import prepare_refinement, request_hash
from gamingcreator.application.detail_refinement_budget import canonical_detail_json
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.inspection import inspection_view
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.storage import RunConfiguration, RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.actor_details import (
    ActorDetail,
    CandidateDetail,
    MatchStatus,
    ShotDetail,
    source_range_for_evidence,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.detail_refinement_sidecar import (
    BudgetWriterLock,
    begin_attempt,
    reuse_or_refuse,
    send_refinement,
    sidecar_directory,
    unchanged_source_event,
)

RUN = "run-1"
MEDIA = "media-1"
EVENT = f"{RUN}:{MEDIA}:event:" + "ab" * 12
OTHER = f"{RUN}:{MEDIA}:event:" + "cd" * 12
DURATION = 54_743_220


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


def _event(
    event_id: str, images: tuple[EvidenceReference, ...], facts: tuple[str, ...]
) -> SemanticEvent:
    return SemanticEvent(
        event_id,
        MEDIA,
        RUN,
        SourceRange(images[0].source_time.time_us, images[-1].source_time.time_us + 1, DURATION),
        facts,
        ("pending",),
        tuple(item.evidence_id for item in images),
        "visual",
        "具体名称无法确认。",
    )


def timeline() -> StoredTimeline:
    first = (
        _image(0, 28_000_000, "1" * 64),
        _image(1, 28_500_000, "2" * 64),
        _image(2, 29_000_000, "3" * 64),
    )
    second = (
        _image(3, 35_000_000, "4" * 64),
        _image(4, 35_500_000, "5" * 64),
    )
    events = (
        _event(EVENT, first, ("画面左侧有白色头发的角色。",)),
        _event(OTHER, second, ("画面中间有红色外套。",)),
    )
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
    return StoredTimeline(run, (), first + second, (), events, ())


def _detail(request: object) -> CandidateDetail:
    assert hasattr(request, "evidence")
    from gamingcreator.application.detail_refinement import DetailRefinementRequest

    assert type(request) is DetailRefinementRequest
    shot = ShotDetail(
        "shot-1",
        source_range_for_evidence(request.evidence),
        tuple(item.evidence_id for item in request.evidence),
        (),
        (ActorDetail("shot-1", "actor-1", "画面中的可见主体，控制身份未确认。", ()),),
    )
    assert request.base_prompt_hash is not None
    return CandidateDetail(
        request.run_id,
        MEDIA,
        request.event_id,
        request.candidate_id,
        request.event_fingerprint,
        request.media_sha256,
        request.configuration_hash,
        request.pipeline_version,
        request.base_prompt_version,
        request.base_prompt_hash,
        request.identity.prompt_hash,
        request.source_range,
        request.evidence,
        (shot,),
    )


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def refine(
        self, request: object, context: CancellationContext
    ) -> ProviderResult[CandidateDetail]:
        self.calls += 1
        return ProviderResult(
            ProviderStatus.COMPLETED,
            _detail(request),
            InvocationMetadata(
                "deepseek",
                "deepseek-flash",
                None,
                None,
                "actor-detail-refinement-v1",
                "actor-detail-refinement-schema-v1",
                1,
                ProviderUsage(),
            ),
        )


def test_missing_sidecar_is_unverified_and_keeps_the_source_event(tmp_path: Path) -> None:
    stored = timeline()
    event = stored.events[0]
    before = (event.observable_facts, event.source_range, event.evidence_ids)
    outcome = reuse_or_refuse(tmp_path, stored, event.event_id)
    assert outcome.status == MatchStatus.UNVERIFIED
    assert outcome.detail is None and outcome.reused is False
    assert outcome.request is not None
    assert outcome.request_hash == request_hash(outcome.request)
    assert unchanged_source_event(stored, event.event_id).observable_facts == before[0]
    view = inspection_view(stored, (), "budget-sidecar")
    row = next(item for item in view.timeline if item.event_id == event.event_id)
    assert row.facts == before[0]
    assert (row.start_us, row.end_us) == (before[1].start_us, before[1].end_us)
    assert row.evidence_ids == before[2]


def test_same_key_reuse_makes_zero_extra_provider_calls(tmp_path: Path) -> None:
    stored = timeline()
    provider = CountingProvider()
    first = asyncio.run(
        send_refinement(
            tmp_path,
            stored,
            EVENT,
            provider,
            budget_id="budget-a",
            ceiling=Decimal("5"),
            reservation=Decimal("1"),
        )
    )
    assert provider.calls == 1 and first.detail is not None and first.reused is False
    assert first.request_hash == request_hash(first.request)  # type: ignore[arg-type]
    second = asyncio.run(
        send_refinement(
            tmp_path,
            stored,
            EVENT,
            provider,
            budget_id="budget-a",
            ceiling=Decimal("5"),
            reservation=Decimal("1"),
        )
    )
    assert provider.calls == 1
    assert second.reused is True and second.detail is not None
    assert second.status != MatchStatus.FULL
    assert second.request_hash == first.request_hash
    raw = json.loads(
        (sidecar_directory(tmp_path, RUN, second.request_hash) / "result.json").read_text(
            encoding="utf-8"
        )
    )
    assert raw["costCny"] is None
    assert raw["payloadJson"] == canonical_detail_json(second.detail)


def test_explicit_retry_keeps_both_attempts_and_interrupt_blocks_send(tmp_path: Path) -> None:
    stored = timeline()
    prepared = prepare_refinement(stored, EVENT)
    assert prepared.request is not None
    number = begin_attempt(
        tmp_path,
        prepared.request,
        budget_id="budget-a",
        ceiling=Decimal("10"),
        reservation=Decimal("1"),
        retry=False,
    )
    assert number == 1
    provider = CountingProvider()
    with pytest.raises(AppError) as blocked:
        asyncio.run(
            send_refinement(
                tmp_path,
                stored,
                EVENT,
                provider,
                budget_id="budget-a",
                ceiling=Decimal("10"),
                reservation=Decimal("1"),
                retry=False,
            )
        )
    assert blocked.value.code == "budget.interrupted" and provider.calls == 0
    asyncio.run(
        send_refinement(
            tmp_path,
            stored,
            EVENT,
            provider,
            budget_id="budget-a",
            ceiling=Decimal("10"),
            reservation=Decimal("1"),
            retry=True,
        )
    )
    assert provider.calls == 1
    attempts = sidecar_directory(tmp_path, RUN, prepared.request_hash or "") / "attempts"
    assert (attempts / "1-planned.json").is_file()
    assert (attempts / "2-planned.json").is_file()
    assert not (attempts / "1-result.json").is_file() or (attempts / "1-planned.json").is_file()


def test_unknown_survives_resume_and_a_second_budget_directory(tmp_path: Path) -> None:
    stored = timeline()
    prepared = prepare_refinement(stored, EVENT)
    other = prepare_refinement(stored, OTHER)
    assert prepared.request is not None and other.request is not None
    begin_attempt(
        tmp_path,
        prepared.request,
        budget_id="budget-a",
        ceiling=Decimal("5"),
        reservation=Decimal("2"),
        retry=False,
    )
    with pytest.raises(AppError) as resumed:
        begin_attempt(
            tmp_path,
            other.request,
            budget_id="budget-a",
            ceiling=Decimal("3"),
            reservation=Decimal("2"),
            retry=False,
        )
    assert resumed.value.code == "budget.exhausted"
    with pytest.raises(AppError) as moved:
        begin_attempt(
            tmp_path,
            other.request,
            budget_id="budget-b",
            ceiling=Decimal("3"),
            reservation=Decimal("2"),
            retry=False,
        )
    assert moved.value.code == "budget.exhausted"
    ledger = (tmp_path / "detail-refinement-budgets" / "budget-a" / "ledger.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"costCny": null' in ledger
    assert (
        sidecar_directory(tmp_path, RUN, request_hash(prepared.request))
        / "attempts"
        / "1-planned.json"
    ).is_file()
    assert not (tmp_path / "detail-refinement-budgets" / "budget-b" / "ledger.jsonl").exists()


def test_two_keys_share_one_ceiling(tmp_path: Path) -> None:
    stored = timeline()
    first = prepare_refinement(stored, EVENT)
    second = prepare_refinement(stored, OTHER)
    assert first.request is not None and second.request is not None
    begin_attempt(
        tmp_path,
        first.request,
        budget_id="shared",
        ceiling=Decimal("3"),
        reservation=Decimal("2"),
        retry=False,
    )
    with pytest.raises(AppError) as caught:
        begin_attempt(
            tmp_path,
            second.request,
            budget_id="shared",
            ceiling=Decimal("3"),
            reservation=Decimal("2"),
            retry=False,
        )
    assert caught.value.code == "budget.exhausted"


def test_overlapping_sends_recheck_the_open_attempt_inside_the_lock(tmp_path: Path) -> None:
    stored = timeline()
    provider = CountingProvider()
    entered = asyncio.Event()
    release = asyncio.Event()
    original = provider.refine

    async def gated(
        request: object, context: CancellationContext
    ) -> ProviderResult[CandidateDetail]:
        entered.set()
        await release.wait()
        return await original(request, context)

    provider.refine = gated  # type: ignore[method-assign]

    async def overlap() -> AppError:
        first = asyncio.create_task(
            send_refinement(
                tmp_path,
                stored,
                EVENT,
                provider,
                budget_id="budget-a",
                ceiling=Decimal("10"),
                reservation=Decimal("1"),
                retry=False,
            )
        )
        await entered.wait()
        try:
            await send_refinement(
                tmp_path,
                stored,
                EVENT,
                provider,
                budget_id="budget-a",
                ceiling=Decimal("10"),
                reservation=Decimal("1"),
                retry=False,
            )
        except AppError as error:
            blocked = error
        else:
            raise AssertionError("The overlapping send reserved a second attempt.")
        release.set()
        await first
        return blocked

    blocked = asyncio.run(overlap())
    assert blocked.code == "budget.interrupted"
    assert provider.calls == 1
    prepared = prepare_refinement(stored, EVENT)
    assert prepared.request_hash is not None
    attempts = sidecar_directory(tmp_path, RUN, prepared.request_hash) / "attempts"
    assert (attempts / "1-planned.json").is_file()
    assert not (attempts / "2-planned.json").exists()


def test_budget_lock_serializes_check_then_reserve(tmp_path: Path) -> None:
    stored = timeline()
    prepared = prepare_refinement(stored, EVENT)
    assert prepared.request is not None
    with BudgetWriterLock(tmp_path):
        with pytest.raises(AppError) as caught:
            begin_attempt(
                tmp_path,
                prepared.request,
                budget_id="shared",
                ceiling=Decimal("5"),
                reservation=Decimal("1"),
                retry=False,
            )
    assert caught.value.code == "storage.writer_busy"


def test_bad_hash_and_path_or_symlink_escape_fail_closed(tmp_path: Path) -> None:
    stored = timeline()
    outcome = reuse_or_refuse(tmp_path, stored, EVENT)
    assert outcome.request is not None and outcome.request_hash is not None
    digest = freeze_request_for_test(tmp_path, outcome.request)
    target = sidecar_directory(tmp_path, RUN, digest) / "request.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    canonical = document["canonicalJson"]
    document["canonicalJson"] = ("0" if canonical[0] != "0" else "1") + canonical[1:]
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AppError) as damaged:
        reuse_or_refuse(tmp_path, stored, EVENT)
    assert damaged.value.code == "refinement.source_mismatch"
    assert damaged.value.code != "match.full"
    with pytest.raises(AppError) as escaped:
        sidecar_directory(tmp_path, "../outside", "a" * 64)
    assert escaped.value.code == "refinement.path"
    outside = tmp_path / "outside-target"
    outside.mkdir()
    link_parent = tmp_path / "linked-project" / "runs" / RUN
    link_parent.mkdir(parents=True)
    link = link_parent / "detail-refinements"
    if not _link_directory(outside, link):
        pytest.fail("Could not create a directory link for the escape check.")
    with pytest.raises(AppError) as linked:
        sidecar_directory(tmp_path / "linked-project", RUN, "ab" * 32)
    assert linked.value.code == "refinement.path"


def freeze_request_for_test(project: Path, request: object) -> str:
    from gamingcreator.application.detail_refinement import DetailRefinementRequest
    from gamingcreator.infrastructure.detail_refinement_sidecar import freeze_request

    assert type(request) is DetailRefinementRequest
    return freeze_request(project, request)


def _link_directory(target: Path, link: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
        )
        return completed.returncode == 0 and link.exists()


def test_nonvisual_candidate_stays_unverified_without_attributes(tmp_path: Path) -> None:
    stored = timeline()
    audio = SemanticEvent(
        f"{RUN}:{MEDIA}:event:" + "ef" * 12,
        MEDIA,
        RUN,
        SourceRange(1_000_000, 2_000_000, DURATION),
        ("旁白说了一句话。",),
        (),
        (),
        "audio",
        None,
    )
    combined = replace(stored, events=(*stored.events, audio))
    provider = CountingProvider()
    outcome = asyncio.run(
        send_refinement(
            tmp_path,
            combined,
            audio.event_id,
            provider,
            budget_id="budget-a",
            ceiling=Decimal("5"),
            reservation=Decimal("1"),
        )
    )
    assert outcome.status == MatchStatus.UNVERIFIED
    assert outcome.detail is None and outcome.request is None and provider.calls == 0
