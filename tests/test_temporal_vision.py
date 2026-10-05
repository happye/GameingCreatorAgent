"""Offline transport contracts; synthetic images never prove gameplay understanding."""

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
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.deepseek_vision import (
    MAX_IMAGES,
    MAX_IMAGES_V3,
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    SCHEMA_VERSION,
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
        assert self.recorder.begun and not self.recorder.finished
        self.payloads.append(payload)
        return HttpResponse(
            200,
            json.dumps(
                {
                    "id": "chatcmpl-temporal-offline",
                    "model": "deepseek-flash",
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
    references = []
    for index in range(frames):
        # Change synthetic scan bytes to exercise verified content hashes, not real motion.
        data = header + b"\x9f" + bytes([0xC0 if static else 0xC0 + index])
        data += b"\x00" * 863 + b"\x7f\xff\xd9"
        path = tmp_path / f"frame-{index}.jpg"
        path.write_bytes(data)
        references.append(
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
    return VisionRequest("run-1", tuple(references), PROMPT_VERSION_V3, SCHEMA_VERSION, 2048)


def action_event(*, frames: int = 3) -> dict[str, object]:
    return {
        "startUs": 1_000_000,
        "endUs": 1_000_001 + (frames - 1) * 500_000,
        "observableFacts": [
            "A character takes off, rises over a platform edge, then lands on the next platform."
        ],
        "mechanicTags": ["jumping"],
        "evidenceIds": [f"f{index}" for index in range(frames)],
        "uncertainty": "Player control cannot be confirmed from this camera angle.",
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


def schema_code(result: ProviderResult[tuple[SemanticEvent, ...]]) -> str:
    assert result.error and result.error.code == "provider.schema"
    assert not result.error.retryable and result.output is None
    details = result.metadata.execution_details
    assert details is not None
    return cast(str, json.loads(details)["schemaError"])


@pytest.mark.parametrize("language", ["zh", "en"])
def test_v3_joint_action_maps_aliases_and_records_version(tmp_path: Path, language: str) -> None:
    request = replace(request_fixture(tmp_path), language=language)
    result, transport, recorder, budget = analyze(request, [action_event()])
    assert result.status == ProviderStatus.COMPLETED and result.output
    event = result.output[0]
    assert event.source_range.start_us == 1_000_000
    assert event.source_range.end_us == 2_000_001
    assert event.evidence_ids == tuple(item.evidence_id for item in request.evidence)
    assert event.mechanic_tags == ("jumping",)
    assert result.metadata.prompt_version == PROMPT_VERSION_V3
    assert recorder.finished[0] == (InvocationStatus.COMPLETED, result.metadata, None)
    assert budget.frames == 3
    messages = cast(list[dict[str, object]], transport.payloads[0]["messages"])
    blocks = cast(list[dict[str, object]], messages[1]["content"])
    info = json.loads(cast(str, blocks[0]["text"]))
    assert info == {
        "durationUs": 10_000_000,
        "language": language,
        "gameTerms": [],
        "windowFirstSourceUs": 1_000_000,
        "windowLastSourceUs": 2_000_000,
    }
    frame_info = [json.loads(cast(str, blocks[index]["text"])) for index in (1, 3, 5)]
    assert [frame["evidenceId"] for frame in frame_info] == ["f0", "f1", "f2"]
    assert [frame["sourceUs"] for frame in frame_info] == [1_000_000, 1_500_000, 2_000_000]
    serialized = json.dumps(transport.payloads[0])
    assert str(tmp_path) not in serialized and "run-1:media-1:image:" not in serialized


def test_v3_supports_nine_aliases_and_rejects_tenth_image(tmp_path: Path) -> None:
    request = request_fixture(tmp_path, frames=MAX_IMAGES_V3)
    result, transport, _, _ = analyze(request, [action_event(frames=MAX_IMAGES_V3)])
    assert result.status == ProviderStatus.COMPLETED and result.output
    assert len(result.output[0].evidence_ids) == 9
    assert json.dumps(transport.payloads[0]).count("data:image/jpeg;base64,") == 9
    result, transport, recorder, budget = analyze(request_fixture(tmp_path, frames=10), [])
    assert result.error and result.error.code == "provider.input"
    assert transport.payloads == [] and recorder.begun == [] and budget.frames == 0


@pytest.mark.parametrize("version", [PROMPT_VERSION, PROMPT_VERSION_V2])
def test_legacy_versions_still_reject_six_images(tmp_path: Path, version: str) -> None:
    request = replace(request_fixture(tmp_path, frames=MAX_IMAGES + 1), prompt_version=version)
    result, transport, recorder, _ = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert transport.payloads == [] and recorder.begun == []


@pytest.mark.parametrize("ordering", ["descending", "duplicate"])
def test_v3_rejects_nonincreasing_source_times_without_reordering(
    tmp_path: Path, ordering: str
) -> None:
    request = request_fixture(tmp_path)
    if ordering == "descending":
        request = replace(request, evidence=tuple(reversed(request.evidence)))
    else:
        items = list(request.evidence)
        items[1] = replace(items[1], source_time=items[0].source_time)
        request = replace(request, evidence=tuple(items))
    result, transport, recorder, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert transport.payloads == [] and recorder.begun == [] and budget.frames == 0


@pytest.mark.parametrize("boundary", ["before_window", "after_window"])
def test_v3_rejects_event_extent_outside_observed_window(tmp_path: Path, boundary: str) -> None:
    event = action_event()
    event["startUs" if boundary == "before_window" else "endUs"] = (
        999_999 if boundary == "before_window" else 2_000_002
    )
    event["observableFacts"] = ["private-untrusted-model-text"]
    result, _, recorder, _ = analyze(request_fixture(tmp_path), [event])
    assert schema_code(result) == "event_window_range"
    assert "private-untrusted-model-text" not in (result.metadata.execution_details or "")
    assert recorder.finished[0][1] == result.metadata


@pytest.mark.parametrize("frames", [1, 3])
def test_v3_single_frame_evidence_cannot_claim_action(tmp_path: Path, frames: int) -> None:
    event = action_event(frames=frames)
    event["evidenceIds"] = ["f0"]
    result, _, _, _ = analyze(request_fixture(tmp_path, frames=frames), [event])
    assert schema_code(result) == "event_temporal_evidence"


def test_v3_identical_image_hashes_cannot_claim_action(tmp_path: Path) -> None:
    result, _, _, _ = analyze(request_fixture(tmp_path, static=True), [action_event()])
    assert schema_code(result) == "event_static_evidence"


@pytest.mark.parametrize("frames", [1, 3])
def test_v3_single_frame_or_static_window_can_abstain(tmp_path: Path, frames: int) -> None:
    request = request_fixture(tmp_path, frames=frames, static=True)
    if frames == 1:
        # The last source microsecond remains a valid empty tail window.
        item = replace(request.evidence[0], source_time=SourceInstant(9_999_999, 10_000_000))
        request = replace(request, evidence=(item,))
    result, _, recorder, _ = analyze(request, [])
    assert result.status == ProviderStatus.COMPLETED and result.output == ()
    assert recorder.finished[0][0] == InvocationStatus.COMPLETED


@pytest.mark.parametrize("alias", ["f9", "f00", "F0", "run-1:media-1:image:000000"])
def test_v3_rejects_foreign_or_noncanonical_aliases(tmp_path: Path, alias: str) -> None:
    event = action_event()
    event["evidenceIds"] = ["f0", alias]
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    assert schema_code(result) == "evidence_unknown"


def test_v3_cited_frame_must_be_inside_half_open_event(tmp_path: Path) -> None:
    event = action_event()
    event["endUs"] = 2_000_000
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    assert schema_code(result) == "evidence_outside_range"


def test_v3_rejects_per_frame_event_collection(tmp_path: Path) -> None:
    events = [dict(action_event(), observableFacts=[f"Action {index}"]) for index in range(4)]
    result, _, _, _ = analyze(request_fixture(tmp_path), events)
    assert schema_code(result) == "event_collection"


def test_legacy_prompt_hashes_remain_frozen_and_v3_has_independent_identity() -> None:
    assert vision_prompt_fingerprint(PROMPT_VERSION) == (
        "c3a6d3f286b5e8b582a91929afcfde038d39ff605d017619919e1a583c507d26"
    )
    assert vision_prompt_fingerprint(PROMPT_VERSION_V2) == (
        "f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236"
    )
    fingerprints = {
        vision_prompt_fingerprint(version)
        for version in (PROMPT_VERSION, PROMPT_VERSION_V2, PROMPT_VERSION_V3)
    }
    assert len(fingerprints) == 3
    with pytest.raises(ValueError, match="Unsupported vision prompt version"):
        vision_prompt_fingerprint("phase0-vision-v7")


def test_temporal_example_pins_the_shipped_frame_boundary_prompt_hash() -> None:
    root = Path(__file__).resolve().parents[1]
    temporal = json.loads((root / "config.temporal.example.json").read_text(encoding="utf-8"))
    legacy = json.loads((root / "config.example.json").read_text(encoding="utf-8"))
    latest_hash = vision_prompt_fingerprint("phase0-vision-v4")
    assert temporal["vision"]["promptVersion"] == "phase0-vision-v4"
    assert temporal["vision"]["promptHash"] == latest_hash
    assert len(latest_hash) == 64 and set(latest_hash) <= set("0123456789abcdef")
    assert temporal["sampling"] == {"intervalMs": 500, "windowFrames": 9, "windowOverlap": 2}
    assert legacy["vision"]["promptVersion"] == PROMPT_VERSION_V2
    assert legacy["vision"]["promptHash"] == (
        "f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236"
    )


def test_provider_reports_expanded_implementation_limit() -> None:
    recorder = Recorder()
    provider = DeepSeekVisionProvider(
        FakeTransport([], recorder), BudgetLedger(Decimal("1"), 3, 40), Decimal("0.1"), recorder
    )
    assert provider.capabilities.max_images == MAX_IMAGES_V3 == 9
    assert provider.capabilities.max_image_width == 1280
    assert provider.capabilities.image_sequence and not provider.capabilities.native_video
