import asyncio
import hashlib
import json
import os
import struct
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import (
    CancellationContext,
    CostStatus,
    InvocationMetadata,
    ProviderCapabilities,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
    VisionProvider,
    VisionRequest,
)
from gamingcreator.application.storage import InvocationStatus, StoredInvocation
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure import deepseek_vision
from gamingcreator.infrastructure.deepseek_vision import (
    MAX_IMAGES,
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    SCHEMA_VERSION,
    DeepSeekVisionProvider,
)
from gamingcreator.infrastructure.http_transport import (
    DEEPSEEK_ENDPOINT,
    MAX_RESPONSE_BYTES,
    HttpResponse,
    HttpxVisionTransport,
    TransportError,
)


class Recorder:
    def __init__(self) -> None:
        self.records: list[StoredInvocation] = []
        self.begun_metadata: list[InvocationMetadata] = []
        self.finished = asyncio.Event()

    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None:
        self.begun_metadata.append(metadata)
        self.records.append(
            StoredInvocation(
                invocation_id,
                run_id,
                stage_id,
                logical_request_id,
                InvocationStatus.RUNNING,
                metadata,
                None,
            )
        )

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None:
        for index, record in enumerate(self.records):
            if record.invocation_id == invocation_id:
                self.records[index] = replace(
                    record, status=status, metadata=metadata, error_code=error_code
                )
                self.finished.set()
                return
        raise AssertionError("Attempt was not persisted before sending.")


class FakeTransport:
    def __init__(self, replies: list[HttpResponse | Exception], recorder: Recorder) -> None:
        self.replies = replies
        self.recorder = recorder
        self.payloads: list[dict[str, object]] = []

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        assert self.recorder.records[-1].status == InvocationStatus.RUNNING
        self.payloads.append(payload)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class WaitingTransport:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.closed = False

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        self.started.set()
        try:
            await asyncio.Future[None]()
        finally:
            self.closed = True
        raise AssertionError("Cancelled request cannot complete.")


def request_fixture(tmp_path: Path, *, frames: int = 1, width: int = 512) -> VisionRequest:
    # FFmpeg-generated 512x288 black JPEG, kept inline so contracts need no native tool.
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
    references = []
    for index in range(frames):
        path = tmp_path / f"frame-{index}.jpg"
        path.write_bytes(data)
        references.append(
            EvidenceReference(
                f"run-1:media-1:image:{index:06d}",
                "media-1",
                "image",
                SourceInstant(1_000_000 + index * 100_000, 5_000_000),
                path,
                hashlib.sha256(data).hexdigest(),
                "media-v1",
            )
        )
    return VisionRequest("run-1", tuple(references), PROMPT_VERSION, SCHEMA_VERSION, 1024)


def valid_event() -> dict[str, object]:
    return {
        "startUs": 900_000,
        "endUs": 1_600_000,
        "observableFacts": ["Character moves sideways."],
        "mechanicTags": ["dodge"],
        "evidenceIds": ["run-1:media-1:image:000000"],
        "uncertainty": None,
    }


def response_fixture(
    *,
    events: object = None,
    usage: object = None,
    finish_reason: str = "stop",
    content: str | None = None,
) -> HttpResponse:
    body: dict[str, object] = {
        "id": "chatcmpl-offline",
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": content
                    if content is not None
                    else json.dumps({"events": [valid_event()] if events is None else events}),
                },
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return HttpResponse(200, json.dumps(body).encode())


def provider_fixture(
    replies: list[HttpResponse | Exception],
    *,
    budget: BudgetLedger | None = None,
    reservation: Decimal | None = Decimal("0.1"),
) -> tuple[DeepSeekVisionProvider, FakeTransport, Recorder, BudgetLedger]:
    recorder = Recorder()
    transport = FakeTransport(replies, recorder)
    ledger = budget if budget is not None else BudgetLedger(Decimal(1), 10, 50)
    provider = DeepSeekVisionProvider(transport, ledger, reservation, recorder, retry_delays=(0, 0))
    return provider, transport, recorder, ledger


def test_selected_images_only_and_metadata_without_invented_costs(tmp_path: Path) -> None:
    provider, transport, recorder, ledger = provider_fixture(
        [response_fixture(usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14})]
    )
    protocol: VisionProvider = provider
    result = asyncio.run(
        protocol.analyze(request_fixture(tmp_path, frames=5), CancellationContext("run-1", 2))
    )
    assert result.status == ProviderStatus.COMPLETED and result.output
    event = result.output[0]
    assert event.event_id.startswith("run-1:media-1:event:")
    assert event.run_id == "run-1" and event.media_id == "media-1"
    assert event.observable_facts == ("Character moves sideways.",)
    assert result.metadata.actual_model == "deepseek-flash"
    assert result.metadata.model_revision is None
    assert result.metadata.request_id == "chatcmpl-offline"
    assert result.metadata.elapsed_ms is not None
    assert result.metadata.usage.input_tokens == 10
    assert result.metadata.usage.cached_input_tokens is None
    assert result.metadata.usage.original_cost is result.metadata.usage.cost_cny is None
    assert result.metadata.usage.cost_status == CostStatus.UNVERIFIED
    assert recorder.records[0].metadata == result.metadata
    assert recorder.records[0].status == InvocationStatus.COMPLETED
    assert ledger.frames == MAX_IMAGES and ledger.committed_cny == Decimal("0.1")
    payload = transport.payloads[0]
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    serialized = json.dumps(payload)
    assert serialized.count("data:image/jpeg;base64,") == 5
    assert str(tmp_path) not in serialized
    assert "sourceUs" in serialized and "durationUs" in serialized
    assert provider.capabilities.max_images == 5
    assert provider.capabilities.max_image_width == 512
    assert not provider.capabilities.native_video


@pytest.mark.parametrize("language", ["zh", "en"])
def test_v2_aliases_have_source_bounds_and_remap_to_original_evidence(
    tmp_path: Path, language: str
) -> None:
    event = valid_event()
    event["evidenceIds"] = ["f1", "f0"]
    event["observableFacts"] = [
        "角色向侧面移动。" if language == "zh" else "Character moves sideways."
    ]
    provider, transport, recorder, _ = provider_fixture([response_fixture(events=[event])])
    request = replace(
        request_fixture(tmp_path, frames=2),
        prompt_version=PROMPT_VERSION_V2,
        language=language,
        stage_id="vision-000004",
    )
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.status == ProviderStatus.COMPLETED and result.output
    assert result.output[0].evidence_ids == tuple(item.evidence_id for item in request.evidence)
    assert recorder.records[0].stage_id == "vision-000004"
    assert result.metadata.prompt_version == PROMPT_VERSION_V2
    payload = transport.payloads[0]
    serialized = json.dumps(payload)
    assert "run-1:media-1:image:" not in serialized
    messages = payload["messages"]
    assert isinstance(messages, list)
    system, user = messages
    assert "strictly greater" in system["content"]
    blocks = user["content"]
    info = json.loads(blocks[0]["text"])
    assert info["windowFirstSourceUs"] == 1_000_000
    assert info["windowLastSourceUs"] == 1_100_000
    assert info["language"] == language
    assert json.loads(blocks[1]["text"])["evidenceId"] == "f0"
    assert json.loads(blocks[3]["text"])["evidenceId"] == "f1"


@pytest.mark.parametrize("reference", ["f2", "f00", "F0", "run-1:media-1:image:000000"])
def test_v2_never_guesses_or_accepts_foreign_frame_aliases(tmp_path: Path, reference: str) -> None:
    event = valid_event()
    event["evidenceIds"] = [reference]
    provider, _, recorder, _ = provider_fixture([response_fixture(events=[event])])
    request = replace(request_fixture(tmp_path, frames=2), prompt_version=PROMPT_VERSION_V2)
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.error and result.error.code == "provider.schema"
    assert result.metadata.execution_details
    assert json.loads(result.metadata.execution_details)["schemaError"] == "evidence_unknown"
    assert recorder.records[0].metadata == result.metadata


@pytest.mark.parametrize("version", [PROMPT_VERSION, PROMPT_VERSION_V2])
def test_half_open_boundary_error_has_safe_diagnostic_and_never_adjusts_time(
    tmp_path: Path, version: str
) -> None:
    event = valid_event()
    event["endUs"] = 1_000_000
    if version == PROMPT_VERSION_V2:
        event["evidenceIds"] = ["f0"]
    event["observableFacts"] = ["private-untrusted-response-text"]
    provider, _, recorder, ledger = provider_fixture([response_fixture(events=[event])])
    request = replace(request_fixture(tmp_path), prompt_version=version)
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.error and result.error.code == "provider.schema" and not result.error.retryable
    assert result.output is None
    assert result.metadata.execution_details
    details = json.loads(result.metadata.execution_details)
    assert details["schemaError"] == "evidence_outside_range"
    assert details["reservationCny"] == "0.1" and details["inputFrames"] == 1
    assert details["evidenceIds"] == [request.evidence[0].evidence_id]
    assert "private-untrusted-response-text" not in repr(result)
    assert ledger.reserved_cny == Decimal("0.1")
    assert recorder.records[0].status == InvocationStatus.FAILED
    assert recorder.begun_metadata[0].execution_details
    assert "schemaError" not in json.loads(recorder.begun_metadata[0].execution_details)


@pytest.mark.parametrize(
    "field,value,diagnostic",
    [
        ("startUs", True, "time_type"),
        ("startUs", -1, "time_range"),
        ("endUs", 900_000, "time_range"),
        ("endUs", 5_000_001, "time_range"),
        ("confidence", 0.9, "event_fields"),
        ("observableFacts", [], "event_facts"),
        ("mechanicTags", "dodge", "event_tags"),
        ("evidenceIds", [], "event_evidence"),
        ("uncertainty", False, "uncertainty"),
    ],
)
def test_event_schema_diagnostics_use_finite_codes(
    tmp_path: Path, field: str, value: object, diagnostic: str
) -> None:
    event = valid_event()
    event[field] = value
    provider, _, _, _ = provider_fixture([response_fixture(events=[event])])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.metadata.execution_details
    assert json.loads(result.metadata.execution_details)["schemaError"] == diagnostic


@pytest.mark.parametrize(
    "content,diagnostic",
    [
        ("private-invalid-json", "json_invalid"),
        ('{"events":[],"events":[]}', "json_duplicate"),
        ('{"events":NaN}', "json_nonfinite"),
        ('{"unexpected":[]}', "event_collection"),
    ],
)
def test_model_json_schema_diagnostic_never_contains_response(
    tmp_path: Path, content: str, diagnostic: str
) -> None:
    provider, _, _, _ = provider_fixture([response_fixture(content=content)])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "provider.schema"
    assert result.metadata.execution_details
    assert json.loads(result.metadata.execution_details)["schemaError"] == diagnostic
    assert "private-invalid-json" not in repr(result)


def test_finish_reason_schema_diagnostic_keeps_known_price_estimate(tmp_path: Path) -> None:
    recorder = Recorder()
    transport = FakeTransport(
        [
            response_fixture(
                finish_reason="content_filter",
                usage={
                    "prompt_tokens": 1000,
                    "completion_tokens": 200,
                    "prompt_cache_hit_tokens": 300,
                },
            )
        ],
        recorder,
    )
    ledger = BudgetLedger(Decimal(10), 10, 50)
    provider = DeepSeekVisionProvider(
        transport, ledger, None, recorder, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "provider.schema"
    assert result.metadata.execution_details
    assert json.loads(result.metadata.execution_details)["schemaError"] == "finish_reason"
    assert result.metadata.usage.cost_status == CostStatus.ESTIMATED
    assert result.metadata.usage.cost_cny == ledger.known_cost_cny
    assert ledger.reserved_cny == 0


def test_v2_zero_events_and_one_microsecond_final_frame_are_valid(tmp_path: Path) -> None:
    request = request_fixture(tmp_path)
    item = replace(request.evidence[0], source_time=SourceInstant(4_999_999, 5_000_000))
    request = replace(request, evidence=(item,), prompt_version=PROMPT_VERSION_V2)
    event = valid_event()
    event.update(startUs=4_999_999, endUs=5_000_000, evidenceIds=["f0"])
    provider, _, _, _ = provider_fixture([response_fixture(events=[event])])
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.output and result.output[0].source_range.end_us == 5_000_000
    provider, _, _, _ = provider_fixture([response_fixture(events=[])])
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.status == ProviderStatus.COMPLETED and result.output == ()


def test_snapshot_prices_usage_and_persists_reservation_before_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deepseek_vision, "_request_time_utc", lambda: datetime(2026, 10, 4, 3, tzinfo=UTC)
    )
    recorder = Recorder()
    transport = FakeTransport(
        [
            response_fixture(
                usage={
                    "prompt_tokens": 1000,
                    "completion_tokens": 200,
                    "prompt_cache_hit_tokens": 300,
                }
            )
        ],
        recorder,
    )
    ledger = BudgetLedger(Decimal(10), 10, 50)
    provider = DeepSeekVisionProvider(
        transport, ledger, None, recorder, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path, frames=2), CancellationContext("run-1", 2))
    )
    assert result.status == ProviderStatus.COMPLETED
    assert result.metadata.price_version == DEEPSEEK_FLASH_20261004.version
    assert result.metadata.usage.cost_status == CostStatus.ESTIMATED
    assert result.metadata.usage.cost_cny == ledger.known_cost_cny == Decimal("0.001506")
    assert ledger.reserved_cny == 0 and ledger.unresolved_attempts == 0
    begun = recorder.begun_metadata[0]
    assert begun.price_version == result.metadata.price_version
    assert begun.execution_details
    details = json.loads(begun.execution_details)
    assert details == {
        "reservationCny": "2.008192",
        "inputFrames": 2,
        "evidenceIds": ["run-1:media-1:image:000000", "run-1:media-1:image:000001"],
        "inputTokenCeiling": 1_000_000,
        "period": "offpeak",
        "periodBasis": "china_weekend",
        "requestedAtUtc": "2026-10-04T03:00:00+00:00",
    }
    assert begun.usage.cost_cny is None and begun.actual_model is None


@pytest.mark.parametrize("unknown", ["cached", "actual_model"])
def test_snapshot_keeps_reservation_when_billing_input_is_unknown(
    tmp_path: Path, unknown: str
) -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 200}
    if unknown != "cached":
        usage["prompt_cache_hit_tokens"] = 300
    response = response_fixture(usage=usage)
    if unknown == "actual_model":
        decoded = json.loads(response.body)
        decoded["model"] = "future-new-model"
        response = HttpResponse(200, json.dumps(decoded).encode())
    recorder = Recorder()
    transport = FakeTransport([response], recorder)
    ledger = BudgetLedger(Decimal(10), 10, 50)
    provider = DeepSeekVisionProvider(
        transport, ledger, None, recorder, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.status == ProviderStatus.COMPLETED
    assert result.metadata.usage.cost_cny is None
    assert result.metadata.usage.cost_status == CostStatus.UNVERIFIED
    assert ledger.known_cost_cny == 0 and ledger.reserved_cny == Decimal("2.008192")


def test_priced_retry_keeps_failed_unknown_reservation_and_independent_periods(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    times = iter((datetime(2026, 10, 4, 3, tzinfo=UTC), datetime(2026, 10, 5, 1, tzinfo=UTC)))
    monkeypatch.setattr(deepseek_vision, "_request_time_utc", lambda: next(times))
    recorder = Recorder()
    transport = FakeTransport(
        [
            HttpResponse(503, b"private"),
            response_fixture(
                usage={
                    "prompt_tokens": 1000,
                    "completion_tokens": 200,
                    "prompt_cache_hit_tokens": 300,
                }
            ),
        ],
        recorder,
    )
    ledger = BudgetLedger(Decimal(10), 10, 50)
    provider = DeepSeekVisionProvider(
        transport,
        ledger,
        None,
        recorder,
        price_snapshot=DEEPSEEK_FLASH_20261004,
        retry_delays=(0, 0),
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.metadata.attempt == 2 and ledger.requests == 2
    assert result.metadata.usage.cost_cny == Decimal("0.003012")
    assert ledger.reserved_cny == Decimal("2.008192")
    assert ledger.committed_cny == Decimal("2.011204")
    assert recorder.records[0].metadata.usage.cost_cny is None
    first, second = recorder.begun_metadata
    assert first.execution_details and second.execution_details
    assert json.loads(first.execution_details)["period"] == "offpeak"
    assert json.loads(second.execution_details)["period"] == "peak"


def test_snapshot_does_not_allow_undersized_manual_reservation_and_budget_stops_before_send(
    tmp_path: Path,
) -> None:
    recorder = Recorder()
    transport = FakeTransport([], recorder)
    ledger = BudgetLedger(Decimal(1), 10, 50)
    provider = DeepSeekVisionProvider(
        transport, ledger, Decimal("0.01"), recorder, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "budget.exhausted"
    assert not recorder.records and not transport.payloads
    assert ledger.requests == 0


def test_truncated_paid_response_settles_known_estimated_cost(tmp_path: Path) -> None:
    recorder = Recorder()
    transport = FakeTransport(
        [
            response_fixture(
                finish_reason="length",
                usage={
                    "prompt_tokens": 1000,
                    "completion_tokens": 200,
                    "prompt_cache_hit_tokens": 300,
                },
            )
        ],
        recorder,
    )
    ledger = BudgetLedger(Decimal(10), 10, 50)
    provider = DeepSeekVisionProvider(
        transport, ledger, None, recorder, price_snapshot=DEEPSEEK_FLASH_20261004
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "provider.response_limit"
    assert result.metadata.usage.cost_status == CostStatus.ESTIMATED
    assert result.metadata.usage.cost_cny == ledger.known_cost_cny
    assert ledger.reserved_cny == 0 and len(recorder.records) == 1


@pytest.mark.parametrize("ceiling", [0, -1, True, 1_000_001])
def test_snapshot_rejects_invalid_input_token_ceiling(ceiling: int) -> None:
    recorder = Recorder()
    with pytest.raises(ValueError):
        DeepSeekVisionProvider(
            FakeTransport([], recorder),
            BudgetLedger(Decimal(10), 10, 50),
            None,
            recorder,
            price_snapshot=DEEPSEEK_FLASH_20261004,
            input_token_ceiling=ceiling,
        )


@pytest.mark.parametrize("reservation", [Decimal(0), Decimal("NaN"), Decimal(-1)])
def test_snapshot_rejects_invalid_manual_reservation_without_network(
    tmp_path: Path, reservation: Decimal
) -> None:
    recorder = Recorder()
    transport = FakeTransport([], recorder)
    provider = DeepSeekVisionProvider(
        transport,
        BudgetLedger(Decimal(10), 10, 50),
        reservation,
        recorder,
        price_snapshot=DEEPSEEK_FLASH_20261004,
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "budget.estimate_invalid"
    assert not transport.payloads and not recorder.records


def test_empty_events_are_valid_and_ids_are_program_generated_stable(tmp_path: Path) -> None:
    provider, _, _, _ = provider_fixture([response_fixture(events=[])])
    assert (
        asyncio.run(
            provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
        ).output
        == ()
    )
    ids = []
    for _ in range(2):
        provider, _, _, _ = provider_fixture([response_fixture()])
        result = asyncio.run(
            provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
        )
        assert result.output
        ids.append(result.output[0].event_id)
    assert ids[0] == ids[1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("startUs", True),
        ("startUs", 1.0),
        ("startUs", "1"),
        ("startUs", -1),
        ("endUs", 900_000),
        ("endUs", 5_000_001),
        ("endUs", 2**63),
        ("endUs", 1_000_000),
        ("observableFacts", []),
        ("observableFacts", [" "]),
        ("observableFacts", [False]),
        ("mechanicTags", "dodge"),
        ("evidenceIds", ["invented"]),
        ("evidenceIds", []),
        ("evidenceIds", ["foreign:media-1:image:000000"]),
        ("uncertainty", ""),
        ("uncertainty", 1),
        ("confidence", 0.9),
        ("mediaId", "foreign"),
        ("runId", "foreign"),
    ],
)
def test_model_events_are_strict_and_fail_without_retry(
    tmp_path: Path, field: str, value: object
) -> None:
    event = valid_event()
    event[field] = value
    provider, transport, recorder, _ = provider_fixture([response_fixture(events=[event])])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.status == ProviderStatus.FAILED
    assert result.error and result.error.code == "provider.schema" and not result.error.retryable
    assert len(transport.payloads) == len(recorder.records) == 1
    assert result.metadata.actual_model == "deepseek-flash"


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        '{"events":[],"unexpected":true}',
        '{"events":[],"events":[]}',
        '{"events":NaN}',
        "private-error-body",
        "{",
    ],
)
def test_malformed_duplicate_or_extra_model_json_is_sanitized(tmp_path: Path, content: str) -> None:
    provider, _, _, _ = provider_fixture([response_fixture(content=content)])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "provider.schema"
    assert "private-error-body" not in repr(result)


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": True},
        {"completion_tokens": -1},
        {"prompt_cache_hit_tokens": 1.5},
        {"prompt_tokens": 5, "prompt_cache_hit_tokens": 6},
        {"prompt_cache_hit_tokens": 1, "prompt_tokens_details": {"cached_tokens": 2}},
        {"prompt_tokens": 10, "prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 9},
        {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 13},
        "private-usage-body",
    ],
)
def test_usage_is_validated_without_turning_unknown_into_zero(
    tmp_path: Path, usage: object
) -> None:
    provider, _, _, _ = provider_fixture([response_fixture(usage=usage)])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "provider.schema"
    assert result.metadata.usage.original_cost is None


def test_valid_cached_counts_and_missing_usage_remain_distinct(tmp_path: Path) -> None:
    for usage, expected in [
        (None, None),
        ({"prompt_tokens": 10, "prompt_cache_hit_tokens": 0}, 0),
        ({"prompt_tokens": 10, "prompt_tokens_details": {"cached_tokens": 2}}, 2),
    ]:
        provider, _, _, _ = provider_fixture([response_fixture(usage=usage)])
        result = asyncio.run(
            provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
        )
        assert result.status == ProviderStatus.COMPLETED
        assert result.metadata.usage.cached_input_tokens == expected


def test_truncation_keeps_usage_and_attempt_is_not_retried(tmp_path: Path) -> None:
    provider, transport, recorder, ledger = provider_fixture(
        [
            response_fixture(
                finish_reason="length", usage={"prompt_tokens": 10, "completion_tokens": 4}
            )
        ]
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "provider.response_limit"
    assert result.metadata.usage.output_tokens == 4
    assert len(transport.payloads) == len(recorder.records) == ledger.requests == 1


@pytest.mark.parametrize(
    "problem",
    [
        "wide",
        "six",
        "cross_media",
        "cross_run",
        "hash",
        "audio",
        "schema",
        "prompt",
        "budget_tokens",
        "video",
    ],
)
def test_preflight_rejects_capability_evidence_and_namespace_mismatch(
    tmp_path: Path, problem: str
) -> None:
    request = request_fixture(
        tmp_path, width=513 if problem == "wide" else 512, frames=6 if problem == "six" else 1
    )
    item = request.evidence[0]
    if problem == "cross_media":
        request = replace(request, evidence=(item, replace(item, media_id="media-2")))
    elif problem == "cross_run":
        request = replace(
            request, evidence=(replace(item, evidence_id="other:media-1:image:000000"),)
        )
    elif problem == "hash":
        request = replace(request, evidence=(replace(item, sha256="a" * 64),))
    elif problem == "audio":
        request = replace(request, evidence=(replace(item, kind="audio"),))
    elif problem == "schema":
        request = replace(request, schema_version="unknown")
    elif problem == "prompt":
        request = replace(request, prompt_version="unknown")
    elif problem == "budget_tokens":
        request = replace(request, max_output_tokens=True)
    elif problem == "video":
        item.artifact_path.write_bytes(b"not-a-jpeg-video")
        request = replace(
            request,
            evidence=(replace(item, sha256=hashlib.sha256(b"not-a-jpeg-video").hexdigest()),),
        )
    provider, transport, recorder, ledger = provider_fixture([])
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.records and ledger.requests == 0


@pytest.mark.parametrize("problem", ["sof_only", "no_scan", "truncated", "trailing", "components"])
def test_incomplete_jpeg_is_rejected_before_network(tmp_path: Path, problem: str) -> None:
    request = request_fixture(tmp_path)
    item = request.evidence[0]
    image = bytearray(item.artifact_path.read_bytes())
    if problem == "sof_only":
        image = bytearray(b"\xff\xd8\xff\xc0" + struct.pack(">HBHHB", 8, 8, 288, 512, 0))
        image.extend(b"\xff\xd9")
    elif problem == "no_scan":
        image = image[: image.index(b"\xff\xda")] + b"\xff\xd9"
    elif problem == "truncated":
        image = image[:-2]
    elif problem == "trailing":
        image.extend(b"x")
    else:
        image[image.index(b"\xff\xc0") + 9] = 0
    item.artifact_path.write_bytes(image)
    request = replace(request, evidence=(replace(item, sha256=hashlib.sha256(image).hexdigest()),))
    provider, transport, recorder, ledger = provider_fixture([])
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.records and ledger.requests == 0


@pytest.mark.parametrize("mode", ["cancelled", "timeout"])
def test_durable_begin_wait_is_included_in_deadline_and_cancel(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        context = CancellationContext("run-1", 0.01 if mode == "timeout" else 2)

        class SlowRecorder(Recorder):
            async def begin_invocation(
                self,
                invocation_id: str,
                run_id: str,
                stage_id: str,
                logical_request_id: str,
                metadata: InvocationMetadata,
            ) -> None:
                await super().begin_invocation(
                    invocation_id, run_id, stage_id, logical_request_id, metadata
                )
                if mode == "cancelled":
                    context.cancelled.set()
                else:
                    await asyncio.sleep(0.02)

        recorder = SlowRecorder()
        transport = FakeTransport([], recorder)
        ledger = BudgetLedger(Decimal(1), 3, 15)
        provider = DeepSeekVisionProvider(transport, ledger, Decimal("0.1"), recorder)
        result = await provider.analyze(request_fixture(tmp_path), context)
        assert result.error and result.error.code == f"provider.{mode}"
        assert not transport.payloads and len(recorder.records) == 1
        assert recorder.records[0].status == (
            InvocationStatus.CANCELLED if mode == "cancelled" else InvocationStatus.FAILED
        )
        assert ledger.reserved_cny == Decimal("0.1")

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [401, 403, 400, 402, 302])
def test_nonretryable_http_errors_discard_private_body(tmp_path: Path, status: int) -> None:
    provider, transport, recorder, _ = provider_fixture(
        [HttpResponse(status, b"private-error-body")]
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and not result.error.retryable
    assert len(transport.payloads) == len(recorder.records) == 1
    assert "private-error-body" not in repr(result)


@pytest.mark.parametrize(
    "reply",
    [HttpResponse(429, b""), HttpResponse(500, b""), TransportError("provider.network", True)],
)
def test_each_retry_has_a_separate_durable_attempt_and_unknown_charge(
    tmp_path: Path, reply: HttpResponse | Exception
) -> None:
    provider, transport, recorder, ledger = provider_fixture([reply, reply, reply])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.status == ProviderStatus.FAILED and result.metadata.attempt == 3
    assert len(transport.payloads) == len(recorder.records) == ledger.requests == 3
    assert [r.metadata.attempt for r in recorder.records] == [1, 2, 3]
    assert len({r.invocation_id for r in recorder.records}) == 3
    assert len({r.logical_request_id for r in recorder.records}) == 1
    assert all(r.status == InvocationStatus.FAILED for r in recorder.records)
    assert ledger.reserved_cny == Decimal("0.3") and ledger.known_cost_cny == 0


def test_retry_does_not_inherit_previous_attempt_usage_or_model(tmp_path: Path) -> None:
    provider, _, recorder, _ = provider_fixture(
        [response_fixture(finish_reason="length", usage={"prompt_tokens": 100})]
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.metadata.usage.input_tokens == 100
    provider, _, recorder, _ = provider_fixture([HttpResponse(429, b""), response_fixture()])
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.status == ProviderStatus.COMPLETED
    assert recorder.records[0].metadata.actual_model is None
    assert recorder.records[1].metadata.usage.input_tokens is None


@pytest.mark.parametrize("reservation", [None, Decimal(0), Decimal("NaN")])
def test_missing_reservation_blocks_network_and_recording(
    tmp_path: Path, reservation: Decimal | None
) -> None:
    provider, transport, recorder, _ = provider_fixture([], reservation=reservation)
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code.startswith("budget.")
    assert not transport.payloads and not recorder.records


def test_retry_budget_stops_before_next_attempt(tmp_path: Path) -> None:
    provider, transport, recorder, ledger = provider_fixture(
        [HttpResponse(429, b"")], budget=BudgetLedger(Decimal("0.1"), 3, 15)
    )
    result = asyncio.run(
        provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
    )
    assert result.error and result.error.code == "budget.exhausted"
    assert len(transport.payloads) == len(recorder.records) == ledger.requests == 1


@pytest.mark.parametrize("mode", ["context", "timeout", "external"])
def test_cancel_and_timeout_stop_transport_and_finish_unknown_attempt(
    tmp_path: Path, mode: str
) -> None:
    async def scenario() -> None:
        transport = WaitingTransport()
        recorder = Recorder()
        ledger = BudgetLedger(Decimal(1), 3, 15)
        provider = DeepSeekVisionProvider(transport, ledger, Decimal("0.1"), recorder)
        context = CancellationContext("run-1", 0.03 if mode == "timeout" else 2)
        pending = asyncio.create_task(provider.analyze(request_fixture(tmp_path), context))
        await asyncio.wait_for(transport.started.wait(), 1)
        if mode == "context":
            context.cancelled.set()
        elif mode == "external":
            pending.cancel()
        if mode == "external":
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            result = await asyncio.wait_for(pending, 1)
            assert (
                result.error
                and result.error.code == f"provider.{mode if mode == 'timeout' else 'cancelled'}"
            )
        assert transport.closed
        assert recorder.records[0].status == (
            InvocationStatus.FAILED if mode == "timeout" else InvocationStatus.CANCELLED
        )
        assert recorder.records[0].metadata.elapsed_ms is not None
        assert ledger.reserved_cny == Decimal("0.1")

    asyncio.run(scenario())


def test_provider_protocol_can_be_replaced_without_network(tmp_path: Path) -> None:
    class OfflineProvider:
        @property
        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(image_sequence=True)

        async def analyze(
            self, request: VisionRequest, context: CancellationContext
        ) -> ProviderResult[tuple[SemanticEvent, ...]]:
            return ProviderResult(
                ProviderStatus.COMPLETED,
                (),
                InvocationMetadata(
                    "fixture",
                    "fixture-model",
                    "fixture-model",
                    "snapshot-1",
                    request.prompt_version,
                    request.schema_version,
                    1,
                    ProviderUsage(),
                ),
            )

    provider: VisionProvider = OfflineProvider()
    assert (
        asyncio.run(
            provider.analyze(request_fixture(tmp_path), CancellationContext("run-1", 2))
        ).output
        == ()
    )


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, parts: list[bytes], *, block: bool = False) -> None:
        self.parts = parts
        self.block = block
        self.closed = False
        self.started = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.started.set()
        for part in self.parts:
            yield part
        if self.block:
            await asyncio.Future[None]()

    async def aclose(self) -> None:
        self.closed = True


def test_httpx_uses_official_url_no_proxy_and_no_private_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Replace the environment object rather than reading any existing credential value.
    monkeypatch.setattr(
        os,
        "environ",
        {
            "DEEPSEEK_API_KEY": "offline-test",
            "HTTPS_PROXY": "http://offline.invalid",
            "SSL_CERT_FILE": "missing-private-path",
        },
    )
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == DEEPSEEK_ENDPOINT
        assert request.headers["authorization"] == "Bearer offline-test"
        return httpx.Response(
            302, headers={"location": "https://offline.invalid"}, content=b"private-error-body"
        )

    response = asyncio.run(HttpxVisionTransport(httpx.MockTransport(handler)).post({}, 1))
    assert response.status_code == 302 and response.body == b"" and len(requests) == 1


@pytest.mark.parametrize("mode", ["header", "stream", "compressed"])
def test_httpx_bounded_body_and_response_cleanup(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setattr(os, "environ", {"DEEPSEEK_API_KEY": "offline-test"})
    stream = ResponseStream([b"x" * (MAX_RESPONSE_BYTES // 2 + 1)] * 2)
    headers = {"content-length": str(MAX_RESPONSE_BYTES + 1)} if mode == "header" else {}
    if mode == "compressed":
        headers["content-encoding"] = "gzip"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, stream=stream)

    with pytest.raises(TransportError, match="provider.response_limit"):
        asyncio.run(HttpxVisionTransport(httpx.MockTransport(handler)).post({}, 1))
    assert stream.closed


def test_httpx_network_error_never_contains_raw_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "environ", {"DEEPSEEK_API_KEY": "offline-test"})

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-error-body", request=request)

    with pytest.raises(TransportError) as captured:
        asyncio.run(HttpxVisionTransport(httpx.MockTransport(handler)).post({}, 1))
    assert str(captured.value) == "provider.network" and captured.value.retryable
    assert captured.value.__cause__ is None


def test_httpx_missing_credential_fails_before_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "environ", {})

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Credential failure cannot send requests.")

    with pytest.raises(TransportError, match="provider.auth"):
        asyncio.run(HttpxVisionTransport(httpx.MockTransport(handler)).post({}, 1))


def test_httpx_cancel_closes_active_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "environ", {"DEEPSEEK_API_KEY": "offline-test"})

    async def scenario() -> None:
        stream = ResponseStream([], block=True)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=stream)

        transport = HttpxVisionTransport(httpx.MockTransport(handler))
        pending = asyncio.create_task(transport.post({}, 2))
        await asyncio.wait_for(stream.started.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert stream.closed

    asyncio.run(scenario())
