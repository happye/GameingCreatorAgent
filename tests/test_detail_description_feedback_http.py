"""Description feedback is visible, exact-result scoped and read-only; no human quality gate."""

import hashlib
import json
from dataclasses import replace
from urllib.parse import urlencode

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import publish_v2_fixture, snapshot
from test_detail_query_http import body, post
from test_inspection_http import get, workspace

from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash


def feedback_fixture(project, timeline, *, two_actors=False):
    target, detail = publish_v2_fixture(project, timeline)
    if two_actors:
        shot = detail.shots[0]
        other = replace(shot.actors[0], actor_id="right", description="旧模型误认的物品描述")
        detail = replace(detail, shots=(replace(shot, actors=shot.actors + (other,)),))
        saved = json.loads((target / "result.json").read_text())
        saved.update(payloadJson=canonical_detail_json(detail), payloadHash=payload_hash(detail))
        (target / "result.json").write_text(json.dumps(saved), encoding="utf-8")
    common = {
        "runId": timeline.run.run_id,
        "eventId": timeline.events[0].event_id,
        "requestHash": target.name,
        "refinementPayloadHash": payload_hash(detail),
        "scope": "actor-description",
        "source": "direct-project-user-feedback",
    }
    cases = [
        {
            **common,
            "caseId": "accepted-description",
            "targetActorIds": ["shot-1/left"],
            "verdict": "accepted",
            "statement": '确认此描述 <img src=x onerror="window.feedbackInjected=1">',
        }
    ]
    if two_actors:
        cases.append(
            {
                **common,
                "caseId": "rejected-description",
                "targetActorIds": ["shot-1/right"],
                "verdict": "rejected",
                "statement": "这是靠近镜头的持有物，不是新人物。",
            }
        )
    report = json.dumps(
        {
            "schemaVersion": "actor-detail-pilot-report-v1",
            "cases": [
                {
                    "caseId": case["caseId"],
                    "runId": common["runId"],
                    "eventId": common["eventId"],
                    "requestHash": common["requestHash"],
                    "attempt": {
                        "status": "completed",
                        "requestHash": common["requestHash"],
                        "payloadHash": common["refinementPayloadHash"],
                        "payloadJson": canonical_detail_json(detail),
                    },
                }
                for case in cases
            ],
        }
    ).encode("utf-8")
    report_sha = hashlib.sha256(report).hexdigest()
    value = {
        "schemaVersion": "detail-pilot-human-feedback-v1",
        "recordedOn": "2026-10-06",
        "pilotReportSha256": report_sha,
        "cases": cases,
        "unmentionedEntries": "unreviewed",
        "phase0QualityGate": None,
        "newProviderCalls": 0,
    }
    directory = project / "detail-description-feedback"
    reports = directory / "reports"
    reports.mkdir(parents=True)
    (reports / (report_sha + ".json")).write_bytes(report)
    feedback = directory / "feedback.json"
    feedback.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return feedback, value, target, detail


def inspect(base, project, timeline, profile="v2"):
    return get(
        base,
        "/api/inspect?"
        + urlencode(
            {"project": str(project), "run": timeline.run.run_id, "detailProfile": profile}
        ),
    )


def test_existing_feedback_is_exactly_projected_without_source_changes(tmp_path, monkeypatch):
    project, _, timeline = seed_project(tmp_path)
    _, _, _, detail = feedback_fixture(project, timeline, two_actors=True)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, timeline)
        assert status == 200
        row = json.loads(raw)["timeline"][0]["detailRefinement"]
        feedback = row["descriptionFeedback"]
        assert feedback["scope"] == "actor-description"
        assert feedback["phase0QualityGate"] is None
        assert [item["verdict"] for item in feedback["reviews"]] == ["accepted", "rejected"]
        assert row["payloadHash"] == payload_hash(detail)
        status, _, raw = post(base, body(project, timeline))
        matched = json.loads(raw)
        assert status == 200 and matched["result"]["status"] == "full"
        assert matched["humanLabels"] is matched["qualityGate"] is None
        status, _, raw = inspect(base, project, timeline, "v4")
        other = json.loads(raw)["timeline"][0]["detailRefinement"]
        assert status == 200 and other["availability"] == "missing"
        assert not other.get("descriptionFeedback")
    assert snapshot(project) == before


def test_absent_feedback_never_creates_a_namespace(tmp_path, monkeypatch):
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, timeline)
        assert status == 200
        assert json.loads(raw)["timeline"][0]["detailRefinement"]["descriptionFeedback"] is None
    assert snapshot(project) == before
    assert not (project / "detail-description-feedback").exists()


@pytest.mark.parametrize(
    "damage", ["missing", "broken", "report", "report_identity", "duplicate", "target", "oversize"]
)
def test_damaged_feedback_fails_explicitly_and_cannot_become_approval(
    tmp_path, monkeypatch, damage
):
    project, _, timeline = seed_project(tmp_path)
    path, value, _, _ = feedback_fixture(project, timeline)
    if damage == "missing":
        path.unlink()
    elif damage == "broken":
        path.write_text("{broken}")
    elif damage == "report":
        report = next((path.parent / "reports").iterdir())
        report.write_text("changed")
    elif damage == "report_identity":
        report = next((path.parent / "reports").iterdir())
        original = json.loads(report.read_bytes())
        original["cases"][0]["runId"] = "another-run"
        changed = json.dumps(original).encode("utf-8")
        digest = hashlib.sha256(changed).hexdigest()
        (path.parent / "reports" / (digest + ".json")).write_bytes(changed)
        value["pilotReportSha256"] = digest
        path.write_text(json.dumps(value), encoding="utf-8")
    elif damage == "oversize":
        path.write_bytes(b" " * 1_048_577)
    else:
        if damage == "duplicate":
            value["cases"].append(
                dict(value["cases"][0], caseId="contradictory", verdict="rejected")
            )
        else:
            value["cases"][0]["targetActorIds"] = ["shot-1/missing"]
        path.write_text(json.dumps(value), encoding="utf-8")
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, timeline)
        assert status == 409 and json.loads(raw)["code"] == "detail_feedback.damaged"
    assert snapshot(project) == before


def test_a_changed_payload_does_not_inherit_its_previous_description_confirmation(
    tmp_path, monkeypatch
):
    project, _, timeline = seed_project(tmp_path)
    _, _, target, detail = feedback_fixture(project, timeline)
    actor = replace(detail.shots[0].actors[0], description="新的模型描述")
    detail = replace(detail, shots=(replace(detail.shots[0], actors=(actor,)),))
    saved = json.loads((target / "result.json").read_text())
    saved.update(payloadJson=canonical_detail_json(detail), payloadHash=payload_hash(detail))
    (target / "result.json").write_text(json.dumps(saved))
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, timeline)
        assert status == 200
        feedback = json.loads(raw)["timeline"][0]["detailRefinement"]["descriptionFeedback"]
        assert feedback["status"] == "unreviewed" and feedback["reviews"] == []
    assert snapshot(project) == before


@pytest.mark.parametrize("width", [1366, 390])
def test_browser_shows_description_feedback_safely_in_details_and_matches(
    tmp_path, monkeypatch, width
):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    feedback_fixture(project, timeline, two_actors=True)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 844})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#actor-details > summary").click()
            panel = page.locator("#actor-detail-list")
            playwright.expect(panel).to_contain_text("用户已确认此描述")
            playwright.expect(panel).to_contain_text("用户已指出此描述有误")
            playwright.expect(panel).to_contain_text("旧模型误认的物品描述")
            playwright.expect(panel).to_contain_text("仅针对描述")
            assert panel.locator(".detail-description-review img").count() == 0
            assert page.evaluate("window.feedbackInjected === undefined")
            page.locator("#open-detail-query").click()
            page.locator("#match-detail-query").click()
            matched = page.locator("#detail-match-result")
            playwright.expect(matched).to_contain_text("用户已确认此描述")
            playwright.expect(matched).to_contain_text("用户已指出此描述有误")
            playwright.expect(matched).to_contain_text("属性和检索质量仍须独立核对")
            assert matched.locator(".detail-description-review img").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#close-detail-query").click()
            page.locator("#detail-profile").select_option("v4")
            playwright.expect(page.locator("#detail-profile")).to_be_enabled()
            playwright.expect(panel).not_to_contain_text("用户已确认此描述")
            assert errors == []
        finally:
            browser.close()
    assert snapshot(project) == before


@pytest.mark.parametrize("damage", ["payload", "request", "scope", "duplicate", "null"])
def test_browser_cannot_apply_feedback_from_a_forged_or_mismatched_response(
    tmp_path, monkeypatch, damage
):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    feedback_fixture(project, timeline)
    refuse_sends(monkeypatch)
    from gamingcreator.ui import server

    original = server.inspect_run

    async def forged(*args, **kwargs):
        report = await original(*args, **kwargs)
        feedback = report["timeline"][0]["detailRefinement"]["descriptionFeedback"]
        if damage == "payload":
            feedback["refinementPayloadHash"] = "f" * 64
        elif damage == "request":
            feedback["requestHash"] = "e" * 64
        elif damage == "scope":
            feedback["scope"] = "all-attributes"
        elif damage == "duplicate":
            feedback["reviews"].append(dict(feedback["reviews"][0], verdict="rejected"))
        else:
            feedback["reviews"].append(None)
        return report

    monkeypatch.setattr(server, "inspect_run", forged)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#actor-details > summary").click()
            panel = page.locator("#actor-detail-list")
            playwright.expect(panel).to_contain_text("人工反馈与当前结果不一致，未应用")
            playwright.expect(panel).not_to_contain_text("用户已确认此描述")
        finally:
            browser.close()
