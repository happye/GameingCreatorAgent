"""B06: 手动预览偏好按素材身份保存；换一条素材不继承；只存是否用代理。"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from test_benchmark_source_clock_browser import synthesize
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_preview_clock_align_browser import (
    _seed_from_file,
    plant_playable_proxy,
    seed_playable_project,
)

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

PREF_KEY = "gamingcreator:preview-preference-v1"


def media_query(page, selector="#source-video"):
    src = page.locator(selector).get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def stored_prefs(page):
    return page.evaluate(
        """(key) => {
            try { return JSON.parse(localStorage.getItem(key) || "{}"); }
            catch { return null; }
        }""",
        PREF_KEY,
    )


def seed_two_playable_media(root):
    first_project, first, _timeline = seed_playable_project(root, kind="zero")
    second_path = root / "artifacts" / "source-2.mp4"
    synthesize(second_path, "nonzero")
    project, second, _second_timeline = _seed_from_file(
        root, second_path, run_id="run-2", source_name="source-2.mp4"
    )
    plant_playable_proxy(root, first.asset.source_path, first.asset.sha256, first.asset.duration_us)
    plant_playable_proxy(
        root, second.asset.source_path, second.asset.sha256, second.asset.duration_us
    )
    assert first.asset.media_id != second.asset.media_id
    return project, first, second


def test_workbench_remembers_manual_original_after_reload(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    media_id = bundle.asset.media_id
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            box = page.locator("#proxy-toggle-input")
            expect(box).to_be_checked()
            box.uncheck()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            assert "proxy" not in media_query(page)
            prefs = stored_prefs(page)
            assert prefs == {media_id: False}
            page.reload()
            expect(page.locator("#timeline-count")).not_to_have_text("0", timeout=20000)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("#proxy-toggle-input")).not_to_be_checked()
            assert "proxy" not in media_query(page)
            assert stored_prefs(page) == {media_id: False}
            assert not errors, errors
        finally:
            browser.close()


def test_workbench_switching_media_does_not_inherit_preference(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, first, second = seed_two_playable_media(tmp_path)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#run-select")).to_be_enabled(timeout=20000)
            page.locator("#run-select").select_option("run-1")
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            page.locator("#proxy-toggle-input").uncheck()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            assert stored_prefs(page) == {first.asset.media_id: False}
            page.locator("#run-select").select_option("run-2")
            expect(page.locator("#source-name")).to_have_text("source-2.mp4", timeout=20000)
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            expect(page.locator("#proxy-toggle-input")).to_be_checked()
            assert media_query(page).get("proxy") == "1"
            assert stored_prefs(page) == {first.asset.media_id: False}
            page.locator("#run-select").select_option("run-1")
            expect(page.locator("#source-name")).to_have_text("source.mp4", timeout=20000)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("#proxy-toggle-input")).not_to_be_checked()
            assert "proxy" not in media_query(page)
            assert stored_prefs(page) == {first.asset.media_id: False}
            assert not errors, errors
        finally:
            browser.close()


def test_preview_preference_storage_drops_non_choice_fields(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    media_id = bundle.asset.media_id
    junk = {
        media_id: False,
        "videoUrl": "/api/media?project=p&run=r",
        "evidenceId": f"run-1:{media_id}:image:000000",
        "sha256": bundle.asset.sha256,
    }
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                f"localStorage.setItem({PREF_KEY!r}, {__import__('json').dumps(junk)!r});"
            )
            page.goto(base)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            loaded = page.evaluate("() => PreviewPreference.load()")
            assert loaded == {media_id: False}
            page.locator("#proxy-toggle-input").check()
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            assert stored_prefs(page) == {media_id: True}
            assert "videoUrl" not in stored_prefs(page)
            assert "evidenceId" not in stored_prefs(page)
            assert "sha256" not in stored_prefs(page)
            assert not errors, errors
        finally:
            browser.close()


def test_studio_asset_preview_honors_saved_preference(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    media_id = bundle.asset.media_id
    studio_boot = "localStorage.setItem('studio-v1', JSON.stringify({project:'artifacts/project', workspace:'assets'}));"
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(
                studio_boot
                + f"localStorage.setItem({PREF_KEY!r}, {json.dumps({media_id: False})!r});"
            )
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("#proxy-toggle-input")).not_to_be_checked()
            assert "proxy" not in media_query(page, ".viewer video")
            page.locator("#proxy-toggle-input").check()
            expect(page.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            assert media_query(page, ".viewer video").get("proxy") == "1"
            assert stored_prefs(page) == {media_id: True}
            # add_init_script would also run on reload and overwrite the saved true, so open a new page instead.
            page2 = browser.new_page(viewport={"width": 1366, "height": 860})
            errors2 = []
            page2.on("pageerror", lambda error: errors2.append(str(error)))
            page2.add_init_script(
                studio_boot
                + f"localStorage.setItem({PREF_KEY!r}, {json.dumps({media_id: True})!r});"
            )
            page2.goto(f"{base}/studio")
            expect(page2.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page2.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            expect(page2.locator("#proxy-toggle-input")).to_be_checked()
            assert media_query(page2, ".viewer video").get("proxy") == "1"
            assert stored_prefs(page2) == {media_id: True}
            assert not errors, errors
            assert not errors2, errors2
            page2.close()
        finally:
            browser.close()
