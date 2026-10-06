"""Offline drafts preserve omitted requirements and require an explicit scope in the workspace."""

import json
import threading

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import publish_v2_fixture, snapshot
from test_inspection_http import get, workspace


def post_draft(base, text):
    return get(
        base,
        "/api/draft-detail-query",
        method="POST",
        data=json.dumps({"text": text}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )


def test_draft_api_needs_no_project_and_cannot_read_or_send(tmp_path, monkeypatch):
    from gamingcreator.ui import server

    def forbidden(*args, **kwargs):
        raise AssertionError("Drafting must not access a project or invoke matching")

    monkeypatch.setattr(server, "resolve_project", forbidden)
    monkeypatch.setattr(server, "match_details", forbidden)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base:
        status, _, raw = post_draft(base, "白发，红色外套")
        report = json.loads(raw)
        assert status == 200 and report["status"] == "ready"
        assert report["originalText"] == "白发，红色外套"
        assert "".join(span["text"] for span in report["spans"]) == report["originalText"]
        conditions = report["constraint"]["actorAll"]
        garment = [item for item in conditions if item["kind"].startswith("clothing_")]
        assert {item["partGroup"] for item in garment} == {"clothing1"}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "damage", ["duplicate", "extra", "type", "oversize", "origin", "host", "content_type"]
)
def test_bad_draft_requests_cannot_access_a_project(tmp_path, monkeypatch, damage):
    refuse_sends(monkeypatch)
    value = {"text": "白发"}
    headers = {"Content-Type": "application/json"}
    raw = None
    if damage == "duplicate":
        raw = b'{"text":"white hair","text":"black hair"}'
    elif damage == "extra":
        value["project"] = "arbitrary"
    elif damage == "type":
        value["text"] = []
    elif damage == "oversize":
        value["text"] = "白" * 2049
    elif damage == "origin":
        headers["Origin"] = "https://attacker.invalid"
    elif damage == "host":
        headers["Host"] = "attacker.invalid"
    else:
        headers["Content-Type"] = "text/plain"
    with workspace(tmp_path) as base:
        status, _, _ = get(
            base,
            "/api/draft-detail-query",
            method="POST",
            data=raw or json.dumps(value).encode(),
            headers=headers,
        )
        assert status == (403 if damage in {"origin", "host"} else 400)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "text",
    [
        "没穿红外套",
        "未穿红外套",
        "doesn't wear red coat",
        "white hair instead of red coat",
        "奔跑后跳跃",
    ],
)
def test_negation_substitution_and_sequence_cannot_become_positive_api_conditions(tmp_path, text):
    with workspace(tmp_path) as base:
        status, _, raw = post_draft(base, text)
        report = json.loads(raw)
        assert status == 200 and report["status"] == "unsupported"
        assert report["constraint"] is None
        assert "".join(span["text"] for span in report["spans"]) == text


@pytest.mark.parametrize("width", [1366, 390])
def test_browser_draft_keeps_unknown_text_and_limits_matching_scope(tmp_path, monkeypatch, width):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 844})
            errors, external, matches = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    external.append(request.url) if not request.url.startswith(base + "/") else None
                ),
            )
            page.on(
                "request",
                lambda request: (
                    matches.append(request) if "/api/match-details" in request.url else None
                ),
            )
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#open-detail-query").click()
            page.locator("#detail-draft-text").fill("白发")
            page.locator("#generate-detail-draft").click()
            playwright.expect(page.locator("#detail-draft-status")).to_contain_text(
                "已生成可编辑条件"
            )
            assert matches == []
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                "当前条件有共同支持"
            )
            text = '白发，恶魔领主😀<img src=x onerror="window.draftInjected=1">'
            page.locator("#detail-draft-text").fill(text)
            playwright.expect(page.locator("#match-detail-query")).to_be_disabled()
            page.locator("#generate-detail-draft").click()
            playwright.expect(page.locator("#detail-draft-status")).to_contain_text(
                "还有要求未能处理"
            )
            playwright.expect(page.locator("#detail-draft-gaps")).to_contain_text("恶魔领主")
            playwright.expect(page.locator("#detail-draft-gaps")).to_contain_text("😀")
            assert page.locator("#detail-draft-text").input_value() == text
            assert page.locator("#detail-draft-gaps img").count() == 0
            assert page.evaluate("window.draftInjected === undefined")
            playwright.expect(page.locator("#match-detail-query")).to_be_disabled()
            page.locator("#detail-draft-subset").check()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                "当前条件有共同支持"
            )
            playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                "其他要求尚未核对"
            )
            playwright.expect(page.locator("#detail-match-result")).not_to_contain_text(
                "全部条件有共同支持"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            box = page.locator("#detail-query-dialog").bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
            assert not errors and not external
        finally:
            browser.close()
    assert snapshot(project) == before


def test_browser_unsupported_query_does_not_turn_or_into_and(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#open-detail-query").click()
            page.locator("#detail-draft-text").fill("白发或黑发")
            page.locator("#add-detail-condition").click()
            rows = page.locator(".detail-condition")
            rows.nth(1).locator(".condition-kind").select_option("clothing_shape")
            rows.nth(1).locator(".condition-value").select_option("coat")
            rows.nth(1).locator(".condition-group").select_option("clothing2")
            page.locator("#add-detail-condition").click()
            rows.nth(2).locator(".condition-kind").select_option("held_class")
            rows.nth(2).locator(".condition-value").select_option("staff")
            rows.nth(2).locator(".condition-group").select_option("held3")
            page.locator("#generate-detail-draft").click()
            playwright.expect(page.locator("#detail-draft-status")).to_contain_text("暂不支持")
            playwright.expect(page.locator(".detail-condition")).to_have_count(3)
            assert rows.nth(0).locator(".condition-value").input_value() == "white"
            assert rows.nth(1).locator(".condition-group").input_value() == "clothing2"
            assert rows.nth(2).locator(".condition-group").input_value() == "held3"
            playwright.expect(page.locator("#match-detail-query")).to_be_disabled()
            page.locator("#detail-draft-subset").check()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                "其他要求尚未核对"
            )
        finally:
            browser.close()


@pytest.mark.parametrize("change", ["text", "condition", "close", "profile", "run"])
def test_late_draft_response_cannot_replace_a_changed_context(tmp_path, monkeypatch, change):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    from gamingcreator.ui import server

    original = server.draft_detail_query
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def delayed(text):
        report = original(text)
        started.set()
        release.wait(10)
        finished.set()
        return report

    monkeypatch.setattr(server, "draft_detail_query", delayed)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#open-detail-query").click()
            page.locator("#detail-draft-text").fill("黑发")
            page.locator("#generate-detail-draft").click()
            assert started.wait(5)
            if change == "text":
                page.locator("#detail-draft-text").fill("白发")
            elif change == "condition":
                page.locator(".condition-value").select_option("red")
            elif change == "close":
                page.locator("#close-detail-query").click()
            elif change == "profile":
                page.locator("#detail-profile").evaluate(
                    "node => { node.value = 'v3'; node.dispatchEvent(new Event('change')); }"
                )
                playwright.expect(page.locator("#detail-profile")).to_be_enabled()
            else:
                page.locator("#run-select").dispatch_event("change")
                playwright.expect(page.locator("#detail-query-dialog")).not_to_be_visible()
            release.set()
            assert finished.wait(5)
            page.wait_for_timeout(150)
            assert page.locator(".condition-value").input_value() != "black"
            playwright.expect(page.locator("#detail-draft-status")).not_to_contain_text(
                "已生成可编辑条件"
            )
        finally:
            release.set()
            browser.close()
    assert snapshot(project) == before


def test_draft_confirmation_cannot_be_given_before_omissions_are_displayed(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    from gamingcreator.ui import server

    original = server.draft_detail_query
    started, release = threading.Event(), threading.Event()

    def delayed(text):
        report = original(text)
        started.set()
        release.wait(10)
        return report

    monkeypatch.setattr(server, "draft_detail_query", delayed)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#open-detail-query").click()
            page.locator("#detail-draft-text").fill("白发，恶魔领主")
            page.locator("#detail-draft-subset").check()
            page.locator("#generate-detail-draft").click()
            assert started.wait(5)
            playwright.expect(page.locator("#detail-draft-subset")).to_be_disabled()
            playwright.expect(page.locator("#detail-draft-subset")).not_to_be_checked()
            # A stale or programmatic selection must not survive the new response either.
            page.locator("#detail-draft-subset").evaluate("node => { node.checked = true; }")
            release.set()
            playwright.expect(page.locator("#detail-draft-gaps")).to_contain_text("恶魔领主")
            playwright.expect(page.locator("#detail-draft-subset")).not_to_be_checked()
            playwright.expect(page.locator("#match-detail-query")).to_be_disabled()
        finally:
            release.set()
            browser.close()
