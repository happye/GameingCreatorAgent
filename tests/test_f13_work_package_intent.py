"""F13：新建作品的请求身份错误不能再说成平台包。

作品走本地存储，平台包走会话存储；错误码和同一请求号规则保持不变。
"""

from __future__ import annotations

import threading

import pytest
from test_creation_jobs import service  # noqa: F401
from test_studio_planning_browser import planning, studio  # noqa: F401

from gamingcreator.ui.server import create_server

SCRIPT = """
async ({kind, action, payload, scope, second}) => {
    const client = await import('/assets/studio/api.js');
    const store = kind === 'work' ? 'localStorage' : 'sessionStorage';
    const run = async () => {
        if (action === 'reuse') {
            const first = client.requestId(kind, payload, scope);
            const again = client.requestId(kind, payload, scope);
            return {first, again, same: first === again};
        }
        if (action === 'conflict') {
            client.requestId(kind, payload, scope);
            return client.requestId(kind, second, scope);
        }
        if (action === 'save') {
            const original = Storage.prototype.setItem;
            Storage.prototype.setItem = function (key, value) {
                if (this === window[store]) throw new Error('fixture storage denied');
                return original.call(this, key, value);
            };
            try { return client.requestId(kind, payload, scope); }
            finally { Storage.prototype.setItem = original; }
        }
        if (action === 'read') {
            const key = 'studio-intent-v1:' + kind + ':' + scope;
            window[store].setItem(key, '{not-json');
            try { return client.requestId(kind, payload, scope); }
            finally { window[store].removeItem(key); }
        }
        if (action === 'keys') {
            const workId = client.requestId('work', payload, scope);
            const packageId = client.requestId('package', payload, scope);
            return {
                workId,
                packageId,
                distinct: workId !== packageId,
                workKey: localStorage.getItem('studio-intent-v1:work:' + scope) ? 'local' : null,
                packageKey: sessionStorage.getItem('studio-intent-v1:package:' + scope) ? 'session' : null,
                workInSession: sessionStorage.getItem('studio-intent-v1:work:' + scope),
                packageInLocal: localStorage.getItem('studio-intent-v1:package:' + scope),
            };
        }
        throw new Error('unknown action');
    };
    try { return {ok: true, value: await run()}; }
    catch (error) { return {ok: false, code: error.code, message: error.message}; }
}
"""


def _call(page, **kwargs):
    return page.evaluate(SCRIPT, kwargs)


def test_work_and_package_intent_errors_and_storage_are_distinct(service):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base + "/studio")
            payload = {"projectId": "artifacts/project"}
            reused = _call(
                page, kind="work", action="reuse", payload=payload, scope="artifacts/project"
            )
            assert reused["ok"] and reused["value"]["same"]
            assert len(reused["value"]["first"]) == 32

            keys = _call(
                page, kind="work", action="keys", payload=payload, scope="artifacts/project"
            )
            assert keys["ok"]
            assert keys["value"]["distinct"]
            assert keys["value"]["workKey"] == "local"
            assert keys["value"]["packageKey"] == "session"
            assert keys["value"]["workInSession"] is None
            assert keys["value"]["packageInLocal"] is None

            work_conflict = _call(
                page,
                kind="work",
                action="conflict",
                payload=payload,
                second={"projectId": "other"},
                scope="artifacts/project",
            )
            assert work_conflict["ok"] is False
            assert work_conflict["code"] == "intent.conflict"
            assert "作品请求身份" in work_conflict["message"]
            assert "平台包" not in work_conflict["message"]

            package_conflict = _call(
                page,
                kind="package",
                action="conflict",
                payload={"profile": {"Platform": "douyin"}},
                second={"profile": {"Platform": "kuaishou"}},
                scope="fixture-package",
            )
            assert package_conflict["ok"] is False
            assert package_conflict["code"] == "intent.conflict"
            assert "平台包请求身份" in package_conflict["message"]
            assert "作品" not in package_conflict["message"]

            work_save = _call(
                page, kind="work", action="save", payload={"n": 1}, scope="fixture-work-save"
            )
            assert work_save["ok"] is False
            assert work_save["code"] == "intent.storage"
            assert "作品请求身份" in work_save["message"]
            assert "本地存储" in work_save["message"]
            assert "平台包" not in work_save["message"]
            assert "会话存储" not in work_save["message"]

            package_save = _call(
                page,
                kind="package",
                action="save",
                payload={"profile": {"Platform": "bilibili"}},
                scope="fixture-package-save",
            )
            assert package_save["ok"] is False
            assert package_save["code"] == "intent.storage"
            assert "平台包请求身份" in package_save["message"]
            assert "会话存储" in package_save["message"]
            assert "作品" not in package_save["message"]

            work_read = _call(
                page, kind="work", action="read", payload={"n": 2}, scope="fixture-work-read"
            )
            assert work_read["ok"] is False
            assert work_read["code"] == "intent.storage"
            assert "作品请求身份" in work_read["message"]
            assert "本地存储" in work_read["message"]
            assert "平台包" not in work_read["message"]

            package_read = _call(
                page, kind="package", action="read", payload={"n": 3}, scope="fixture-package-read"
            )
            assert package_read["ok"] is False
            assert package_read["code"] == "intent.storage"
            assert "平台包请求身份" in package_read["message"]
            assert "会话存储" in package_read["message"]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_new_work_button_does_not_call_a_storage_error_a_package(studio):  # noqa: F811
    page, expect = studio.page, studio.expect
    page.evaluate(
        """() => {
            const original = Storage.prototype.setItem;
            Storage.prototype.setItem = function (key, value) {
                if (String(key).includes("studio-intent-v1:work:")) throw new Error("fixture storage denied");
                return original.call(this, key, value);
            };
        }"""
    )
    page.get_by_role("button", name="新建作品", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="作品请求身份")).to_be_visible()
    expect(page.get_by_text("平台包请求身份")).to_have_count(0)
    expect(page.get_by_text("本地存储")).to_be_visible()
