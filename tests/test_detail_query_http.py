"""Strict conditions through HTTP and browser; source facts and paid calls stay untouched."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import manifest, publish_v2_fixture, snapshot
from test_inspection_http import get, workspace

from gamingcreator.application.detail_query import query_options
from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash
from gamingcreator.domain.actor_details import (
    AttributeKind,
    AttributeStatus,
    DetailAttribute,
    normalize_attribute_value,
)


def post(base, value, **kwargs):
    return get(
        base,
        "/api/match-details",
        method="POST",
        data=json.dumps(value).encode(),
        headers={"Content-Type": "application/json", **kwargs},
    )


def body(project, timeline, query=None, profile="v2"):
    return {
        "project": str(project),
        "run": timeline.run.run_id,
        "event": timeline.events[0].event_id,
        "profile": profile,
        "constraint": query or manifest(),
    }


def base_rows(project):
    with closing(
        sqlite3.connect((project / "timeline.sqlite3").as_uri() + "?mode=ro", uri=True)
    ) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            for table in (
                "media_assets",
                "analysis_runs",
                "semantic_events",
                "evidence",
                "event_evidence",
                "provider_invocations",
            )
        }


def test_query_options_come_from_frozen_vocabulary():
    options = query_options()
    assert {entry["kind"] for entry in options["kinds"]} == {kind.value for kind in AttributeKind}
    for entry in options["kinds"]:
        for item in entry["values"]:
            assert (
                normalize_attribute_value(AttributeKind(entry["kind"]), item["value"])
                == item["value"]
            )
            assert item["label"]


def test_matching_uses_exact_profile_and_does_not_save_or_send(tmp_path, monkeypatch):
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        query = manifest(("hair_color", "白发", "hair"))
        status, _, raw = post(base, body(project, timeline, query))
        assert status == 200
        result = json.loads(raw)
        assert result["result"]["status"] == "full"
        assert result["humanLabels"] is result["qualityGate"] is None
        assert result["refinementProfile"] == "v2"
        query["actorAll"].append({"kind": "held_class", "value": "staff", "partGroup": "item"})
        status, _, raw = post(base, body(project, timeline, query))
        assert status == 200 and json.loads(raw)["result"]["status"] == "partial"
        assert json.loads(raw)["result"]["matches"][0]["uncertain"]
    assert snapshot(project) == before


@pytest.mark.parametrize("same_part", [True, False])
def test_http_does_not_pool_separate_garments(tmp_path, same_part):
    project, _, timeline = seed_project(tmp_path)
    target, detail = publish_v2_fixture(project, timeline)
    actor = detail.shots[0].actors[0]
    ids, interval = detail.shots[0].evidence_ids, detail.shots[0].source_range
    attributes = (
        DetailAttribute(
            "coat", AttributeKind.CLOTHING_SHAPE, "coat", AttributeStatus.OBSERVED, ids, interval
        ),
        DetailAttribute(
            "coat" if same_part else "scarf",
            AttributeKind.CLOTHING_COLOR,
            "red",
            AttributeStatus.OBSERVED,
            ids,
            interval,
        ),
    )
    detail = replace(
        detail, shots=(replace(detail.shots[0], actors=(replace(actor, attributes=attributes),)),)
    )
    document = json.loads((target / "result.json").read_text())
    document.update(payloadJson=canonical_detail_json(detail), payloadHash=payload_hash(detail))
    (target / "result.json").write_text(json.dumps(document))
    query = manifest(("clothing_shape", "coat", "garment"), ("clothing_color", "red", "garment"))
    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project, timeline, query))
        assert status == 200
        assert json.loads(raw)["result"]["status"] == ("full" if same_part else "partial")


def test_missing_structure_returns_unverified_without_creating_a_sidecar(tmp_path, monkeypatch):
    project, _, timeline = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project, timeline))
        assert status == 200 and json.loads(raw)["result"]["status"] == "unverified"
    assert snapshot(project) == before
    assert not (project / "detail-refinement-budgets").exists()


def test_v3_does_not_borrow_frozen_v2_results(tmp_path, monkeypatch):
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project, timeline, profile="v3"))
        report = json.loads(raw)
        assert status == 200 and report["refinementProfile"] == "v3"
        assert report["result"]["status"] == "unverified"
        assert report["refinementPayloadHash"] is None
    assert snapshot(project) == before


@pytest.mark.parametrize(
    "damage",
    [
        "profile",
        "event",
        "foreign_run",
        "query",
        "duplicate",
        "extra",
        "type",
        "origin",
        "host",
        "content_type",
        "oversize",
    ],
)
def test_bad_match_requests_are_rejected_before_source_mutation(tmp_path, damage):
    project, _, timeline = seed_project(tmp_path)
    before = snapshot(project)
    value = body(project, timeline)
    headers = {"Content-Type": "application/json"}
    data = None
    if damage == "profile":
        value["profile"] = "future"
    elif damage == "event":
        value["event"] = "other-event"
    elif damage == "foreign_run":
        value["run"] = "other-run"
    elif damage == "query":
        value["constraint"] = {"freeQuery": "白发红衣"}
    elif damage == "duplicate":
        data = (
            json.dumps(value)
            .replace('"profile": "v2"', '"profile": "v2", "profile": "v1"')
            .encode()
        )
    elif damage == "extra":
        value["save"] = True
    elif damage == "type":
        value["event"] = []
    elif damage == "origin":
        headers["Origin"] = "https://attacker.invalid"
    elif damage == "host":
        headers["Host"] = "attacker.invalid"
    elif damage == "content_type":
        headers["Content-Type"] = "text/plain"
    else:
        data = b" " * 65537
    with workspace(tmp_path) as base:
        status, _, _ = get(
            base,
            "/api/match-details",
            method="POST",
            data=data or json.dumps(value).encode(),
            headers=headers,
        )
        assert status == 404 if damage == "foreign_run" else status in {400, 403, 409}
    assert snapshot(project) == before


@pytest.mark.parametrize("change", ["condition", "close", "profile", "run"])
def test_late_match_response_cannot_restore_changed_context(tmp_path, monkeypatch, change):
    import asyncio
    import threading

    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    from gamingcreator.ui import server

    original = server.match_details
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    async def delayed(*args, **kwargs):
        report = await original(*args, **kwargs)
        started.set()
        await asyncio.to_thread(release.wait, 10)
        finished.set()
        return report

    monkeypatch.setattr(server, "match_details", delayed)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#open-detail-query").click()
            page.locator("#match-detail-query").click()
            assert started.wait(5)
            if change == "condition":
                page.locator(".condition-value").select_option("black")
            elif change in {"close", "profile"}:
                page.locator("#close-detail-query").click()
                if change == "profile":
                    page.locator("#detail-profile").select_option("v1")
                    playwright.expect(page.locator("#open-detail-query")).to_be_enabled()
            else:
                page.locator("#run-select").dispatch_event("change")
                playwright.expect(page.locator("#detail-query-dialog")).not_to_be_visible()
            release.set()
            assert finished.wait(5)
            page.wait_for_timeout(150)
            playwright.expect(page.locator("#detail-match-result")).not_to_contain_text(
                "全部条件有共同支持"
            )
            if change == "run":
                playwright.expect(page.locator("#match-detail-query")).to_be_disabled()
            else:
                playwright.expect(page.locator("#match-detail-query")).to_be_enabled()
            if change == "condition":
                page.locator("#match-detail-query").click()
                playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                    "有相反证据"
                )
        finally:
            release.set()
            browser.close()
    assert snapshot(project) == before


def test_browser_rejects_matching_a_replaced_detail_payload(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    from gamingcreator.ui import server

    original = server.match_details

    async def replaced(*args, **kwargs):
        report = await original(*args, **kwargs)
        report["refinementPayloadHash"] = "f" * 64
        return report

    monkeypatch.setattr(server, "match_details", replaced)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            page.locator("#open-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).to_contain_text("身份不一致")
            playwright.expect(page.locator("#detail-match-result")).not_to_contain_text(
                "全部条件有共同支持"
            )
        finally:
            browser.close()


def test_browser_matches_explicit_conditions_and_clears_old_results(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    original_rows = base_rows(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768}, accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            assert page.locator("#detail-profile").input_value() == "v2"
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("白色")
            page.locator("#search-button").click()
            playwright.expect(page.locator("#candidate-count")).to_have_text("1")
            page.locator("#candidate-list .clip-preview").click()
            page.locator("#add-active").click()
            candidate = page.locator(".candidate-card").inner_text()
            page.locator("#open-detail-query").click()
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                "全部条件有共同支持"
            )
            assert page.evaluate("window.detailInjected === undefined")
            page.locator("#add-detail-condition").click()
            rows = page.locator(".detail-condition")
            rows.nth(1).locator(".condition-kind").select_option("held_class")
            rows.nth(1).locator(".condition-value").select_option("staff")
            playwright.expect(page.locator("#detail-match-result")).not_to_contain_text(
                "全部条件有共同支持"
            )
            page.locator("#match-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).to_contain_text(
                "部分条件有支持"
            )
            playwright.expect(page.locator("#detail-match-result")).to_contain_text("不确定")
            page.locator(".detail-support-frames button").first.click()
            playwright.expect(page.locator("#evidence-dialog")).to_be_visible()
            page.locator("#close-evidence").click()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
            box = page.locator("#detail-query-dialog").bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= 391
            page.locator("#close-detail-query").click()
            page.locator("#detail-profile").select_option("v1")
            playwright.expect(page.locator("#open-detail-query")).to_be_enabled()
            assert page.locator("#active-title").inner_text() == "候选 #1"
            assert page.locator(".candidate-card").inner_text() == candidate
            with page.expect_download() as download:
                page.locator("#export-json").click()
            from pathlib import Path

            saved = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            assert saved["selectedClips"][0]["rank"] == 1
            assert "detailRefinement" not in saved["selectedClips"][0]
            page.locator("#open-detail-query").click()
            playwright.expect(page.locator("#detail-match-result")).not_to_contain_text(
                "部分条件有支持"
            )
            assert errors == []
        finally:
            browser.close()
    after = snapshot(project)
    # Ordinary lexical search retains its existing search record behavior.
    assert base_rows(project) == original_rows
    for name, data in before.items():
        if name != "timeline.sqlite3":
            assert after[name] == data
