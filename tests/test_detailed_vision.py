"""Bounded detail transport and prose hygiene; synthetic frames do not prove visual quality."""

import hashlib
import struct
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from test_temporal_frame_contract import (
    action_event,
    analyze,
    request_fixture,
    schema_detail,
)

from gamingcreator.application.providers import ProviderStatus, VisionRequest
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.deepseek_vision import (
    MAX_FACT_CHARACTERS_V5,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_BYTES_V5,
    MAX_IMAGE_WIDTH_V5,
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    PROMPT_VERSION_V5,
    SCHEMA_VERSION,
    SCHEMA_VERSION_V4,
    vision_prompt_fingerprint,
)


def detailed_request(
    tmp_path: Path, *, frames: int = 3, static: bool = False, width: int = 1280
) -> VisionRequest:
    request = request_fixture(tmp_path, frames=frames, static=static)
    evidence = []
    for item in request.evidence:
        image = bytearray(item.artifact_path.read_bytes())
        struct.pack_into(">H", image, image.index(b"\xff\xc0") + 7, width)
        item.artifact_path.write_bytes(image)
        evidence.append(replace(item, sha256=hashlib.sha256(image).hexdigest()))
    return replace(request, evidence=tuple(evidence), prompt_version=PROMPT_VERSION_V5)


def resize_image(request: VisionRequest, size: int) -> VisionRequest:
    """Extend a synthetic scan only to check bounded reads, not decoder or vision accuracy."""
    evidence = request.evidence[0]
    data = evidence.artifact_path.read_bytes()
    assert size >= len(data)
    image = data[:-2] + b"\x00" * (size - len(data)) + data[-2:]
    evidence.artifact_path.write_bytes(image)
    return replace(
        request,
        evidence=(
            replace(evidence, sha256=hashlib.sha256(image).hexdigest()),
            *request.evidence[1:],
        ),
    )


def test_v5_is_new_identity_with_all_legacy_prompt_bytes_frozen() -> None:
    expected = {
        PROMPT_VERSION: "c3a6d3f286b5e8b582a91929afcfde038d39ff605d017619919e1a583c507d26",
        PROMPT_VERSION_V2: "f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236",
        PROMPT_VERSION_V3: "27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d",
        PROMPT_VERSION_V4: "9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48",
    }
    assert {version: vision_prompt_fingerprint(version) for version in expected} == expected
    fingerprint = vision_prompt_fingerprint(PROMPT_VERSION_V5)
    assert fingerprint == "c64c644e9889fcfd91cc0e9a26d8bf1b9546ce73c548e6ac056a5067498ff98a"
    assert fingerprint not in expected.values()
    with pytest.raises(ValueError, match="Unsupported"):
        vision_prompt_fingerprint("phase0-vision-v7")


@pytest.mark.parametrize("language", ["zh", "en"])
def test_v5_preserves_actor_bound_details_and_requests_original_image_detail(
    tmp_path: Path, language: str
) -> None:
    request = replace(detailed_request(tmp_path, frames=9), language=language)
    event = action_event(frames=9)
    event.update(
        observableFacts=[
            "黑色角状头盔、银灰尖肩甲的高大角色右手握金色长杖，向前举杖后释放扩张的紫色圆弧。",
            "面向角色的红斗篷人向左退开；背景为有破损石柱的灰色圆形广场。",
        ],
        mechanicTags=["举杖", "释放圆弧"],
        uncertainty="无法从画面确认Boss身份、官方装备或技能名称，也不能确认玩家控制。",
    )
    result, transport, _, _ = analyze(request, [event])
    assert result.status == ProviderStatus.COMPLETED and result.output
    assert result.output[0].observable_facts == tuple(cast(list[str], event["observableFacts"]))
    assert result.output[0].uncertainty == event["uncertainty"]
    messages = cast(list[dict[str, object]], transport.payloads[0]["messages"])
    prompt = cast(str, messages[0]["content"])
    for instruction in (
        "FIRST write a complete subject + visible attributes + action sentence",
        "Bind attributes to the correct actor",
        "held equipment/tool shape and grip",
        "other actors' separate appearances",
        "environment/background",
        "effect shape/color/direction",
        "Uncertain player/NPC control does not erase observable actor attributes",
        "Never invent official character/item/skill names",
        "Do not repeat per-frame captions or turn static inventory into actions",
        "NEVER write f0, f1 or any frame alias",
    ):
        assert instruction in prompt
    blocks = cast(list[dict[str, object]], messages[1]["content"])
    images = [
        cast(dict[str, object], block["image_url"]) for block in blocks if "image_url" in block
    ]
    assert len(images) == 9 and all(image["detail"] == "original" for image in images)
    assert result.metadata.prompt_version == PROMPT_VERSION_V5
    assert result.metadata.schema_version == SCHEMA_VERSION_V4


@pytest.mark.parametrize(
    "prompt", [PROMPT_VERSION, PROMPT_VERSION_V2, PROMPT_VERSION_V3, PROMPT_VERSION_V4]
)
def test_legacy_payload_does_not_gain_original_detail_field(tmp_path: Path, prompt: str) -> None:
    schema = SCHEMA_VERSION_V4 if prompt == PROMPT_VERSION_V4 else SCHEMA_VERSION
    request = replace(
        detailed_request(tmp_path, width=512), prompt_version=prompt, schema_version=schema
    )
    result, transport, _, _ = analyze(request, [])
    assert result.status == ProviderStatus.COMPLETED
    messages = cast(list[dict[str, object]], transport.payloads[0]["messages"])
    blocks = cast(list[dict[str, object]], messages[1]["content"])
    for block in blocks:
        if "image_url" in block:
            assert set(cast(dict[str, object], block["image_url"])) == {"url"}


@pytest.mark.parametrize("schema", [SCHEMA_VERSION, "temporal-actions-v2"])
def test_v5_rejects_other_schemas_before_budget_or_transport(tmp_path: Path, schema: str) -> None:
    request = replace(detailed_request(tmp_path), schema_version=schema)
    result, transport, recorder, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun
    assert budget.requests == budget.frames == 0


@pytest.mark.parametrize("width, accepted", [(1280, True), (1281, False)])
def test_v5_enforces_project_image_width_cap(tmp_path: Path, width: int, accepted: bool) -> None:
    result, transport, _, _ = analyze(detailed_request(tmp_path, width=width), [])
    assert bool(transport.payloads) is accepted
    assert (result.status == ProviderStatus.COMPLETED) is accepted
    assert MAX_IMAGE_WIDTH_V5 == 1280


@pytest.mark.parametrize(
    "prompt", [PROMPT_VERSION, PROMPT_VERSION_V2, PROMPT_VERSION_V3, PROMPT_VERSION_V4]
)
def test_legacy_input_still_rejects_images_wider_than_512(tmp_path: Path, prompt: str) -> None:
    schema = SCHEMA_VERSION_V4 if prompt == PROMPT_VERSION_V4 else SCHEMA_VERSION
    request = replace(
        detailed_request(tmp_path, width=513), prompt_version=prompt, schema_version=schema
    )
    result, transport, _, _ = analyze(request, [])
    assert result.error and result.error.code == "provider.input" and not transport.payloads


@pytest.mark.parametrize("extra, accepted", [(0, True), (1, False)])
def test_v5_bounded_read_enforces_three_mib_cap(tmp_path: Path, extra: int, accepted: bool) -> None:
    request = resize_image(detailed_request(tmp_path), MAX_IMAGE_BYTES_V5 + extra)
    result, transport, _, _ = analyze(request, [])
    assert bool(transport.payloads) is accepted
    assert (result.status == ProviderStatus.COMPLETED) is accepted


@pytest.mark.parametrize(
    "prompt", [PROMPT_VERSION, PROMPT_VERSION_V2, PROMPT_VERSION_V3, PROMPT_VERSION_V4]
)
def test_legacy_byte_cap_remains_one_mib(tmp_path: Path, prompt: str) -> None:
    schema = SCHEMA_VERSION_V4 if prompt == PROMPT_VERSION_V4 else SCHEMA_VERSION
    request = resize_image(detailed_request(tmp_path, width=512), MAX_IMAGE_BYTES + 1)
    request = replace(request, prompt_version=prompt, schema_version=schema)
    result, transport, _, _ = analyze(request, [])
    assert result.error and result.error.code == "provider.input" and not transport.payloads


def test_v5_rejects_tenth_image_without_sending(tmp_path: Path) -> None:
    result, transport, _, _ = analyze(detailed_request(tmp_path, frames=10), [])
    assert result.error and result.error.code == "provider.input" and not transport.payloads


@pytest.mark.parametrize("facts", [["detail"] * 7, ["细" * (MAX_FACT_CHARACTERS_V5 + 1)]])
def test_v5_rejects_unbounded_fact_output(tmp_path: Path, facts: list[str]) -> None:
    event = dict(action_event(), observableFacts=facts)
    result, _, _, _ = analyze(detailed_request(tmp_path), [event])
    schema_detail(result, "event_facts")


def test_v5_accepts_six_distinct_facts_at_hard_character_bound(tmp_path: Path) -> None:
    facts = ["细" * 995, "甲", "乙", "丙", "丁", "戊"]
    event = dict(action_event(), observableFacts=facts)
    result, _, _, _ = analyze(detailed_request(tmp_path), [event])
    assert result.output and result.output[0].observable_facts == tuple(facts)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "f0中角色举杖，f0至f2间紫色波纹扩张。",
            "00:00:01.000中角色举杖，00:00:01.000至00:00:02.000间紫色波纹扩张。",
        ),
        ("f0/f1 and f0-f2", "00:00:01.000/00:00:01.500 and 00:00:01.000-00:00:02.000"),
        ("f0o and F1 and MF1 and foo_f1 and f1_item", "f0o and F1 and MF1 and foo_f1 and f1_item"),
        (
            "item-f0 and f0-name and item.f1 and pre-f0-f2 and f0-f2.name",
            "item-f0 and f0-name and item.f1 and pre-f0-f2 and f0-f2.name",
        ),
    ],
)
def test_v5_resolves_only_exact_lowercase_alias_tokens(
    tmp_path: Path, raw: str, expected: str
) -> None:
    event = dict(action_event(), observableFacts=[raw])
    result, _, _, _ = analyze(detailed_request(tmp_path), [event])
    assert result.output and result.output[0].observable_facts == (expected,)


def test_v5_alias_resolution_uses_actual_input_clock_in_all_free_text(tmp_path: Path) -> None:
    request = detailed_request(tmp_path, frames=5)
    event = dict(
        action_event(frames=5),
        startFrameId="f3",
        endFrameId="f4",
        evidenceIds=["f3", "f4"],
        observableFacts=["f3中蓝衣角色开始奔跑，至f4移到石墙前。"],
        mechanicTags=["f4可见移动"],
        uncertainty="f3的人物控制方式无法确认。",
    )
    result, _, _, _ = analyze(request, [event])
    assert result.output
    output = result.output[0]
    assert output.source_range == SourceRange(2_500_000, 3_000_001, 10_000_000)
    assert output.observable_facts == (
        "00:00:02.500中蓝衣角色开始奔跑，至00:00:03.000移到石墙前。",
    )
    assert output.mechanic_tags == ("00:00:03.000可见移动",)
    assert output.uncertainty == "00:00:02.500的人物控制方式无法确认。"
    normalized = dict(
        event,
        observableFacts=list(output.observable_facts),
        mechanicTags=list(output.mechanic_tags),
        uncertainty=output.uncertainty,
    )
    again, _, _, _ = analyze(request, [normalized])
    assert again.output == result.output


def test_v5_time_references_preserve_hours_minutes_milliseconds(tmp_path: Path) -> None:
    request = detailed_request(tmp_path)
    request = replace(
        request,
        evidence=tuple(
            replace(item, source_time=SourceInstant(3_661_123_456 + index * 500_000, 5_000_000_000))
            for index, item in enumerate(request.evidence)
        ),
    )
    event = dict(action_event(), observableFacts=["f0至f2角色冲刺。"])
    result, _, _, _ = analyze(request, [event])
    assert result.output and result.output[0].observable_facts == (
        "01:01:01.123至01:01:02.123角色冲刺。",
    )


@pytest.mark.parametrize("field", ["observableFacts", "mechanicTags", "uncertainty"])
@pytest.mark.parametrize("alias", ["f8", "f9", "f123", "f01"])
def test_v5_rejects_unknown_prose_alias_without_recording_arbitrary_text(
    tmp_path: Path, field: str, alias: str
) -> None:
    event = action_event()
    prose = f"{alias}中secret-model-text不能泄露"
    event[field] = prose if field == "uncertainty" else [prose]
    result, _, _, _ = analyze(detailed_request(tmp_path), [event])
    detail = schema_detail(result, "event_prose_alias")
    assert detail["eventIndex"] == 0
    if alias == "f8":
        assert detail["frameAlias"] == "f8"
    else:
        assert "frameAlias" not in detail
    assert "secret-model-text" not in (result.metadata.execution_details or "")


@pytest.mark.parametrize("field", ["observableFacts", "mechanicTags", "uncertainty"])
@pytest.mark.parametrize("alias", ["f1", "f8"])
def test_v5_prose_cannot_reference_uncited_or_outside_event_frames(
    tmp_path: Path, field: str, alias: str
) -> None:
    # f1 is inside the interval but not cited; f8 is supplied outside the event.
    event = dict(action_event(), evidenceIds=["f0", "f2"])
    prose = f"{alias}中角色持有权杖"
    event[field] = prose if field == "uncertainty" else [prose]
    result, _, _, _ = analyze(detailed_request(tmp_path, frames=9), [event])
    detail = schema_detail(result, "event_prose_alias")
    assert detail["frameAlias"] == alias


def test_v5_checks_fact_bound_after_alias_expansion(tmp_path: Path) -> None:
    event = dict(action_event(), observableFacts=["细" * 995 + "f0"])
    result, _, _, _ = analyze(detailed_request(tmp_path), [event])
    schema_detail(result, "event_facts")


def test_v4_free_text_stays_frozen_when_it_contains_aliases(tmp_path: Path) -> None:
    event = dict(action_event(), observableFacts=["f0中角色开始跳跃。"])
    result, _, _, _ = analyze(request_fixture(tmp_path), [event])
    assert result.output and result.output[0].observable_facts == ("f0中角色开始跳跃。",)


def test_v5_keeps_static_evidence_action_guard(tmp_path: Path) -> None:
    result, _, _, _ = analyze(detailed_request(tmp_path, static=True), [action_event()])
    schema_detail(result, "event_static_evidence")


def test_v5_keeps_source_order_guard_before_paid_attempt(tmp_path: Path) -> None:
    request = detailed_request(tmp_path)
    request = replace(request, evidence=tuple(reversed(request.evidence)))
    result, transport, recorder, budget = analyze(request, [action_event()])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun and budget.requests == 0


def test_v5_requires_distinct_boundary_instants_and_cited_boundaries(tmp_path: Path) -> None:
    request = detailed_request(tmp_path)
    same = dict(action_event(), startFrameId="f1", endFrameId="f1", evidenceIds=["f1"])
    result, _, _, _ = analyze(request, [same])
    schema_detail(result, "event_frame_boundaries")
    missing = dict(action_event(), evidenceIds=["f0", "f1"])
    result, _, _, _ = analyze(request, [missing])
    schema_detail(result, "event_boundary_evidence")


@pytest.mark.parametrize("frames", [1, 3, 9])
def test_v5_empty_events_are_valid_for_insufficient_or_static_observation(
    tmp_path: Path, frames: int
) -> None:
    result, transport, _, _ = analyze(detailed_request(tmp_path, frames=frames, static=True), [])
    assert result.status == ProviderStatus.COMPLETED and result.output == ()
    assert len(transport.payloads) == 1


def test_v5_keeps_three_event_limit(tmp_path: Path) -> None:
    result, _, _, _ = analyze(detailed_request(tmp_path), [action_event()] * 4)
    schema_detail(result, "event_collection")
