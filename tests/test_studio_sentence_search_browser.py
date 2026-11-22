"""The Studio preserves ranked slots and only offers actions for verified clips."""

import pytest
from test_detail_inspection import refuse_sends
from test_inspection_http import workspace
from test_preview_clock_align_browser import seed_playable_project

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser


def test_studio_sentence_search_keeps_unavailable_ranked_slots(tmp_path, monkeypatch):
    refuse_sends(monkeypatch)
    project, bundle, timeline = seed_playable_project(tmp_path)
    reference = project.relative_to(tmp_path).as_posix()
    source = {
        "runId": "run-1",
        "mediaId": bundle.asset.media_id,
        "sourceSha256": bundle.asset.sha256,
        "sourceName": bundle.asset.source_path.name,
    }
    event = timeline.events[0]
    first = {
        **source,
        "rank": 1,
        "candidateId": "verified",
        "eventId": event.event_id,
        "startUs": event.source_range.start_us,
        "endUs": event.source_range.end_us,
    }
    transcript = {
        **first,
        "rank": 2,
        "candidateId": "transcript",
        "eventId": None,
        "startUs": 100_000,
        "endUs": 1_200_000,
        "displayFacts": ["语音：准备进入下一场。"],
    }
    mismatched = {
        **first,
        "rank": 3,
        "candidateId": "mismatched",
        "eventId": "unverified-event",
    }
    posts = []

    def respond(route):
        request = route.request.post_data_json
        posts.append(request)
        route.fulfill(
            json={
                "schemaVersion": "project-search-v1",
                "project": reference,
                "query": request["query"],
                "mode": "hybrid",
                "topK": 10,
                "sources": [{**source, "durationUs": bundle.asset.duration_us}],
                "candidates": [first, transcript, mismatched],
            }
        )

    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            page.route("**/api/search-project", respond)
            page.goto(f"{base}/studio")
            search = page.locator(".clip-search")
            query = search.get_by_role("searchbox")
            query.fill("白色头发")
            playwright.expect(search.locator(".hit-main")).to_have_count(1)
            assert posts == []

            search.get_by_label("搜索方式").select_option("sentence")
            query.fill("想看白发角色")
            search.get_by_role("button", name="一句话搜索", exact=True).click()
            playwright.expect(search.locator(".hit")).to_have_count(3)
            assert posts == [
                {
                    "project": reference,
                    "runs": ["run-1"],
                    "query": "想看白发角色",
                    "mode": "hybrid",
                    "top": 10,
                }
            ]
            verified = search.locator('[data-rank="1"]')
            playwright.expect(verified).to_have_attribute("data-event-id", event.event_id)
            voice = search.locator('[data-rank="2"]')
            playwright.expect(voice).to_contain_text("仅命中语音转录")
            playwright.expect(voice).to_contain_text("语音：准备进入下一场。")
            playwright.expect(voice.get_by_role("button", name="加入片段篮")).to_have_count(0)
            unavailable = search.locator('[data-rank="3"]')
            playwright.expect(unavailable).to_contain_text("无法核对这段画面的时间线")
            playwright.expect(unavailable.get_by_role("button")).to_have_count(0)
            verified.get_by_role("button", name="加入片段篮").click()
            playwright.expect(page.locator(".basket .hit")).to_have_count(1)
            voice.get_by_role("button", name="回看语音转录片段").click()
            viewer = page.get_by_label("预览窗")
            playwright.expect(viewer).to_contain_text("仅播放语音转录片段")
            inspector = page.get_by_label("检查器", exact=True).filter(
                has=page.locator(".panel-body")
            )
            playwright.expect(inspector.get_by_role("button", name="加入片段篮")).to_have_count(0)
            page.keyboard.press("b")
            playwright.expect(page.locator(".basket .hit")).to_have_count(1)
            query.fill("另一个查询")
            playwright.expect(search.locator(".hit")).to_have_count(0)
            assert len(posts) == 1
        finally:
            browser.close()
