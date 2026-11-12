"""Real HTTP, saved plan receipts and an explicit fake text provider; no cloud calls."""

import json
import threading
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_plan_proposals import output
from test_plan_reasoning_jobs import planning as planning_fixture

from gamingcreator.application import ai_budget
from gamingcreator.application.knowledge import planning_knowledge
from gamingcreator.application.plan_proposals import (
    compile_plan_proposal,
    create_plan_snapshot,
    validate_plan_proposal,
    with_knowledge,
)
from gamingcreator.application.plan_topics import with_topics
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui import creation_jobs, server
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.plan_reasoning_jobs import original_snapshot


@pytest.fixture
def planning(service, monkeypatch):  # noqa: F811
    async def planner(project, runs, brief, destination, *args, **kwargs):
        store = await SqliteTimelineStore.open(project)
        timeline = await store.load_completed_timeline("run")
        snapshot = create_plan_snapshot(
            CreativeBrief.from_json(json.loads(brief.read_text())),
            (timeline,),
            30,
            tuple(args[0] or ()),
            kwargs.get("clip_ranges"),
        )
        report = compile_plan_proposal(
            snapshot, validate_plan_proposal(snapshot, output(snapshot, ((1, 2),)))
        )
        write_creation(destination, {"plans.json": report}, ())

    monkeypatch.setattr(creation_jobs, "execute_plan_creation", planner)
    return planning_fixture.__wrapped__(service, monkeypatch)


@pytest.fixture
def studio(planning, monkeypatch):
    pw = pytest.importorskip("playwright.sync_api")
    ctx = planning

    def factory(jobs, **kwargs):
        return CreationReasoningService(jobs, transport=ctx.transport, **kwargs)

    async def runs(project):
        return {"runs": []}

    monkeypatch.setattr(server, "CreationReasoningService", factory)
    monkeypatch.setattr(server, "project_runs_payload", runs)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-never-sent")
    # Over budget: these tests cover the per-call confirmation path (2026-11-11 budget rule).
    monkeypatch.setattr(ai_budget, "MONTHLY_CAP_CNY", Decimal(0))
    (ctx.jobs.repository / "artifacts/other").mkdir()
    (ctx.jobs.repository / "artifacts/other/timeline.sqlite3").touch()
    http = server.create_server("127.0.0.1", 0, ctx.jobs.repository)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            prefs = json.dumps({"project": "artifacts/project", "workspace": "edit"})
            last = json.dumps({"artifacts/project": {"id": ctx.root, "kind": "plan"}})
            page.add_init_script(
                "if (!sessionStorage.seeded) {sessionStorage.seeded=1;"
                f"localStorage.setItem('studio-v1', {prefs!r});"
                f"localStorage.setItem('studio-last-job-v1', {last!r});}}"
            )
            page.route("**/api/evidence?*", lambda route: route.fulfill(status=204))
            page.goto(f"http://127.0.0.1:{http.server_port}/studio")
            pw.expect(page.locator(".timeline .clip")).to_have_count(2)
            page.locator(".dynamic-planning > summary").click()
            yield SimpleNamespace(page=page, ctx=ctx, expect=pw.expect)
            assert not errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def prepare(studio):
    studio.page.get_by_role("button", name="让 AI 重新策划").click()
    studio.expect(studio.page.get_by_label("同意本次动态策划费用")).to_be_visible()
    assert not studio.ctx.transport.calls


def confirm(studio):
    studio.page.get_by_label("同意本次动态策划费用").check()
    studio.page.get_by_role("button", name="确认动态策划（最高", exact=False).click()


def test_theme_preview_adoption_and_reload(studio):
    from concurrent.futures import ThreadPoolExecutor

    from test_theme_planning_jobs import theme_root

    ctx, page, expect = studio.ctx, studio.page, studio.expect
    theme_root(ctx, ranges=True)
    store = KnowledgeStore(ctx.jobs.repository)
    store.add(
        {
            "game": "g",
            "title": "角色介绍",
            "text": "角色介绍与技能思路",
            "sourceKind": "wiki",
            "sourceLabel": "registered wiki",
        }
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        snapshot = pool.submit(original_snapshot, ctx.jobs, ctx.root).result()[0]
    snapshot = with_topics(
        with_knowledge(
            snapshot,
            planning_knowledge(
                store.entries(),
                snapshot.brief.game,
                snapshot.brief.mandatory_topics,
                snapshot.brief.objective,
            ),
        )
    )
    value = output(snapshot, ((2, 1),))
    value["schemaVersion"] = "plan-proposal-v3"
    value["plans"][0]["knowledgeUses"] = []
    for shot in value["plans"][0]["shots"]:
        shot["topicUses"] = []
    value["plans"][0]["shots"][0]["topicUses"] = [
        {
            "topic": "角色介绍",
            "rationale": "这段观察适合作为角色介绍的开场",
            "observationQuote": snapshot.payload["candidates"][1]["facts"][0],
        }
    ]
    ctx.transport.content = value
    page.evaluate(
        "id => localStorage.setItem('studio-last-job-v1', JSON.stringify({'artifacts/project': {id, kind: 'plan'}}))",
        ctx.root,
    )
    page.reload()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    page.locator(".dynamic-planning > summary").click()
    prepare(studio)
    confirm(studio)
    preview = page.get_by_label("动态方案预览")
    coverage = preview.get_by_label("方案主题安排")
    coverage.locator("summary").click()
    expect(coverage).to_contain_text("角色介绍")
    expect(coverage).to_contain_text("缺少对应画面")
    expect(coverage).to_contain_text("摘要原文：fact 2")
    expect(coverage).to_contain_text("这段观察适合作为角色介绍的开场")
    with page.expect_response(
        lambda r: r.url.split("?")[0].endswith("/edit") and ctx.root not in r.url
    ):
        page.get_by_role("button", name="采用这些方案（不再调用模型）").click()
    expect(preview).to_have_count(0)
    inspector = page.get_by_label("检查器", exact=True)
    expect(inspector.get_by_label("方案主题安排")).to_be_visible()
    inspector.get_by_label("方案主题安排").locator("summary").click()
    expect(inspector).to_contain_text("摘要原文：fact 2")
    page.reload()
    coverage = page.get_by_label("检查器", exact=True).get_by_label("方案主题安排")
    expect(coverage).to_be_visible()
    coverage.locator("summary").click()
    expect(coverage).to_contain_text("角色介绍")
    assert len(ctx.transport.calls) == 1


def test_automatic_plan_http400_preserves_recovery_after_send(studio, monkeypatch):
    monkeypatch.setattr(ai_budget, "MONTHLY_CAP_CNY", Decimal(30))
    page, expect = studio.page, studio.expect

    def lose(route):
        if route.request.post_data_json["action"] == "execute_budget":
            route.fetch()
            route.fulfill(status=400, json={"error": "result write failed"})
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", lose)
    page.get_by_role("button", name="让 AI 重新策划").click()
    recover = page.get_by_role("button", name="读取本次策划结果（不重新调用）")
    expect(recover).to_be_enabled()
    expect(page.get_by_label("同意本次动态策划费用")).to_have_count(0)
    recover.click()
    expect(page.get_by_label("动态方案预览")).to_be_visible()
    assert len(studio.ctx.transport.calls) == 1


def test_confirm_preview_adopt_and_reopen(studio):
    page, expect = studio.page, studio.expect
    prepare(studio)
    expect(page.get_by_role("button", name="确认动态策划（最高", exact=False)).to_be_disabled()
    page.get_by_text("本次将发送的文字", exact=True).click()
    expect(page.locator(".dynamic-planning pre").last).to_contain_text("candidate-3")
    artifacts = Path(__file__).resolve().parents[1] / ".cache/scratch"
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact = artifacts / "dynamic-planning-quote.png"
    page.screenshot(path=str(artifact), full_page=True)
    confirm(studio)
    preview = page.get_by_label("动态方案预览")
    expect(preview).to_contain_text("6.0 秒 / 目标 6.0 秒")
    expect(preview.locator("li").first).to_contain_text("6.0–9.0 秒")
    expect(preview.locator("li").last).to_contain_text("0.0–3.0 秒")
    page.get_by_text("本次将发送的文字", exact=True).click()
    preview.scroll_into_view_if_needed()
    page.screenshot(path=str(artifacts / "dynamic-planning-preview.png"), full_page=True)
    # showPlan writes lastJob before the asynchronous editor load; timeline
    # fallback clips are already visible then and are not an editor-ready signal.
    with page.expect_response(
        lambda response: (
            response.url.split("?")[0].endswith("/edit") and studio.ctx.root not in response.url
        )
    ) as loaded_editor:
        page.get_by_role("button", name="采用这些方案（不再调用模型）").click()
    assert loaded_editor.value.status == 200
    editor = loaded_editor.value.json()
    page.wait_for_function(
        "root => JSON.parse(localStorage.getItem('studio-last-job-v1'))['artifacts/project'].id !== root",
        arg=studio.ctx.root,
    )
    expect(page.locator(".timeline .clip")).to_have_count(2)
    expect(page.locator(".dynamic-plan-preview")).to_have_count(0)
    last = page.evaluate("JSON.parse(localStorage.getItem('studio-last-job-v1'))")
    assert editor["parentJobId"] == last["artifacts/project"]["id"]
    expect(page.get_by_role("status", name="版本保存状态")).to_have_text(
        "修改镜头、声音或叠加后可保存新版本"
    )
    page.locator(".timeline .clip").first.click()
    expect(page.get_by_label("速度")).to_have_value("1/1")
    page.reload()
    expect(page.locator(".timeline .clip")).to_have_count(2)
    assert len(studio.ctx.transport.calls) == 1
    last = page.evaluate("JSON.parse(localStorage.getItem('studio-last-job-v1'))")
    adopted = last["artifacts/project"]["id"]
    assert adopted != studio.ctx.root
    report = studio.ctx.jobs.plan_report(studio.ctx.jobs.directory(adopted))
    assert report["reasoningProvenance"]["promptVersion"] == "plan-reasoning-prompt-v1"
    assert [s["eventId"] for s in report["plans"][0]["segments"]] == ["2", "0"]


@pytest.mark.parametrize("reload_editor", [False, True])
def test_lost_execute_response_restores_without_send(studio, reload_editor):
    page, expect = studio.page, studio.expect

    def lose(route):
        if route.request.post_data_json["action"] == "execute":
            route.fetch()
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", lose)
    prepare(studio)
    confirm(studio)
    expect(page.get_by_role("button", name="读取本次策划结果（不重新调用）")).to_be_enabled()
    if reload_editor:
        page.reload()
        page.locator(".dynamic-planning > summary").click()
        page.get_by_text("已确认策划的结果记录（1）", exact=True).click()
        page.get_by_role("button", name="读取策划结果（不调用模型）").click()
    else:
        page.get_by_role("button", name="读取本次策划结果（不重新调用）").click()
    expect(page.get_by_label("动态方案预览")).to_be_visible()
    assert len(studio.ctx.transport.calls) == 1


def test_failed_restore_clears_previous_preview_and_dirty_blocks(studio):
    page, expect = studio.page, studio.expect
    prepare(studio)
    confirm(studio)
    expect(page.get_by_label("动态方案预览")).to_be_visible()

    def fail(route):
        if route.request.post_data_json["action"] == "result":
            route.fulfill(status=503, json={"message": "结果暂时不可读"})
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", fail)
    page.get_by_text("已确认策划的结果记录（1）", exact=True).click()
    page.get_by_role("button", name="读取策划结果（不调用模型）").click()
    expect(page.get_by_text("结果暂时不可读", exact=True)).to_be_visible()
    expect(page.get_by_label("动态方案预览")).to_have_count(0)
    expect(page.get_by_role("button", name="采用这些方案（不再调用模型）")).to_have_count(0)
    page.locator(".timeline .clip").first.click()
    page.get_by_label("速度").select_option("2/1")
    expect(page.get_by_role("button", name="让 AI 重新策划")).to_be_disabled()
    expect(page.get_by_role("button", name="读取策划结果（不调用模型）")).to_be_disabled()
    assert len(studio.ctx.transport.calls) == 1


def test_short_selection_shows_actual_duration_and_gap(studio):
    ctx = studio.ctx
    ctx.transport.content["plans"][0]["shots"] = [
        {"candidateId": "candidate-3", "role": "最后事件先展示"}
    ]
    prepare(studio)
    confirm(studio)
    preview = studio.page.get_by_label("动态方案预览")
    studio.expect(preview).to_contain_text("3.0 秒 / 目标 6.0 秒")
    studio.expect(preview).to_contain_text("本案选材不足：差 3.0 秒")
    studio.expect(preview.locator("ol li")).to_have_count(1)
    assert len(ctx.transport.calls) == 1


def test_project_roundtrip_discards_late_prepare(studio):
    page, expect = studio.page, studio.expect
    held = []

    def hold(route):
        if route.request.post_data_json["action"] == "prepare_plan":
            held.append(route)
        else:
            route.continue_()

    page.route("**/api/creation/reasoning", hold)
    with page.expect_request("**/api/creation/reasoning"):
        page.get_by_role("button", name="让 AI 重新策划").click()
    page.get_by_label("项目", exact=True).select_option("artifacts/other")
    expect(page.locator(".dynamic-planning")).to_have_count(0)
    page.get_by_label("项目", exact=True).select_option("artifacts/project")
    expect(page.locator(".dynamic-planning")).to_have_count(1)
    held[0].fulfill(
        json={"preparedHash": "a" * 64, "snapshotFingerprint": "b" * 64, "maxCostCny": "2"}
    )
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    expect(page.get_by_label("同意本次动态策划费用")).to_have_count(0)
    assert not studio.ctx.transport.calls


def test_job_roundtrip_discards_late_prepare(studio):
    page, expect = studio.page, studio.expect
    # Mount the production panel with real HTTP; drive parent job props through A/B/A.
    page.evaluate(
        """async root => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {PlanReasoningPanel} = await import('/assets/studio/planning.js');
        const host = document.createElement('div'); document.body.replaceChildren(host);
        window.mountPlanning = jobId => render(h(PlanReasoningPanel, {
            project:'artifacts/project', jobId, disabled:false, onAdopt:()=>{}
        }), host);
        window.mountPlanning(root);
    }""",
        studio.ctx.root,
    )
    page.locator(".dynamic-planning > summary").click()
    held = []
    page.route("**/api/creation/reasoning", lambda route: held.append(route))
    with page.expect_request("**/api/creation/reasoning"):
        page.get_by_role("button", name="让 AI 重新策划").click()
    page.evaluate("window.mountPlanning('other-job')")
    page.evaluate("root => window.mountPlanning(root)", studio.ctx.root)
    held[0].fulfill(
        json={"preparedHash": "a" * 64, "snapshotFingerprint": "b" * 64, "maxCostCny": "2"}
    )
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    expect(page.get_by_label("同意本次动态策划费用")).to_have_count(0)
    assert not studio.ctx.transport.calls


def test_clarification_preserves_initial_plan(studio):
    studio.ctx.transport.content.update(
        kind="clarification", plans=[], questions=["你想突出最后一段操作吗？"]
    )
    prepare(studio)
    confirm(studio)
    studio.expect(studio.page.get_by_text("你想突出最后一段操作吗？", exact=True)).to_be_visible()
    studio.expect(studio.page.get_by_label("动态方案预览")).to_have_count(0)
    studio.expect(
        studio.page.get_by_role("button", name="采用这些方案（不再调用模型）")
    ).to_have_count(0)
    studio.expect(studio.page.locator(".timeline .clip")).to_have_count(2)
    assert len(studio.ctx.transport.calls) == 1


@pytest.mark.parametrize("activity", ["speed", "speed-roundtrip", "project", "project-roundtrip"])
def test_edits_during_adoption_are_preserved(studio, activity):
    page, expect = studio.page, studio.expect
    prepare(studio)
    confirm(studio)
    expect(page.get_by_label("动态方案预览")).to_be_visible()
    held = []

    def hold(route):
        if route.request.url.endswith("/" + studio.ctx.root):
            route.continue_()
        else:
            held.append(route)

    page.route("**/api/creation/jobs/*", hold)
    with page.expect_request("**/api/creation/jobs/*"):
        page.get_by_role("button", name="采用这些方案（不再调用模型）").click()
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    assert held
    if activity.startswith("speed"):
        page.locator(".timeline .clip").first.click()
        page.get_by_label("速度").select_option("2/1")
        if activity == "speed-roundtrip":
            page.get_by_label("速度").select_option("1/1")
        expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
    else:
        page.get_by_label("项目", exact=True).select_option("artifacts/other")
        expect(page.locator(".dynamic-planning")).to_have_count(0)
        if activity == "project-roundtrip":
            page.get_by_label("项目", exact=True).select_option("artifacts/project")
            expect(page.locator(".dynamic-planning")).to_have_count(1)
    page.unroute("**/api/creation/jobs/*", hold)
    held[0].continue_()
    if activity == "project-roundtrip":
        # Returning to A starts another follow which cancels the adopted GET;
        # its current-job restore may replace the status message.
        expect(page.locator(".timeline .clip")).to_have_count(2)
    else:
        expect(
            page.get_by_text("动态方案已登记到作品，当前编辑已保留，可稍后打开。", exact=True)
        ).to_be_visible()
    adopted = held[0].request.url.rsplit("/", 1)[-1]
    assert finish(studio.ctx.jobs, adopted)["status"] == "completed"
    if activity.startswith("speed"):
        expect(page.get_by_label("速度")).to_have_value("2/1" if activity == "speed" else "1/1")
        expect(page.get_by_text("有未保存的修改", exact=True)).to_be_visible()
    elif activity == "project":
        expect(page.get_by_label("项目", exact=True)).to_have_value("artifacts/other")
        expect(page.locator(".dynamic-planning")).to_have_count(0)
        expect(page.locator(".timeline .clip")).to_have_count(0)
    last = page.evaluate("JSON.parse(localStorage.getItem('studio-last-job-v1'))")
    assert last["artifacts/project"]["id"] == studio.ctx.root
    assert len(studio.ctx.transport.calls) == 1


def test_registered_knowledge_quote_preview_adopt_reopen(studio):
    from test_plan_reasoning_jobs import knowledge_context, knowledge_output, prepared

    ctx, page, expect = studio.ctx, studio.page, studio.expect
    from concurrent.futures import ThreadPoolExecutor

    def register():
        _, _, entry = knowledge_context(ctx)
        prep = prepared(ctx)
        knowledge_output(ctx, prep, entry)
        return entry

    with ThreadPoolExecutor(max_workers=1) as executor:
        entry = executor.submit(register).result()
    prepare(studio)
    page.get_by_text("本次登记知识（1 条）", exact=True).click()
    expect(page.locator(".dynamic-planning")).to_contain_text(entry["text"])
    confirm(studio)
    preview = page.get_by_label("动态方案预览")
    expect(preview).to_be_visible()
    preview.locator(".knowledge-uses > summary").click()
    expect(preview).to_contain_text(entry["text"])
    expect(preview).to_contain_text(entry["source"]["label"])
    artifacts = Path(__file__).resolve().parents[1] / ".cache/scratch"
    artifacts.mkdir(parents=True, exist_ok=True)
    preview.scroll_into_view_if_needed()
    page.screenshot(path=str(artifacts / "knowledge-planning-preview.png"), full_page=True)
    page.get_by_role("button", name="采用这些方案（不再调用模型）").click()
    expect(page.locator(".dynamic-plan-preview")).to_have_count(0)
    expect(page.locator(".knowledge-uses > summary")).to_have_count(1)
    page.reload()
    expect(page.locator(".knowledge-uses > summary")).to_have_count(1)
    page.locator(".knowledge-uses > summary").click()
    expect(page.locator(".knowledge-uses")).to_contain_text(entry["text"])
    page.screenshot(path=str(artifacts / "knowledge-planning-reopened.png"), full_page=True)
    assert len(ctx.transport.calls) == 1


@pytest.mark.parametrize("lose_response", [False, True])
def test_within_budget_one_click_plans_and_a_lost_response_never_resends(
    studio, monkeypatch, lose_response
):
    """2026-11-11: inside ¥30/month and ¥1/video the AI plans on one click."""
    page, expect = studio.page, studio.expect
    monkeypatch.setattr(ai_budget, "MONTHLY_CAP_CNY", Decimal(30))

    def lose(route):
        if route.request.post_data_json["action"] == "execute_budget":
            route.fetch()
            route.abort("failed")
        else:
            route.continue_()

    if lose_response:
        page.route("**/api/creation/reasoning", lose)
    page.get_by_role("button", name="让 AI 重新策划").click()
    if lose_response:
        page.get_by_role("button", name="读取本次策划结果（不重新调用）").click()
    expect(page.get_by_label("动态方案预览")).to_contain_text("6.0 秒 / 目标 6.0 秒")
    expect(page.get_by_label("同意本次动态策划费用")).to_have_count(0)
    expect(page.get_by_label("AI预算")).to_contain_text("这条视频")
    assert len(studio.ctx.transport.calls) == 1
