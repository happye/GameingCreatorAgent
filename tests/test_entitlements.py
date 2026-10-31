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
