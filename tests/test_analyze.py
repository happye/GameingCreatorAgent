import asyncio
import hashlib
import json
import struct
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.analysis import (
    PIPELINE_VERSION,
    REQUIRED_STAGES,
    AnalysisPorts,
    resume_analysis,
    run_new_analysis,
)
from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.inputs import AnalysisConfig, PreparedAnalyze
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderCapabilities,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
    VisionRequest,
)
from gamingcreator.application.storage import InvocationStatus, RunConfiguration, RunStatus
from gamingcreator.cli.main import vision_for_run
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.deepseek_vision import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    DeepSeekVisionProvider,
)
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.http_transport import HttpResponse, HttpxVisionTransport
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

RUN_ID = "run-1"
CONFIG = AnalysisConfig("deepseek", "deepseek-flash", 2, 5)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jpeg_bytes(width: int = 512) -> bytes:
    data = bytearray(
        bytes.fromhex(
            "ffd8ffe000104a46494600010200000100010000fffe00104c61766336322e32392e31303000"
            "ffdb0043000828282f282f373737373737413c41434343414141414343434848485555554848"
            "4843434848505055555c5f5c575755575f5f646464787873738c8c91acaccfffc4004b0001"
            "010000000000000000000000000000000801010000000000000000000000000000000010"
            "0100000000000000000000000000000000110100000000000000000000000000000000ff"
            "c00011080120020003012200021100031100ffda000c03010002110311003f00"
        )
        + b"\x9f\xc0"
        + b"\x00" * 863
        + b"\x7f\xff\xd9"
    )
    struct.pack_into(">H", data, data.index(b"\xff\xc0") + 7, width)
    return bytes(data)


class ScriptedMedia:
    def __init__(self, bundle: MediaPreprocessingResult, output: Path) -> None:
        self.bundle = bundle
        self.output = output
        self.calls = 0

    async def probe(self, source: Path, context: CancellationContext) -> MediaAsset:
        return self.bundle.asset

    async def preprocess(
        self,
        source: Path,
        output: Path,
        parameters: SamplingParameters,
        context: CancellationContext,
    ) -> MediaPreprocessingResult:
        self.calls += 1
        assert output == self.output
        assert parameters.max_width == 512 and parameters.max_frames == CONFIG.max_input_frames
        return self.bundle


class ScriptedAsr:
    def __init__(self, result: ProviderResult[tuple]) -> None:
        self.result = result
        self.calls = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(audio=True, structured_output=True)

    async def transcribe(self, request, context):
        self.calls += 1
        assert request.run_id == context.run_id
        return self.result


class ScriptedVision:
    def __init__(self, event: SemanticEvent) -> None:
        self.event = event
        self.calls = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            image_sequence=True,
            structured_output=True,
            max_images=5,
            max_image_width=512,
            local_time_semantics="source_microseconds",
        )

    async def analyze(self, request, context):
        self.calls += 1
        assert request.evidence and context.run_id == request.run_id
        metadata = InvocationMetadata(
            "substitute",
            "local-fixture",
            "local-fixture",
            "rev",
            PROMPT_VERSION,
            SCHEMA_VERSION,
            1,
            ProviderUsage(),
            elapsed_ms=1,
        )
        return ProviderResult(ProviderStatus.COMPLETED, (self.event,), metadata)


class FakeTransport:
    def __init__(self, replies: list[HttpResponse | Exception]) -> None:
        self.replies = replies
        self.payloads: list[dict[str, object]] = []

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        self.payloads.append(payload)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class IdleRecorder:
    async def begin_invocation(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Invocation was recorded before a budget check.")

    async def finish_invocation(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Invocation was recorded before a budget check.")


def asr_metadata() -> InvocationMetadata:
    return InvocationMetadata(
        "fake-asr",
        "fake-tiny",
        None,
        None,
        "asr-hotwords-v1",
        "transcript-v1",
        1,
        ProviderUsage(),
        elapsed_ms=4,
    )


def asr_result(status: ProviderStatus, error: str | None = None) -> ProviderResult[tuple]:
    failure = None if error is None else ProviderFailure(error, False)
    output = None if failure is not None else ()
    return ProviderResult(status, output, asr_metadata(), failure)


def response(evidence_id: str, *, content: str | None = None) -> HttpResponse:
    event = {
        "startUs": 900_000,
        "endUs": 1_600_000,
        "observableFacts": ["Character moves sideways."],
        "mechanicTags": ["dodge"],
        "evidenceIds": [evidence_id],
        "uncertainty": None,
    }
    body = {
        "id": "chatcmpl-offline",
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content if content is not None else json.dumps({"events": [event]}),
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }
    return HttpResponse(200, json.dumps(body).encode())


def build_bundle(root: Path) -> tuple[MediaPreprocessingResult, Path, Path]:
    source = root / "source.mp4"
    source.write_bytes(b"fixture-source")
    digest = sha256(source)
    asset = MediaAsset(
        digest,
        source.resolve(),
        digest,
        (MediaStream(0, "video", Fraction(1, 1000), 0, 5000),),
        Fraction(0),
        5_000_000,
        "fixture",
    )
    project = root / "project"
    output = project / "runs" / RUN_ID / "media"
    output.mkdir(parents=True)
    image_path = output / "frame.jpg"
    payload = jpeg_bytes()
    image_path.write_bytes(payload)
    image = VisualEvidence(
        f"{RUN_ID}:{digest}:image:000000",
        image_path,
        hashlib.sha256(payload).hexdigest(),
        1000,
        Fraction(1, 1000),
        asset.instant(1000, Fraction(1, 1000)),
    )
    bundle = MediaPreprocessingResult(
        asset, (image,), None, output / "media-manifest.json", "fixture-v1", "fixture-processor"
    )
    write_manifest(bundle, SamplingParameters(max_width=512, max_frames=CONFIG.max_input_frames))
    return bundle, project, source


def prepared(source: Path, project: Path, *, resume: str | None = None) -> PreparedAnalyze:
    if resume is not None:
        return PreparedAnalyze(source.resolve(), project, None, None, resume)
    return PreparedAnalyze(source.resolve(), project, CONFIG, Decimal("1.00"), None)


def test_deepseek_pipeline_keeps_unknown_cost_and_resume_does_not_call_again(
    tmp_path: Path,
) -> None:
    asr = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))

    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        transport = FakeTransport([response(bundle.images[0].evidence_id)])
        store = await SqliteTimelineStore.open(project)
        vision = DeepSeekVisionProvider(
            transport,
            BudgetLedger(Decimal("1"), 2, 5),
            Decimal("0.1"),
            store,
            retry_delays=(0, 0),
        )
        ports = AnalysisPorts(
            ScriptedMedia(bundle, project / "runs" / RUN_ID / "media"), asr, vision, store
        )
        try:
            outcome = await run_new_analysis(
                prepared(source, project),
                ports,
                bundle.asset,
                project,
                run_id=RUN_ID,
                timeout_seconds=5,
            )
            assert outcome.event_count == 1 and outcome.transcript_count == 0
            assert asr.calls == 1 and len(transport.payloads) == 1
            assert "Bearer" not in json.dumps(transport.payloads[0])
            timeline = await store.load_completed_timeline(RUN_ID)
            visual = next(item for item in timeline.invocations if item.stage_id == "vision")
            heard = next(item for item in timeline.invocations if item.stage_id == "asr")
            assert visual.metadata.usage.cost_cny is visual.metadata.usage.original_cost is None
            assert visual.metadata.usage.cost_status.value == "unverified"
            assert visual.metadata.attempt == 1 and visual.status == InvocationStatus.COMPLETED
            assert heard.status == InvocationStatus.NO_AUDIO
            exported = json.loads(
                (project / "runs" / RUN_ID / "semantic_timeline.json").read_text(encoding="utf-8")
            )
            assert exported["events"][0]["observableFacts"] == ["Character moves sideways."]
            assert all(item["costCny"] is None for item in exported["invocations"])
            (project / "runs" / RUN_ID / "semantic_timeline.json").unlink()
            resumed = await resume_analysis(
                prepared(source, project, resume=RUN_ID), store, project
            )
            assert resumed.event_count == 1 and len(transport.payloads) == 1
            assert (project / "runs" / RUN_ID / "semantic_timeline.json").is_file()
            with pytest.raises(AppError) as mismatch:
                other = tmp_path / "other.mp4"
                other.write_bytes(b"other-source")
                await resume_analysis(prepared(other, project, resume=RUN_ID), store, project)
            assert mismatch.value.code == "input.resume"
        finally:
            await store.close()

    asyncio.run(scenario())


def test_missing_price_stops_before_http_and_failed_run_is_not_replayed(tmp_path: Path) -> None:
    asr = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))
    transport = FakeTransport([])

    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        vision = DeepSeekVisionProvider(
            transport, BudgetLedger(Decimal("1"), 2, 5), None, store, retry_delays=(0, 0)
        )
        ports = AnalysisPorts(
            ScriptedMedia(bundle, project / "runs" / RUN_ID / "media"), asr, vision, store
        )
        try:
            with pytest.raises(AppError) as error:
                await run_new_analysis(
                    prepared(source, project),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                    timeout_seconds=5,
                )
            assert error.value.code == "budget.estimate_missing"
            assert error.value.exit_code == 7 and error.value.run_id == RUN_ID
            assert transport.payloads == [] and asr.calls == 1
            stored = await store.load_run(RUN_ID)
            assert stored.status == RunStatus.FAILED
            assert stored.error_code == "budget.estimate_missing"
            await store.load_media_bundle(RUN_ID)
            assert not (project / "runs" / RUN_ID / "semantic_timeline.json").exists()
            invocations = await store.load_invocations(RUN_ID)
            assert [item.stage_id for item in invocations] == ["asr"]
            with pytest.raises(AppError) as replay:
                await resume_analysis(prepared(source, project, resume=RUN_ID), store, project)
            assert replay.value.code == "budget.estimate_missing"
            assert transport.payloads == []
        finally:
            await store.close()

    asyncio.run(scenario())


def test_malformed_model_json_fails_the_run_without_a_completed_timeline(tmp_path: Path) -> None:
    asr = ScriptedAsr(asr_result(ProviderStatus.NO_SPEECH))

    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        transport = FakeTransport(
            [response(bundle.images[0].evidence_id, content='{"events":"bad"}')]
        )
        store = await SqliteTimelineStore.open(project)
        vision = DeepSeekVisionProvider(
            transport,
            BudgetLedger(Decimal("1"), 2, 5),
            Decimal("0.1"),
            store,
            retry_delays=(0, 0),
        )
        ports = AnalysisPorts(
            ScriptedMedia(bundle, project / "runs" / RUN_ID / "media"), asr, vision, store
        )
        try:
            with pytest.raises(AppError) as error:
                await run_new_analysis(
                    prepared(source, project),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                    timeout_seconds=5,
                )
            assert error.value.code == "provider.schema" and len(transport.payloads) == 1
            stored = await store.load_run(RUN_ID)
            assert stored.status == RunStatus.FAILED
            visual = next(
                item for item in await store.load_invocations(RUN_ID) if item.stage_id == "vision"
            )
            assert visual.status == InvocationStatus.FAILED
            assert visual.metadata.usage.cost_cny is None
            with pytest.raises(AppError):
                await store.load_completed_timeline(RUN_ID)
        finally:
            await store.close()

    asyncio.run(scenario())


def test_substitute_provider_completes_without_a_transport(tmp_path: Path) -> None:
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        image = bundle.images[0]
        event = SemanticEvent(
            "event-1",
            bundle.asset.media_id,
            RUN_ID,
            SourceRange(900_000, 1_600_000, bundle.asset.duration_us),
            ("Observed fixture action",),
            ("dodge",),
            (image.evidence_id,),
            "visual",
            None,
        )
        vision = ScriptedVision(event)
        asr = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))
        store = await SqliteTimelineStore.open(project)
        ports = AnalysisPorts(
            ScriptedMedia(bundle, project / "runs" / RUN_ID / "media"), asr, vision, store
        )
        try:
            outcome = await run_new_analysis(
                prepared(source, project),
                ports,
                bundle.asset,
                project,
                run_id=RUN_ID,
                timeout_seconds=5,
            )
            assert outcome.event_count == 1 and vision.calls == 1
            timeline = await store.load_completed_timeline(RUN_ID)
            assert timeline.events == (event,)
            assert not any(item.metadata.provider == "deepseek" for item in timeline.invocations)
        finally:
            await store.close()

    asyncio.run(scenario())


def test_asr_failure_does_not_call_vision(tmp_path: Path) -> None:
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        asr = ScriptedAsr(asr_result(ProviderStatus.FAILED, "asr.inference"))
        vision = ScriptedVision(
            SemanticEvent(
                "unused",
                bundle.asset.media_id,
                RUN_ID,
                SourceRange(0, 1, bundle.asset.duration_us),
                ("unused",),
                (),
                (bundle.images[0].evidence_id,),
                "visual",
                None,
            )
        )
        store = await SqliteTimelineStore.open(project)
        ports = AnalysisPorts(
            ScriptedMedia(bundle, project / "runs" / RUN_ID / "media"), asr, vision, store
        )
        try:
            with pytest.raises(AppError) as error:
                await run_new_analysis(
                    prepared(source, project),
                    ports,
                    bundle.asset,
                    project,
                    run_id=RUN_ID,
                    timeout_seconds=5,
                )
            assert error.value.code == "asr.inference" and vision.calls == 0 and asr.calls == 1
            assert (await store.load_run(RUN_ID)).status == RunStatus.FAILED
        finally:
            await store.close()

    asyncio.run(scenario())


def test_cli_vision_factory_stops_before_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(self: HttpxVisionTransport, payload: dict[str, object], timeout_seconds: float):
        raise AssertionError("network")

    monkeypatch.setattr(HttpxVisionTransport, "post", explode)
    image = tmp_path / "frame.jpg"
    payload = jpeg_bytes()
    image.write_bytes(payload)
    request = VisionRequest(
        RUN_ID,
        (
            EvidenceReference(
                f"{RUN_ID}:media-1:image:000000",
                "media-1",
                "image",
                SourceInstant(1_000_000, 5_000_000),
                image,
                hashlib.sha256(payload).hexdigest(),
                "fixture-v1",
            ),
        ),
        PROMPT_VERSION,
        SCHEMA_VERSION,
        1024,
    )
    provider = vision_for_run(IdleRecorder(), BudgetLedger(Decimal("1"), 2, 5))
    result = asyncio.run(provider.analyze(request, CancellationContext(RUN_ID, 2)))
    assert result.error is not None and result.error.code == "budget.estimate_missing"


def configuration() -> RunConfiguration:
    return RunConfiguration(
        CONFIG,
        Decimal("1.00"),
        PIPELINE_VERSION,
        hashlib.sha256(PIPELINE_VERSION.encode()).hexdigest(),
        REQUIRED_STAGES,
    )


def event_for(bundle: MediaPreprocessingResult) -> SemanticEvent:
    return SemanticEvent(
        "event-1",
        bundle.asset.media_id,
        RUN_ID,
        SourceRange(900_000, 1_600_000, bundle.asset.duration_us),
        ("Observed fixture action",),
        ("dodge",),
        (bundle.images[0].evidence_id,),
        "visual",
        None,
    )


async def seed_media(store: SqliteTimelineStore, bundle: MediaPreprocessingResult) -> None:
    await store.create_run(RUN_ID, bundle.asset, configuration())
    await store.begin_stage(RUN_ID, "media", bundle.asset.sha256)
    await store.persist_media_bundle(RUN_ID, bundle)


async def seed_asr(store: SqliteTimelineStore, bundle: MediaPreprocessingResult) -> None:
    await store.begin_stage(RUN_ID, "asr", bundle.asset.sha256)
    await store.persist_timeline(RUN_ID, "asr", (), (), bundle.asset.sha256)


def test_resume_continues_after_completed_media_and_asr(tmp_path: Path) -> None:
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        media = ScriptedMedia(bundle, project / "runs" / RUN_ID / "media")
        asr = ScriptedAsr(asr_result(ProviderStatus.NO_SPEECH))
        vision = ScriptedVision(event_for(bundle))
        ports = AnalysisPorts(media, asr, vision, store)
        try:
            await seed_media(store, bundle)
            await seed_asr(store, bundle)
            outcome = await resume_analysis(
                prepared(source, project, resume=RUN_ID),
                store,
                project,
                ports,
                timeout_seconds=5,
            )
            assert outcome.event_count == 1
            assert media.calls == 0 and asr.calls == 0 and vision.calls == 1
            assert (await store.load_run(RUN_ID)).status == RunStatus.COMPLETED
        finally:
            await store.close()

    asyncio.run(scenario())


def test_resume_reruns_asr_when_only_media_is_complete(tmp_path: Path) -> None:
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        media = ScriptedMedia(bundle, project / "runs" / RUN_ID / "media")
        asr = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))
        vision = ScriptedVision(event_for(bundle))
        ports = AnalysisPorts(media, asr, vision, store)
        try:
            await seed_media(store, bundle)
            outcome = await resume_analysis(
                prepared(source, project, resume=RUN_ID),
                store,
                project,
                ports,
                timeout_seconds=5,
            )
            assert outcome.transcript_count == 0 and outcome.event_count == 1
            assert media.calls == 0 and asr.calls == 1 and vision.calls == 1
        finally:
            await store.close()

    asyncio.run(scenario())


def test_resume_does_not_redo_a_running_stage(tmp_path: Path) -> None:
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        store = await SqliteTimelineStore.open(project)
        media = ScriptedMedia(bundle, project / "runs" / RUN_ID / "media")
        asr = ScriptedAsr(asr_result(ProviderStatus.NO_AUDIO))
        vision = ScriptedVision(event_for(bundle))
        try:
            await store.create_run(RUN_ID, bundle.asset, configuration())
            await store.begin_stage(RUN_ID, "media", bundle.asset.sha256)
            with pytest.raises(AppError) as error:
                await resume_analysis(
                    prepared(source, project, resume=RUN_ID),
                    store,
                    project,
                    AnalysisPorts(media, asr, vision, store),
                    timeout_seconds=5,
                )
            assert error.value.code == "storage.run_incomplete"
            assert media.calls == 0 and asr.calls == 0 and vision.calls == 0
            assert (await store.load_run(RUN_ID)).status == RunStatus.RUNNING
        finally:
            await store.close()

    asyncio.run(scenario())


def test_resume_without_price_does_not_send_or_redo_finished_stages(tmp_path: Path) -> None:
    async def scenario():
        bundle, project, source = build_bundle(tmp_path)
        transport = FakeTransport([response(bundle.images[0].evidence_id)])
        store = await SqliteTimelineStore.open(project)
        media = ScriptedMedia(bundle, project / "runs" / RUN_ID / "media")
        asr = ScriptedAsr(asr_result(ProviderStatus.NO_SPEECH))
        vision = DeepSeekVisionProvider(
            transport, BudgetLedger(Decimal("1"), 2, 5), None, store, retry_delays=(0, 0)
        )
        ports = AnalysisPorts(media, asr, vision, store)
        try:
            await seed_media(store, bundle)
            await seed_asr(store, bundle)
            with pytest.raises(AppError) as error:
                await resume_analysis(
                    prepared(source, project, resume=RUN_ID),
                    store,
                    project,
                    ports,
                    timeout_seconds=5,
                )
            assert error.value.code == "budget.estimate_missing"
            assert transport.payloads == [] and media.calls == 0 and asr.calls == 0
            assert (await store.load_run(RUN_ID)).status == RunStatus.FAILED
            with pytest.raises(AppError) as replay:
                await resume_analysis(prepared(source, project, resume=RUN_ID), store, project)
            assert replay.value.code == "budget.estimate_missing" and transport.payloads == []
        finally:
            await store.close()

    asyncio.run(scenario())
