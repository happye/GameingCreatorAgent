"""Real local HTTP, reasoning validation, save and render; text transport is fake."""

# ruff: noqa: F401, F811
import json
import subprocess

import pytest
from test_creation_jobs import service
from test_narration_jobs import engine
from test_studio_audio_graph_browser import studio_audio
from test_studio_overlays_browser import green_png

from gamingcreator.infrastructure.http_transport import HttpResponse
from gamingcreator.ui import server


@pytest.fixture(autouse=True)
def fake_transport(monkeypatch):
    calls = []

    class Transport:
        async def post(self, payload, timeout_seconds):
            calls.append(payload)
            context = json.loads(payload["messages"][1]["content"])["context"]
            identity = context["overlays"][0]["overlayId"]
            response = dict(
                schemaVersion="creation-reasoning-overlays-v1",
                kind="overlay_edit_proposal",
                message="延长此独立图层并淡出",
                questions=[],
                clips=[],
                citations=[identity],
                overlayEdit=dict(overlayId=identity, endFrame=90, fadeOutFrames=15),
            )
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "model": "fake",
                        "id": "fake-e2e",
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": json.dumps(response)},
                            }
                        ],
                    }
                ).encode(),
            )

    original = server.CreationReasoningService
    monkeypatch.setattr(
        server,
        "CreationReasoningService",
        lambda *a, **kw: original(*a, transport=Transport(), **kw),
    )
    monkeypatch.setattr(server, "reasoning_config", lambda: {"available": True, "provider": "fake"})
    return calls


def test_real_http_overlay_proposal_saves_and_extends_export(studio_audio, service, fake_transport):
    expect = pytest.importorskip("playwright.sync_api").expect
    page = studio_audio
    page.get_by_role("tab", name="叠加", exact=True).click()
    page.get_by_label("上传PNG叠加", exact=True).set_input_files(
        {"name": "green.png", "mimeType": "image/png", "buffer": green_png()}
    )
    expect(page.get_by_label("结束秒", exact=True)).to_be_visible()
    page.get_by_label("结束秒", exact=True).fill("1")
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    page.get_by_label("创作助手模式").select_option("ai")
    page.get_by_label("创作对话需求").fill("让这张独立图层多留两秒，然后慢慢消失")
    page.get_by_role("button", name="准备请求（不发送）").click()
    assert fake_transport == []
    page.get_by_label("同意本次文字发送和费用上限").check()
    page.get_by_role("button", name="确认本次调用", exact=False).click()
    expect(page.get_by_text("图层预览：", exact=False)).to_be_visible()
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("1")
    page.get_by_role("button", name="应用AI建议").click()
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("3")
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("tab", name="叠加", exact=True).click()
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("3")
    page.get_by_role("button", name="导出成片", exact=True).click()
    expect(page.get_by_role("button", name="成片", exact=True)).to_be_visible(timeout=60000)
    origin = page.url.removesuffix("/studio")
    jobs = page.request.get(f"{origin}/api/creation/jobs?projectId=artifacts/project").json()[
        "jobs"
    ]
    job = next(job for job in jobs if job["kind"] == "render")
    path = service.directory(job["jobId"]) / "result/video.mp4"
    pixel = subprocess.run(
        [
            str(service.repository / ".tools/ffmpeg/bin/ffmpeg.exe"),
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            r"select=eq(n\,60),format=rgb24,crop=1:1:100:100",
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
        check=True,
        capture_output=True,
        timeout=20,
    ).stdout
    assert len(pixel) == 3 and pixel[1] > 220 and max(pixel[0], pixel[2]) < 25, pixel
    assert len(fake_transport) == 1
