"""Studio reasoning uses real HTTP/chain/proposals and an explicitly fake model transport."""

import json
import threading
from types import SimpleNamespace

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_proposals import output
from test_creation_reasoning_service import Transport
from test_creation_revision_jobs import revisions  # noqa: F401

from gamingcreator.application.creation_proposals import create_snapshot
from gamingcreator.ui import server as implementation
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.revision_jobs import load_chain


@pytest.fixture
def studio(revisions, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    jobs, root, _ = revisions
    chain = load_chain(jobs, root, "hook-first")
    snapshot = create_snapshot(root, chain.plan_id, chain.digest, chain.root_sha, chain.edl)
    response = output(snapshot)
    response["clips"] = response["clips"][:-1]
    transport = Transport(response)

    def factory(created_jobs, **kwargs):
        return CreationReasoningService(created_jobs, transport=transport, **kwargs)

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(implementation, "CreationReasoningService", factory)
    monkeypatch.setattr(implementation, "project_runs_payload", runs)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-never-sent")
    server = implementation.create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": root, "kind": "plan"}})
            page.add_init_script(
                "if (!sessionStorage.seeded) { sessionStorage.seeded=1;"
                f"localStorage.setItem('studio-v1', {prefs!r});"
                f"localStorage.setItem('studio-last-job-v1', {last!r}); }}"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.goto(f"http://127.0.0.1:{server.server_port}/studio")
            pw.expect(page.get_by_text("方案原样", exact=True)).to_be_visible()
            page.locator(".plan").filter(has_text="最后一条先作开场").click()
            pw.expect(page.locator(".plan").filter(has_text="最后一条先作开场")).to_have_attribute(
                "aria-current", "true"
            )
            yield SimpleNamespace(page=page, transport=transport, errors=errors)
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def prepare(studio):
    page = studio.page
    page.get_by_label("创作助手模式").select_option("ai")
    page.get_by_label("创作对话需求").fill("第二个镜头节奏太急，最后一个镜头可以去掉")
    page.get_by_role("button", name="准备请求（不发送）").click()
    pytest.importorskip("playwright.sync_api").expect(
        page.get_by_text("查看将发送的文字")
    ).to_be_visible()


def confirm(studio):
    studio.page.get_by_label("同意本次文字发送和费用上限").check()
    studio.page.get_by_role("button", name="确认本次调用", exact=False).click()


def test_explicit_confirmation_preview_validate_apply_save_and_reopen(studio):
    page = studio.page
    expect = pytest.importorskip("playwright.sync_api").expect
    expect(page.get_by_label("创作助手模式")).to_have_value("local")
    assert not studio.transport.calls
    prepare(studio)
    assert not studio.transport.calls
    expect(page.get_by_role("button", name="确认本次调用", exact=False)).to_be_disabled()
    page.get_by_text("查看将发送的文字").click()
    expect(page.locator(".reasoning pre")).to_contain_text("第二个镜头节奏太急")
    confirm(studio)
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
    expect(page.get_by_label("本次文本模型费用")).to_contain_text("实际费用未知")
    expect(page.get_by_text("方案原样", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="保存版本")).to_be_disabled()
    page.get_by_role("button", name="应用AI建议").click()
    expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
    page.get_by_role("button", name="保存版本").click()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    page.reload()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    assert len(studio.transport.calls) == 1
    assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")


def test_clarification_changes_nothing_and_dirty_state_blocks_model(studio):
    page = studio.page
    expect = pytest.importorskip("playwright.sync_api").expect
    studio.transport.content.update(
        kind="clarification", clips=[], questions=["你想放慢第二段，还是增加标志停留？"]
    )
    prepare(studio)
    confirm(studio)
    expect(page.get_by_text("你想放慢第二段，还是增加标志停留？", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="应用AI建议")).to_have_count(0)
    expect(page.get_by_text("方案原样", exact=True)).to_be_visible()
    page.locator(".timeline .clip").first.click()
    page.get_by_label("速度").select_option("2/1")
    expect(page.get_by_role("button", name="准备请求（不发送）")).to_be_disabled()
    assert len(studio.transport.calls) == 1


def test_delayed_prepare_is_discarded_after_mode_roundtrip(studio):
    page = studio.page
    expect = pytest.importorskip("playwright.sync_api").expect
    held = []

    def hold(route):
        if route.request.post_data_json["action"] == "prepare":
            held.append(route)
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", hold)
    page.get_by_label("创作助手模式").select_option("ai")
    page.get_by_label("创作对话需求").fill("改节奏")
    with page.expect_request("**/api/creation/reasoning"):
        page.get_by_role("button", name="准备请求（不发送）").click()
    page.get_by_label("创作助手模式").select_option("local")
    page.get_by_label("创作助手模式").select_option("ai")
    held[0].fulfill(
        json={"preparedHash": "a" * 64, "snapshotFingerprint": "b" * 64, "maxCostCny": "2"}
    )
    expect(page.get_by_role("button", name="确认本次调用", exact=False)).to_have_count(0)
    assert not studio.transport.calls


@pytest.mark.parametrize("reload_editor", [False, True])
def test_lost_execute_response_is_recovered_without_another_model_call(studio, reload_editor):
    page = studio.page
    expect = pytest.importorskip("playwright.sync_api").expect

    def lose_response(route):
        if route.request.post_data_json["action"] == "execute":
            route.fetch()
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", lose_response)
    prepare(studio)
    confirm(studio)
    expect(page.get_by_role("button", name="读取本次结果（不重新调用）")).to_be_enabled()
    if reload_editor:
        page.reload()
    else:
        page.get_by_label("创作助手模式").select_option("local")
    page.get_by_label("创作助手模式").select_option("ai")
    expect(page.get_by_role("button", name="应用AI建议")).to_have_count(0)
    page.locator(".reasoning-history summary").click()
    page.get_by_role("button", name="读取已确认结果（不调用模型）").click()
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
    assert len(studio.transport.calls) == 1


def test_paid_result_survives_dirty_changes_but_requires_clean_saved_parent(studio):
    page = studio.page
    expect = pytest.importorskip("playwright.sync_api").expect
    prepare(studio)
    confirm(studio)
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
    page.get_by_role("tab", name="声音", exact=True).click()
    page.get_by_label("原声音量").select_option("-6")
    expect(page.get_by_role("button", name="应用AI建议")).to_have_count(0)
    page.locator(".reasoning-history summary").click()
    expect(page.get_by_role("button", name="读取已确认结果（不调用模型）")).to_be_disabled()
    page.get_by_role("button", name="撤销修改").click()
    page.get_by_role("button", name="读取已确认结果（不调用模型）").click()
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
    assert len(studio.transport.calls) == 1


def test_failed_history_restore_cannot_apply_another_attempt(studio):
    page = studio.page
    expect = pytest.importorskip("playwright.sync_api").expect
    prepare(studio)
    confirm(studio)
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
    prepare(studio)
    studio.transport.content["clips"][0]["speed"] = {"numerator": 2, "denominator": 1}
    confirm(studio)
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
    page.locator(".reasoning-history summary").click()
    buttons = page.get_by_role("button", name="读取已确认结果（不调用模型）")
    buttons.nth(1).click()
    expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()

    def fail_result(route):
        if route.request.post_data_json["action"] == "result":
            route.fulfill(status=503, json={"message": "结果暂时不可读"})
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", fail_result)
    buttons.first.click()
    expect(page.get_by_text("结果暂时不可读", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="应用AI建议")).to_have_count(0)
    expect(page.locator(".timeline .clip")).to_have_count(3)
    assert len(studio.transport.calls) == 2
