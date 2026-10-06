"""Unscored ten-slot diagnostics stay bound to one completed local search."""

import asyncio
import json
from urllib.parse import urlencode

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query_http import base_rows
from test_inspection_http import get, workspace

from gamingcreator.application.inspection import InspectionView, RankedRow
from gamingcreator.application.retrieval_diagnostics import retrieval_diagnostics
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def row(rank, event_id, candidate_id=None):
    return RankedRow(
        rank,
        event_id,
        candidate_id or f"clip-{rank}",
        100_000,
        800_000,
        ("f0 白色主体",),
        ("frame-1",),
        0.9,
        "fixture",
    )


def diagnose(rows=(), *, query="跳跃", status="completed", top=10, reason=None, evidence=()):
    return retrieval_diagnostics(
        InspectionView("unused.sqlite3", "run-1", status, (), tuple(rows), reason),
        project="artifacts/project",
        query=query,
        mode="lexical",
        requested_top_k=top,
        media_id="media-1",
        media_sha256="a" * 64,
        duration_us=2_000_000,
        config_hash="b" * 64,
        retrieval_version="test-version",
        evidence=evidence,
    )


def test_two_candidates_leave_eight_slots_and_no_human_quality_claim():
    rows = (row(7, "event-1"), row(3, "event-2"))
    doc = diagnose(rows)
    assert doc["missingCount"] == 8
    assert doc["returnedCount"] == 2 and doc["knownDuplicateCount"] == 0
    assert [slot["position"] for slot in doc["slots"]] == list(range(1, 11))
    assert [slot["candidate"]["rank"] for slot in doc["slots"][:2]] == [7, 3]
    assert [slot["status"] for slot in doc["slots"][2:]] == ["missing"] * 8
    assert all(doc[key] is None for key in ("humanLabels", "qualityGate", "usefulRate"))
    assert all(slot["humanGrade"] is None for slot in doc["slots"])
    assert all(slot["independenceStatus"] == "unreviewed" for slot in doc["slots"])
    assert rows[0].facts == ("f0 白色主体",)
    assert doc["slots"][0]["candidate"]["observableFacts"] == list(rows[0].facts)
    assert "f0" not in doc["slots"][0]["candidate"]["displayFacts"][0]


def test_duplicates_stay_in_place_and_eleventh_does_not_fill_them():
    rows = [row(1, "repeat"), row(2, "repeat")]
    rows.extend(row(rank, f"event-{rank}") for rank in range(3, 12))
    doc = diagnose(rows)
    assert doc["returnedCount"] == 11 and doc["missingCount"] == 0
    assert doc["knownDuplicateCount"] == 1
    assert doc["slots"][1]["status"] == "known_duplicate"
    assert doc["slots"][1]["duplicateOfPosition"] == 1
    assert [slot["candidate"]["rank"] for slot in doc["slots"]] == list(range(1, 11))


def test_audio_fallback_does_not_collide_with_event_id_namespace():
    doc = diagnose([row(1, "same"), row(2, None, "same"), row(3, None, "same"), row(4, None)])
    assert [slot["status"] for slot in doc["slots"][:4]] == [
        "candidate",
        "candidate",
        "known_duplicate",
        "candidate",
    ]
    assert doc["slots"][2]["duplicateOfPosition"] == 2


@pytest.mark.parametrize("top", [1, 2, 9, 10, 100])
def test_requested_limit_is_explicit_and_missing_positions_remain(top):
    doc = diagnose([row(1, "one")], top=top)
    assert doc["requestedTopK"] == top
    assert doc["limitedByRequestedTopK"] is (top < 10)
    assert doc["missingCount"] == 9


@pytest.mark.parametrize(
    "query,status",
    [("", "completed"), (" \t", "completed"), ("跳跃", "running"), ("跳跃", "failed")],
)
def test_no_diagnostic_for_unexecuted_search(query, status):
    assert diagnose(query=query, status=status) is None


def test_completed_zero_hits_retain_reason_and_source_binding():
    doc = diagnose(reason="semantic_ambiguity_without_lexical_anchor")
    assert doc["missingCount"] == 10
    assert doc["abstentionReason"] == "semantic_ambiguity_without_lexical_anchor"
    assert {
        key: doc[key]
        for key in (
            "project",
            "runId",
            "mediaId",
            "mediaSha256",
            "durationUs",
            "configHash",
            "retrievalVersion",
        )
    } == {
        "project": "artifacts/project",
        "runId": "run-1",
        "mediaId": "media-1",
        "mediaSha256": "a" * 64,
        "durationUs": 2_000_000,
        "configHash": "b" * 64,
        "retrievalVersion": "test-version",
    }


def test_http_projects_saved_search_without_changing_source_facts(tmp_path, monkeypatch):
    project, _, _ = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    before = base_rows(project)
    params = {
        "project": project.relative_to(tmp_path).as_posix(),
        "run": "run-1",
        "mode": "lexical",
        "top": 2,
    }
    with workspace(tmp_path) as base:
        for query, hits in (("", 0), ("白色", 1), ("汽车修理工", 0)):
            status, _, body = get(base, "/api/inspect?" + urlencode({**params, "query": query}))
            assert status == 200
            payload = json.loads(body)
            doc = payload["retrievalDiagnostics"]
            if not query:
                assert doc is None
                continue
            assert doc["query"] == query and doc["project"] == params["project"]
            assert doc["returnedCount"] == hits and doc["missingCount"] == 10 - hits
            assert doc["limitedByRequestedTopK"]
            assert doc["mediaSha256"] == payload["media"]["sha256"]
            assert doc["configHash"] == payload["configHash"]
            assert doc["schemaVersion"] == "retrieval-diagnostics-v2"
            for slot, candidate in zip(doc["slots"], payload["candidates"], strict=False):
                for key in ("candidateId", "eventId", "startUs", "endUs", "rank", "evidenceIds"):
                    assert slot["candidate"][key] == candidate[key]
                evidence = slot["candidate"]["evidenceSummary"]
                assert evidence["status"] == "registered_single_frame"
                assert evidence["registeredImageCount"] == 1
                assert evidence["actionUnderstandingVerified"] is None
    assert base_rows(project) == before
    assert len(list(project.glob("runs/run-1/searches/*.json"))) == 2


def test_incomplete_http_never_executes_search_or_creates_diagnostics(tmp_path, monkeypatch):
    project, _, _ = seed_project(tmp_path, completed=False)
    refuse_sends(monkeypatch)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Incomplete runs must not search.")

    monkeypatch.setattr("gamingcreator.ui.service.execute_search", forbidden)
    with workspace(tmp_path) as base:
        status, _, body = get(
            base,
            "/api/inspect?" + urlencode({"project": str(project), "run": "run-1", "query": "跳跃"}),
        )
        assert status == 200
        assert json.loads(body)["retrievalDiagnostics"] is None


@pytest.mark.parametrize("width,height", [(1366, 768), (390, 844)])
def test_browser_diagnostic_download_preview_and_no_extra_search(
    tmp_path, monkeypatch, width, height
):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, _ = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height}, accept_downloads=True
            )
            errors, searches = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    searches.append(request.url) if "/api/inspect?" in request.url else None
                ),
            )
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            playwright.expect(page.locator("#open-retrieval-diagnostics")).to_be_disabled()
            page.locator("#mode").select_option("lexical")
            page.locator("#top").fill("2")
            page.locator("#query").fill("白色")
            with page.expect_response(lambda response: "/api/inspect?" in response.url) as received:
                page.locator("#search-button").click()
            expected = received.value.json()["retrievalDiagnostics"]
            playwright.expect(page.locator("#open-retrieval-diagnostics")).to_be_enabled()
            search_count = len(searches)
            page.locator("#open-retrieval-diagnostics").click()
            playwright.expect(page.locator(".diagnostics-slot")).to_have_count(10)
            playwright.expect(page.locator(".diagnostics-slot.missing")).to_have_count(9)
            playwright.expect(page.locator(".diagnostics-evidence")).to_contain_text(
                "已登记 1 张画面"
            )
            playwright.expect(page.locator(".diagnostics-evidence")).to_contain_text(
                "不能据此确认动作过程"
            )
            playwright.expect(page.locator("#retrieval-diagnostics-summary")).to_contain_text(
                "本次只请求 2 条"
            )
            with page.expect_download() as downloaded:
                page.locator("#download-retrieval-diagnostics").click()
            assert json.loads(downloaded.value.path().read_text(encoding="utf-8")) == expected
            assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
            assert page.locator("#retrieval-diagnostics-dialog").evaluate(
                "node => node.scrollWidth <= node.clientWidth"
            )
            page.locator(".diagnostics-preview").click()
            playwright.expect(page.locator("#retrieval-diagnostics-dialog")).not_to_be_visible()
            playwright.expect(page.locator("#active-title")).to_have_text("候选 #1")
            assert len(searches) == search_count
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize(
    "change", ["query", "mode", "top", "refresh", "project", "run", "failure", "late-response"]
)
def test_browser_invalidates_old_diagnostic_context(tmp_path, monkeypatch, change):
    playwright = pytest.importorskip("playwright.sync_api")
    project, bundle, timeline = seed_project(tmp_path)
    other_project, _, _ = seed_project(tmp_path / "artifacts" / "other")
    if change == "run":

        async def another_run():
            store = await SqliteTimelineStore.open(project)
            try:
                await store.create_run("run-2", bundle.asset, timeline.run.configuration)
            finally:
                await store.close()

        asyncio.run(another_run())
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("白色")
            page.locator("#search-button").click()
            playwright.expect(page.locator("#open-retrieval-diagnostics")).to_be_enabled()
            page.locator("#open-retrieval-diagnostics").click()
            if change in ("query", "mode", "top"):
                # Programmatic input simulates edits while a modal is open, so its
                # captured preview/export handlers must also be invalidated.
                page.locator(f"#{change}").evaluate(
                    "node => { node.value = node.id === 'query' ? '别的条件' : node.id === 'mode' ? 'semantic' : '1'; node.dispatchEvent(new Event(node.id === 'mode' ? 'change' : 'input', {bubbles:true})); }"
                )
            else:
                page.locator("#close-retrieval-diagnostics").click()
                if change == "refresh":
                    page.locator("#refresh-view").click()
                elif change == "project":
                    page.locator(".manual-project summary").click()
                    page.locator("#project-path").fill(str(other_project))
                    page.locator("#project-form").evaluate("node => node.requestSubmit()")
                elif change == "run":
                    page.locator("#run-select").select_option("run-2")
                    playwright.expect(page.locator("#run-state")).to_contain_text("run-2")
                elif change == "failure":
                    page.route(
                        "**/api/inspect?**",
                        lambda route: route.fulfill(
                            status=500,
                            content_type="application/json",
                            body=json.dumps({"message": "fixture search failed"}),
                        ),
                    )
                    page.locator("#search-button").click()
                    playwright.expect(page.locator("#search-context")).to_contain_text("查询未完成")
                else:

                    def late(route):
                        response = route.fetch()
                        page.locator("#query").evaluate(
                            "node => {node.value='射击'; node.dispatchEvent(new Event('input', {bubbles:true}));}"
                        )
                        route.fulfill(response=response)

                    page.route("**/api/inspect?**", late)
                    page.locator("#search-button").click()
            if change != "run":
                playwright.expect(page.locator("#search-button")).to_be_enabled()
            playwright.expect(page.locator("#open-retrieval-diagnostics")).to_be_disabled()
            playwright.expect(page.locator("#retrieval-diagnostics-dialog")).not_to_be_visible()
            playwright.expect(page.locator("#download-retrieval-diagnostics")).to_be_disabled()
        finally:
            browser.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("mediaSha256", "f" * 64),
        ("configHash", "f" * 64),
        ("project", "another-project"),
        ("candidateId", "another-candidate"),
    ],
)
def test_browser_refuses_diagnostics_from_replaced_source(tmp_path, monkeypatch, field, value):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("白色")

            def tampered(route):
                response = route.fetch()
                payload = response.json()
                doc = payload["retrievalDiagnostics"]
                if field == "candidateId":
                    doc["slots"][0]["candidate"][field] = value
                else:
                    doc[field] = value
                route.fulfill(response=response, json=payload)

            page.route("**/api/inspect?**", tampered)
            page.locator("#search-button").click()
            playwright.expect(page.locator("#candidate-count")).to_have_text("1")
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            playwright.expect(page.locator("#open-retrieval-diagnostics")).to_be_disabled()
        finally:
            browser.close()


def test_browser_zero_hits_and_query_markup_are_plain_text(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    seed_project(tmp_path)
    refuse_sends(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#mode").select_option("lexical")
            query = '<img src=x onerror="window.diagnosticInjected=true">'
            page.locator("#query").fill(query)
            page.locator("#search-button").click()
            playwright.expect(page.locator("#open-retrieval-diagnostics")).to_be_enabled()
            page.locator("#open-retrieval-diagnostics").click()
            playwright.expect(page.locator(".diagnostics-slot.missing")).to_have_count(10)
            playwright.expect(page.locator("#retrieval-diagnostics-summary")).to_contain_text(query)
            assert page.locator("#retrieval-diagnostics-dialog img").count() == 0
            assert page.evaluate("window.diagnosticInjected === undefined")
        finally:
            browser.close()
