import json

import pytest
from test_clip_replacement_jobs import replacements  # noqa: F401
from test_creation_jobs import service  # noqa: F401
from test_creation_reasoning_service import Transport

from gamingcreator.application.creation_mixed_actions import SCHEMA as ACTIONS_SCHEMA
from gamingcreator.application.creation_mixed_actions import (
    SCHEMA_V3,
    actions_snapshot,
    edit_original_rows,
    validate_actions,
)
from gamingcreator.application.creation_mixed_proposals import (
    SCHEMA,
    mixed_followup,
    mixed_snapshot,
    validate_mixed,
)
from gamingcreator.application.creation_proposals import clip_rows
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.ui.creation_reasoning_http import reasoning_post
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.replacement_jobs import candidates


def test_mixed_swap_and_delete_share_one_request_and_verified_projection(
    replacements,  # noqa: F811
):
    jobs, job_id, _ = replacements
    plan = "hook-first"
    before = jobs.edit(job_id, plan)
    other = next(c for c in candidates(jobs, job_id, plan)["candidates"] if c["runId"] == "B")
    outbound = Transport(
        {
            "schemaVersion": SCHEMA,
            "kind": "mixed_edit",
            "replacement": {"target": "S2", "candidate": ""},
            "edit": {"target": "S1", "action": "delete", "keepMs": 0},
            "message": "先换第二镜，并删除原第一镜。",
        }
    )
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=outbound
    )
    snapshot, project_id = reasoning._replacement_snapshot(job_id, plan)
    alias = next(
        c["alias"]
        for c in snapshot.payload["replacementCandidates"]
        if c["candidateId"] == other["candidateId"]
    )
    outbound.content["replacement"]["candidate"] = alias
    mixed = mixed_snapshot(snapshot)
    trim = {"target": "S1", "action": "trim_tail", "keepMs": 500}
    assert validate_mixed(mixed, {**outbound.content, "edit": trim})["edit"] == trim
    shorter = mixed_followup(mixed, clip_rows(mixed), trim)
    assert shorter[0]["endUs"] - shorter[0]["startUs"] == 500_000
    with pytest.raises(ValueError, match="different"):
        validate_mixed(mixed, {**outbound.content, "edit": {**trim, "target": "S2"}})
    identity = {"jobId": job_id, "planId": plan}
    quote = reasoning._prepare(
        mixed, project_id, job_id, plan, "第二镜换画面，同时删除第一镜", "mixed"
    )
    assert outbound.calls == []
    assert quote["schemaVersion"] == SCHEMA
    context = json.loads(quote["payloadPreview"]["user"])
    assert context["maxSelections"] == 1
    assert other["candidateId"] not in quote["payloadPreview"]["user"]
    token = {"preparedHash": quote["preparedHash"]}
    result = reasoning_post(
        reasoning,
        {
            "action": "execute",
            **token,
            "snapshotFingerprint": quote["snapshotFingerprint"],
            "confirmedMaxCny": quote["maxCostCny"],
        },
    )
    assert result["status"] == "completed", result
    assert len(outbound.calls) == 1
    projection_request = {
        "action": "validate",
        **identity,
        **token,
        "expectedParentReceiptSha256": before["expectedParentReceiptSha256"],
    }
    projection = reasoning_post(reasoning, projection_request)
    assert projection["replacements"] == [
        {"targetClipId": before["clips"][1]["clipId"], "candidateId": other["candidateId"]}
    ]
    assert projection["clips"][0]["runId"] == "B"
    assert [c["clipId"] for c in projection["clips"]] == [c["clipId"] for c in before["clips"][1:]]
    assert reasoning_post(reasoning, {"action": "result", **token}) == result
    with pytest.raises(ValueError, match="parent changed"):
        reasoning_post(reasoning, {**projection_request, "expectedParentReceiptSha256": "0" * 64})
    assert len(outbound.calls) == 1


def test_combined_actions_bind_to_original_shots_after_an_earlier_delete(replacements):  # noqa: F811
    jobs, job_id, _ = replacements
    plan = "hook-first"
    before = jobs.edit(job_id, plan)
    other = next(c for c in candidates(jobs, job_id, plan)["candidates"] if c["runId"] == "B")
    outbound = Transport(None)
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=outbound
    )
    replacement_snapshot, project_id = reasoning._replacement_snapshot(job_id, plan)
    snapshot = actions_snapshot(replacement_snapshot)
    prototype = clip_rows(snapshot)[0]
    fade = {"type": "crossfade", "frames": 5}
    fades = [
        {**prototype, "clipId": label, "transitionIn": fade if i else {"type": "cut", "frames": 0}}
        for i, label in enumerate(("a", "b", "c"))
    ]
    edited = edit_original_rows(
        snapshot,
        fades,
        [
            {"action": "trim_tail", "clipId": "b", "keepMs": 300},
            {"action": "delete", "clipId": "c"},
        ],
    )
    assert edited[1]["transitionIn"] == fade
    alias = next(
        c["alias"]
        for c in snapshot.payload["replacementCandidates"]
        if c["candidateId"] == other["candidateId"]
    )
    steps = [
        {"action": "delete", "target": "S1"},
        {"action": "insert_after", "after": "S2", "candidate": alias, "durationMs": 1000},
        {"action": "trim_tail", "target": "S2", "keepMs": 500},
    ]
    outbound.content = {
        "schemaVersion": ACTIONS_SCHEMA,
        "kind": "mixed_edit",
        "actions": steps,
        "message": "组合剪辑",
    }
    payload = snapshot.payload
    first = payload["parent_edl"]["segments"][0]
    sources = payload["replacementSourceIntervals"]
    occupied = next(
        c["alias"]
        for c in payload["replacementCandidates"]
        if sources[c["candidateId"]]["sourceSha256"] == first["sourceSha256"]
        and sources[c["candidateId"]]["startUs"] == first["startUs"]
    )
    replace_after_removal = [steps[0], {"action": "replace", "target": "S2", "candidate": occupied}]
    assert validate_actions(snapshot, {**outbound.content, "actions": replace_after_removal})
    duplicate = [
        {
            **steps[1],
            "candidate": occupied,
            "durationMs": (first["endUs"] - first["startUs"]) // 1000,
        },
        steps[2],
    ]
    with pytest.raises(ValueError, match="Duplicate source interval"):
        validate_actions(snapshot, {**outbound.content, "actions": duplicate})
    with pytest.raises(ValueError, match="anchor must stay"):
        validate_actions(
            snapshot, {**outbound.content, "actions": [steps[0], {**steps[1], "after": "S1"}]}
        )
    identity = {"jobId": job_id, "planId": plan}
    quote = reasoning._prepare(
        snapshot, project_id, job_id, plan, "删第一镜，插第二镜后并剪短第二镜", "mixed"
    )
    result = reasoning_post(
        reasoning,
        {
            "action": "execute",
            "preparedHash": quote["preparedHash"],
            "snapshotFingerprint": quote["snapshotFingerprint"],
            "confirmedMaxCny": quote["maxCostCny"],
        },
    )
    assert result["status"] == "completed", result
    proposal = reasoning_post(
        reasoning,
        {
            "action": "validate",
            **identity,
            "preparedHash": quote["preparedHash"],
            "expectedParentReceiptSha256": before["expectedParentReceiptSha256"],
        },
    )
    original, inserted, *rest = proposal["clips"]
    assert original["clipId"] == before["clips"][1]["clipId"]
    assert original["endUs"] - original["startUs"] == 500_000
    assert inserted["runId"] == "B"
    assert proposal["insertions"][0]["afterClipId"] == original["clipId"]
    assert proposal["insertions"][0]["newClipId"] == inserted["clipId"]
    assert [row["clipId"] for row in rest] == [row["clipId"] for row in before["clips"][2:]]
    assert len(outbound.calls) == 1


def test_combined_speed_and_move_use_the_same_original_shot(replacements, monkeypatch):  # noqa: F811
    jobs, job_id, _ = replacements
    plan = "hook-first"
    before = jobs.edit(job_id, plan)
    steps = [
        {"action": "move_before", "target": "S2", "anchor": "S1"},
        {"action": "set_speed", "target": "S2", "speed": "0.5x"},
    ]
    output = {
        "schemaVersion": SCHEMA_V3,
        "kind": "mixed_edit",
        "actions": steps,
        "message": "移镜并慢放",
    }
    outbound = Transport(output)
    reasoning = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=outbound
    )
    snapshot = actions_snapshot(reasoning._replacement_snapshot(job_id, plan)[0], version=SCHEMA_V3)
    with pytest.raises(ValueError, match="move anchor must stay"):
        validate_actions(
            snapshot, {**output, "actions": [*steps, {"action": "delete", "target": "S1"}]}
        )
    prototype = clip_rows(snapshot)[0]
    fade = {"type": "crossfade", "frames": 5}
    fades = [
        {**prototype, "clipId": label, "transitionIn": fade if i else {"type": "cut", "frames": 0}}
        for i, label in enumerate(("a", "b", "c", "d"))
    ]
    moved = edit_original_rows(
        snapshot, fades, [{"action": "move_before", "clipId": "a", "anchorClipId": "d"}]
    )
    assert [row["clipId"] for row in moved] == ["b", "c", "a", "d"]
    assert moved[1]["transitionIn"] == fade
    assert moved[-1]["transitionIn"]["type"] == "cut"
    fades[1].update(endUs=fades[1]["startUs"] + 600_000, transitionIn={**fade, "frames": 4})
    fades[2]["transitionIn"] = {**fade, "frames": 10}
    faster = edit_original_rows(
        snapshot, fades, [{"action": "set_speed", "clipId": "b", "speed": "2x"}]
    )
    assert faster[1]["transitionIn"]["frames"] == 4
    assert faster[2]["transitionIn"]["type"] == "cut"
    identity = {"jobId": job_id, "planId": plan}
    quote = reasoning_post(
        reasoning,
        {"action": "prepare_mixed", **identity, "instruction": "第二镜移到第一镜前并慢放"},
    )
    assert quote["schemaVersion"] == SCHEMA_V3
    token = {"preparedHash": quote["preparedHash"]}
    assert (
        reasoning_post(
            reasoning,
            {
                "action": "execute",
                **token,
                "snapshotFingerprint": quote["snapshotFingerprint"],
                "confirmedMaxCny": quote["maxCostCny"],
            },
        )["status"]
        == "completed"
    )
    preview = reasoning_post(
        reasoning,
        {
            "action": "validate",
            **identity,
            **token,
            "expectedParentReceiptSha256": before["expectedParentReceiptSha256"],
        },
    )
    assert [clip["clipId"] for clip in preview["clips"][:2]] == [
        before["clips"][1]["clipId"],
        before["clips"][0]["clipId"],
    ]
    assert preview["clips"][0]["speed"] == {"numerator": 1, "denominator": 2}
    assert len(outbound.calls) == 1

    def obstructed(*_args):
        raise ValueError("Inherited layer is beyond the shortened timeline")

    monkeypatch.setattr(reasoning, "_combined_editor", obstructed)
    blocked = reasoning_post(
        reasoning, {"action": "prepare_mixed", **identity, "instruction": "再次慢放样本"}
    )
    refused = reasoning_post(
        reasoning,
        {
            "action": "execute",
            "preparedHash": blocked["preparedHash"],
            "snapshotFingerprint": blocked["snapshotFingerprint"],
            "confirmedMaxCny": blocked["maxCostCny"],
        },
    )
    assert refused["status"] == "failed" and refused["failureStage"] == "validate_timeline"
    assert refused["providerOutputSha256"] and refused["billing"]
    assert (
        reasoning_post(reasoning, {"action": "result", "preparedHash": blocked["preparedHash"]})
        == refused
    )
