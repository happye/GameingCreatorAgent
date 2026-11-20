"""A11: long Chinese project names must not cover main buttons; Tab and text-field arrows."""

from __future__ import annotations

import json
import threading

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

from gamingcreator.ui.server import create_server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

LONG_NAME = "很长的中文项目名称用来检查顶栏会不会挡住主按钮以及超长文件名显示" * 2
MAIN_BUTTONS = ("素材", "剪辑", "发布", "素材箱", "检查器")
NEW_CONTROLS = ("适应窗口", "2倍", "4倍", "8倍", "旁白起点")


def _visible_and_clickable(page, locator):
    expect(locator).to_be_visible()
    box = locator.bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0, box
    topbar = page.locator("header.topbar").bounding_box()
    assert topbar
    assert box["y"] + box["height"] <= topbar["y"] + topbar["height"] + 1
    assert box["x"] >= topbar["x"] - 1
    assert box["x"] + box["width"] <= topbar["x"] + topbar["width"] + 1
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    hit = page.evaluate(
        """([x, y]) => {
            const el = document.elementFromPoint(x, y);
            if (!el) return null;
            const btn = el.closest("button, a, [role=tab]");
            return {tag: el.tagName, text: (btn || el).innerText || "", label: (btn || el).getAttribute("aria-label") || ""};
        }""",
        [cx, cy],
    )
    assert hit, (box, "no element at center")
    return box, hit


def test_long_chinese_project_name_does_not_cover_main_buttons(service, monkeypatch):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    long_dir = service.repository / "artifacts" / LONG_NAME
    long_dir.mkdir(parents=True, exist_ok=True)
    (long_dir / "timeline.sqlite3").touch()
    server = create_server("127.0.0.1", 0, service.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            # Tight width so a long name would push or cover the right-side buttons if unconstrained.
            page = browser.new_page(viewport={"width": 1100, "height": 800})
            prefs = json.dumps({"project": f"artifacts/{LONG_NAME}", "workspace": "assets"})
            page.add_init_script(f"localStorage.setItem('studio-v1', {prefs!r});")
            page.goto(f"http://127.0.0.1:{server.server_port}/studio")
            expect(page.get_by_label("项目")).to_have_value(f"artifacts/{LONG_NAME}")
            select = page.get_by_label("项目")
            select_box = select.bounding_box()
            assert select_box and select_box["width"] <= 241, select_box
            hits = {}
            for name in MAIN_BUTTONS:
                loc = (
                    page.get_by_role("tab", name=name)
                    if name in {"素材", "剪辑", "发布"}
                    else page.get_by_role("button", name=name)
                )
                box, hit = _visible_and_clickable(page, loc)
                # The center of the button must belong to that control, not the overflowing project select.
                assert name in (hit["text"] + hit["label"]), (name, hit, box)
                hits[name] = box
            # The closed select must not overlap any main button's box.
            for name, box in hits.items():
                overlap_x = not (
                    select_box["x"] + select_box["width"] <= box["x"] + 1
                    or box["x"] + box["width"] <= select_box["x"] + 1
                )
                overlap_y = not (
                    select_box["y"] + select_box["height"] <= box["y"] + 1
                    or box["y"] + box["height"] <= select_box["y"] + 1
                )
                assert not (overlap_x and overlap_y), (name, select_box, box)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()


def _focused_label(page):
    return page.evaluate(
        """() => {
            const el = document.activeElement;
            if (!el) return "";
            const label = el.getAttribute("aria-label") || "";
            const text = (el.innerText || el.value || "").trim().replace(/\\s+/g, " ");
            return label || text.slice(0, 40);
        }"""
    )


def test_tab_reaches_new_timeline_controls(studio_audio):  # noqa: F811
    page = studio_audio
    expect(page.get_by_role("slider", name="旁白起点")).to_be_visible()
    page.locator("header.topbar").click()
    seen = []
    first = None
    for _ in range(80):
        page.keyboard.press("Tab")
        label = _focused_label(page)
        if first is None:
            first = (
                page.evaluate(
                    "() => document.activeElement && document.activeElement.outerHTML.slice(0, 180)"
                ),
                label,
            )
        _key = page.evaluate("() => document.activeElement")
        seen.append(label)
        # Stop after a full cycle: we return to the first distinct control after collecting something.
        if len(seen) > 8 and seen[-1] == seen[0] and label:
            break
    joined = " | ".join(seen)
    missing = [name for name in NEW_CONTROLS if not any(name in item for item in seen)]
    assert not missing, f"Tab 没到: {missing}\n顺序: {joined}"


def test_arrows_in_text_field_do_not_move_narration(studio_audio):  # noqa: F811
    page = studio_audio
    slider = page.get_by_role("slider", name="旁白起点")
    expect(slider).to_be_visible()
    before = slider.get_attribute("aria-valuenow")
    assert before is not None
    field = page.locator("textarea, input[type=text], input:not([type]), input[type=search]").first
    expect(field).to_be_visible()
    field.click()
    tag = field.evaluate(
        "el => el.tagName + ':' + (el.type || '') + ':' + (el.getAttribute('aria-label') || el.name || '')"
    )
    assert "start" not in tag.lower() and "起点" not in tag
    field.press("ArrowLeft")
    field.press("ArrowRight")
    field.press("Shift+ArrowLeft")
    field.press("Shift+ArrowRight")
    after = slider.get_attribute("aria-valuenow")
    assert after == before, (before, after, tag)
