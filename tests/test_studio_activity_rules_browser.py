"""Studio rule import: real extraction, HTTP jobs and offline planning; no paid calls."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_activity_rules import RULES, site  # noqa: F401
from test_creation_jobs import service  # noqa: F401
from test_plan_reasoning_jobs import planning  # noqa: F401

from gamingcreator.cli.creation import execute_plan_creation
from gamingcreator.ui import creation_jobs, server


@pytest.fixture
def studio(planning, monkeypatch):  # noqa: F811
    pw = pytest.importorskip("playwright.sync_api")
    monkeypatch.setattr(creation_jobs, "execute_plan_creation", execute_plan_creation)

    async def runs(project):
        return {
            "runs": [
                {
                    "id": "run",
                    "status": "completed",
                    "completedEligible": True,
                    "sourceName": "规则验收录像",
                }
            ]
        }

    monkeypatch.setattr(server, "project_runs_payload", runs)
    (planning.jobs.repository / "artifacts/other").mkdir()
    (planning.jobs.repository / "artifacts/other/timeline.sqlite3").touch()
    http = server.create_server("127.0.0.1", 0, planning.jobs.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            network = []
            pending = set()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: (
                    network.append({"console": message.text}) if message.type == "error" else None
                ),
            )
            page.on("request", lambda request: pending.add(request.url))
            page.on("requestfinished", lambda request: pending.discard(request.url))
            page.on(
                "requestfailed",
                lambda request: network.append({"url": request.url, "failure": request.failure}),
            )
            page.on(
                "response",
                lambda response: (
                    network.append({"url": response.url, "status": response.status})
                    if response.status >= 400
                    else None
                ),
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.add_init_script(
                "localStorage.setItem('studio-v1', JSON.stringify({project:'artifacts/project',workspace:'edit'}))"
            )
            page.route(
                "**/api/inspect?*",
                lambda route: route.fulfill(
                    json={
                        "runId": "run",
                        "timeline": [],
                        "evidence": [],
                        "media": {"durationUs": 6000000},
                    }
                ),
            )
            try:
                page.goto(f"http://127.0.0.1:{http.server_port}/studio")
                page.get_by_role("tab", name="剪辑", exact=True).click()
            except Exception:
                try:
                    (planning.jobs.repository / "studio-bootstrap-failure.json").write_text(
                        json.dumps(
                            {
                                "url": page.url,
                                "pageErrors": errors,
                                "network": network,
                                "pending": sorted(pending),
                                "body": page.locator("body").inner_text(timeout=1000),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass  # Diagnostics must not replace the original setup exception.
                raise
            page.locator(".activity-rules > summary").click()
            yield SimpleNamespace(page=page, expect=pw.expect, ctx=planning)
            assert not errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


@pytest.mark.parametrize("source", ["text", "file"])
def test_extract_apply_and_real_plan(studio, source):
    page, expect = studio.page, studio.expect
    page.get_by_label("游戏", exact=True).fill("测试游戏")
    page.get_by_label("秒数", exact=True).fill("300")
    page.locator(".brief .runs input").check()
    if source == "text":
        page.get_by_label("规则文字").fill(RULES)
    else:
        page.get_by_label("或选择文件").set_input_files(
            {"name": "rules.txt", "mimeType": "text/plain", "buffer": RULES.encode()}
        )
    page.get_by_role("button", name="解析规则", exact=True).click()
    expect(page.locator(".rules-result")).to_contain_text("第3行")
    expect(page.get_by_label("秒数", exact=True)).to_have_value("300")
    page.get_by_label("游戏", exact=True).fill("解析后修改的游戏")
    page.locator(".brief details").last.locator("summary").click()
    page.get_by_label("创作目标", exact=True).fill("保留我的目标")
    page.get_by_label("必须包含的主题", exact=False).fill("已有主题,代号Atom新版本")
    page.get_by_role("button", name="填入创作需求", exact=True).click()
    expect(page.get_by_label("秒数", exact=True)).to_have_value("180")
    expect(page.get_by_label("创作目标", exact=True)).to_have_value("保留我的目标")
    topics = page.get_by_label("必须包含的主题", exact=False)
    expect(topics).to_have_value("已有主题, 代号Atom新版本, 星际奔跑")
    topics.fill(topics.input_value() + ", 新增话题")
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/api/creation/plans")
    ) as accepted:
        page.get_by_role("button", name="生成方案", exact=True).click()
    job_id = accepted.value.json()["jobId"]
    from test_creation_jobs import finish

    assert finish(studio.ctx.jobs, job_id)["status"] == "completed"
    report = studio.ctx.jobs.plan_report(studio.ctx.jobs.directory(job_id))
    brief = report["brief"]
    assert brief["game"] == "解析后修改的游戏"
    assert brief["objective"] == "保留我的目标"
    assert brief["targetDuration"] == 180
    assert brief["platforms"] == ["douyin"]
    assert brief["contentType"] == "campaign"
    assert brief["mandatoryTopics"] == ["已有主题", "代号Atom新版本", "星际奔跑", "新增话题"]
    folder = Path(".cache/scratch/studio-activity-rules")
    folder.mkdir(parents=True, exist_ok=True)
    expect(page.locator(".plan").first).to_be_visible()
    page.locator(".rules-result").scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
    page.screenshot(path=str(folder / f"{source}-viewport.png"))


def test_invalid_and_unknown_inputs(studio):
    page, expect = studio.page, studio.expect
    page.get_by_label("或选择文件").set_input_files(
        {"name": "rules.exe", "mimeType": "application/octet-stream", "buffer": b"bad"}
    )
    page.get_by_role("button", name="解析规则", exact=True).click()
    expect(page.locator(".activity-rules [role=status]")).to_contain_text("未能解析")
    page.get_by_label("或选择文件").set_input_files([])
    page.get_by_label("规则文字").fill("欢迎踊跃参加")
    page.get_by_role("button", name="解析规则", exact=True).click()
    expect(page.locator(".rules-result")).to_contain_text("未识别")
    page.get_by_role("button", name="填入创作需求", exact=True).click()
    expect(page.get_by_label("秒数", exact=True)).to_have_value("60")
    page.get_by_label("规则文字").fill("新规则")
    expect(page.get_by_role("button", name="填入创作需求", exact=True)).to_have_count(0)


def test_web_address_reads_page_once_and_shows_provenance(studio, site):  # noqa: F811
    page, expect = studio.page, studio.expect
    page.get_by_label("规则文字").fill("会被网页地址覆盖的文字")
    page.get_by_label("或网页地址").fill(site + "/rules.html")
    expect(page.locator(".activity-rules")).to_contain_text("将读取网页（优先于文字）")
    page.get_by_role("button", name="解析规则", exact=True).click()
    result = page.locator(".rules-result")
    expect(result).to_contain_text("来源：网页（" + site + "/rules.html，读取于")
    expect(page.locator(".activity-rules [role=status]")).to_contain_text("识别到 8/8 项")
    expect(result).to_contain_text("星际奔跑")
    page.get_by_label("或网页地址").fill("ftp://example.com/rules")
    page.get_by_role("button", name="解析规则", exact=True).click()
    expect(page.locator(".activity-rules [role=status]")).to_contain_text("http:// 或 https://")


@pytest.mark.parametrize("change", ["input", "aba", "unmount", "request"])
@pytest.mark.parametrize("failure", [False, True])
def test_late_results_ignore_abort(studio, change, failure):
    page, expect = studio.page, studio.expect
    # Hold only this endpoint in the browser, deliberately ignoring AbortSignal.
    page.evaluate("""() => {
        const original = window.fetch;
        window.pendingRules = [];
        window.fetch = (url, options) => String(url).includes('/api/creation/activity-rules')
            ? new Promise((resolve, reject) => pendingRules.push({resolve, reject}))
            : original(url, options);
    }""")
    page.get_by_label("规则文字").fill(RULES)
    page.get_by_role("button", name="解析规则", exact=True).click()
    if change == "input":
        page.get_by_label("规则文字").fill("新规则")
    elif change == "request":
        page.get_by_role("button", name="重新解析规则", exact=True).click()
    elif change == "aba":
        project = page.get_by_label("项目", exact=True)
        original = project.input_value()
        project.select_option("artifacts/other")
        expect(page.get_by_label("规则文字")).to_have_value("")
        project.select_option(original)
        page.locator(".activity-rules > summary").click()
    else:
        page.get_by_role("tab", name="素材", exact=True).click()
        page.get_by_role("tab", name="剪辑", exact=True).click()
        page.locator(".activity-rules > summary").click()
    from gamingcreator.application.activity_rules import extract_activity_rules

    payload = {**extract_activity_rules(RULES), "source": {"sourceKind": "pasted"}}
    page.evaluate(
        """({failure, payload}) => {
        if (failure) pendingRules[0].reject(new Error('迟到错误'));
        else pendingRules[0].resolve(new Response(JSON.stringify(payload), {status:200}));
    }""",
        {"failure": failure, "payload": payload},
    )
    # A later task gives promise handlers and Preact rendering a chance to finish.
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    expect(page.locator(".rules-result")).to_have_count(0)
    expect(page.locator(".activity-rules")).not_to_contain_text("迟到错误")


def test_duration_conflict_and_plan_gate(studio):
    page, expect = studio.page, studio.expect
    page.get_by_label("规则文字").fill("视频时长不少于90秒，不超过30秒")
    page.get_by_role("button", name="解析规则", exact=True).click()
    expect(page.locator(".rules-result")).to_be_visible()
    page.get_by_role("button", name="填入创作需求", exact=True).click()
    expect(page.get_by_label("秒数", exact=True)).to_have_value("60")
    expect(page.locator(".rules-result")).to_contain_text("未识别")
    response = page.request.post(
        page.url.split("/studio")[0] + "/api/entitlement", data={"plan": "free"}
    )
    assert response.ok
    page.get_by_role("button", name="解析规则", exact=True).click()
    expect(page.locator(".activity-rules [role=status]")).to_contain_text("未能解析")
    expect(page.locator(".rules-result")).to_have_count(0)
