"""A04: pointerup must not write a stale narration selection or asset."""
# ruff: noqa: F811

from __future__ import annotations

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def narration_start_frame(page):
    return page.evaluate(
        """() => {
            const scroll = document.querySelector(".track-scroll");
            const bar = document.querySelector('[data-track="voice"] .bar');
            if (!scroll || !bar) return null;
            const scale = Number(scroll.dataset.scale);
            const fps = Number(scroll.dataset.fps);
            if (!scale || !fps) return null;
            return Math.round((parseFloat(bar.style.left) / scale) * fps / 1e6);
        }"""
    )


def _drag_interrupt(page, interrupt):
    start = page.get_by_role("slider", name="旁白起点")
    start.scroll_into_view_if_needed()
    box = start.bounding_box()
    assert box and box["width"] > 4
    mid_y = box["y"] + box["height"] / 2
    origin = start.get_attribute("aria-valuenow")
    page.mouse.move(box["x"] + 2, mid_y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] + 120, mid_y, steps=12)
    moved = start.get_attribute("aria-valuenow")
    assert moved not in (None, origin), moved
    interrupt()
    page.mouse.up()
    return moved


def test_pointerup_after_mid_drag_edits_does_not_write_stale_state(studio_audio):
    page = studio_audio
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")

    # First commit a start-frame change so Ctrl+Z has a real previous state.
    start.focus()
    page.keyboard.press("ArrowRight")
    expect(start).to_have_attribute("aria-valuenow", "16")

    dragged = _drag_interrupt(page, lambda: page.keyboard.press("Control+z"))
    expect(start).to_have_attribute("aria-valuenow", "15")
    assert start.get_attribute("aria-valuenow") != dragged

    # Volume change mid-drag must keep the new gain and drop the unfinished start.
    page.get_by_role("tab", name="声音", exact=True).click()
    gain = page.get_by_label("旁白音量")
    _drag_interrupt(
        page,
        lambda: gain.evaluate(
            """el => { el.value = '-6'; el.dispatchEvent(new Event('change', {bubbles: true})); }"""
        ),
    )
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(gain).to_have_value("-6")

    # Changing the music track mid-drag must keep the new track and drop the unfinished start.
    music = page.locator("aside[aria-label='检查器'] select").filter(
        has=page.locator("option", has_text="不加配乐")
    )
    expect(music).not_to_have_value("")
    _drag_interrupt(
        page,
        lambda: music.evaluate(
            """el => { el.value = ''; el.dispatchEvent(new Event('change', {bubbles: true})); }"""
        ),
    )
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(music).to_have_value("")
    expect(start).to_have_count(1)

    # Trim mid-drag must keep the new in-point and drop the unfinished start.
    # This fixture's narration is already tight, so a 0.5s trim can make it
    # unfit and remove the slider role; read the start from the bar position.
    page.locator(".insp-tabs").get_by_role("tab", name="镜头", exact=True).click()
    page.locator(".timeline .clip").first.evaluate("el => el.click()")
    inlet = page.get_by_role("spinbutton", name="入点")
    expect(inlet).to_be_visible()
    before = inlet.input_value()
    _drag_interrupt(
        page,
        lambda: inlet.evaluate(
            """el => {
                el.value = String((Number(el.value) + 0.5).toFixed(2));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }"""
        ),
    )
    expect(inlet).not_to_have_value(before)
    assert narration_start_frame(page) == 15
