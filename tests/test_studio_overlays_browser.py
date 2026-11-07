"""Real Studio uploads, version persistence and FFmpeg export; fake planning/voices."""

# ruff: noqa: F811

import json
import struct
import subprocess
import zlib

from test_overlay_assets import chunk
from test_studio_audio_graph_browser import engine, service, studio_audio  # noqa: F401


def green_png():
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\xff\0\xff" * 2) * 2))
        + chunk(b"IEND", b"")
    )


def canvas_pixel(page, tools, tmp_path, name):
    canvas = page.locator(".program-frame")
    path = tmp_path / f"{name}.png"
    canvas.screenshot(path=str(path))
    size = canvas.bounding_box()
    # Sample inside the top-left 20%-wide green image, away from codec edges.
    x, y = int(size["width"] * 0.2), int(size["height"] * 0.2)
    result = subprocess.run(
        [
            str(tools),
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"crop=1:1:{x}:{y}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-threads",
            "1",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=20,
    )
    return tuple(result.stdout)


def test_png_text_save_reload_preview_and_export(studio_audio, service, tmp_path):  # noqa: F811
    from playwright.sync_api import expect

    page = studio_audio
    origin = page.url.removesuffix("/studio")
    page.get_by_role("tab", name="叠加", exact=True).click()
    page.get_by_label("上传PNG叠加", exact=True).set_input_files(
        {"name": "green.png", "mimeType": "image/png", "buffer": green_png()}
    )
    panel = page.locator(".overlay-row").first
    expect(panel).to_be_visible()
    for label, value in (("横向位置%", "10"), ("纵向位置%", "10"), ("宽度%", "20")):
        panel.get_by_label(label, exact=True).fill(value)
        panel.get_by_label(label, exact=True).press("Tab")
    page.get_by_label("叠加文字", exact=True).fill("中文玩法提示")
    page.get_by_role("button", name="添加文字", exact=True).click()
    expect(page.locator(".overlay-row")).to_have_count(2)
    expect(page.locator(".overlay-scale img")).to_have_count(2)
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本", timeout=15000
    )
    remembered = page.evaluate("JSON.parse(localStorage.getItem('studio-last-job-v1'))")
    revision = remembered["artifacts/project"]["id"]
    editor = page.request.get(
        f"{origin}/api/creation/jobs/{revision}/edit?planId=hook-first"
    ).json()
    assert len(editor["overlays"]["items"]) == 2
    assert editor["overlays"]["items"][1]["text"] == "中文玩法提示"
    # Saved versions are also openable from the visible works list.
    page.get_by_role("tab", name="素材", exact=True).click()
    versions = page.locator("details.group").filter(
        has=page.locator("summary").filter(has_text="剪辑版本")
    )
    versions.locator("summary").click()
    expect(versions.get_by_role("button").first).to_be_enabled()
    versions.get_by_role("button").first.click()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("tab", name="叠加", exact=True).click()
    expect(page.locator(".overlay-row")).to_have_count(2)
    expect(page.locator(".overlay-scale img")).to_have_count(2)
    page.locator(".overlay-scale img").first.wait_for()
    page.wait_for_function(
        "() => [...document.querySelectorAll('.overlay-scale img')].every(i => i.complete && i.naturalWidth)"
    )
    tools = service.repository / ".tools/ffmpeg/bin/ffmpeg.exe"
    pixel = canvas_pixel(page, tools, tmp_path, "overlay-preview")
    assert pixel[1] > 220 and max(pixel[0], pixel[2]) < 25, pixel
    page.get_by_role("button", name="导出成片", exact=True).click()
    expect(page.get_by_role("button", name="成片", exact=True)).to_be_visible(timeout=60000)
    video = page.locator("video[controls]")
    expect(video).to_be_visible()
    # Export is already composited: the live sprite layer must be hidden in result mode.
    expect(page.locator(".program-frame")).to_be_hidden()
    jobs = page.request.get(f"{origin}/api/creation/jobs?projectId=artifacts/project").json()[
        "jobs"
    ]
    render = next(job for job in jobs if job["kind"] == "render")
    receipt = json.loads((service.directory(render["jobId"]) / "result/receipt.json").read_text())
    assert receipt["overlays"] == editor["overlays"]
    assert_rendered_pixels(tools, service.directory(render["jobId"]) / "result/video.mp4")


def assert_rendered_pixels(tools, rendered):
    pixels = subprocess.run(
        [
            str(tools),
            "-v",
            "error",
            "-i",
            str(rendered),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-threads",
            "1",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=20,
    ).stdout
    offset = (144 * 1280 + 256) * 3
    pixel = pixels[offset : offset + 3]
    assert pixel[1] > 220 and max(pixel[0], pixel[2]) < 25, pixel
    # The Chinese sprite is visibly white in the same exported frame.
    top = pixels[: 256 * 1280 * 3]
    assert sum(min(top[i : i + 3]) > 220 for i in range(0, len(top), 3)) > 100


def test_overlay_clock_validation_reset_and_clear(studio_audio):
    from playwright.sync_api import expect

    page = studio_audio
    result = page.evaluate("""async () => {
        const {overlayFrame,overlayOpacity,overlayGeometry}=await import('/assets/studio/overlays.js');
        const item={startFrame:65,endFrame:130,fadeInFrames:0,fadeOutFrames:0,x:4250,y:3667,width:1000};
        return {frames:[30,60,120].flatMap(fps => [65,127,130].map(n=>overlayFrame(n*1e6/fps,fps))),
          before:overlayFrame((65-.00001)*1e6/30,30),
          alpha:[64,65,129,130].map(n=>overlayOpacity(item,overlayFrame(n*1e6/30,30))),
          geometry:overlayGeometry(item,{width:2,height:2},40,30)};
    }""")
    assert result == {
        "frames": [65, 127, 130] * 3,
        "before": 64,
        "alpha": [0, 1, 1, 0],
        "geometry": {"x": 17, "y": 11, "width": 4, "height": 4},
    }
    page.get_by_role("tab", name="叠加", exact=True).click()
    page.get_by_label("叠加文字", exact=True).fill("淡出提示")
    page.get_by_role("button", name="添加文字", exact=True).click()
    panel = page.locator(".overlay-row")
    expect(panel).to_have_count(1)
    panel.get_by_label("结束秒", exact=True).fill("999")
    expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_disabled()
    expect(page.get_by_role("alert")).to_contain_text("时长内")
    page.get_by_role("button", name="撤销修改", exact=True).click()
    expect(panel).to_have_count(0)
    page.get_by_label("叠加文字", exact=True).fill("保留后清除")
    page.get_by_role("button", name="添加文字", exact=True).click()
    expect(panel).to_have_count(1)
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本"
    )
    page.get_by_role("button", name="删除图层", exact=True).click()
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本"
    )
    page.reload()
    page.get_by_role("tab", name="叠加", exact=True).click()
    expect(panel).to_have_count(0)


def test_late_asset_registration_cannot_restore_reset_layers(studio_audio):
    from playwright.sync_api import expect

    page = studio_audio
    page.get_by_role("tab", name="叠加", exact=True).click()
    page.get_by_label("叠加文字", exact=True).fill("先添加")
    with page.expect_response("**/api/creation/overlay-assets") as response:
        page.get_by_role("button", name="添加文字", exact=True).click()
    asset = response.value.json()
    expect(page.locator(".overlay-row")).to_have_count(1)
    pending = []
    page.route("**/api/creation/overlay-assets", lambda route: pending.append(route))
    page.get_by_label("叠加文字", exact=True).fill("迟到的登记")
    with page.expect_request("**/api/creation/overlay-assets"):
        page.get_by_role("button", name="添加文字", exact=True).click()
    expect(page.get_by_text("正在登记叠加素材…", exact=True)).to_be_visible()
    page.get_by_role("button", name="撤销修改", exact=True).click()
    expect(page.locator(".overlay-row")).to_have_count(0)
    assert len(pending) == 1
    pending[0].fulfill(status=200, json=asset)
    expect(page.get_by_text("正在登记叠加素材…", exact=True)).to_have_count(0)
    expect(page.locator(".overlay-row")).to_have_count(0)
    expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_disabled()
