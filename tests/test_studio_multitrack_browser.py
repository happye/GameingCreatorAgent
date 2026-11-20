"""G01–G14: multi-track editor closed loop on isolated local media."""
# ruff: noqa: F811

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
FFPROBE = ROOT / ".tools/ffmpeg/bin/ffprobe.exe"

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def _ffprobe(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-show_entries",
            "format=format_name:stream=codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        timeout=20,
    )
    return json.loads(raw)


def _select_shot(page):
    field = page.get_by_label("镜头字幕", exact=True)
    for _ in range(20):
        page.locator(".timeline .clip").first.click(position={"x": 10, "y": 10})
        try:
            field.wait_for(state="visible", timeout=500)
            break
        except Exception:  # noqa: BLE001 - editor still loading; retry the click
            continue
    return field


def test_multitrack_zoom_narration_undo_save_and_ffmpeg(studio_audio, tmp_path):
    page = studio_audio
    # G01 / G03: fixed Chinese lane names; revision clips stay visible.
    for name in ("画面", "原声", "旁白", "配乐", "字幕"):
        expect(page.locator(".track-name", has_text=name)).to_be_visible()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    # G06: default "no subtitles" reuses the existing empty cue list; no extra ASR.
    # The inspector "字幕预览状态" lives on the 导出 tab; the track itself is visible here.
    expect(page.locator(".caption-lane .lane-empty")).to_contain_text("不加字幕")

    dirty_before = page.get_by_role("status", name="版本保存状态").inner_text()
    area = page.locator(".track-area")
    fit_width = area.evaluate("el => el.scrollWidth")
    page.get_by_role("button", name="8倍", exact=True).click()
    expect(page.get_by_role("button", name="8倍", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    page.wait_for_function("el => el.scrollWidth > el.clientWidth * 2", arg=area.element_handle())
    # G02: 8x can scroll to the last frame; fit restores the view without dirtying.
    page.evaluate("el => { el.scrollLeft = el.scrollWidth; }", area.element_handle())
    assert area.evaluate("el => el.scrollLeft + el.clientWidth >= el.scrollWidth - 2")
    page.get_by_role("button", name="适应窗口", exact=True).click()
    expect(page.get_by_role("button", name="适应窗口", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    page.wait_for_function(
        "([el, before]) => Math.abs(el.scrollWidth - before) < 8",
        arg=[area.element_handle(), fit_width],
    )
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)

    # G05: clicking the output ruler seeks without saving or moving narration.
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")
    ruler = page.get_by_label("输出时间刻度")
    box = ruler.bounding_box()
    assert box and box["width"] > 20
    page.mouse.click(box["x"] + box["width"] * 0.7, box["y"] + box["height"] / 2)
    lefts = page.locator(".playhead").evaluate_all("els => els.map(el => el.style.left)")
    assert lefts and all(item == lefts[0] for item in lefts)
    assert lefts[0] not in ("", "0px")
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)

    # G12: Escape cancels an in-progress drag and does not push undo.
    # Drag earlier: this 3s cut only has a few frames of room to the right of start 15.
    # Scroll first so the bar is not under the assistant dock (raw mouse coords skip actionability).
    start.scroll_into_view_if_needed()
    handle = start.bounding_box()
    assert handle and handle["width"] > 4
    mid_y = handle["y"] + handle["height"] / 2
    mid_x = handle["x"] + handle["width"] / 2
    page.mouse.move(mid_x, mid_y)
    page.mouse.down()
    page.mouse.move(mid_x - 160, mid_y, steps=20)
    expect(start).not_to_have_attribute("aria-valuenow", "15", timeout=5000)
    page.keyboard.press("Escape")
    page.mouse.up()
    expect(start).to_have_attribute("aria-valuenow", "15")
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)

    # G11: move earlier so a long stand-in cannot overflow the tail.
    start.focus()
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("Shift+ArrowLeft")
    expect(start).to_have_attribute("aria-valuenow", "4")
    page.get_by_role("button", name="撤销一步").click()
    expect(start).to_have_attribute("aria-valuenow", "14")
    page.get_by_role("button", name="撤销一步").click()
    expect(start).to_have_attribute("aria-valuenow", "15")
    page.get_by_role("button", name="重做").click()
    expect(start).to_have_attribute("aria-valuenow", "14")
    start.focus()
    page.keyboard.press("ArrowLeft")
    expect(start).to_have_attribute("aria-valuenow", "13")

    # G06 / G07: sidecar mode shows existing preview cues; a cue click opens the editor.
    export_tab = page.locator(".insp-tabs").get_by_role("tab", name="导出", exact=True)
    export_tab.click()
    expect(export_tab).to_have_attribute("aria-selected", "true")
    page.locator("label.form-row").filter(has=page.locator("option[value='sidecar']")).locator(
        "select"
    ).select_option("sidecar")
    field = _select_shot(page)
    field.fill("第一镜字幕预览")
    expect(page.locator(".caption-block")).to_contain_text("第一镜字幕预览", timeout=10000)
    page.locator(".caption-block").first.click()
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("第一镜字幕预览")

    with page.expect_request(
        lambda r: r.method == "POST" and r.url.endswith("/api/creation/revisions")
    ) as submitted:
        page.get_by_role("button", name="保存版本", exact=True).click()
    body = json.loads(submitted.value.post_data)
    assert body["narration"]["startFrame"] == 13
    assert body["narration"]["gainDb"] == -60
    expect(page.get_by_role("status", name="版本保存状态")).to_contain_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=30000
    )
    expect(start).to_have_attribute("aria-valuenow", "13")

    page.reload()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(page.get_by_role("slider", name="旁白起点")).to_have_attribute("aria-valuenow", "13")

    with page.expect_download(timeout=120000) as pending:
        page.get_by_role("button", name="导出成片", exact=True).click()
        expect(page.locator("a[download]")).to_be_visible(timeout=120000)
        page.locator("a[download]").click()
    download = pending.value
    assert download.suggested_filename.endswith(".mp4")
    dest = tmp_path / download.suggested_filename
    download.save_as(dest)
    probe = _ffprobe(dest)
    types = {stream.get("codec_type") for stream in probe.get("streams", [])}
    assert "video" in types
    assert "mp4" in (probe.get("format") or {}).get("format_name", "")


def _screen_x(rect, *, center=False):
    left = rect["x"] if "x" in rect else rect["left"]
    width = rect.get("width", 0)
    return left + width / 2 if center else left


def test_multitrack_same_output_frame_uses_screen_x(studio_audio):
    """A01: one output frame shares one screen X across ruler and all lanes.

    Compares getBoundingClientRect, not style.left. The previous check could
    pass while the ruler and playheads were still offset by the name gutter.
    """
    page = studio_audio
    for name in ("画面", "原声", "旁白", "配乐", "字幕"):
        expect(page.locator(".track-name", has_text=name)).to_be_visible()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    page.locator(".timeline .clip").first.wait_for(state="visible")
    page.locator(".track-area .playhead").first.wait_for(state="visible")

    layout = page.evaluate(
        """() => {
            const tracks = ["ruler", "picture", "source", "voice", "music", "caption"];
            const playheads = {};
            for (const name of tracks) {
                const el = document.querySelector(`[data-track="${name}"] .playhead`);
                if (!el) return {missing: name};
                const box = el.getBoundingClientRect();
                playheads[name] = {left: box.left, styleLeft: el.style.left};
            }
            const clip = document.querySelector("[data-track='picture'] .clip");
            const wave = document.querySelector("[data-track='source'] canvas.wave");
            const mark = [...document.querySelectorAll(".ruler span")].find((el) => el.textContent === "00:00");
            const clipBox = clip.getBoundingClientRect();
            const waveBox = wave ? wave.getBoundingClientRect() : null;
            const markBox = mark ? mark.getBoundingClientRect() : null;
            const pictureHead = playheads.picture;
            const styleDelta = parseFloat(clip.style.left) - parseFloat(pictureHead.styleLeft);
            const origin = pictureHead.left - parseFloat(pictureHead.styleLeft);
            const gutter = document.querySelector("[data-track='picture'] .track-name").getBoundingClientRect().width;
            return {
                playheads,
                clipLeft: clipBox.left,
                waveLeft: waveBox ? waveBox.left : null,
                markCenter: markBox ? markBox.left + markBox.width / 2 : null,
                expectedClipLeft: pictureHead.left + styleDelta,
                timeZeroX: origin,
                gutter,
            };
        }"""
    )
    assert "missing" not in layout, f"缺少播放指针: {layout}"
    lefts = [
        layout["playheads"][name]["left"]
        for name in ("ruler", "picture", "source", "voice", "music", "caption")
    ]
    assert max(lefts) - min(lefts) <= 1, f"同一输出帧的屏幕横坐标不一致: {layout['playheads']}"
    assert abs(layout["clipLeft"] - layout["expectedClipLeft"]) <= 1
    if layout["waveLeft"] is not None:
        assert abs(layout["waveLeft"] - layout["clipLeft"]) <= 1
    assert layout["markCenter"] is not None
    assert abs(layout["markCenter"] - layout["timeZeroX"]) <= 1
    # The name column is still there; alignment must hold despite it, not by ignoring it.
    assert layout["gutter"] >= 30


def test_multitrack_zoom_scroll_click_seeks_within_one_frame(studio_audio):
    """A02: fit/2x/4x/8x clicks on the real content position seek within one output frame."""
    page = studio_audio
    expect(page.locator(".timeline .clip")).to_have_count(2)
    page.locator(".ruler").wait_for(state="visible")
    dirty_before = page.get_by_role("status", name="版本保存状态").inner_text()
    narration_before = page.get_by_role("slider", name="旁白起点").get_attribute("aria-valuenow")

    def layout():
        info = page.evaluate(
            """() => {
                const scroll = document.querySelector(".track-scroll");
                const area = document.querySelector(".track-area");
                const ruler = document.querySelector(".ruler");
                if (!scroll || !area || !ruler) return {error: "missing"};
                const box = ruler.getBoundingClientRect();
                const areaBox = area.getBoundingClientRect();
                return {
                    scale: Number(scroll.dataset.scale),
                    totalUs: Number(scroll.dataset.totalUs),
                    fps: Number(scroll.dataset.fps),
                    ruler: {left: box.left, top: box.top, width: box.width, height: box.height, right: box.right},
                    area: {left: areaBox.left, right: areaBox.right, top: areaBox.top, bottom: areaBox.bottom,
                           scrollLeft: area.scrollLeft, clientWidth: area.clientWidth, scrollWidth: area.scrollWidth},
                };
            }"""
        )
        assert info.get("scale") and info.get("totalUs") and info.get("fps"), info
        return info

    def clamp_out(us, total_us, fps):
        step = 1_000_000 / fps
        snapped = round(us / step) * step
        return max(0, min(max(0, total_us - 1), snapped))

    def seek_and_read(target_us):
        info = layout()
        scale, total_us, fps = info["scale"], info["totalUs"], info["fps"]
        # Scroll so the target sits in the visible ruler, then click that actual screen point.
        page.evaluate(
            """([targetUs, scale]) => {
                const area = document.querySelector(".track-area");
                const gutter = 36;
                const targetOffset = gutter + targetUs * scale;
                const desired = targetOffset - area.clientWidth / 2;
                area.scrollLeft = Math.max(0, Math.min(area.scrollWidth - area.clientWidth, desired));
            }""",
            [target_us, scale],
        )
        info = layout()
        scale, total_us, fps = info["scale"], info["totalUs"], info["fps"]
        click_x = info["ruler"]["left"] + target_us * scale
        click_y = info["ruler"]["top"] + info["ruler"]["height"] / 2
        assert info["area"]["left"] + 1 <= click_x <= info["area"]["right"] - 1, (click_x, info)
        page.mouse.click(click_x, click_y)
        expected = clamp_out(target_us, total_us, fps)
        page.wait_for_function(
            """expectedLeft => {
                const head = document.querySelector("[data-track='picture'] .playhead");
                return head && Math.abs(parseFloat(head.style.left) - expectedLeft) <= 1;
            }""",
            arg=expected * scale,
            timeout=3000,
        )
        measured = page.evaluate(
            """() => {
                const scroll = document.querySelector(".track-scroll");
                const head = document.querySelector("[data-track='picture'] .playhead");
                const ruler = document.querySelector(".ruler");
                const box = head.getBoundingClientRect();
                return {
                    styleLeft: parseFloat(head.style.left),
                    screenLeft: box.left,
                    origin: ruler.getBoundingClientRect().left,
                    scale: Number(scroll.dataset.scale),
                };
            }"""
        )
        actual_us = measured["styleLeft"] / measured["scale"]
        screen_us = (measured["screenLeft"] - measured["origin"]) / measured["scale"]
        return expected, actual_us, screen_us, 1_000_000 / fps

    for zoom in ("适应窗口", "2倍", "4倍", "8倍"):
        page.get_by_role("button", name=zoom, exact=True).click()
        expect(page.get_by_role("button", name=zoom, exact=True)).to_have_attribute(
            "aria-pressed", "true"
        )
        total_us = layout()["totalUs"]
        # Avoid the exact ends so clamping at totalUs-1 is not the only thing being tested.
        for frac in (0.2, 0.5, 0.8):
            expected, actual_us, screen_us, frame_us = seek_and_read(total_us * frac)
            assert abs(actual_us - expected) <= frame_us + 0.5, (
                zoom,
                frac,
                actual_us,
                expected,
                frame_us,
            )
            assert abs(screen_us - expected) <= frame_us + 0.5, (
                zoom,
                frac,
                screen_us,
                expected,
                frame_us,
            )
            expect(page.get_by_role("status", name="版本保存状态")).to_have_text(dirty_before)
            expect(page.get_by_role("slider", name="旁白起点")).to_have_attribute(
                "aria-valuenow", narration_before
            )
