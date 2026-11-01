"""Creation UI copy contracts: watermark notes, ranked-history plan cards, timeline size."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"
PLAN, REV, RENDER = "a" * 32, "b" * 32, "c" * 32

FEATURE_LABELS = {
    "activityRules": "活动规则解析",
    "multiPlatform": "同一成片生成多个平台包",
    "timelineExport": "专业时间线导出",
    "sandboxPublish": "发布流程（沙箱）",
}

FREE_ENTITLEMENT = {
    "plan": "free",
    "label": "Free",
    "billing": "none-local-evaluation",
    "features": {name: False for name in FEATURE_LABELS},
    "featureLabels": FEATURE_LABELS,
    "monthlyRenders": 10,
    "rendersThisMonth": 1,
    "monthlyPreparationMinutes": 60,
    "preparationMinutesThisMonth": 0.0,
    "watermark": "GamingCreator Free",
    "plans": {
        "founder": "创始人验证版（默认，不限）",
        "free": "Free",
        "creator": "Creator",
        "pro": "Creator Pro",
    },
}


def make_editor(**extra):
    return {
        "parentJobId": REV,
        "planId": "p1",
        "expectedParentReceiptSha256": "d" * 64,
        "fps": 30,
        "clips": [
            {
                "clipId": "c0",
                "startUs": 0,
                "endUs": 1_000_000,
                "outputFrames": 30,
                "scriptDraft": "开场",
            }
        ],
        "ancestry": [],
        **extra,
    }


def plan_card(plan_id, structure, *, local_renders=None, ranked=None, ready=True):
    card = {
        "id": plan_id,
        "structure": structure,
        "scriptStatus": "saved-descriptions-draft-human-review-required",
        "ready": ready,
        "gaps": [],
        "segments": [
            {
                "startUs": 0,
                "endUs": 1_000_000,
                "outputFrames": 30,
                "scriptDraft": "片段",
            }
        ],
    }
    if local_renders is not None:
        card["localRenders"] = local_renders
    if ranked is not None:
        card["rankedByHistory"] = ranked
    return card


@contextmanager
def workspace(*, entitlement=None, jobs=None, editors=None, job_payloads=None):
    """Strict-route creation workspace: unregistered paths return 未模拟 (no KeyError fallthrough)."""
    pw = pytest.importorskip("playwright.sync_api")
    entitlement = entitlement if entitlement is not None else FREE_ENTITLEMENT
    editors = editors or {REV: make_editor()}
    jobs = list(
        jobs
        or [
            {
                "jobId": REV,
                "kind": "revision",
                "status": "completed",
                "projectId": "one",
                "createdAt": "2026-11-01T00:00:00",
            }
        ]
    )
    payloads = dict(job_payloads or {})
    timeline_gets: list[str] = []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        def route(r):
            parts = urlsplit(r.request.url)
            path, method = parts.path, r.request.method
            query = parts.query
            if path == "/creation":
                r.fulfill(
                    body=(STATIC / "creation.html").read_text("utf-8-sig"),
                    content_type="text/html",
                )
            elif path.startswith("/assets/"):
                name = path.rsplit("/", 1)[1]
                r.fulfill(
                    body=(STATIC / name).read_text("utf-8-sig"),
                    content_type="text/css" if name.endswith("css") else "text/javascript",
                )
            elif path == "/api/creation/platform-profiles":
                r.fulfill(json={"profiles": []})
            elif path == "/api/creation/music":
                r.fulfill(json={"tracks": [], "issues": []})
            elif path == "/api/creation/voices":
                r.fulfill(json={"voices": [], "licenseStatus": "unknown"})
            elif path == "/api/entitlement":
                if method == "POST":
                    body = json.loads(r.request.post_data or "{}")
                    plan = body.get("plan", entitlement["plan"])
                    payload = dict(entitlement)
                    payload["plan"] = plan
                    if plan == "free":
                        payload["watermark"] = "GamingCreator Free"
                        payload["monthlyRenders"] = 10
                        payload["monthlyPreparationMinutes"] = 60
                        payload["features"] = {name: False for name in FEATURE_LABELS}
                        payload["label"] = "Free"
                    else:
                        payload["watermark"] = None
                        payload["monthlyRenders"] = None
                        payload["monthlyPreparationMinutes"] = None
                        payload["features"] = {name: True for name in FEATURE_LABELS}
                        payload["label"] = entitlement["plans"].get(plan, plan)
                    r.fulfill(json=payload)
                else:
                    r.fulfill(json=entitlement)
            elif path == "/api/enterprise/team":
                r.fulfill(json={"team": None})
            elif path == "/api/enterprise/audit":
                r.fulfill(body="{}", content_type="application/json")
            elif path == "/api/projects":
                r.fulfill(json={"projects": [{"path": "one", "name": "测试项目"}]})
            elif path.startswith("/api/runs"):
                r.fulfill(json={"runs": []})
            elif path.startswith("/api/creation/jobs?") or path == "/api/creation/jobs":
                r.fulfill(json={"jobs": jobs})
            elif "/edit" in path and "/jobs/" in path:
                job_id = path.split("/jobs/")[1].split("/")[0]
                r.fulfill(json=editors[job_id])
            elif "/timeline" in path and "/jobs/" in path:
                timeline_gets.append(path + (("?" + query) if query else ""))
                r.fulfill(
                    status=200,
                    body="<xml/>",
                    content_type="application/xml",
                    headers={"Content-Disposition": "attachment; filename=timeline.fcpxml"},
                )
            elif path.endswith("/video") or path.endswith("/subtitles"):
                r.fulfill(status=204)
            elif path.endswith("/publication"):
                r.fulfill(
                    json={
                        "renderJobId": RENDER,
                        "expectedRenderReceiptSha256": "e" * 64,
                        "frames": 30,
                        "fps": 30,
                        "videoUrl": f"/api/creation/jobs/{RENDER}/video",
                        "coverFrame": 0,
                        "title": "t",
                        "description": "d",
                        "tags": [],
                        "draftStatus": "editable-template-not-ai",
                    }
                )
            elif path.startswith("/api/creation/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                if job_id in payloads:
                    r.fulfill(json=payloads[job_id])
                else:
                    match = next((j for j in jobs if j["jobId"] == job_id), None)
                    if match is None:
                        r.fulfill(status=404, json={"error": f"未模拟 {path}"})
                    else:
                        r.fulfill(json={**match, "projectId": "one"})
            else:
                r.fulfill(status=404, json={"error": f"未模拟 {path}"})

        page.route("**/*", route)
        try:
            page.goto("http://workspace.test/creation")
            yield pw, page, timeline_gets
        finally:
            browser.close()


def test_artifact_watermark_note_under_creation():
    render = {
        "jobId": RENDER,
        "kind": "render",
        "status": "completed",
        "projectId": "one",
        "createdAt": "2026-11-01T01:00:00",
        "artifact": {
            "mediaType": "video/mp4",
            "sizeBytes": 2048,
            "previewUrl": f"/api/creation/jobs/{RENDER}/video",
            "downloadUrl": f"/api/creation/jobs/{RENDER}/video?download=1",
            "watermark": "GamingCreator Free",
        },
    }
    with workspace(
        jobs=[render],
        job_payloads={RENDER: render},
    ) as (pw, page, _):
        page.locator("#history button").filter(has_text="视频").click()
        note = page.locator("#artifact p").filter(has_text="水印")
        pw.expect(note).to_contain_text(
            "成片右上角带“GamingCreator Free”水印（Free 套餐，生成时确定）。"
        )


def test_plan_panel_watermark_tip():
    with workspace(entitlement=FREE_ENTITLEMENT) as (pw, page, _):
        pw.expect(page.locator("#plan-panel h3")).to_have_text("套餐与用量")
        info = page.locator("#plan-info")
        pw.expect(info).to_contain_text("新成片右上角带“GamingCreator Free”水印")
        pw.expect(info).to_contain_text("未接入任何支付")


def test_plan_card_ranked_by_history_true_and_false():
    plan_job = {
        "jobId": PLAN,
        "kind": "plan",
        "status": "completed",
        "projectId": "one",
        "createdAt": "2026-11-01T02:00:00",
        "fps": 30,
        "plans": [
            plan_card("hist", "最后一条先作开场", local_renders=2, ranked=True),
            plan_card("plain", "按时间顺序", local_renders=3, ranked=False),
            plan_card("fresh", "高光优先"),
        ],
    }
    with workspace(
        jobs=[plan_job],
        job_payloads={PLAN: plan_job},
        editors={PLAN: make_editor(parentJobId=PLAN, planId="hist")},
    ) as (pw, page, _):
        page.locator("#history button").filter(has_text="方案").click()
        cards = page.locator(".plan-card")
        pw.expect(cards).to_have_count(3)
        ranked = cards.nth(0)
        unranked = cards.nth(1)
        plain = cards.nth(2)
        pw.expect(ranked).to_contain_text(
            "你常用的结构 · 本项目已有 2 个方案用它做成成片，所以排到了通用方案前面"
        )
        pw.expect(unranked).to_contain_text("你常用的结构 · 本项目已有 3 个方案用它做成成片")
        assert "所以排到了通用方案前面" not in unranked.inner_text()
        assert "你常用的结构" not in plain.inner_text()


def test_timeline_export_click_includes_size_param():
    revision = {
        "jobId": REV,
        "kind": "revision",
        "status": "completed",
        "projectId": "one",
        "createdAt": "2026-11-01T03:00:00",
        "planId": "p1",
    }
    with workspace(
        jobs=[revision],
        job_payloads={REV: {**revision, "editor": make_editor()}},
        editors={REV: make_editor()},
    ) as (pw, page, timeline_gets):
        page.locator("#history button").filter(has_text="剪辑版本").click()
        link = page.locator("#timeline-fcpxml")
        pw.expect(link).to_be_visible()
        page.locator("#size").select_option("720,1280")
        page.evaluate(
            """() => {
              const a = document.getElementById('timeline-fcpxml');
              a.addEventListener('click', (e) => e.preventDefault(), true);
            }"""
        )
        link.click()
        href = link.get_attribute("href") or ""
        assert "size=720x1280" in href, href
        assert "format=fcpxml" in href
        assert f"/api/creation/jobs/{REV}/timeline" in href
