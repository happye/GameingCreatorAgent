"""First run: a project without recordings shows a three-step guide, not a dead end."""

import threading
from urllib.parse import urlsplit

import pytest

from gamingcreator.ui.server import create_server


@pytest.mark.parametrize(
    "recordings",
    [
        [],
        [
            {
                "id": "r",
                "status": "completed",
                "completedEligible": True,
                "sourceName": "录像",
                "durationUs": 1_000_000,
            }
        ],
    ],
)
def test_empty_project_shows_first_run_guide(tmp_path, recordings):
    playwright = pytest.importorskip("playwright.sync_api")
    server = create_server("127.0.0.1", 0, tmp_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    posts = []

    def answer(route):
        path = urlsplit(route.request.url).path
        if route.request.method == "POST":
            posts.append(path)
        if path == "/api/projects":
            route.fulfill(json={"projects": [{"path": "p", "name": "p"}]})
        elif path == "/api/runs":
            route.fulfill(json={"runs": recordings})
        elif path == "/api/creation/jobs":
            route.fulfill(json={"jobs": []})
        else:
            route.continue_()

    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/api/**", answer)
            page.route(
                "**/api/inspect?*",
                lambda route: route.fulfill(
                    json={"runId": "r", "timeline": [], "evidence": [], "media": {"durationUs": 1}}
                ),
            )
            page.goto(f"http://127.0.0.1:{server.server_port}/studio")
            guide = page.get_by_role("note", name="第一次使用")
            if recordings:
                playwright.expect(page.get_by_text("原始录像（1 个文件）")).to_be_visible()
                playwright.expect(guide).to_have_count(0)
            else:
                playwright.expect(guide).to_be_visible()
                playwright.expect(guide.get_by_role("link", name="素材工作台")).to_have_attribute(
                    "href", "/"
                )
            assert not posts  # the guide never sends anything
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
