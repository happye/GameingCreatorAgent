"""Persistent work selection over real local HTTP, with no paid calls."""

import json
from urllib.parse import urljoin

from test_studio_planning_browser import planning, service, studio  # noqa: F401


def new_work(studio):  # noqa: F811
    page = studio.page
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/creation/works") and response.request.method == "POST"
        )
    ) as response:
        page.get_by_role("button", name="新建作品", exact=True).click()
    work_id = response.value.json()["work"]["workId"]
    studio.expect(page.get_by_label("当前作品")).to_have_value(work_id)
    return work_id


def test_work_drafts_are_isolated_and_verified_after_reload(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    first = new_work(studio)
    page.get_by_label("游戏", exact=True).fill("作品A游戏")
    second = new_work(studio)
    assert second != first
    expect(page.get_by_label("游戏", exact=True)).to_have_value("")
    expect(page.locator(".plan")).to_have_count(0)
    page.get_by_label("游戏", exact=True).fill("作品B游戏")
    page.get_by_label("当前作品").select_option(first)
    expect(page.get_by_label("游戏", exact=True)).to_have_value("作品A游戏")
    with page.expect_response(lambda response: f"/api/creation/works/{first}?" in response.url):
        page.reload()
    expect(page.get_by_label("当前作品")).to_have_value(first)
    expect(page.get_by_label("游戏", exact=True)).to_have_value("作品A游戏")
    stored = page.evaluate("JSON.parse(localStorage.getItem('studio-last-job-v1'))")
    assert f"artifacts/project:work:{second}" not in stored


def test_lost_create_response_retries_same_persisted_identity(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    attempts = []

    def transport(route):
        if route.request.method != "POST":
            route.continue_()
            return
        attempts.append(route.request.post_data_json["requestId"])
        response = route.fetch()
        if len(attempts) == 1:
            route.abort("failed")
        else:
            route.fulfill(response=response)

    page.route("**/api/creation/works", transport)
    page.get_by_role("button", name="新建作品", exact=True).click()
    expect(page.get_by_text("可重试新建以恢复本次作品。", exact=False)).to_be_visible()
    page.reload()
    expect(page.get_by_role("button", name="新建作品", exact=True)).to_be_enabled()
    page.get_by_role("button", name="新建作品", exact=True).click()
    expect(page.get_by_label("当前作品")).to_have_value(attempts[0])
    assert attempts == [attempts[0], attempts[0]]
    response = page.request.get(
        urljoin(page.url, "/api/creation/works?projectId=artifacts/project")
    ).json()
    assert [work["workId"] for work in response["works"]] == [attempts[0]]


def test_old_draft_does_not_create_work_and_brief_uses_verified_work(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    assert page.request.get(
        urljoin(page.url, "/api/creation/works?projectId=artifacts/project")
    ).json() == {"works": []}
    expect(page.get_by_label("当前作品")).to_have_value("")
    work_id = new_work(studio)
    # A quote is intercepted before the fake provider: this asserts the boundary payload.
    captured = []

    def reasoning(route):
        body = route.request.post_data_json
        captured.append(body)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"budget": {"eligible": False, "reason": "test"}}),
        )

    page.route("**/api/creation/reasoning", reasoning)
    page.get_by_label("一句话需求", exact=True).fill("做一分钟玩法展示")
    page.get_by_role("button", name="解析", exact=True).click()
    expect(page.get_by_label("一句话需求状态")).to_contain_text("本机规则")
    assert captured[0]["action"] == "prepare_brief"
    assert captured[0]["projectId"] == "artifacts/project"
    assert captured[0]["workId"] == work_id


def test_root_plan_carries_work_and_late_acceptance_cannot_fill_next_work(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    page.route(
        "**/api/runs?*",
        lambda route: route.fulfill(
            json={"runs": [{"id": "run", "sourceName": "测试录像", "completedEligible": True}]}
        ),
    )
    page.reload()
    first = new_work(studio)
    page.get_by_label("游戏", exact=True).fill("A")
    page.get_by_label("测试录像", exact=True).check()
    page.get_by_label("生成后让AI再策划").uncheck()
    pending = []
    page.route("**/api/creation/plans", lambda route: pending.append(route))
    page.get_by_role("button", name="生成方案", exact=True).click()
    expect(page.get_by_role("button", name="正在生成…", exact=True)).to_be_visible()
    # Process the intercepted request before switching, then deliver it after B exists.
    page.wait_for_timeout(50)
    assert pending[0].request.post_data_json["workId"] == first
    second = new_work(studio)
    pending[0].fulfill(json={"jobId": studio.ctx.root})
    expect(page.get_by_label("当前作品")).to_have_value(second)
    expect(page.get_by_label("游戏", exact=True)).to_have_value("")
    expect(page.locator(".plan")).to_have_count(0)
    stored = page.evaluate("JSON.parse(localStorage.getItem('studio-last-job-v1'))")
    assert f"artifacts/project:work:{second}" not in stored


def test_damaged_catalog_does_not_block_verified_current_work(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    work_id = new_work(studio)
    page.get_by_label("游戏", exact=True).fill("保留当前作品")
    (studio.ctx.jobs.root / "works" / ("f" * 32 + ".json")).write_bytes(b"{")
    page.reload()
    expect(page.get_by_label("当前作品")).to_have_value(work_id)
    expect(page.get_by_label("游戏", exact=True)).to_have_value("保留当前作品")
    expect(page.get_by_text("作品列表暂不可读", exact=False)).to_be_visible()


def test_cross_origin_cannot_create_work(studio):  # noqa: F811
    page = studio.page
    response = page.request.post(
        urljoin(page.url, "/api/creation/works"),
        data={"projectId": "artifacts/project", "requestId": "f" * 32},
        headers={"Origin": "https://example.com"},
    )
    assert response.status == 403
    assert not (studio.ctx.jobs.root / "works" / ("f" * 32 + ".json")).exists()


def test_open_intent_is_consumed_when_switching_work_and_tabs(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    page.get_by_role("tab", name="素材", exact=True).click()
    bin_panel = page.get_by_label("素材箱", exact=True)
    bin_panel.locator("details.group").filter(has_text="方案").locator("summary").click()
    bin_panel.locator("button.row").first.click()
    expect(page.get_by_label("当前作品")).to_have_value("")
    work_id = new_work(studio)
    page.get_by_label("游戏", exact=True).fill("往返保留作品")
    page.get_by_role("tab", name="素材", exact=True).click()
    page.get_by_role("tab", name="剪辑", exact=True).click()
    expect(page.get_by_label("当前作品")).to_have_value(work_id)
    expect(page.get_by_label("游戏", exact=True)).to_have_value("往返保留作品")
    # A new navigation intent to that same old job must still work.
    page.get_by_role("tab", name="素材", exact=True).click()
    bin_panel.locator("details.group").filter(has_text="方案").locator("summary").click()
    bin_panel.locator("button.row").first.click()
    expect(page.get_by_label("当前作品")).to_have_value("")


def test_consumed_navigation_does_not_discard_dirty_editor_on_layout_change(studio):  # noqa: F811
    from test_studio_caption_editor_browser import select_shot

    page, expect = studio.page, studio.expect
    page.get_by_role("tab", name="素材", exact=True).click()
    bin_panel = page.get_by_label("素材箱", exact=True)
    bin_panel.locator("details.group").filter(has_text="方案").locator("summary").click()
    with page.expect_response(lambda response: response.url.split("?")[0].endswith("/edit")):
        bin_panel.locator("button.row").first.click()
    expect(page.get_by_text("方案原样", exact=True)).to_be_visible()
    select_shot(page)
    page.get_by_label("速度").select_option("2/1")
    expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
    page.get_by_role("button", name="检查器", exact=True).click()
    page.get_by_role("button", name="检查器", exact=True).click()
    expect(page.get_by_label("速度")).to_have_value("2/1")
    expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
