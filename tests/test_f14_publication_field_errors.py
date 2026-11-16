"""F14: publication form and API name the field; raw ValueError is not shown."""
# ruff: noqa: F811

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_publication import payload, rendered  # noqa: F401

from gamingcreator.domain.errors import AppError
from gamingcreator.domain.publication import user_input_message, validate_metadata
from gamingcreator.ui.server import create_server

VALID = {"coverFrame": 0, "title": "标题", "description": "", "tags": []}


@pytest.mark.parametrize(
    "field,value,text",
    [
        ("title", "", "标题不能为空。"),
        ("title", "a" * 201, "标题不能超过 200 字。"),
        ("title", "x\x00", "标题包含无效字符。"),
        ("description", "a" * 5001, "简介不能超过 5000 字。"),
        ("description", "x\x01", "简介包含无效字符。"),
        ("tags", ["a", "a"], "标签不能重复。"),
        ("tags", ["x"] * 21, "标签不能超过 20 个。"),
        ("tags", ["x" * 51], "单个标签不能超过 50 字。"),
        ("tags", [[]], "标签格式无效。"),
        ("coverFrame", 4, "封面帧超出成片范围。"),
        ("coverFrame", -1, "封面帧超出成片范围。"),
        ("coverFrame", True, "封面帧超出成片范围。"),
    ],
)
def test_metadata_names_the_field(field, value, text):
    data = dict(VALID)
    data[field] = value
    with pytest.raises(ValueError) as caught:
        validate_metadata(data, 4)
    assert str(caught.value) == text
    assert "Invalid local publication" not in str(caught.value)


def test_user_input_message_hides_internal_errors():
    assert user_input_message(ValueError("标题不能为空。")) == "标题不能为空。"
    assert user_input_message(ValueError("Render receipt changed")) == "无法保存发布信息。"
    assert user_input_message(ValueError("decoder failure")) == "无法保存发布信息。"
    assert "Invalid" not in user_input_message(
        ValueError("Invalid local publication metadata or output frame.")
    )


def test_submit_names_title_and_hides_prepare_errors(rendered, monkeypatch):
    jobs, render = rendered
    value = payload(jobs, render)
    value.update(requestId=uuid4().hex, title="a" * 201)
    with pytest.raises(AppError) as caught:
        jobs.submit("publication", value)
    assert caught.value.code == "creation.input"
    assert caught.value.message == "标题不能超过 200 字。"

    import gamingcreator.ui.publication_jobs as publication

    def broken(*args, **kwargs):
        raise ValueError("Render receipt changed")

    monkeypatch.setattr(publication, "prepare", broken)
    value = payload(jobs, render)
    value.update(requestId=uuid4().hex)
    with pytest.raises(AppError) as hidden:
        jobs.submit("publication", value)
    assert hidden.value.message == "无法保存发布信息。"
    assert "Render receipt" not in hidden.value.message


def _post(base, path, body):
    request = Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except HTTPError as error:
        return error.code, json.loads(error.read().decode())


def test_http_field_error_and_hidden_internal_error(rendered, monkeypatch):
    jobs, render = rendered
    server = create_server("127.0.0.1", 0, jobs.repository)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        value = payload(jobs, render)
        value.update(requestId=uuid4().hex, description="a" * 5001)
        status, body = _post(base, "/api/creation/publications", value)
        assert status == 400
        assert body["code"] == "creation.input"
        assert body["message"] == "简介不能超过 5000 字。"
        assert "Invalid local" not in body["message"]
        assert "ValueError" not in body["message"]
        assert "无法提交：" not in body["message"]

        import gamingcreator.ui.publication_jobs as publication

        monkeypatch.setattr(
            publication,
            "prepare",
            lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("decoder failure")),
        )
        value = payload(jobs, render)
        value.update(requestId=uuid4().hex)
        status, body = _post(base, "/api/creation/publications", value)
        assert status == 400
        assert body["message"] == "无法保存发布信息。"
        assert "decoder" not in body["message"]
    finally:
        server.shutdown()
        server.server_close()


def test_form_helper_and_publish_fields_browser(service, monkeypatch):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    import gamingcreator.ui.server as server_module

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server_module, "project_runs_payload", runs)
    draft = {
        "publicationJobId": None,
        "publicationReceiptSha256": None,
        "renderJobId": "a" * 32,
        "expectedRenderReceiptSha256": "d" * 64,
        "coverFrame": 0,
        "title": "游戏 · 目标",
        "description": "目标",
        "tags": ["游戏"],
        "frames": 300,
        "fps": {"numerator": 30, "denominator": 1},
        "width": 1280,
        "height": 720,
        "videoUrl": "/api/creation/jobs/" + "a" * 32 + "/video",
    }
    posted = []

    def answer(route):
        path = "/" + route.request.url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]
        if path == "/api/creation/jobs":
            return route.fulfill(
                json={
                    "jobs": [
                        {
                            "jobId": "a" * 32,
                            "kind": "render",
                            "status": "completed",
                            "createdAt": "2026-11-03T10:00:00Z",
                        }
                    ]
                }
            )
        if path == "/api/creation/platform-profiles":
            return route.fulfill(json={"profiles": []})
        if path == "/api/creation/reasoning/config":
            return route.fulfill(json={"available": False})
        if path.endswith("/publication") and route.request.method == "GET":
            return route.fulfill(json=draft)
        if path == "/api/creation/publications":
            posted.append(json.loads(route.request.post_data))
            return route.fulfill(
                status=400,
                json={
                    "code": "creation.input",
                    "message": "无法提交：Invalid local publication metadata or output frame.",
                    "exitCode": 2,
                },
            )
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
            page.goto(base + "/assets/studio/publication_form.js")
            helper = page.evaluate(
                """async () => {
                    const mod = await import('/assets/studio/publication_form.js');
                    const overTags = mod.publicationFieldErrors({
                        title: "好标题",
                        description: "",
                        tags: Array.from({length: 21}, (_, i) => "标签" + i),
                    });
                    const longDesc = mod.publicationFieldErrors({
                        title: "好标题",
                        description: "x".repeat(5001),
                        tags: [],
                    });
                    const hidden = mod.publicationErrorFields(
                        "无法提交：Invalid local publication metadata or output frame."
                    );
                    const named = mod.publicationErrorFields("标题不能超过 200 字。");
                    return {overTags, longDesc, hidden, named};
                }"""
            )
            assert helper["overTags"] == {"tags": "标签不能超过 20 个。"}
            assert helper["longDesc"] == {"description": "简介不能超过 5000 字。"}
            assert helper["hidden"] == {"message": "无法保存发布信息。", "fields": {}}
            assert helper["named"] == {"message": "", "fields": {"title": "标题不能超过 200 字。"}}

            page.route(lambda url: "/api/creation/" in url, answer)
            page.goto(base + "/studio")
            page.get_by_role("tab", name="发布").click()
            tags = (
                page.locator("[aria-label=发布信息] label").filter(has_text="标签").locator("input")
            )
            playwright.expect(tags).to_be_visible()
            tags.fill("，".join([f"标签{i}" for i in range(21)]))
            page.get_by_role("button", name="保存发布信息").click()
            playwright.expect(page.locator("[data-field=tags]")).to_have_text(
                "标签不能超过 20 个。"
            )
            assert posted == []

            tags.fill("游戏")
            playwright.expect(page.locator("[data-field=tags]")).to_have_count(0)
            page.get_by_role("button", name="保存发布信息").click()
            playwright.expect(page.get_by_text("无法保存发布信息。")).to_be_visible()
            assert "Invalid local" not in page.content()
            assert "ValueError" not in page.content()
            assert posted  # the intercepted English error was mapped, not shown raw
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
