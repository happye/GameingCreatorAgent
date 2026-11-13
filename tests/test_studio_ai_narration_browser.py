"""AI preview uses real Studio HTTP and fake paid transport; never a real model."""

import json
from decimal import Decimal

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_reasoning_service import Transport
from test_narration_jobs import engine  # noqa: F401
from test_studio_narration_tools_browser import studio_plan  # noqa: F401

from gamingcreator.application import ai_budget
from gamingcreator.ui import server
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService


class NarrationTransport(Transport):
    async def post(self, payload, timeout_seconds):
        frozen = json.loads(payload["messages"][-1]["content"])
        clip = next(c for c in frozen["snapshot"]["clips"] if c["scriptDraft"].strip())
        self.content = {
            "schemaVersion": "narration-understanding-v1",
            "snapshotFingerprint": frozen["snapshotFingerprint"],
            "lines": [
                {
                    "clipId": clip["clipId"],
                    "text": "一起出发。",
                    "observationQuote": clip["scriptDraft"][:20],
                    "knowledgeUses": [],
                }
            ],
        }
        return await super().post(payload, timeout_seconds)


@pytest.fixture
def ai_setup(monkeypatch):
    transport = NarrationTransport({})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-never-sent")
    monkeypatch.setattr(
        server,
        "CreationReasoningService",
        lambda jobs, **kw: CreationReasoningService(jobs, transport=transport, **kw),
    )
    return transport


@pytest.fixture
def ai_studio(ai_setup, studio_plan):  # noqa: F811
    return studio_plan, ai_setup


def test_ai_preview_adopt_then_local_voice(ai_studio):
    studio, transport = ai_studio
    page, expect = studio.page, studio.expect
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    expect(page.get_by_role("button", name="填入旁白稿", exact=True)).to_be_visible()
    expect(page.get_by_role("textbox", name="旁白稿", exact=True)).to_have_count(0)
    page.get_by_role("button", name="填入旁白稿", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白稿", exact=True)).to_have_value("一起出发。")
    page.get_by_role("button", name="合成旁白", exact=True).click()
    expect(page.get_by_role("button", name="编辑旁白文字", exact=True)).to_be_visible(timeout=30000)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("failure", ["lost", "400"])
def test_send_error_recovers_read_only(ai_studio, failure):
    studio, transport = ai_studio
    page, expect = studio.page, studio.expect

    def lose(route):
        body = route.request.post_data_json
        if body.get("action") != "execute_budget":
            return route.continue_()
        route.fetch()
        if failure == "lost":
            route.abort()
        else:
            route.fulfill(status=400, json={"error": "response lost after send"})

    page.route("**/api/creation/reasoning", lose)
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    recover = page.get_by_role("button", name="读取上次 AI 旁白结果（不重新调用）")
    expect(recover).to_be_enabled()
    recover.click()
    expect(page.get_by_role("button", name="填入旁白稿", exact=True)).to_be_visible()
    assert len(transport.calls) == 1


def test_user_edit_invalidates_preview(ai_studio):
    studio, _ = ai_studio
    page, expect = studio.page, studio.expect
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    expect(page.get_by_role("button", name="填入旁白稿", exact=True)).to_be_visible()
    page.get_by_role("button", name="手写旁白稿", exact=True).click()
    page.get_by_role("textbox", name="旁白稿", exact=True).fill("我的新文字")
    expect(page.get_by_role("button", name="填入旁白稿", exact=True)).to_have_count(0)
    expect(page.get_by_role("textbox", name="旁白稿", exact=True)).to_have_value("我的新文字")


@pytest.mark.parametrize("unavailable", [True, False])
def test_unconfigured_or_over_budget_uses_template(ai_studio, monkeypatch, unavailable):
    studio, transport = ai_studio
    page, expect = studio.page, studio.expect
    if unavailable:
        monkeypatch.delenv("DEEPSEEK_API_KEY")
    else:
        monkeypatch.setattr(ai_budget, "MONTHLY_CAP_CNY", Decimal(0))
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    if not unavailable:
        page.get_by_role("button", name="使用规则模板旁白", exact=True).click()
    expect(page.get_by_role("textbox", name="旁白稿", exact=True)).to_be_visible()
    assert not transport.calls


def test_switch_plan_discards_old_ai_preview(ai_studio):
    studio, transport = ai_studio
    page, expect = studio.page, studio.expect
    page.get_by_role("button", name="起草旁白稿", exact=True).click()
    expect(page.get_by_role("button", name="填入旁白稿", exact=True)).to_be_visible()
    other = page.locator('.plan:not([aria-current="true"])').first
    expect(other).to_be_visible()
    other.click()
    expect(page.get_by_role("button", name="填入旁白稿", exact=True)).to_have_count(0)
    expect(page.get_by_role("textbox", name="旁白稿", exact=True)).to_have_count(0)
    assert len(transport.calls) == 1
