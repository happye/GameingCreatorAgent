"""Feedback statistics: recommendation adoption, real edits only, and the output funnel."""

# ruff: noqa: F811
import hashlib
import json
import threading
import urllib.request

from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401

from gamingcreator.application.creation_feedback import (
    edit_kinds,
    normalize_edit_kinds,
    summarize_feedback,
    trim_suggestion,
)

ONE = {"numerator": 1, "denominator": 1}
CUT = {"type": "cut", "frames": 0}


def row(clip, start=0, end=1_000_000, speed=ONE, transition=CUT):
    return {
        "clipId": clip,
        "startUs": start,
        "endUs": end,
        "speed": speed,
        "transitionIn": transition,
    }


def test_edit_kinds_compare_clips_and_inherited_settings():
    parent = [row("a"), row("b", 1_000_000, 2_000_000), row("c", 2_000_000, 3_000_000)]
    request = {
        "clips": [
            row("c", 2_000_000, 2_500_000),
            row("a", speed={"numerator": 2, "denominator": 1}, transition=CUT),
        ],
        "audioMix": {"bgm": None, "sourceGainDb": 0, "ducking": "off"},
        "subtitleOverrides": [{"clipId": "a", "text": "新字幕"}],
        "replacements": [{"targetClipId": "b"}],
    }
    kinds = edit_kinds(parent, request)
    assert kinds == ["删镜头", "换顺序", "裁剪", "变速", "替换镜头", "字幕"]
    # Resending the parent's effective audio is not an audio edit.
    assert "配乐" not in kinds
    unchanged = {"clips": parent, "subtitleOverrides": [{"clipId": "a", "text": "新字幕"}]}
    assert (
        edit_kinds(parent, unchanged, {"subtitleOverrides": unchanged["subtitleOverrides"]}) == []
    )


def test_deleting_a_shot_with_a_subtitle_override_is_only_a_deletion():
    parent = [row("a"), row("b", 1_000_000, 2_000_000)]
    inherited = {"subtitleOverrides": [{"clipId": "b", "text": "旧字幕"}]}
    request = {"clips": [row("a")], "subtitleOverrides": []}
    assert edit_kinds(parent, request, inherited) == ["删镜头"]


def test_summary_adoption_and_funnel_from_records():
    receipt = "r" * 64
    clip0 = hashlib.sha256(f"{receipt}:0".encode()).hexdigest()
    clip1 = hashlib.sha256(f"{receipt}:1".encode()).hexdigest()
    plans = [
        {
            "id": "guide-steps",
            "mode": "guide",
            "segments": [
                {"startUs": 0, "endUs": 1_000_000},
                {"startUs": 5_000_000, "endUs": 6_000_000},
            ],
        },
        {"id": "chronological", "segments": []},
    ]
    jobs = [
        {"jobId": "p1", "kind": "plan", "status": "completed", "request": {}, "plans": plans},
        {"jobId": "p2", "kind": "plan", "status": "completed", "request": {}, "plans": plans},
        {
            "jobId": "v1",
            "kind": "revision",
            "status": "completed",
            "createdAt": "1",
            "request": {"parentJobId": "p1", "clips": [row(clip1, 5_000_000, 6_000_000)]},
            "root": {"rootJobId": "p1", "rootPlanId": "guide-steps", "rootReceiptSha256": receipt},
            "segments": [row(clip1, 5_000_000, 6_000_000)],
        },
        {
            "jobId": "r1",
            "kind": "render",
            "status": "completed",
            "request": {"revisionJobId": "v1"},
        },
        {
            "jobId": "u1",
            "kind": "publication",
            "status": "completed",
            "request": {"renderJobId": "r1"},
        },
        {
            "jobId": "k1",
            "kind": "package",
            "status": "completed",
            "request": {"publicationJobId": "u1"},
        },
        {
            "jobId": "r2",
            "kind": "render",
            "status": "completed",
            "request": {"planJobId": "p2", "planId": "chronological"},
        },
        {
            "jobId": "x",
            "kind": "render",
            "status": "failed",
            "request": {"planJobId": "p2", "planId": "x"},
        },
    ]
    summary = summarize_feedback(jobs)
    assert summary["plansGenerated"] == 2 and summary["chains"] == 2
    assert (summary["recommendationOffered"], summary["recommendationAdopted"]) == (2, 1)
    assert summary["editKinds"] == {"删镜头": 1}
    assert summary["funnel"] == {"chosen": 2, "rendered": 2, "published": 1, "packaged": 1}
    assert summary["averageRevisions"] == 0.5
    assert clip0 != clip1


def test_real_saved_jobs_and_http(revisions):
    jobs, root, _ = revisions
    req = payload(jobs, root)
    req["clips"] = req["clips"][:-1]
    child = jobs.submit("revision", req)["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    summary = jobs.feedback(jobs.read(jobs.directory(root) / "status.json")["projectId"])
    assert summary["chains"] == 1 and summary["editKinds"].get("删镜头") == 1
    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        project = jobs.read(jobs.directory(root) / "status.json")["projectId"]
        url = f"http://127.0.0.1:{server.server_port}/api/creation/feedback?projectId={project}"
        with urllib.request.urlopen(url) as response:
            assert json.loads(response.read())["editKinds"] == summary["editKinds"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_trim_suggestion_thresholds_and_normalize():
    assert normalize_edit_kinds({"裁剪": 2, "未知": 9, "删镜头": 0, "x": "1"}) == {"裁剪": 2}
    assert trim_suggestion({"裁剪": 2, "删镜头": 2})["applied"] is False  # below min count
    assert trim_suggestion({"裁剪": 3, "删镜头": 4})["applied"] is False  # share < 0.5
    hit = trim_suggestion({"裁剪": 3, "删镜头": 2, "变速": 1})
    assert hit["applied"] is True and hit["share"] == 0.5 and hit["minTrimEdits"] == 3
