"""A10: a late or failed cover candidate from video A must not overwrite a hand pick on B."""
# ruff: noqa: F811

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest
from test_creation_jobs import service  # noqa: F401

from gamingcreator.ui.server import create_server

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
RENDER_A, RENDER_B = "a" * 32, "b" * 32
DIGEST_A, DIGEST_B = "c" * 64, "d" * 64

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def _color_clip(path: Path, color: str) -> bytes:
    import subprocess

    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(FFMPEG),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color={color}:s=64x48:r=30:d=1",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    return path.read_bytes()


def _fulfill_video(route, data: bytes):
    start, end = 0, len(data) - 1
    rng = route.request.headers.get("range") or route.request.headers.get("Range")
    status = 200
    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(data)),
    }
    body = data
    if rng and rng.startswith("bytes="):
        part = rng.split("=", 1)[1].split(",")[0]
        left, _, right = part.partition("-")
        start = int(left or 0)
        end = int(right) if right else len(data) - 1
        end = min(end, len(data) - 1)
        body = data[start : end + 1]
        status = 206
        headers["Content-Length"] = str(len(body))
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    route.fulfill(status=status, body=body, headers=headers)


def _draft(render_id, digest, title, cover_frame=0):
    return {
        "publicationJobId": None,
        "publicationReceiptSha256": None,
        "renderJobId": render_id,
        "expectedRenderReceiptSha256": digest,
        "coverFrame": cover_frame,
        "title": title,
        "description": title,
        "tags": ["游戏"],
        "frames": 30,
        "fps": {"numerator": 30, "denominator": 1},
        "width": 64,
        "height": 48,
        "videoUrl": f"/api/creation/jobs/{render_id}/video",
    }


def _pick_b_while_a_pending(service, monkeypatch, tmp_path, fail_a: bool):
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    video_a = _color_clip(tmp_path / "a.mp4", "red")
    video_b = _color_clip(tmp_path / "b.mp4", "blue")
    assert hashlib.sha256(video_a).digest() != hashlib.sha256(video_b).digest()
    release_a = threading.Event()

    def answer(route):
        path = "/" + route.request.url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]
        if path == "/api/creation/jobs":
            return route.fulfill(
                json={
                    "jobs": [
                        {
                            "jobId": RENDER_A,
                            "kind": "render",
                            "status": "completed",
                            "name": "成片A",
                            "createdAt": "2026-11-03T10:00:00Z",
                        },
                        {
                            "jobId": RENDER_B,
                            "kind": "render",
                            "status": "completed",
                            "name": "成片B",
                            "createdAt": "2026-11-03T11:00:00Z",
                        },
                    ]
                }
            )
        if path == "/api/creation/reasoning/config":
            return route.fulfill(json={"available": False})
        if path == "/api/creation/platform-profiles":
            return route.fulfill(json={"profiles": []})
        if path == f"/api/creation/jobs/{RENDER_A}/publication":
            return route.fulfill(json=_draft(RENDER_A, DIGEST_A, "成片A标题"))
        if path == f"/api/creation/jobs/{RENDER_B}/publication":
            return route.fulfill(json=_draft(RENDER_B, DIGEST_B, "成片B标题"))
        if path == f"/api/creation/jobs/{RENDER_A}/video":
            if not release_a.wait(timeout=8):
                return route.abort()
            if fail_a:
                return route.fulfill(
                    status=500, body=b"nope", headers={"Content-Type": "text/plain"}
                )
            return _fulfill_video(route, video_a)
        if path == f"/api/creation/jobs/{RENDER_B}/video":
            return _fulfill_video(route, video_b)
        return route.continue_()

    server = create_server("127.0.0.1", 0, service.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 860})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(lambda url: "/api/creation/" in url, answer)
            page.goto(base + "/studio")
            page.get_by_role("tab", name="发布").click()
            expect(page.get_by_label("发布信息").locator("input").first).to_have_value("成片A标题")
            expect(page.locator(".cover-picks button")).to_have_count(0)

            page.get_by_role("button", name="成片B").click()
            expect(page.get_by_label("发布信息").locator("input").first).to_have_value("成片B标题")
            expect(page.locator(".cover-picks button")).not_to_have_count(0, timeout=15000)
            second = page.locator(".cover-picks button").nth(1)
            assert RENDER_B in (second.get_attribute("data-video-src") or "")
            second.click()
            expect(second).to_have_attribute("aria-pressed", "true")
            picked = page.locator(".transport .tc").inner_text()
            assert "封面：第 0 帧" not in picked, picked
            preview = page.locator("img.cover").get_attribute("src")
            assert preview and preview.startswith("data:image/jpeg")

            # Release A while still on B. Give candidates time to finish, then assert B is intact.
            release_a.set()
            page.wait_for_timeout(4000)
            expect(page.locator(".transport .tc")).to_have_text(picked)
            expect(page.locator("img.cover")).to_have_attribute("src", preview)
            buttons = page.locator(".cover-picks button")
            expect(buttons).not_to_have_count(0)
            for button in buttons.all():
                src = button.get_attribute("data-video-src") or ""
                assert RENDER_B in src and RENDER_A not in src, src
            expect(page.locator(".cover-picks button").nth(1)).to_have_attribute(
                "aria-pressed", "true"
            )
            assert not errors, errors
            browser.close()
    finally:
        release_a.set()
        server.shutdown()
        server.server_close()


def test_late_cover_from_a_does_not_overwrite_b_hand_pick(service, monkeypatch, tmp_path):  # noqa: F811
    _pick_b_while_a_pending(service, monkeypatch, tmp_path, fail_a=False)


def test_failed_cover_from_a_keeps_b_hand_pick(service, monkeypatch, tmp_path):  # noqa: F811
    _pick_b_while_a_pending(service, monkeypatch, tmp_path, fail_a=True)
