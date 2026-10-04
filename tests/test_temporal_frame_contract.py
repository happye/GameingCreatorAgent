"""Frame-alias boundaries are transport contracts, not proof of action understanding."""

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    VisionRequest,
)
from gamingcreator.application.storage import InvocationStatus
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.deepseek_vision import (
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V4,
    DeepSeekVisionProvider,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.http_transport import HttpResponse


class Recorder:
    def __init__(self) -> None:
        self.begun: list[InvocationMetadata] = []
        self.finished: list[tuple[InvocationStatus, InvocationMetadata, str | None]] = []

    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None:
        self.begun.append(metadata)

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None:
        self.finished.append((status, metadata, error_code))


class FakeTransport:
    def __init__(self, events: list[dict[str, object]], recorder: Recorder) -> None:
        self.events = events
        self.recorder = recorder
        self.payloads: list[dict[str, object]] = []

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        assert len(self.recorder.begun) == 1 and not self.recorder.finished
        self.payloads.append(payload)
        return HttpResponse(
            200,
            json.dumps(
                {
                    "id": "chatcmpl-frame-contract-offline",
                    "model": "deepseek-flash",
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 3,
                        "prompt_cache_hit_tokens": 2,
                        "prompt_cache_miss_tokens": 18,
                        "total_tokens": 23,
                    },
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps({"events": self.events}),
                            },
                        }
                    ],
                }
            ).encode(),
        )


def request_fixture(tmp_path: Path, *, frames: int = 3, static: bool = False) -> VisionRequest:
    header = bytes.fromhex(
        "ffd8ffe000104a46494600010200000100010000fffe00104c61766336322e32392e31303000"
        "ffdb0043000828282f282f373737373737413c41434343414141414343434848485555554848"
        "4843434848505055555c5f5c575755575f5f646464787873738c8c91acaccfffc4004b0001"
        "010000000000000000000000000000000801010000000000000000000000000000000010"
        "0100000000000000000000000000000000110100000000000000000000000000000000ff"
        "c00011080120020003012200021100031100ffda000c03010002110311003f00"
    )
    evidence = []
    for index in range(frames):
        # Distinct synthetic scans exercise verified hashes; they do not simulate gameplay.
        data = header + b"\x9f" + bytes([0xC0 if static else 0xC0 + index])
        data += b"\x00" * 863 + b"\x7f\xff\xd9"
        path = tmp_path / f"frame-{index}.jpg"
        path.write_bytes(data)
        evidence.append(
            EvidenceReference(
                f"run-1:media-1:image:{index:06d}",
                "media-1",
                "image",
                SourceInstant(1_000_000 + index * 500_000, 10_000_000),
                path,
                hashlib.sha256(data).hexdigest(),
                "media-v1",
            )
        )
    return VisionRequest("run-1", tuple(evidence), PROMPT_VERSION_V4, SCHEMA_VERSION_V4, 2048)


def action_event(*, frames: int = 3) -> dict[str, object]:
    return {
        "startFrameId": "f0",
        "endFrameId": f"f{frames - 1}",
        "observableFacts": ["A character takes off, rises, then lands on a platform."],
        "mechanicTags": ["jumping"],
        "evidenceIds": [f"f{index}" for index in range(frames)],
        "uncertainty": "Player control is not confirmed.",
    }


def analyze(
    request: VisionRequest, events: list[dict[str, object]]
) -> tuple[ProviderResult[tuple[SemanticEvent, ...]], FakeTransport, Recorder, BudgetLedger]:
    recorder = Recorder()
    transport = FakeTransport(events, recorder)
    budget = BudgetLedger(Decimal("1"), 3, 40)
    provider = DeepSeekVisionProvider(transport, budget, Decimal("0.1"), recorder)
    result = asyncio.run(provider.analyze(request, CancellationContext("run-1", 2)))
    return result, transport, recorder, budget


def schema_detail(
    result: ProviderResult[tuple[SemanticEvent, ...]], code: str
) -> dict[str, object]:
    assert result.error and result.error.code == "provider.schema"
    assert not result.error.retryable and result.output is None
    details = cast(dict[str, object], json.loads(result.metadata.execution_details or "{}"))
    assert details["schemaError"] == code
    return cast(dict[str, object], details.get("schemaDetail", {}))


@pytest.mark.parametrize("language", ["zh", "en"])
def test_v4_inclusive_frame_aliases_map_exact_source_range(tmp_path: Path, language: str) -> None:
    request = replace(request_fixture(tmp_path), language=language)
    result, transport, recorder, budget = analyze(request, [action_event()])
    assert result.status == ProviderStatus.COMPLETED and result.output
    event = result.output[0]
    assert event.source_range == SourceRange(1_000_000, 2_000_001, 10_000_000)
    assert event.evidence_ids == tuple(item.evidence_id for item in request.evidence)
    assert event.mechanic_tags == ("jumping",)
    assert result.metadata.prompt_version == PROMPT_VERSION_V4
    assert result.metadata.schema_version == SCHEMA_VERSION_V4
    assert recorder.finished == [(InvocationStatus.COMPLETED, result.metadata, None)]
    assert result.metadata.usage.input_tokens == 20
    assert result.metadata.usage.output_tokens == 3
    assert result.metadata.usage.cached_input_tokens == 2
    assert result.metadata.usage.cost_cny is None
    assert budget.frames == 3 and budget.requests == 1
    messages = cast(list[dict[str, object]], transport.payloads[0]["messages"])
    system = cast(str, messages[0]["content"])
    assert "startFrameId" in system and "endFrameId" in system
    assert "Do NOT return startUs or endUs or calculate microseconds" in system
    blocks = cast(list[dict[str, object]], messages[1]["content"])
    frames = [json.loads(cast(str, blocks[index]["text"])) for index in (1, 3, 5)]
    assert frames == [
        {"evidenceId": "f0", "sourceUs": 1_000_000},
        {"evidenceId": "f1", "sourceUs": 1_500_000},
        {"evidenceId": "f2", "sourceUs": 2_000_000},
    ]
    serialized = json.dumps(transport.payloads[0])
    assert str(tmp_path) not in serialized and "run-1:media-1:image:" not in serialized


def test_v4_can_select_subset_boundaries_and_skip_intermediate_frames(tmp_path: Path) -> None:
    request = request_fixture(tmp_path, frames=5)
    event = action_event(frames=5)
    event.update(startFrameId="f1", endFrameId="f3", evidenceIds=["f1", "f3"])
    result, _, _, _ = analyze(request, [event])
    assert result.output and result.output[0].source_range == SourceRange(
        1_500_000, 2_500_001, 10_000_000
    )
    assert result.output[0].evidence_ids == (
        request.evidence[1].evidence_id,
        request.evidence[3].evidence_id,
    )


def test_v4_last_frame_can_be_last_source_microsecond(tmp_path: Path) -> None:
    request = request_fixture(tmp_path, frames=2)
    first, last = request.evidence
    request = replace(
        request,
        evidence=(first, replace(last, source_time=SourceInstant(9_999_999, 10_000_000))),
    )
    result, _, _, _ = analyze(request, [action_event(frames=2)])
    assert result.output and result.output[0].source_range.end_us == 10_000_000


def test_v4_nine_frame_cap_and_three_action_cap(tmp_path: Path) -> None:
    request = request_fixture(tmp_path, frames=9)
    result, transport, _, _ = analyze(request, [action_event(frames=9)])
    assert result.output and len(result.output[0].evidence_ids) == 9
    assert json.dumps(transport.payloads[0]).count("data:image/jpeg;base64,") == 9
    result, transport, recorder, budget = analyze(request_fixture(tmp_path, frames=10), [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun and budget.requests == 0
    result, _, _, _ = analyze(
        request, [dict(action_event(frames=9), observableFacts=[f"Action {i}"]) for i in range(4)]
    )
    schema_detail(result, "event_collection")


@pytest.mark.parametrize("version", [PROMPT_VERSION, PROMPT_VERSION_V2, PROMPT_VERSION_V3])
def test_v4_schema_cannot_be_used_with_legacy_prompt(tmp_path: Path, version: str) -> None:
    request = replace(request_fixture(tmp_path), prompt_version=version)
    result, transport, recorder, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun and budget.requests == 0


def test_v4_requires_its_own_schema_before_http(tmp_path: Path) -> None:
    request = replace(request_fixture(tmp_path), schema_version=SCHEMA_VERSION)
    result, transport, recorder, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun and budget.requests == 0


@pytest.mark.parametrize("mode", ["descending", "same_time"])
def test_v4_rejects_unordered_source_frames_before_http(tmp_path: Path, mode: str) -> None:
    request = request_fixture(tmp_path)
    if mode == "descending":
        request = replace(request, evidence=tuple(reversed(request.evidence)))
    else:
        items = list(request.evidence)
        items[1] = replace(items[1], source_time=items[0].source_time)
        request = replace(request, evidence=tuple(items))
    result, transport, recorder, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun and budget.requests == 0


@pytest.mark.parametrize("field", ["startFrameId", "endFrameId"])
@pytest.mark.parametrize("alias", ["f9", "f00", "F0", "run-1:media-1:image:000000", 0, None])
def test_v4_rejects_unknown_or_wrong_endpoint_types(
    tmp_path: Path, field: str, alias: object
) -> None:
    event = action_event()
    event[field] = alias
    result, _, recorder, _ = analyze(request_fixture(tmp_path), [event])
    code = "evidence_unknown" if isinstance(alias, str) else "event_frame_boundaries"
    assert schema_detail(result, code) == {"eventIndex": 0}
    assert recorder.finished[0][1] == result.metadata


@pytest.mark.parametrize("mode", ["omitted", "old_times", "extra_time"])
def test_v4_exact_six_fields_reject_omitted_or_numeric_boundaries(
    tmp_path: Path, mode: str
) -> None:
    event = action_event()
    if mode == "omitted":
        del event["endFrameId"]
    elif mode == "old_times":
        del event["startFrameId"]
        del event["endFrameId"]
        event.update(startUs=1_000_000, endUs=2_000_001)
    else:
        event["endUs"] = 2_000_001
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    assert schema_detail(result, "event_fields") == {"eventIndex": 0}


@pytest.mark.parametrize("bounds", [("f2", "f0"), ("f1", "f1")])
def test_v4_rejects_reversed_or_identical_boundaries(
    tmp_path: Path, bounds: tuple[str, str]
) -> None:
    event = action_event()
    event.update(startFrameId=bounds[0], endFrameId=bounds[1])
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    detail = schema_detail(result, "event_frame_boundaries")
    assert detail["eventIndex"] == 0 and set(detail) == {"eventIndex", "startUs", "endUs"}


@pytest.mark.parametrize("aliases", [["f0", "f1"], ["f1", "f2"]])
def test_v4_requires_both_boundaries_in_evidence(tmp_path: Path, aliases: list[str]) -> None:
    event = action_event()
    event["evidenceIds"] = aliases
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    schema_detail(result, "event_boundary_evidence")


def test_v4_evidence_cannot_come_from_outside_selected_frames(tmp_path: Path) -> None:
    event = action_event()
    event["startFrameId"] = "f1"
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    assert schema_detail(result, "evidence_outside_range") == {
        "eventIndex": 0,
        "startUs": 1_500_000,
        "endUs": 2_000_001,
        "frameAlias": "f0",
        "sourceUs": 1_000_000,
    }


def test_v4_evidence_must_preserve_frame_order(tmp_path: Path) -> None:
    event = action_event()
    event["evidenceIds"] = ["f0", "f2", "f1"]
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    schema_detail(result, "event_evidence_order")


def test_v4_single_frame_cannot_claim_action(tmp_path: Path) -> None:
    result, _, _, _ = analyze(request_fixture(tmp_path, frames=1), [action_event(frames=1)])
    schema_detail(result, "event_frame_boundaries")


def test_v4_equal_image_hashes_cannot_claim_action(tmp_path: Path) -> None:
    result, _, _, _ = analyze(request_fixture(tmp_path, static=True), [action_event()])
    schema_detail(result, "event_static_evidence")


@pytest.mark.parametrize("frames", [1, 3])
def test_v4_static_or_single_frame_window_can_return_no_actions(
    tmp_path: Path, frames: int
) -> None:
    result, _, recorder, _ = analyze(request_fixture(tmp_path, frames=frames, static=True), [])
    assert result.status == ProviderStatus.COMPLETED and result.output == ()
    assert recorder.finished[0][0] == InvocationStatus.COMPLETED


def test_v3_outside_range_retains_safe_numeric_diagnostic_and_usage(tmp_path: Path) -> None:
    request = replace(
        request_fixture(tmp_path), prompt_version=PROMPT_VERSION_V3, schema_version=SCHEMA_VERSION
    )
    event = action_event()
    del event["startFrameId"]
    del event["endFrameId"]
    event.update(startUs=1_000_000, endUs=2_000_000)
    event["observableFacts"] = ["private-model-content-never-store-this"]
    result, transport, recorder, budget = analyze(request, [event])
    assert schema_detail(result, "evidence_outside_range") == {
        "eventIndex": 0,
        "startUs": 1_000_000,
        "endUs": 2_000_000,
        "frameAlias": "f2",
        "sourceUs": 2_000_000,
    }
    assert "private-model-content-never-store-this" not in (result.metadata.execution_details or "")
    assert result.metadata.usage.input_tokens == 20 and result.metadata.usage.output_tokens == 3
    assert result.metadata.usage.cached_input_tokens == 2 and result.metadata.usage.cost_cny is None
    assert len(transport.payloads) == len(recorder.begun) == len(recorder.finished) == 1
    assert recorder.finished[0] == (InvocationStatus.FAILED, result.metadata, "provider.schema")
    assert budget.requests == 1 and budget.reserved_cny == Decimal("0.1")


def test_diagnostics_do_not_echo_arbitrary_endpoint_content(tmp_path: Path) -> None:
    request = replace(
        request_fixture(tmp_path), prompt_version=PROMPT_VERSION_V3, schema_version=SCHEMA_VERSION
    )
    event = action_event()
    del event["startFrameId"]
    del event["endFrameId"]
    event.update(startUs="private-model-secret", endUs=2_000_001)
    result, _, _, _ = analyze(request, [event])
    assert schema_detail(result, "time_type") == {"eventIndex": 0, "endUs": 2_000_001}
    assert "private-model-secret" not in (result.metadata.execution_details or "")


def test_v4_unknown_alias_diagnostic_is_limited_to_canonical_aliases(tmp_path: Path) -> None:
    event = action_event()
    event["endFrameId"] = "f8"
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    assert schema_detail(result, "evidence_unknown") == {"eventIndex": 0, "frameAlias": "f8"}


def test_all_previous_prompt_hashes_are_frozen_and_v4_has_new_identity() -> None:
    assert vision_prompt_fingerprint(PROMPT_VERSION) == (
        "c3a6d3f286b5e8b582a91929afcfde038d39ff605d017619919e1a583c507d26"
    )
    assert vision_prompt_fingerprint(PROMPT_VERSION_V2) == (
        "f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236"
    )
    assert vision_prompt_fingerprint(PROMPT_VERSION_V3) == (
        "27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d"
    )
    assert vision_prompt_fingerprint(PROMPT_VERSION_V4) == (
        "9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48"
    )
    with pytest.raises(ValueError, match="Unsupported vision prompt version"):
        vision_prompt_fingerprint("phase0-vision-v6")
