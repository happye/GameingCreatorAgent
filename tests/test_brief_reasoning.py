"""Stage B AI brief understanding (2026-11-12): bounded fields, no invented game, budget path."""

import asyncio

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_reasoning_http import http  # noqa: F401
from test_creation_reasoning_service import Transport
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.application.brief_reasoning import brief_request, brief_snapshot, validate_brief
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService

# The J1 fifth-trial sentence the rule parser got wrong ("技能解说" became the type).
SENTENCE = (
    "给新玩家做1分钟漫画群星3V3和1V1玩法展示，讲可玩角色介绍、技能解说、玩法思路和特色，发B站"
)
GAMES = ["漫画群星：大集结", "其他游戏"]


def answer(snapshot, **change):
    return {
        "schemaVersion": "brief-understanding-v1",
        "snapshotFingerprint": snapshot.fingerprint,
        "game": "漫画群星：大集结",
        "contentType": "feature_showcase",
        "targetDurationSeconds": 60,
        "platform": "bilibili",
        "audience": "新玩家",
        "tone": None,
        "mandatoryTopics": ["3V3", "1V1", "可玩角色介绍", "技能解说", "玩法思路", "特色"],
        "exclude": [],
        "notes": "",
        **change,
    }


def test_snapshot_is_text_only_and_stable():
    snapshot = brief_snapshot(SENTENCE, [*GAMES, GAMES[0], "", 3])
    assert snapshot.payload == {"sentence": SENTENCE, "knownGames": GAMES}
    request = brief_request(snapshot)
    assert snapshot.fingerprint in request.user and SENTENCE in request.user
    assert brief_snapshot(SENTENCE, GAMES).fingerprint == snapshot.fingerprint
    for bad in ("", "  ", "长" * 501, None):
        with pytest.raises(ValueError):
            brief_snapshot(bad, GAMES)


def test_ai_fields_match_the_rule_result_shape_and_keep_every_topic():
    snapshot = brief_snapshot(SENTENCE, GAMES)
    brief = validate_brief(snapshot, answer(snapshot))
    fields = brief["fields"]
    assert brief["parser"] == "ai-deepseek-v1" and brief["fingerprintEcho"] == "exact"
    assert fields["objective"] == SENTENCE  # the user's words are never replaced
    assert fields["contentType"] == "feature_showcase" and fields["targetDuration"] == 60
    assert fields["mandatoryTopics"] == [
        "3V3",
        "1V1",
        "可玩角色介绍",
        "技能解说",
        "玩法思路",
        "特色",
    ]
    assert fields["game"] == "漫画群星：大集结" and "tone" not in fields and "exclude" not in fields
    assert "类型：玩法展示" in brief["recognized"] and "平台：B站" in brief["recognized"]


def test_output_is_bounded_and_never_invents_a_game():
    snapshot = brief_snapshot(SENTENCE, GAMES)
    loose = validate_brief(
        snapshot,
        answer(
            snapshot,
            snapshotFingerprint="x",
            game="漫画群星：大集结".upper(),
            mandatoryTopics=[
                "#技能解说",
                "技能解说",
                "长" * 50,
                " ",
                *[f"t{i}" for i in range(12)],
            ],
            audience="新\x07玩家",
            notes="n" * 300,
        ),
    )
    assert loose["fingerprintEcho"] == "mismatch" and len(loose["notes"]) == 200
    assert loose["fields"]["mandatoryTopics"][:2] == ["技能解说", "长" * 30]
    assert (
        len(loose["fields"]["mandatoryTopics"]) == 10 and loose["fields"]["audience"] == "新 玩家"
    )
    # A game in the sentence but not known is kept as written; one from nowhere is refused.
    assert (
        validate_brief(snapshot, answer(snapshot, game="漫画群星"))["fields"]["game"] == "漫画群星"
    )
    for bad in (
        answer(snapshot, game="原神"),
        answer(snapshot, contentType="vlog"),
        answer(snapshot, platform="youtube"),
        answer(snapshot, targetDurationSeconds=60.5),
        answer(snapshot, targetDurationSeconds=True),
        answer(snapshot, targetDurationSeconds=0),
        answer(snapshot, mandatoryTopics="角色、技能"),
        answer(snapshot, audience=3),
        answer(snapshot, notes=None),
        answer(snapshot, schemaVersion="v0"),
        {**answer(snapshot), "objective": "改写"},
        [],
    ):
        with pytest.raises(ValueError):
            validate_brief(snapshot, bad)


def test_service_brief_runs_within_budget_once(tmp_path):
    jobs = CreationJobs(tmp_path)
    snapshot = brief_snapshot(SENTENCE, GAMES)
    transport = Transport(answer(snapshot))
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    prepared = reasoning.prepare_brief(SENTENCE, GAMES)
    assert prepared["purpose"] == "brief" and prepared["budget"]["eligible"]
    assert prepared["payloadSummary"] == {"textOnly": True, "inputFrames": 0, "clipCount": 0}
    assert prepared["snapshotFingerprint"] == snapshot.fingerprint
    send = reasoning.execute_within_budget
    result = asyncio.run(send(prepared["preparedHash"], prepared["snapshotFingerprint"]))
    assert result["status"] == "completed", result
    assert result["brief"]["fields"]["mandatoryTopics"][2] == "可玩角色介绍"
    assert result["billing"]["knownCostCny"] is None
    # Replay returns the stored result; nothing is sent twice.
    assert asyncio.run(send(prepared["preparedHash"], prepared["snapshotFingerprint"])) == result
    assert len(transport.calls) == 1 and reasoning.read_result(prepared["preparedHash"]) == result
    with pytest.raises(ValueError):
        reasoning.revision_for_application(prepared["preparedHash"])
    # Unknown cost remains reserved, in both caps.
    again = reasoning.prepare_brief(SENTENCE, GAMES)["budget"]
    assert again["videoSpentCny"] == prepared["budget"]["ceilingCny"]
    assert again["monthSpentCny"] == prepared["budget"]["ceilingCny"]


def test_service_brief_bad_output_is_kept_and_not_retried(tmp_path):
    jobs = CreationJobs(tmp_path)
    snapshot = brief_snapshot(SENTENCE, GAMES)
    transport = Transport(answer(snapshot, game="原神"))
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    prepared = reasoning.prepare_brief(SENTENCE, GAMES)
    send = reasoning.execute_within_budget
    result = asyncio.run(send(prepared["preparedHash"], prepared["snapshotFingerprint"]))
    assert result["status"] == "failed" and result["failureStage"] == "validate_proposal"
    assert "brief" not in result and result["providerOutputSha256"]
    with pytest.raises(ValueError):
        asyncio.run(send(prepared["preparedHash"], prepared["snapshotFingerprint"]))
    assert len(transport.calls) == 1


def test_reasoning_http_prepare_brief_exact_fields(http):  # noqa: F811
    request, transport, _, _ = http
    value = {"action": "prepare_brief", "text": SENTENCE, "games": GAMES}
    status, prepared = request(value)
    assert status == 200 and prepared["purpose"] == "brief", prepared
    for bad in (
        {**value, "extra": "x"},
        {"action": "prepare_brief", "text": SENTENCE},
        {**value, "games": "漫画群星"},
        {**value, "games": [1]},
        {**value, "games": ["g"] * 51},
        {**value, "text": ""},
        {**value, "text": 3},
    ):
        assert request(bad)[0] == 400, bad
    assert not transport.calls
