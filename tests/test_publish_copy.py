"""Stage B AI publish copy (2026-11-11): bounded text fields, budget path, no frames sent."""

import asyncio

import pytest
from test_creation_reasoning_service import Transport

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.publish_copy import copy_request, copy_snapshot, validate_copy
from gamingcreator.ui import publication_jobs
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService

BRIEF = {
    "game": "漫画群星：大集结",
    "contentType": "feature_showcase",
    "audience": "新玩家",
    "objective": "给新玩家做个玩法展示",
    "mandatoryTopics": ["可玩角色介绍", "技能解说"],
    "platforms": ["bilibili"],
}
SEGMENTS = [
    {"role": "开场", "scriptDraft": "画面中央显示文字横幅“3V3”", "outputFrames": 90},
    {"scriptDraft": "角色释放\x07技能", "outputFrames": 60},
]


def answer(snapshot, **change):
    return {
        "schemaVersion": "publish-copy-v1",
        "snapshotFingerprint": snapshot.fingerprint,
        "title": "新手必看！漫画群星：大集结 3V3 玩法一次讲清",
        "description": "这期带新玩家看懂 3V3。\n\n00:00 模式介绍\n00:03 技能演示\n\n你最想看哪个角色？",
        "tags": ["漫画群星：大集结", "#新手攻略", "新手攻略", "3V3"],
        **change,
    }


def test_snapshot_carries_shot_times_and_no_paths():
    snapshot = copy_snapshot("job", BRIEF, SEGMENTS, 30)
    shots = snapshot.payload["shots"]
    assert [s["startSeconds"] for s in shots] == [0.0, 3.0]
    assert shots[1]["observation"] == "角色释放技能"
    assert snapshot.payload["durationSeconds"] == 5.0
    request = copy_request(snapshot)
    assert snapshot.fingerprint in request.user and "sourcePath" not in request.user
    assert copy_snapshot("job", BRIEF, SEGMENTS, 30).fingerprint == snapshot.fingerprint


def test_output_is_bounded_and_tags_deduplicated():
    snapshot = copy_snapshot("job", BRIEF, SEGMENTS, 30)
    copy = validate_copy(snapshot, answer(snapshot, snapshotFingerprint="x"))
    assert copy["tags"] == ["漫画群星：大集结", "新手攻略", "3V3"]
    assert copy["fingerprintEcho"] == "mismatch" and copy["description"].endswith("角色？")
    long = validate_copy(snapshot, answer(snapshot, title="长" * 200, tags=["t" * 50]))
    assert len(long["title"]) == 80 and long["tags"] == ["t" * 20]
    for bad in (
        {**answer(snapshot), "extra": 1},
        answer(snapshot, tags="a,b"),
        answer(snapshot, title=""),
        answer(snapshot, schemaVersion="v0"),
    ):
        with pytest.raises(ValueError):
            validate_copy(snapshot, bad)


def test_service_copy_runs_within_budget_and_counts_toward_the_video(tmp_path, monkeypatch):
    jobs = CreationJobs(tmp_path)
    monkeypatch.setattr(
        publication_jobs, "copy_inputs", lambda _jobs, job: ("projects/p", BRIEF, SEGMENTS, 30.0)
    )
    snapshot = copy_snapshot("a" * 32, BRIEF, SEGMENTS, 30.0)
    transport = Transport(answer(snapshot))
    service = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    prepared = service.prepare_copy("a" * 32)
    assert prepared["purpose"] == "copy" and prepared["budget"]["eligible"]
    assert prepared["payloadSummary"] == {"textOnly": True, "inputFrames": 0, "clipCount": 2}
    result = asyncio.run(
        service.execute_within_budget(prepared["preparedHash"], prepared["snapshotFingerprint"])
    )
    assert result["status"] == "completed", result
    assert result["copy"]["title"].startswith("新手必看") and len(transport.calls) == 1
    with pytest.raises(ValueError):
        service.revision_for_application(prepared["preparedHash"])
    again = service.prepare_copy("a" * 32)["budget"]
    assert again["videoSpentCny"] == prepared["budget"]["ceilingCny"]


def test_render_copy_spend_belongs_to_the_plan_video(tmp_path):
    """Review 2026-11-11: render -> plan (and revision -> parent) links decide the video."""
    jobs = CreationJobs(tmp_path)
    service = CreationReasoningService(jobs, price_snapshot=DEEPSEEK_FLASH_20261004)
    links = {
        "a" * 32: {"planJobId": "b" * 32, "planId": "p"},
        "c" * 32: {"revisionJobId": "d" * 32},
        "d" * 32: {"parentJobId": "b" * 32},
        "b" * 32: {"runIds": ["run"]},
    }
    for job, request in links.items():
        (jobs.jobs / job).mkdir(parents=True)
        (jobs.jobs / job / "request.json").write_text(
            __import__("json").dumps({"request": request}), encoding="utf-8"
        )
    assert service._video_key("a" * 32) == "b" * 32
    assert service._video_key("c" * 32) == "b" * 32


def test_tags_never_split_in_the_form():
    snapshot = copy_snapshot("job", BRIEF, SEGMENTS, 30)
    copy = validate_copy(snapshot, answer(snapshot, tags=["新手,攻略", "a\nb"]))
    assert copy["tags"] == ["新手 攻略", "a b"]
