"""Template narration drafts stay within the speakable output budget and saved descriptions."""

# ruff: noqa: F811
import json
import threading
import urllib.error
import urllib.request

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401

from gamingcreator.application.narration_script import build_narration_script
from gamingcreator.domain.creation import CreativeBrief

BRIEF = {
    "game": "代号Atom",
    "contentType": "feature_showcase",
    "platforms": ["bilibili"],
    "targetDuration": 12,
    "objective": "整理玩法",
    "audience": "新玩家",
    "tone": "简洁",
    "mandatoryTopics": [],
    "exclude": [],
}


def clip(index, text, start=0):
    return {"clipId": f"c{index}", "scriptDraft": text, "outputStartFrame": start}


def test_budget_markers_duplicates_and_honest_status():
    clips = [
        clip(0, "f0中角色在圆形平台上移动，周围有紫色特效和漂浮的金色圆环；角色跳起", 0),
        clip(1, "f0中角色在圆形平台上移动，周围有紫色特效和漂浮的金色圆环；重复描述", 30),
        clip(2, "", 60),
        clip(3, "镜头在机械齿轮与建筑场景中向右平移", 90),
        clip(4, "蓝色球体与粉色球体在方形平台上向彼此移动并接触", 120),
    ]
    result = build_narration_script(CreativeBrief.from_json(BRIEF), clips, 360, 30)
    assert result["status"] == "template-draft-human-review-required"
    assert result["budgetCharacters"] == 37
    text = result["text"]
    assert text.startswith("代号Atom玩法速览。角色在圆形平台上移动")
    assert "f0" not in text and "…" not in text and len(text) <= result["budgetCharacters"]
    assert result["estimatedSeconds"] <= result["outputSeconds"]
    assert [line["clipId"] for line in result["lines"]] == ["c0"]
    # Duplicate, empty and over-budget clips are counted, never silently padded.
    assert result["omittedClips"] == 4


def test_longer_output_includes_more_clips_in_order_and_guides_open_differently():
    clips = [clip(i, f"第{i}个镜头角色向城堡入口奔跑") for i in range(5)]
    brief = CreativeBrief.from_json({**BRIEF, "contentType": "guide"})
    result = build_narration_script(brief, clips, 900, 30)
    assert result["text"].startswith("代号Atom攻略要点。第0个镜头")
    assert [line["clipId"] for line in result["lines"]] == [f"c{i}" for i in range(5)]
    assert result["omittedClips"] == 0
    with pytest.raises(ValueError):
        build_narration_script(brief, clips, 0, 30)


def test_short_budget_samples_clips_across_the_whole_video():
    clips = [clip(i, f"场景{i}角色奔跑", i * 30) for i in range(10)]
    # 12 seconds -> 37 characters: the opening plus three 7-character sentences.
    result = build_narration_script(CreativeBrief.from_json(BRIEF), clips, 360, 30)
    assert [line["clipId"] for line in result["lines"]] == ["c0", "c4", "c9"]
    assert result["omittedClips"] == 7


def test_job_and_http_use_saved_revision_descriptions(revisions):
    jobs, root, _ = revisions
    snapshot = jobs.edit(root, "hook-first")
    draft = jobs.narration_script(root, "hook-first")
    assert draft["outputSeconds"] == snapshot["actualDuration"]
    descriptions = " ".join(c.get("scriptDraft") or "" for c in snapshot["clips"])
    assert all(line["text"] in descriptions for line in draft["lines"])
    child = jobs.submit("revision", payload(jobs, root))["jobId"]
    assert finish(jobs, child)["status"] == "completed"

    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/api/creation/jobs/{child}/narration-script"
        with urllib.request.urlopen(base + "?planId=hook-first") as response:
            body = json.loads(response.read())
        assert body == jobs.narration_script(child, "hook-first")
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
