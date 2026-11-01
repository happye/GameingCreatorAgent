"""Creator plans are enforced at real entry points; the founder default changes nothing."""

# ruff: noqa: F811
import json
import threading
import urllib.error
import urllib.request

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401

from gamingcreator.application.entitlements import (
    EntitlementError,
    renders_this_month,
    require,
    require_package_platform,
    require_render,
    summary,
)


def test_plan_rules_and_metering():
    assert summary(None, 3)["plan"] == "founder"
    require(None, "timelineExport")
    with pytest.raises(EntitlementError):
        require({"plan": "free"}, "activityRules")
    require({"plan": "creator"}, "activityRules")
    with pytest.raises(EntitlementError):
        require({"plan": "creator"}, "timelineExport")
    require_render({"plan": "free"}, 9)
    with pytest.raises(EntitlementError):
        require_render({"plan": "free"}, 10)
    require_package_platform({"plan": "free"}, set(), "bilibili")
    require_package_platform({"plan": "free"}, {"bilibili"}, "bilibili")
    with pytest.raises(EntitlementError):
        require_package_platform({"plan": "free"}, {"bilibili"}, "douyin")
    jobs = [
        {"kind": "render", "status": "completed", "createdAt": "2026-11-01T00:00:00+00:00"},
        {"kind": "render", "status": "failed", "createdAt": "2026-11-02T00:00:00+00:00"},
        {"kind": "render", "status": "completed", "createdAt": "2026-10-31T23:00:00+00:00"},
        {"kind": "plan", "status": "completed", "createdAt": "2026-11-01T00:00:00+00:00"},
    ]
    assert renders_this_month(jobs, "2026-11-15T00:00:00+00:00") == 1


def test_render_quota_is_enforced_on_real_submission(service, monkeypatch):
    import gamingcreator.application.entitlements as entitlements

    monkeypatch.setitem(entitlements.PLANS["free"], "monthlyRenders", 0)
    service.select_plan("free")
    plan = service.submit("plan", request())["jobId"]
    assert finish(service, plan)["status"] == "completed"
    with pytest.raises(Exception) as denied:
        service.submit(
            "render",
            {
                "requestId": "e" * 32,
                "planJobId": plan,
                "planId": "chronological",
                "width": 1280,
                "height": 720,
            },
        )
    assert getattr(denied.value, "code", "") == "entitlement.denied"
    service.select_plan("founder")
    assert service.entitlement_summary()["plan"] == "founder"


def test_free_render_records_its_watermark_and_paid_plans_do_not(service):
    service.select_plan("free")
    assert service.entitlement_summary()["watermark"] == "GamingCreator Free"
    plan = service.submit("plan", request())["jobId"]
    assert finish(service, plan)["status"] == "completed"
    render = {"planJobId": plan, "planId": "chronological", "width": 1280, "height": 720}
    free = finish(service, service.submit("render", {"requestId": "f" * 32, **render})["jobId"])
    assert free["status"] == "completed" and free["artifact"]["watermark"] == "GamingCreator Free"
    service.select_plan("creator")
    paid = finish(service, service.submit("render", {"requestId": "c" * 32, **render})["jobId"])
    assert paid["status"] == "completed" and "watermark" not in paid["artifact"]
    # Decided at registration: the finished free job keeps its mark after the plan changed.
    assert service.get(free["jobId"])["artifact"]["watermark"] == "GamingCreator Free"
    service.select_plan("founder")


def test_watermark_is_drawn_top_right_and_never_markup(tmp_path):
    import subprocess
    from fractions import Fraction
    from pathlib import Path

    from gamingcreator.infrastructure.ffmpeg_render import _filter_path, _watermark_ass

    for bad in ("", "x" * 41, "{\\b1}hi", "a\nb"):
        with pytest.raises(ValueError):
            _watermark_ass(bad, 320, 180, Fraction(1))
    ffmpeg = Path(__file__).resolve().parents[1] / ".tools/ffmpeg/bin/ffmpeg.exe"
    if not ffmpeg.is_file():
        pytest.skip("Pinned FFmpeg is unavailable")
    ass = tmp_path / "watermark.ass"
    ass.write_text(_watermark_ass("GamingCreator Free", 320, 180, Fraction(1)), encoding="utf-8")
    frame = subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=320x180:d=1",
            "-vf",
            f"ass=filename={_filter_path(ass)}",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert len(frame) == 320 * 180

    def brightest(x0, x1, y0, y1):
        return max(frame[y * 320 + x] for y in range(y0, y1) for x in range(x0, x1))

    assert brightest(160, 320, 0, 30) > 60
    assert brightest(0, 160, 90, 180) == 0


def test_malformed_plan_and_profile_are_refused_cleanly(service):
    for plan in ([], None, {"plan": "free"}):
        with pytest.raises(Exception) as refused:
            service.select_plan(plan)
        assert getattr(refused.value, "code", "") == "entitlement.input"
    with pytest.raises(Exception) as refused:
        service.check_entitlement("package", {"publicationJobId": "a" * 32, "profile": []})
    assert getattr(refused.value, "code", "") == "creation.input"


def test_http_feature_gates(service):
    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path, body):
        req = urllib.request.Request(
            base + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())

    try:
        assert (
            post("/api/creation/activity-rules", {"text": "视频时长不少于30秒"})["knownFields"] == 1
        )
        assert post("/api/entitlement", {"plan": "free"})["plan"] == "free"
        with pytest.raises(urllib.error.HTTPError) as denied:
            post("/api/creation/activity-rules", {"text": "视频时长不少于30秒"})
        assert "不包含" in json.loads(denied.value.read())["message"]
        with urllib.request.urlopen(base + "/api/entitlement") as response:
            data = json.loads(response.read())
        assert (
            data["billing"] == "none-local-evaluation"
            and data["features"]["activityRules"] is False
        )
        with pytest.raises(urllib.error.HTTPError):
            post("/api/entitlement", {"plan": "enterprise-gold"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
