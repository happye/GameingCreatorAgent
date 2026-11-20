"""B03: Studio 素材预览只用检查接口里已核过的代理，不自己拼路径。"""

from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_inspection_http import workspace
from test_preview_clock_align_browser import plant_playable_proxy, seed_playable_project

from gamingcreator.infrastructure.proxy_media import SETTINGS, proxy_directory

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def plant(repository, sha256):
    directory = proxy_directory(repository, sha256)
    directory.mkdir(parents=True)
    body = b"proxy-bytes"
    (directory / "proxy.mp4").write_bytes(body)
    (directory / "receipt.json").write_text(
        json.dumps(
            {
                "schemaVersion": "editing-proxy-receipt-v1",
                "sourceSha256": sha256,
                "settings": SETTINGS,
                "bytes": len(body),
                "proxySha256": hashlib.sha256(body).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def video_query(page):
    src = page.locator(".viewer video").get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def test_studio_asset_preview_uses_verified_proxy(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text(
                "编辑代理（非原片）", timeout=20000
            )
            expect(page.locator("[data-preview-source]")).to_have_attribute(
                "data-preview-source", "proxy"
            )
            assert video_query(page).get("proxy") == "1"
            assert not errors, errors
        finally:
            browser.close()


def test_studio_asset_preview_stays_on_original_without_proxy(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    seed_project(tmp_path)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible(timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("[data-preview-source]")).to_have_attribute(
                "data-preview-source", "original"
            )
            assert "proxy" not in video_query(page)
            assert not errors, errors
        finally:
            browser.close()


def test_studio_choose_preview_rejects_foreign_and_incomplete_urls(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    seed_project(tmp_path)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            page.goto(f"{base}/studio")
            expect(page.locator(".viewer video")).to_be_visible()
            original = "/api/media?project=p&run=r"
            cases = page.evaluate(
                """async ([original]) => {
                    const api = await import("/assets/studio/api.js");
                    const pick = (offered) => api.choosePreview(original, offered);
                    return {
                        none: pick(null),
                        missingFlag: pick("/api/media?project=p&run=r"),
                        file: pick("file:///C:/proxy.mp4"),
                        foreign: pick("https://evil.example/api/media?project=p&run=r&proxy=1"),
                        otherProject: pick("/api/media?project=other&run=r&proxy=1"),
                        otherRun: pick("/api/media?project=p&run=other&proxy=1"),
                        ok: pick("/api/media?project=p&run=r&proxy=1"),
                    };
                }""",
                [original],
            )
            for key in ("none", "missingFlag", "file", "foreign", "otherProject", "otherRun"):
                assert cases[key]["source"] == "original", key
                assert cases[key]["url"] == original, key
                assert "proxy=1" not in (cases[key]["url"] or "")
            assert cases["ok"]["source"] == "proxy"
            assert cases["ok"]["url"] == "/api/media?project=p&run=r&proxy=1"
        finally:
            browser.close()
