"""B02: the workbench auto-selects a verified proxy on first open, and the toggle still works."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from test_detail_inspection import refuse_sends
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


def media_query(page):
    src = page.locator("#source-video").get_attribute("src") or ""
    return {key: values[0] for key, values in parse_qs(urlparse(src).query).items()}


def test_first_open_uses_valid_proxy_and_toggle_can_switch_back(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    plant_playable_proxy(
        tmp_path, bundle.asset.source_path, bundle.asset.sha256, bundle.asset.duration_us
    )
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#timeline-count")).not_to_have_text("0", timeout=15000)
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            box = page.locator("#proxy-toggle-input")
            expect(box).to_be_visible()
            expect(box).to_be_checked()
            assert media_query(page).get("proxy") == "1"
            box.uncheck()
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            assert "proxy" not in media_query(page)
            box.check()
            expect(page.locator("#preview-badge")).to_have_text("编辑代理（非原片）", timeout=20000)
            assert media_query(page).get("proxy") == "1"
            assert not errors, errors
        finally:
            browser.close()


def test_first_open_without_proxy_stays_on_original(tmp_path, monkeypatch):
    playwright = pytest.importorskip("playwright.sync_api")
    refuse_sends(monkeypatch)
    seed_playable_project(tmp_path)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#timeline-count")).not_to_have_text("0", timeout=15000)
            expect(page.locator("#preview-badge")).to_have_text("原始素材", timeout=20000)
            expect(page.locator("#proxy-toggle")).to_have_count(0)
            assert "proxy" not in media_query(page)
            assert not errors, errors
        finally:
            browser.close()
