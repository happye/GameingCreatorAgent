"""A07: a real pointer-up narration drag must survive undo, save, reload, and MP4."""
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


def test_pointerup_narration_drag_saves_reloads_and_exports_mp4(studio_audio, tmp_path):
    page = studio_audio
    start = page.get_by_role("slider", name="旁白起点")
    expect(start).to_have_attribute("aria-valuenow", "15")
    dirty_before = page.get_by_role("status", name="版本保存状态").inner_text()

    # Raw mouse coords skip actionability; scroll so the bar is not under the dock.
    start.scroll_into_view_if_needed()
    handle = start.bounding_box()
    assert handle and handle["width"] > 4
    mid_y = handle["y"] + handle["height"] / 2
    mid_x = handle["x"] + handle["width"] / 2
    page.mouse.move(mid_x, mid_y)
    page.mouse.down()
    # Move earlier: this 3s cut has more room to the left of start 15 than to the right.
    page.mouse.move(mid_x - 80, mid_y, steps=20)
    expect(start).not_to_have_attribute("aria-valuenow", "15", timeout=5000)
    page.mouse.up()
    after = start.get_attribute("aria-valuenow")
    assert after and after != "15", after
    expect(page.get_by_role("status", name="版本保存状态")).not_to_have_text(dirty_before)

    page.get_by_role("button", name="撤销一步").click()
    expect(start).to_have_attribute("aria-valuenow", "15")
    page.get_by_role("button", name="重做").click()
    expect(start).to_have_attribute("aria-valuenow", after)

    with page.expect_request(
        lambda r: r.method == "POST" and r.url.endswith("/api/creation/revisions")
    ) as submitted:
        page.get_by_role("button", name="保存版本", exact=True).click()
    body = json.loads(submitted.value.post_data)
    assert body["narration"]["startFrame"] == int(after), body["narration"]
    expect(page.get_by_role("status", name="版本保存状态")).to_contain_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=30000
    )
    expect(start).to_have_attribute("aria-valuenow", after)

    page.reload()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(page.get_by_role("slider", name="旁白起点")).to_have_attribute("aria-valuenow", after)

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
