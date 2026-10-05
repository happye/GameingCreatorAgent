"""Prompt self-check and unchanged temporal guards, not proof of model eligibility decisions."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from test_detailed_vision import detailed_request, resize_image
from test_temporal_frame_contract import action_event, analyze, schema_detail

from gamingcreator.application.providers import ProviderStatus, VisionRequest
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.deepseek_vision import (
    MAX_IMAGE_BYTES_V5,
    MAX_IMAGE_WIDTH_V5,
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    PROMPT_VERSION_V5,
    PROMPT_VERSION_V6,
    SCHEMA_VERSION,
    vision_prompt_fingerprint,
)


def eligible_request(tmp_path: Path, *, frames: int = 3, static: bool = False) -> VisionRequest:
    return replace(
        detailed_request(tmp_path, frames=frames, static=static), prompt_version=PROMPT_VERSION_V6
    )


def test_v6_adds_distinct_identity_without_changing_v1_through_v5_hashes() -> None:
    expected = {
        PROMPT_VERSION: "c3a6d3f286b5e8b582a91929afcfde038d39ff605d017619919e1a583c507d26",
        PROMPT_VERSION_V2: "f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236",
        PROMPT_VERSION_V3: "27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d",
        PROMPT_VERSION_V4: "9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48",
        PROMPT_VERSION_V5: "c64c644e9889fcfd91cc0e9a26d8bf1b9546ce73c548e6ac056a5067498ff98a",
    }
    assert {version: vision_prompt_fingerprint(version) for version in expected} == expected
    fingerprint = vision_prompt_fingerprint(PROMPT_VERSION_V6)
    assert fingerprint == "a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00"
    assert len(fingerprint) == 64 and fingerprint not in expected.values()
    with pytest.raises(ValueError, match="Unsupported"):
        vision_prompt_fingerprint("phase0-vision-v7")


def test_v6_qualifies_action_before_detail_and_rejects_single_frame_prompt_example(
    tmp_path: Path,
) -> None:
    request = eligible_request(tmp_path)
    _, transport, _, _ = analyze(request, [])
    messages = cast(list[dict[str, object]], transport.payloads[0]["messages"])
    prompt = cast(str, messages[0]["content"])
    assert prompt.startswith(
        "FIRST determine whether each candidate segment contains a visible subject ACTION"
    )
    for clause in (
        "ONLY AFTER it qualifies, add that actor's",
        "a static inventory or a pure camera",
        "cut/transition is NOT an action event",
        "Omit such unsupported segments, but keep other independently",
        "Different image content alone does not prove",
        'startFrameId="f0", endFrameId="f0" is INVALID',
        "at least TWO different source instants",
        "one\n   appearance followed only by a shot change cannot establish an action segment",
        "Each event has exactly the six documented fields. uncertainty is either null",
        "or a nonempty, non-whitespace string; never an empty string, false, a number",
        "an object or an array. Do not emit extra fields",
        "If ANY check fails, REMOVE that event. Never guess or stretch its boundaries",
    ):
        assert clause in prompt
    # All original detail intent remains embedded in the independent new prompt.
    v5_request = replace(request, prompt_version=PROMPT_VERSION_V5)
    _, v5_transport, _, _ = analyze(v5_request, [])
    v5_messages = cast(list[dict[str, object]], v5_transport.payloads[0]["messages"])
    assert cast(str, v5_messages[0]["content"]) in prompt


def test_v6_uses_same_detail_image_profile_and_temporal_schema(tmp_path: Path) -> None:
    request = eligible_request(tmp_path, frames=9)
    event = dict(
        action_event(frames=9),
        observableFacts=["红衣、黑手套角色举起长杖，紫色圆弧向石墙方向扩张。"],
    )
    result, transport, _, _ = analyze(request, [event])
    assert result.status == ProviderStatus.COMPLETED and result.output
    assert result.metadata.schema_version == "temporal-actions-v1"
    assert result.metadata.prompt_version == PROMPT_VERSION_V6
    messages = cast(list[dict[str, object]], transport.payloads[0]["messages"])
    blocks = cast(list[dict[str, object]], messages[1]["content"])
    images = [
        cast(dict[str, object], block["image_url"]) for block in blocks if "image_url" in block
    ]
    assert len(images) == 9 and all(image["detail"] == "original" for image in images)


@pytest.mark.parametrize("boundary", ["width", "frames"])
def test_v6_rejects_exceeded_detail_input_limits_before_transport(
    tmp_path: Path, boundary: str
) -> None:
    request = (
        replace(
            detailed_request(tmp_path, width=MAX_IMAGE_WIDTH_V5 + 1),
            prompt_version=PROMPT_VERSION_V6,
        )
        if boundary == "width"
        else eligible_request(tmp_path, frames=10)
    )
    result, transport, recorder, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and not recorder.begun and budget.requests == 0


def test_v6_rejects_legacy_schema_before_transport(tmp_path: Path) -> None:
    request = replace(eligible_request(tmp_path), schema_version=SCHEMA_VERSION)
    result, transport, _, budget = analyze(request, [])
    assert result.error and result.error.code == "provider.input"
    assert not transport.payloads and budget.requests == 0


@pytest.mark.parametrize("extra, accepted", [(0, True), (1, False)])
def test_v6_retains_three_mib_bounded_read(tmp_path: Path, extra: int, accepted: bool) -> None:
    request = resize_image(eligible_request(tmp_path), MAX_IMAGE_BYTES_V5 + extra)
    result, transport, _, _ = analyze(request, [])
    assert (result.status == ProviderStatus.COMPLETED) is accepted
    assert bool(transport.payloads) is accepted


def test_v6_reproduces_real_single_frame_boundary_failure_without_relaxing_parser(
    tmp_path: Path,
) -> None:
    request = eligible_request(tmp_path, frames=9)
    request = replace(
        request,
        evidence=tuple(
            replace(item, source_time=SourceInstant(31_500_000 + index * 500_000, 54_743_220))
            for index, item in enumerate(request.evidence)
        ),
    )
    appearance = dict(
        action_event(),
        startFrameId="f0",
        endFrameId="f0",
        evidenceIds=["f0"],
        observableFacts=["第一幅画面中，一个穿盔甲的巨型角色站在平台上。"],
    )
    result, _, _, _ = analyze(request, [appearance])
    assert schema_detail(result, "event_frame_boundaries") == {
        "eventIndex": 0,
        "startUs": 31_500_000,
        "endUs": 31_500_001,
    }


def test_v6_does_not_silently_filter_malformed_event_to_complete_a_response(tmp_path: Path) -> None:
    single = dict(action_event(), startFrameId="f0", endFrameId="f0", evidenceIds=["f0"])
    result, _, _, _ = analyze(eligible_request(tmp_path), [single, action_event()])
    schema_detail(result, "event_frame_boundaries")
    assert result.output is None


def test_v6_keeps_static_evidence_guard(tmp_path: Path) -> None:
    result, _, _, _ = analyze(eligible_request(tmp_path, static=True), [action_event()])
    schema_detail(result, "event_static_evidence")


@pytest.mark.parametrize("uncertainty", ["", "  ", False, 0, {}, []])
def test_v6_keeps_uncertainty_type_and_nonempty_contract(
    tmp_path: Path, uncertainty: object
) -> None:
    result, _, _, _ = analyze(
        eligible_request(tmp_path), [dict(action_event(), uncertainty=uncertainty)]
    )
    schema_detail(result, "uncertainty")


def test_v6_keeps_prose_aliases_limited_to_actual_event_references(tmp_path: Path) -> None:
    event = dict(action_event(), evidenceIds=["f0", "f2"], observableFacts=["f1中人物举杖。"])
    result, _, _, _ = analyze(eligible_request(tmp_path), [event])
    assert schema_detail(result, "event_prose_alias")["frameAlias"] == "f1"
    event["observableFacts"] = ["f0中人物举杖，至f2可见光环扩张。"]
    result, _, _, _ = analyze(eligible_request(tmp_path), [event])
    assert result.output and result.output[0].observable_facts == (
        "00:00:01.000中人物举杖，至00:00:02.000可见光环扩张。",
    )


@pytest.mark.parametrize("facts", [[f"Detail {index}" for index in range(7)], ["细" * 1001]])
def test_v6_keeps_six_fact_and_total_character_limit(tmp_path: Path, facts: list[str]) -> None:
    result, _, _, _ = analyze(
        eligible_request(tmp_path), [dict(action_event(), observableFacts=facts)]
    )
    schema_detail(result, "event_facts")


def test_v6_can_return_no_eligible_segments_or_an_independent_supported_action(
    tmp_path: Path,
) -> None:
    request = eligible_request(tmp_path)
    empty, _, _, _ = analyze(request, [])
    assert empty.status == ProviderStatus.COMPLETED and empty.output == ()
    valid, _, _, _ = analyze(request, [action_event()])
    assert valid.status == ProviderStatus.COMPLETED and valid.output
