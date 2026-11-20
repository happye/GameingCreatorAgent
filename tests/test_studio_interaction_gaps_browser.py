"""G17–G19 / G24–G26 isolated Studio UI checks on the existing audio fixture."""
# ruff: noqa: F811

from __future__ import annotations

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401
from test_studio_caption_editor_browser import select_shot

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def select_clip(page, index):
    field = page.get_by_label("镜头字幕", exact=True)
    page.locator(".insp-tabs").get_by_role("tab", name="镜头", exact=True).click()
    clip = page.locator(".timeline .clip").nth(index)
    # Crossfade overlap can intercept pointer events; click the node directly.
    clip.evaluate("el => el.click()")
    field.wait_for(state="visible", timeout=2000)
    expect(clip).to_have_attribute("aria-current", "true")
    return field


def enable_sidecar(page):
    export_tab = page.locator(".insp-tabs").get_by_role("tab", name="导出", exact=True)
    export_tab.click()
    expect(export_tab).to_have_attribute("aria-selected", "true")
    page.locator("label.form-row").filter(has=page.locator("option[value='sidecar']")).locator(
        "select"
    ).select_option("sidecar")
    page.locator(".insp-tabs").get_by_role("tab", name="镜头", exact=True).click()


def test_delete_reorder_captions_follow_clip_and_undo(studio_audio):
    """G17: leftover captions vanish with a deleted clip; undo and clipId mapping hold."""
    page = studio_audio
    enable_sidecar(page)
    expect(page.locator(".caption-lane")).not_to_contain_text("不加字幕")
    select_clip(page, 0).fill("甲镜字幕")
    expect(page.locator(".caption-block").first).to_contain_text("甲镜字幕", timeout=10_000)
    select_clip(page, 1).fill("乙镜字幕")
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("乙镜字幕")
    select_clip(page, 0)
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("甲镜字幕")
    expect(page.locator(".caption-block")).to_have_count(2, timeout=10_000)
    expect(page.locator(".caption-block").nth(0)).to_contain_text("甲镜字幕")
    expect(page.locator(".caption-block").nth(1)).to_contain_text("乙镜字幕")

    select_clip(page, 0)
    page.get_by_role("button", name="后移", exact=True).click()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("甲镜字幕")
    expect(page.locator(".caption-block").nth(0)).to_contain_text("乙镜字幕")
    expect(page.locator(".caption-block").nth(1)).to_contain_text("甲镜字幕")

    page.get_by_role("button", name="删除这段", exact=True).click()
    expect(page.locator(".timeline .clip")).to_have_count(1)
    expect(page.locator(".caption-block")).to_have_count(1, timeout=10_000)
    expect(page.locator(".caption-block").first).to_contain_text("乙镜字幕")
    expect(page.locator(".caption-block")).not_to_contain_text("甲镜字幕")
    # The inspector must follow a remaining clip, not keep the deleted clip as the target.
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("乙镜字幕")
    expect(page.get_by_role("status", name="版本保存状态")).to_contain_text("不会自动截断")

    page.get_by_role("button", name="撤销一步").click()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(page.locator(".caption-block")).to_have_count(2, timeout=10_000)
    expect(page.locator(".caption-block").nth(0)).to_contain_text("乙镜字幕")
    expect(page.locator(".caption-block").nth(1)).to_contain_text("甲镜字幕")


def test_delete_in_textbox_and_discard_command_preview(studio_audio):
    """G18: Delete in a text field keeps clips; cancelling a preview restores them."""
    page = studio_audio
    field = select_shot(page)
    field.fill("ABCD")
    field.press("Home")
    page.keyboard.press("Delete")
    expect(field).to_have_value("BCD")
    expect(page.locator(".timeline .clip")).to_have_count(2)

    titles = page.locator(".timeline .clip").evaluate_all("els => els.map(el => el.title)")
    page.get_by_label("一句话修改镜头").fill("第1个镜头慢放")
    page.get_by_role("button", name="预览改动", exact=True).click()
    expect(page.locator(".timeline .clip.changed")).to_have_count(1, timeout=10_000)
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "请先应用或取消创作助手的改动"
    )
    expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_disabled()
    expect(page.get_by_role("slider", name="旁白起点")).to_have_count(0)
    page.get_by_role("button", name="取消", exact=True).click()
    expect(page.get_by_text("已取消，时间轴没有变化。", exact=True)).to_be_visible()
    expect(page.locator(".timeline .clip.changed")).to_have_count(0)
    expect(page.locator(".timeline .clip")).to_have_count(2)
    assert page.locator(".timeline .clip").evaluate_all("els => els.map(el => el.title)") == titles
    expect(page.get_by_role("slider", name="旁白起点")).to_have_attribute("aria-valuenow", "15")


def test_layout_toggle_and_resize_keep_dirty_edits(studio_audio):
    """G19: collapsing panels or resizing the window must not wipe dirty edits."""
    page = studio_audio
    field = select_shot(page)
    field.fill("布局保留字幕")
    expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
    for name in ("检查器", "素材箱"):
        toggle = page.get_by_role("button", name=name, exact=True)
        toggle.click()
        expect(toggle).to_have_attribute("aria-pressed", "false")
        toggle.click()
        expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("布局保留字幕")
    page.set_viewport_size({"width": 900, "height": 720})
    page.set_viewport_size({"width": 1440, "height": 1000})
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("布局保留字幕")
    expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
    dialogs = []
    page.once("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.get_by_role("tab", name="素材", exact=True).click()
    expect(page.get_by_role("tab", name="剪辑", exact=True)).to_have_attribute(
        "aria-selected", "true"
    )
    assert dialogs and "未保存" in dialogs[0]


def test_envelope_points_survive_zoom_and_scroll(studio_audio):
    """G24: a source keyframe keeps its output-clock frame across zoom and scroll."""
    page = studio_audio
    line = page.get_by_label("原声增益线")
    box = line.bounding_box()
    assert box and box["width"] > 20
    page.mouse.click(box["x"] + box["width"] * 0.4, box["y"] + 4)
    point = line.get_by_role("slider")
    expect(point).to_have_count(1)
    label = point.get_attribute("aria-label")
    value = point.get_attribute("aria-valuenow")
    page.get_by_role("button", name="8倍", exact=True).click()
    expect(page.get_by_role("button", name="8倍", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    area = page.locator(".track-area")
    page.wait_for_function("el => el.scrollWidth > el.clientWidth * 2", arg=area.element_handle())
    point.scroll_into_view_if_needed()
    expect(point).to_be_visible()
    expect(point).to_have_attribute("aria-label", label)
    expect(point).to_have_attribute("aria-valuenow", value)
    page.get_by_role("button", name="撤销一步").click()
    expect(point).to_have_count(0)
    expect(page.get_by_role("slider", name="旁白起点")).to_have_attribute("aria-valuenow", "15")


def test_caption_long_chinese_emoji_style_and_clear(studio_audio):
    """G25: long Chinese, newline, emoji and style switch stay intact; clear uses existing hide."""
    page = studio_audio
    text = "这是一段很长的中文字幕用来核对编辑器不会截断内容" * 3 + "\n第二行 😀🎯"
    field = select_shot(page)
    field.fill(text)
    expect(field).to_have_value(text)
    export_tab = page.locator(".insp-tabs").get_by_role("tab", name="导出", exact=True)
    export_tab.click()
    expect(export_tab).to_have_attribute("aria-selected", "true")
    mode = (
        page.locator("label.form-row")
        .filter(has=page.locator("option[value='burn']"))
        .locator("select")
    )
    mode.select_option("burn")
    expect(mode).to_have_value("burn")
    style = page.locator("label.form-row").filter(has_text="字幕样式").locator("select")
    expect(style).to_be_visible()
    style.select_option("large")
    expect(style).to_have_value("large")
    preview = page.get_by_label("字幕预览", exact=True)
    expect(page.get_by_role("status", name="字幕预览状态")).to_contain_text(
        "字幕内容与时机预览", timeout=10_000
    )
    expect(preview).to_have_attribute("data-subtitle-style", "large")
    expect(preview).to_contain_text("这是一段很长的中文字幕用来核对编辑器不会截断内容")
    expect(preview).to_contain_text("😀🎯")
    page.locator(".insp-tabs").get_by_role("tab", name="镜头", exact=True).click()
    page.get_by_role("button", name="此镜头不显示字幕", exact=True).click()
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("")
    expect(page.get_by_role("status", name="镜头字幕状态")).to_have_text("此镜头不显示字幕。")


def test_overlay_text_delete_does_not_remove_clip_or_audio(studio_audio):
    """G26: Delete while editing an overlay field must not delete a clip or change narration."""
    page = studio_audio
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")
    page.get_by_role("tab", name="叠加", exact=True).click()
    page.get_by_label("叠加文字", exact=True).fill("图层AB")
    page.get_by_role("button", name="添加文字", exact=True).click()
    expect(page.locator(".overlay-row")).to_have_count(1)
    field = page.get_by_label("叠加文字", exact=True).last
    field.click()
    field.press("Home")
    page.keyboard.press("Delete")
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(page.locator(".overlay-row")).to_have_count(1)
    expect(start).to_have_attribute("aria-valuenow", "15")
    page.get_by_role("button", name="撤销一步").click()
    expect(page.locator(".overlay-row")).to_have_count(0)
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(start).to_have_attribute("aria-valuenow", "15")
