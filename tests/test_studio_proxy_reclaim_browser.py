"""Only the selected editing proxy is reclaimed, from the Studio workflow."""

import pytest
from shot_hard_case_fixtures import FFMPEG
from test_inspection_http import workspace
from test_preview_clock_align_browser import plant_playable_proxy, seed_playable_project

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = [pytest.mark.browser, pytest.mark.skipif(not FFMPEG.is_file(), reason="local FFmpeg")]


def test_studio_proxy_reclaim_requires_confirmation_and_returns_to_original(tmp_path):
    _project, bundle, _timeline = seed_playable_project(tmp_path)
    asset = bundle.asset
    source = asset.source_path.read_bytes()
    plant_playable_proxy(tmp_path, asset.source_path, asset.sha256, asset.duration_us)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 950})
            posts, errors = [], []
            page.on(
                "request",
                lambda request: posts.append(request.url) if request.method == "POST" else None,
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/studio")
            preview = page.locator("[data-preview-source]")
            playwright.expect(preview).to_have_attribute(
                "data-preview-source", "proxy", timeout=20000
            )
            page.get_by_role("link", name="代理空间", exact=True).click()
            row = page.locator("#inventory-table tr[data-selected]")
            reclaim = row.get_by_role("button", name=f"回收代理 {asset.sha256}")
            dialog = page.get_by_role("dialog", name="回收这一条编辑代理")
            reclaim.click()
            playwright.expect(dialog).to_contain_text(asset.sha256)
            dialog.get_by_role("button", name="取消").click()
            assert not posts

            reclaim.click()
            dialog.get_by_role("button", name="确认回收").click()
            playwright.expect(page.locator("#inventory-result")).to_have_text(
                f"已回收代理，释放 {len(source)} 字节。"
            )
            playwright.expect(row).to_have_count(0)
            assert posts == [base + "/api/reclaim-proxy"] and not errors
            page.get_by_role("link", name="返回 Studio").click()
            playwright.expect(preview).to_have_attribute(
                "data-preview-source", "original", timeout=20000
            )
        finally:
            browser.close()
    assert asset.source_path.read_bytes() == source
