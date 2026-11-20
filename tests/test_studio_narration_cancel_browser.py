"""A08: cancel, lost capture, Escape, and project switch must not keep a narration drag alive."""
# ruff: noqa: F811

from __future__ import annotations

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def _begin_drag(page, start, *, dx=-80):
    start.scroll_into_view_if_needed()
    handle = start.bounding_box()
    assert handle and handle["width"] > 4
    mid_y = handle["y"] + handle["height"] / 2
    mid_x = handle["x"] + handle["width"] / 2
    page.mouse.move(mid_x, mid_y)
    page.mouse.down()
    page.mouse.move(mid_x + dx, mid_y, steps=20)
    expect(start).not_to_have_attribute("aria-valuenow", "15", timeout=5000)
    return mid_x, mid_y


def _assert_cancelled(page, start, dirty_before, mid_x, mid_y):
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)
    # Further movement or a late mouseup must not revive the cancelled gesture.
    page.mouse.move(mid_x - 160, mid_y, steps=10)
    expect(start).to_have_attribute("aria-valuenow", "15")
    page.mouse.up()
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)


def _dispatch(page, name):
    page.locator(".bar.movable[aria-label='旁白起点']").evaluate(
        """(el, name) => {
            el.dispatchEvent(new PointerEvent(name, {bubbles: true, cancelable: true, pointerId: 1}));
        }""",
        name,
    )


def test_narration_cancel_lost_capture_escape_and_project_switch(studio_audio):
    page = studio_audio
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")
    dirty_before = page.get_by_role("status", name="版本保存状态").inner_text()
    expect(page.get_by_label("项目", exact=True)).to_have_value("artifacts/project")

    mid_x, mid_y = _begin_drag(page, start)
    page.keyboard.press("Escape")
    _assert_cancelled(page, start, dirty_before, mid_x, mid_y)

    mid_x, mid_y = _begin_drag(page, start)
    _dispatch(page, "pointercancel")
    _assert_cancelled(page, start, dirty_before, mid_x, mid_y)

    mid_x, mid_y = _begin_drag(page, start)
    _dispatch(page, "lostpointercapture")
    _assert_cancelled(page, start, dirty_before, mid_x, mid_y)

    mid_x, mid_y = _begin_drag(page, start)
    page.get_by_label("项目", exact=True).select_option("artifacts/other")
    expect(page.get_by_label("项目", exact=True)).to_have_value("artifacts/other")
    expect(page.locator(".timeline .clip")).to_have_count(0)
    page.mouse.move(mid_x - 160, mid_y, steps=10)
    page.mouse.up()
    page.get_by_label("项目", exact=True).select_option("artifacts/project")
    expect(page.get_by_label("项目", exact=True)).to_have_value("artifacts/project")
    expect(page.locator(".timeline .clip")).to_have_count(2)
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)
