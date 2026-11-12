"""AI brief form: real HTTP budget/send/result with a fake model, no footage or paid calls."""

import threading
from types import SimpleNamespace

import pytest
from test_brief_reasoning import GAMES, SENTENCE, answer
from test_creation_reasoning_service import Transport

from gamingcreator.application.brief_reasoning import brief_snapshot
from gamingcreator.ui import server as implementation
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService


@pytest.fixture
def brief_ui(tmp_path, monkeypatch):
    pw = pytest.importorskip("playwright.sync_api")
    transport = Transport(answer(brief_snapshot(SENTENCE, GAMES)))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-never-sent")
    monkeypatch.setattr(
        implementation,
        "CreationReasoningService",
        lambda jobs, **kw: CreationReasoningService(jobs, transport=transport, **kw),
    )
    server = implementation.create_server("127.0.0.1", 0, CreationJobs(tmp_path).repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.route(
                "**/brief-test",
                lambda route: route.fulfill(
                    body="<html><body></body></html>", content_type="text/html"
                ),
            )
            page.goto(f"http://127.0.0.1:{server.server_port}/brief-test")
            page.evaluate("""async () => {
                const {h, render} = await import('/assets/vendor/preact.module.js');
                const {BriefSentence} = await import('/assets/studio/brief_sentence.js');
                render(null, document.body);
                const root = document.createElement('div'); document.body.append(root);
                window.patches = [];
                window.mountBrief = (project = '') => {
                    render(null, root);
                    render(h(BriefSentence, {project, draft: {}, runs: [{sourceName: '漫画群星：大集结.mp4'}, {sourceName: '其他游戏.mp4'}],
                        update: patch => window.patches.push(patch)}), root);
                };
                window.mountBrief();
            }""")
            pw.expect(page.get_by_text("预算内自动调用", exact=False)).to_be_visible()
            yield SimpleNamespace(page=page, transport=transport, expect=pw.expect)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_ai_brief_applies_only_on_click(brief_ui):
    page, expect = brief_ui.page, brief_ui.expect
    page.get_by_label("一句话需求", exact=True).fill(SENTENCE)
    page.get_by_role("button", name="解析", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("AI 理解")
    assert page.evaluate("window.patches") == []
    page.get_by_role("button", name="填入需求").click()
    patch = page.evaluate("window.patches[0]")
    assert patch["contentType"] == "feature_showcase"
    assert "技能解说" in patch["mandatoryTopics"]
    assert len(brief_ui.transport.calls) == 1


@pytest.mark.parametrize("failure", ["network", "http400"])
def test_lost_reply_recovers_without_resending(brief_ui, failure):
    page, expect = brief_ui.page, brief_ui.expect

    def lose_reply(route):
        if route.request.post_data_json["action"] == "execute_budget":
            route.fetch()
            if failure == "network":
                route.abort("failed")
            else:
                route.fulfill(status=400, json={"error": "result write failed"})
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", lose_reply)
    page.get_by_label("一句话需求", exact=True).fill(SENTENCE)
    page.get_by_role("button", name="解析", exact=True).click()
    recover = page.get_by_role("button", name="读取本次 AI 结果（不重新调用）")
    expect(recover).to_be_enabled()
    expect(page.get_by_role("button", name="解析", exact=True)).to_be_disabled()
    # Switching projects unmounts the component; only the original project gets its recovery.
    page.evaluate("window.mountBrief('other')")
    expect(recover).to_have_count(0)
    expect(page.get_by_label("一句话需求", exact=True)).to_have_value("")
    page.evaluate("window.mountBrief()")
    expect(recover).to_be_enabled()
    recover.click()
    expect(page.get_by_role("status")).to_contain_text("AI 理解")
    assert len(brief_ui.transport.calls) == 1


def test_budget_refusal_uses_labelled_local_rules(brief_ui, monkeypatch):
    from decimal import Decimal

    from gamingcreator.application import ai_budget

    monkeypatch.setattr(ai_budget, "MONTHLY_CAP_CNY", Decimal(0))
    page, expect = brief_ui.page, brief_ui.expect
    page.get_by_label("一句话需求", exact=True).fill(SENTENCE)
    page.get_by_role("button", name="解析", exact=True).click()
    expect(page.get_by_role("status")).to_contain_text("本机规则版")
    assert not brief_ui.transport.calls


def test_pre_send_refusal_can_continue_locally_without_losing_recovery(brief_ui):
    page, expect = brief_ui.page, brief_ui.expect

    def refuse(route):
        if route.request.post_data_json["action"] == "execute_budget":
            route.fulfill(status=400, json={"error": "budget exhausted"})
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", refuse)
    page.get_by_label("一句话需求", exact=True).fill(SENTENCE)
    page.get_by_role("button", name="解析", exact=True).click()
    page.get_by_role("button", name="继续本机规则（保留 AI 记录）").click()
    page.get_by_label("一句话需求", exact=True).fill("30秒高光，发抖音")
    page.get_by_role("button", name="解析", exact=True).click()
    expect(page.get_by_role("status", name="一句话需求状态")).to_contain_text("本机规则版")
    expect(page.get_by_role("button", name="读取本次 AI 结果（不重新调用）")).to_be_enabled()
    assert not brief_ui.transport.calls
