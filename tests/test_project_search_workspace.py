"""Joint searches preserve their ranking while source preview and baskets stay isolated."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from test_detail_inspection import refuse_sends
from test_inspection_http import get, workspace
from test_project_retrieval import completed_pool, forbidden, snapshot
from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.media import SamplingParameters
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.project_search_files import read_project_search
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def pool(root):
    directory = root / "artifacts"
    directory.mkdir(parents=True)
    return asyncio.run(completed_pool(directory))


def body(project, **changes):
    return {
        "project": str(project),
        "runs": ["run-0", "run-1", "run-2"],
        "query": "建造",
        "mode": "lexical",
        "top": 10,
        **changes,
    }


def post(base, document, **kwargs):
    return get(
        base,
        "/api/search-project",
        data=json.dumps(document, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", **kwargs},
        method="POST",
    )


def guard(monkeypatch):
    refuse_sends(monkeypatch)
    monkeypatch.setattr(SqliteTimelineStore, "persist_search", forbidden)
    monkeypatch.setattr(SqliteTimelineStore, "recover", forbidden)


def test_http_joint_ranking_records_all_origins_without_mutating_saved_analysis(
    tmp_path, monkeypatch
):
    project, bundles = pool(tmp_path)
    before = snapshot(project)
    guard(monkeypatch)
    with workspace(tmp_path) as base:
        status, _, raw = post(base, body(project))
        assert status == 200
        result = json.loads(raw)
        assert result["project"] == str(project)
        assert {row["runId"] for row in result["candidates"]} == {"run-0", "run-1", "run-2"}
        assert [row["rank"] for row in result["candidates"]] == [1, 2, 3]
        assert result["qualityGate"] is None
        assert result["modelAnalysisCalls"] == result["newReservations"] == 0
        saved = read_project_search(project, result["searchId"])
        assert saved == {key: value for key, value in result.items() if key != "project"}
        for candidate in result["candidates"]:
            run_id = candidate["runId"]
            status, _, raw = get(
                base, "/api/inspect?" + urlencode({"project": str(project), "run": run_id})
            )
            assert status == 200
            view = json.loads(raw)
            assert view["media"]["sha256"] == candidate["sourceSha256"]
            assert view["candidates"] == []
            for evidence_id in candidate["evidenceIds"]:
                resource = next(item for item in view["evidence"] if item["id"] == evidence_id)
                status, _, data = get(base, resource["url"])
                assert status == 200
                bundle = bundles[int(run_id[-1])]
                evidence = (*bundle.images, *((bundle.audio,) if bundle.audio else ()))
                expected = next(item for item in evidence if item.evidence_id == evidence_id)
                assert data == expected.path.read_bytes()
    after = snapshot(project)
    assert {key: after[key] for key in before} == before
    assert len(set(after) - set(before)) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"runs": []},
        {"runs": ["run-0", "run-0"]},
        {"runs": ["run-0", None]},
        {"runs": "run-0"},
        {"runs": ["run-0"] * 101},
        {"runs": ["unknown"]},
        {"query": ""},
        {"query": "x" * 4097},
        {"query": 1},
        {"top": True},
        {"top": 101},
        {"mode": "remote"},
        {"path": "source.fixture"},
    ],
)
def test_http_invalid_scope_is_rejected_before_models_and_writes(tmp_path, monkeypatch, changes):
    project, _ = pool(tmp_path)
    before = snapshot(project)
    guard(monkeypatch)
    monkeypatch.setattr("gamingcreator.cli.main.LocalEmbeddingProvider.from_manifest", forbidden)
    with workspace(tmp_path) as base:
        status, _, _ = post(base, body(project, **changes))
        assert status in (400, 404, 409)
    assert snapshot(project) == before


def test_http_rejects_duplicate_versions_changed_source_and_remote_origin(tmp_path, monkeypatch):
    project, bundles = pool(tmp_path)

    async def duplicate():
        store = await SqliteTimelineStore.open(project)
        try:
            bundle = replace(bundle_fixture(project.parent, "duplicate"), asset=bundles[0].asset)
            write_manifest(bundle, SamplingParameters())
            await store.create_run("duplicate", bundle.asset, CONFIG)
            await store.begin_stage("duplicate", "media", bundle.asset.sha256)
            await store.persist_media_bundle("duplicate", bundle)
            await store.begin_stage("duplicate", "vision", bundle.asset.sha256)
            await store.persist_timeline("duplicate", "vision", (), (), bundle.asset.sha256)
            await store.complete_run("duplicate")
        finally:
            await store.close()

    asyncio.run(duplicate())
    before = snapshot(project)
    guard(monkeypatch)
    monkeypatch.setattr("gamingcreator.cli.main.LocalEmbeddingProvider.from_manifest", forbidden)
    with workspace(tmp_path) as base:
        assert post(base, body(project, runs=["run-0", "duplicate"], mode="hybrid"))[0] == 400
        assert post(base, body(project), Origin="https://external.invalid")[0] == 403
        bundles[1].asset.source_path.write_bytes(b"changed source")
        assert post(base, body(project, mode="hybrid"))[0] == 409
    assert snapshot(project) == before


def choose_sources(page):
    page.locator("#open-search-sources").click()
    assert page.locator("#search-sources-dialog").evaluate(
        "dialog => dialog.scrollWidth <= dialog.clientWidth"
    )
    assert page.locator("#search-sources-list input").first.bounding_box()["width"] <= 24
    for identifier in ("run-0", "run-1", "run-2"):
        page.locator(f'#search-sources-list input[value="{identifier}"]').check()
    page.locator("#apply-search-sources").click()


@pytest.mark.parametrize(
    "viewport", [{"width": 1366, "height": 768}, {"width": 390, "height": 844}]
)
def test_browser_joint_search_source_switch_baskets_download_and_single_mode(
    tmp_path, monkeypatch, viewport
):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    before = snapshot(project)
    guard(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport=viewport)
            errors = []
            requests = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request))
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            playwright.expect(page.locator("#search-scope-label")).to_contain_text("3 段录像")
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
            playwright.expect(page.locator("#download-project-search")).to_be_enabled()
            cards = page.locator(".candidate-card")
            ranks = cards.locator(".rank").all_text_contents()
            assert ranks == ["1", "2", "3"]
            assert page.locator("#open-retrieval-diagnostics").is_hidden()
            for identifier in ("run-1", "run-2", "run-0"):
                card = page.locator(f'.candidate-card[data-run="{identifier}"]')
                card.locator(".clip-preview").click()
                playwright.expect(page.locator("#run-select")).to_have_value(identifier)
                playwright.expect(page.locator("#active-title")).to_contain_text("候选 #")
                assert parse_qs(urlparse(page.locator("#source-video").get_attribute("src")).query)[
                    "run"
                ] == [identifier]
                evidence = page.locator("#evidence-list img, #evidence-list audio")
                playwright.expect(evidence).to_have_count(1)
                assert parse_qs(urlparse(evidence.get_attribute("src")).query)["run"] == [
                    identifier
                ]
                playwright.expect(page.locator("#selection-count")).to_have_text("0")
                card.locator(".select-clip").click()
                playwright.expect(page.locator("#selection-count")).to_have_text("1")
                with page.expect_download() as info:
                    page.locator("#export-json").click()
                export = json.loads(Path(info.value.path()).read_text(encoding="utf-8"))
                assert export["runId"] == identifier
                assert len(export["selectedClips"]) == 1
                assert cards.locator(".rank").all_text_contents() == ranks
            page.locator('.candidate-card[data-run="run-1"] .clip-preview').click()
            playwright.expect(page.locator("#selection-count")).to_have_text("1")
            with page.expect_download() as info:
                page.locator("#download-project-search").click()
            document = json.loads(Path(info.value.path()).read_text(encoding="utf-8"))
            assert len(document["sources"]) == 3
            assert [row["rank"] for row in document["candidates"]] == [1, 2, 3]
            assert (
                len(
                    [request for request in requests if request.url.endswith("/api/search-project")]
                )
                == 1
            )
            assert all(
                parse_qs(urlparse(request.url).query, keep_blank_values=True).get("query") == [""]
                for request in requests
                if "/api/inspect?" in request.url
            )
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert page.locator("#candidate-list").evaluate("list => list.clientHeight") >= 90
            page.locator("#single-search-source").click()
            playwright.expect(page.locator("#search-scope-label")).to_have_text("搜索当前录像")
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            playwright.expect(page.locator(".candidate-card")).to_have_count(0)
            assert not errors
        finally:
            browser.close()
    after = snapshot(project)
    assert {key: after[key] for key in before} == before
    assert len(set(after) - set(before)) == 2


def test_browser_source_version_choice_cancel_and_project_switch(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _ = pool(tmp_path)
    guard(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            def catalog(route):
                response = route.fetch()
                data = response.json()
                if "runs" in data:
                    data["runs"].append({**data["runs"][0], "id": "other-version"})
                route.fulfill(response=response, json=data)

            page.route("**/api/runs?*", catalog)
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            page.locator("#open-search-sources").click()
            first = page.locator('#search-sources-list input[value="run-0"]')
            second = page.locator('#search-sources-list input[value="other-version"]')
            first.check()
            second.check()
            playwright.expect(first).not_to_be_checked()
            playwright.expect(second).to_be_checked()
            page.locator("#close-search-sources").click()
            playwright.expect(page.locator("#search-scope-label")).to_have_text("搜索当前录像")
            choose_sources(page)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            page.locator("#project-form").locator("..").locator("summary").click()
            page.locator("#project-path").fill("artifacts/missing")
            page.locator("#project-form").evaluate("form => form.requestSubmit()")
            playwright.expect(page.locator("#search-scope-label")).to_have_text("搜索当前录像")
            playwright.expect(page.locator("#open-search-sources")).to_be_disabled()
            playwright.expect(page.locator("#search-button")).to_be_disabled()
        finally:
            browser.close()
    assert snapshot(project) == before


def test_browser_late_result_cannot_replace_changed_query_even_when_fetch_ignores_abort(
    tmp_path, monkeypatch
):
    playwright = pytest.importorskip("playwright.sync_api")
    pool(tmp_path)
    guard(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_init_script("""(() => {
                const original = window.fetch;
                window.fetch = async (url, options) => {
                    if (new URL(url).pathname !== '/api/search-project') return original(url, options);
                    const response = await original(url, {...options, signal: undefined});
                    return new Promise(resolve => { window.releaseSearch = () => { window.releaseSearch = null; resolve(response); }; });
                };
            })();""")
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            page.wait_for_function("() => typeof window.releaseSearch === 'function'")
            page.locator("#query").fill("其他需求")
            page.evaluate("window.releaseSearch()")
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            playwright.expect(page.locator("#candidate-count")).to_have_text("0")
            playwright.expect(page.locator("#download-project-search")).to_be_disabled()
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            page.wait_for_function("() => typeof window.releaseSearch === 'function'")
            page.evaluate("window.releaseSearch()")
            playwright.expect(page.locator(".candidate-card")).to_have_count(3)
        finally:
            browser.close()


@pytest.mark.parametrize("field", ["runId", "sourceSha256", "mediaId"])
def test_browser_refuses_candidate_origin_mismatch(tmp_path, monkeypatch, field):
    playwright = pytest.importorskip("playwright.sync_api")
    pool(tmp_path)
    guard(monkeypatch)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            def wrong_source(route):
                response = route.fetch()
                data = response.json()
                data["candidates"][0][field] = "other-source"
                route.fulfill(response=response, json=data)

            page.route("**/api/search-project", wrong_source)
            page.goto(base)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            choose_sources(page)
            playwright.expect(page.locator("#search-button")).to_be_enabled()
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("建造")
            page.locator("#search-button").click()
            playwright.expect(page.locator("#notice")).to_contain_text("来源或排名不一致")
            playwright.expect(page.locator(".candidate-card")).to_have_count(0)
            playwright.expect(page.locator("#download-project-search")).to_be_disabled()
        finally:
            browser.close()
