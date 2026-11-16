"""Plan-area compare entry is read-only and shows actual duration, shot count, and gaps."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from gamingcreator.ui import server

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


@pytest.fixture
def page(tmp_path):
    http = server.create_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    pw = pytest.importorskip("playwright.sync_api")
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            opened = browser.new_page(viewport={"width": 1280, "height": 800})
            errors = []
            opened.on("pageerror", lambda error: errors.append(str(error)))
            requests = []
            opened.on("request", lambda request: requests.append(request.url))
            opened.goto(f"http://127.0.0.1:{http.server_port}/")
            yield SimpleNamespace(page=opened, expect=pw.expect, errors=errors, requests=requests)
            assert not errors
            browser.close()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


SHARED = [
    {"sourceSha256": "aa", "startUs": 0, "endUs": 2_000_000, "outputFrames": 60},
    {"sourceSha256": "bb", "startUs": 0, "endUs": 2_000_000, "outputFrames": 60},
]
PLANS = [
    {"id": "guide-steps", "structure": "按步骤展开", "ready": True, "segments": SHARED, "gaps": []},
    {
        "id": "hook-first",
        "structure": "最后一条先作开场，再回溯",
        "ready": True,
        "segments": SHARED,
        "gaps": [],
    },
    {
        "id": "reverse",
        "structure": "倒序逐条回顾",
        "ready": False,
        "segments": [SHARED[0]],
        "gaps": ["不足三个不同源区间，不能形成完整的三段结构"],
    },
]


def _mount(page, plans, fps):
    page.page.evaluate(
        """async ({plans, fps}) => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {PlanCompare, openPlanComparison} = await import('/assets/studio/compare.js');
        const host = document.createElement('div');
        document.body.replaceChildren(host);
        window.adoptedId = 'guide-steps';
        window.openPlanComparison = openPlanComparison;
        render(h(PlanCompare, {plans, adoptedId: window.adoptedId, fps}), host);
    }""",
        {"plans": plans, "fps": fps},
    )


def test_compare_entry_opens_readonly_view_without_changing_adoption(page):
    _mount(page, PLANS, 30)
    locator = page.page
    expect = page.expect
    expect(locator.locator("#plan-compare-open")).to_be_disabled()
    locator.locator("#plan-compare-left").select_option("hook-first")
    locator.locator("#plan-compare-right").select_option("hook-first")
    expect(locator.locator("#plan-compare-open")).to_be_disabled()
    locator.locator("#plan-compare-right").select_option("reverse")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-view")).to_be_visible()
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-readonly", "true")
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-adopted", "guide-steps")
    left = locator.get_by_role("region", name="方案 A")
    right = locator.get_by_role("region", name="方案 B")
    expect(left).to_contain_text("最后一条先作开场，再回溯")
    expect(left).to_contain_text("总长 4.0 秒（120 帧）")
    expect(left).to_contain_text("镜头数 2")
    expect(left).to_contain_text("没有缺口")
    expect(right).to_contain_text("倒序逐条回顾")
    expect(right).to_contain_text("总长 2.0 秒（60 帧）")
    expect(right).to_contain_text("镜头数 1")
    expect(right).to_contain_text("缺口：不足三个不同源区间，不能形成完整的三段结构")
    alignment = locator.locator("#plan-compare-alignment")
    expect(alignment).to_contain_text("按真实素材身份对齐相同来源")
    expect(alignment).to_contain_text("来源 aa")
    expect(alignment).to_contain_text("方案 A：第 1 镜 · 成片 0.0–2.0 秒（0–60 帧）")
    expect(alignment).to_contain_text("方案 B：第 1 镜 · 成片 0.0–2.0 秒（0–60 帧）")
    expect(alignment).to_contain_text("来源 bb")
    expect(alignment).to_contain_text("方案 A：第 2 镜 · 成片 2.0–4.0 秒（60–120 帧）")
    expect(alignment).to_contain_text("方案 B：这一侧没有这个来源")
    changes = locator.locator("#plan-compare-changes")
    expect(changes).to_contain_text("按素材的真实来源区间比较")
    expect(changes.locator('li[data-change="same"]')).to_contain_text("来源 aa")
    expect(changes.locator('li[data-change="same"]')).to_contain_text("两边都有，顺序一致")
    expect(changes.locator('li[data-change="missing"]')).to_contain_text("来源 bb")
    expect(changes.locator('li[data-change="same"]')).to_contain_text(
        "原片 0 微秒（0 秒） 到 2000000 微秒（2 秒）"
    )
    expect(changes.locator('li[data-change="same"]')).to_contain_text("成片 60 帧")
    expect(changes.locator('li[data-change="same"]')).to_contain_text("速度 1")
    expect(changes.locator('li[data-change="missing"]')).to_contain_text("方案 B 缺少")
    assert page.page.evaluate("window.adoptedId") == "guide-steps"
    assert not any("plan_proposals" in url or "reasoning" in url for url in page.requests)
    locator.locator("#plan-compare-close").click()
    expect(locator.locator("#plan-compare-view")).to_have_count(0)
    assert page.page.evaluate("window.adoptedId") == "guide-steps"


def test_compare_metrics_ignore_template_names_and_keep_unknowns(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
        {"id": "mystery", "structure": "名称完全不同的模板"},
    ]
    _mount(page, plans, None)
    locator = page.page
    expect = page.expect
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    left = locator.get_by_role("region", name="方案 A")
    right = locator.get_by_role("region", name="方案 B")
    expect(left).to_contain_text("总长未知（120 帧，缺帧率）")
    expect(right).to_contain_text("总长未知（120 帧，缺帧率）")
    expect(left).to_contain_text("镜头数 2")
    expect(right).to_contain_text("镜头数 2")
    expect(left).to_contain_text("没有缺口")
    expect(right).to_contain_text("没有缺口")
    alignment = locator.locator("#plan-compare-alignment")
    expect(alignment).to_contain_text("来源 aa")
    expect(alignment).to_contain_text("方案 A：第 1 镜 · 成片 0–60 帧")
    expect(alignment).to_contain_text("方案 B：第 1 镜 · 成片 0–60 帧")
    expect(alignment).to_contain_text("来源 bb")
    expect(alignment).to_contain_text("方案 A：第 2 镜 · 成片 60–120 帧")
    expect(alignment).to_contain_text("方案 B：第 2 镜 · 成片 60–120 帧")
    locator.locator("#plan-compare-close").click()
    locator.locator("#plan-compare-right").select_option("mystery")
    locator.locator("#plan-compare-open").click()
    expect(locator.get_by_role("region", name="方案 B")).to_contain_text("总长未知")
    expect(locator.get_by_role("region", name="方案 B")).to_contain_text("镜头数未知")
    expect(locator.get_by_role("region", name="方案 B")).to_contain_text("缺口未知")
    expect(locator.get_by_role("region", name="方案 B")).not_to_contain_text(
        "名称完全不同的模板算内容不同"
    )
    expect(locator.locator("#plan-compare-alignment")).to_contain_text(
        "两侧片段不完整，来源对齐未知。"
    )
    assert page.page.evaluate("window.adoptedId") == "guide-steps"


def test_shot_changes_split_intervals_and_ignore_duplicate_ids(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "segments": [
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                    "eventId": "clip-1",
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "bb",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                    "eventId": "clip-2",
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "cc",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                },
            ],
            "gaps": [],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "ready": True,
            "segments": [
                {
                    "runId": "run-1",
                    "sourceSha256": "cc",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 1_000_000,
                    "endUs": 3_000_000,
                    "outputFrames": 60,
                    "eventId": "clip-1",
                },
            ],
            "gaps": [],
        },
    ]
    _mount(page, plans, 30)
    locator = page.page
    expect = page.expect
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    changes = locator.locator("#plan-compare-changes")
    expect(changes.locator('li[data-change="missing"]')).to_have_count(2)
    expect(changes.locator('li[data-change="added"]')).to_have_count(1)
    expect(changes.locator('li[data-change="reordered"]')).to_contain_text("来源 cc")
    expect(changes.locator('li[data-change="reordered"]')).to_contain_text("换序")
    expect(changes.locator('li[data-change="missing"]').nth(0)).to_contain_text("来源 aa")
    expect(changes.locator('li[data-change="missing"]').nth(0)).to_contain_text("原片 0.0–2.0 秒")
    expect(changes.locator('li[data-change="added"]')).to_contain_text("来源 aa")
    expect(changes.locator('li[data-change="added"]')).to_contain_text("原片 1.0–3.0 秒")
    expect(changes.locator('li[data-change="added"]')).to_contain_text("方案 B 新增")
    expect(changes.locator('li[data-change="missing"]').nth(0)).to_contain_text(
        "2000000 微秒（2 秒）"
    )
    expect(changes.locator('li[data-change="added"]')).to_contain_text("1000000 微秒（1 秒）")
    expect(changes.locator('li[data-change="added"]')).to_contain_text("3000000 微秒（3 秒）")
    expect(changes.locator('li[data-change="added"]')).to_contain_text("速度 1")
    expect(changes.locator('li[data-change="missing"]').nth(1)).to_contain_text("来源 bb")


def test_compare_shows_theme_reasons_or_explicitly_says_missing(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "segments": [
                {
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                    "scriptDraft": "角色在草地上奔跑",
                    "topicUses": [
                        {
                            "topic": "玩法展示",
                            "rationale": "用开场操作说明核心玩法",
                            "observationQuote": "角色在草地上奔跑",
                        }
                    ],
                }
            ],
            "gaps": [],
        },
        {
            "id": "reverse",
            "structure": "倒序逐条回顾",
            "ready": True,
            "segments": [
                {
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                    "scriptDraft": "角色在草地上奔跑",
                }
            ],
            "gaps": [],
        },
    ]
    _mount(page, plans, 30)
    locator = page.page
    expect = page.expect
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("reverse")
    locator.locator("#plan-compare-open").click()
    reasons = locator.locator("#plan-compare-reasons")
    expect(reasons).to_be_visible()
    left = locator.get_by_role("region", name="主题理由与原始说明（左侧）")
    right = locator.get_by_role("region", name="主题理由与原始说明（右侧）")
    expect(left).to_contain_text("镜头 1")
    expect(left).to_contain_text("主题 玩法展示")
    expect(left).to_contain_text("主题理由：用开场操作说明核心玩法")
    expect(left).to_contain_text("引用的原始说明：角色在草地上奔跑")
    expect(right).to_contain_text("未提供主题理由与原始说明")
    expect(right).not_to_contain_text("倒序逐条回顾")
    expect(right).not_to_contain_text("角色在草地上奔跑")
    expect(reasons).to_contain_text("不会按模板或规则补写成解释")


def test_compare_locates_preview_from_either_side_without_changing_adoption(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
    ]
    page.page.evaluate(
        """async ({plans, fps}) => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {PlanCompare, locatePreviewTarget} = await import('/assets/studio/compare.js');
        const host = document.createElement('div');
        document.body.replaceChildren(host);
        window.adoptedId = 'guide-steps';
        window.locates = [];
        window.dirty = false;
        const target = locatePreviewTarget(plans[1], {startFrame: 60}, 30);
        window.locateTargetSample = target;
        render(h(PlanCompare, {
            plans,
            adoptedId: window.adoptedId,
            fps,
            onLocate: (detail) => { window.locates.push(detail); },
        }), host);
    }""",
        {"plans": plans, "fps": 30},
    )
    locator = page.page
    expect = page.expect
    sample = locator.evaluate("window.locateTargetSample")
    assert sample == {"planId": "hook-first", "outStartUs": 2_000_000, "startFrame": 60}
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-adopted", "guide-steps")
    locator.locator('#plan-compare-alignment button[data-side="left"]').first.click()
    locator.locator('#plan-compare-alignment button[data-side="right"]').first.click()
    locates = locator.evaluate("window.locates")
    assert [row["side"] for row in locates] == ["left", "right"]
    assert locates[0]["planId"] == "guide-steps"
    assert locates[1]["planId"] == "hook-first"
    assert locates[0]["outStartUs"] == 0
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-adopted", "guide-steps")
    assert locator.evaluate("window.adoptedId") == "guide-steps"
    assert locator.evaluate("window.dirty") is False


def test_compare_locate_respects_audio_task_gate(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
    ]
    page.page.evaluate(
        """async ({plans, fps}) => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {PlanCompare} = await import('/assets/studio/compare.js');
        const host = document.createElement('div');
        document.body.replaceChildren(host);
        window.adoptedId = 'guide-steps';
        window.locates = [];
        render(h(PlanCompare, {
            plans,
            adoptedId: window.adoptedId,
            fps,
            locateBlocked: "声音任务正在处理，完成后可定位预览",
            onLocate: (detail) => { window.locates.push(detail); },
        }), host);
    }""",
        {"plans": plans, "fps": 30},
    )
    locator = page.page
    expect = page.expect
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    expect(locator.locator("#plan-compare-open")).to_be_enabled()
    locator.locator("#plan-compare-open").click()
    button = locator.locator("#plan-compare-alignment button.plan-compare-locate").first
    expect(button).to_be_disabled()
    expect(button).to_have_attribute("title", "声音任务正在处理，完成后可定位预览")
    button.click(force=True)
    assert locator.evaluate("window.locates") == []
    assert locator.evaluate("window.adoptedId") == "guide-steps"


def test_compare_resets_on_scope_change_and_close_keeps_adoption_and_dirty(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "ready": True,
            "segments": SHARED,
            "gaps": [],
        },
    ]
    page.page.evaluate(
        """async ({plans, fps}) => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {PlanCompare} = await import('/assets/studio/compare.js');
        const host = document.createElement('div');
        document.body.replaceChildren(host);
        window.adoptedId = 'guide-steps';
        window.dirty = true;
        window.comparePreview = {planId: 'hook-first'};
        window.closeCount = 0;
        window.mount = (scope, samePlans = plans) => {
            render(h(PlanCompare, {
                plans: samePlans,
                adoptedId: window.adoptedId,
                fps,
                compareScope: scope,
                onClose: () => { window.comparePreview = null; window.closeCount += 1; },
            }), host);
        };
        window.mount('project-one:work-a:job-1');
    }""",
        {"plans": plans, "fps": 30},
    )
    locator = page.page
    expect = page.expect
    expect(locator.locator("#plan-compare")).to_have_attribute(
        "data-compare-scope", "project-one:work-a:job-1"
    )
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-view")).to_be_visible()
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-adopted", "guide-steps")
    locator.evaluate("window.comparePreview = {planId: 'hook-first'}")
    close_before = locator.evaluate("window.closeCount")
    locator.locator("#plan-compare-close").click()
    expect(locator.locator("#plan-compare-view")).to_have_count(0)
    assert locator.evaluate("window.adoptedId") == "guide-steps"
    assert locator.evaluate("window.dirty") is True
    assert locator.evaluate("window.comparePreview") is None
    assert locator.evaluate("window.closeCount") == close_before + 1
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-view")).to_be_visible()
    locator.evaluate(
        """() => {
        window.comparePreview = {planId: 'hook-first'};
        const copied = window.mount.__plans || null;
        window.mount('project-one:work-b:job-2', [
            {id: 'guide-steps', structure: '按步骤展开', ready: true, segments: [{sourceSha256: 'aa', startUs: 0, endUs: 2000000, outputFrames: 60}, {sourceSha256: 'bb', startUs: 0, endUs: 2000000, outputFrames: 60}], gaps: []},
            {id: 'hook-first', structure: '最后一条先作开场，再回溯', ready: true, segments: [{sourceSha256: 'aa', startUs: 0, endUs: 2000000, outputFrames: 60}, {sourceSha256: 'bb', startUs: 0, endUs: 2000000, outputFrames: 60}], gaps: []},
        ]);
    }"""
    )
    expect(locator.locator("#plan-compare")).to_have_attribute(
        "data-compare-scope", "project-one:work-b:job-2"
    )
    expect(locator.locator("#plan-compare-view")).to_have_count(0)
    assert locator.evaluate("document.querySelector('#plan-compare-left').value") == ""
    assert locator.evaluate("document.querySelector('#plan-compare-right').value") == ""
    assert locator.evaluate("window.adoptedId") == "guide-steps"
    assert locator.evaluate("window.dirty") is True
    assert locator.evaluate("window.comparePreview") is None
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-view")).to_be_visible()
    locator.evaluate(
        """() => {
        const plans = [
            {id: 'guide-steps', structure: '按步骤展开', ready: true, segments: [{sourceSha256: 'aa', startUs: 0, endUs: 2000000, outputFrames: 60}, {sourceSha256: 'bb', startUs: 0, endUs: 2000000, outputFrames: 60}], gaps: []},
            {id: 'hook-first', structure: '最后一条先作开场，再回溯', ready: true, segments: [{sourceSha256: 'aa', startUs: 0, endUs: 2000000, outputFrames: 60}, {sourceSha256: 'bb', startUs: 0, endUs: 2000000, outputFrames: 60}], gaps: []},
        ];
        window.mount('project-one:work-b:job-2', plans);
    }"""
    )
    expect(locator.locator("#plan-compare-view")).to_be_visible()
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-adopted", "guide-steps")
    assert locator.evaluate("window.adoptedId") == "guide-steps"
    assert locator.evaluate("window.dirty") is True


def test_compare_json_download_exports_diffs_and_sources_without_changing_adoption(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "contentSignature": "sig-left",
            "ready": True,
            "segments": [
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                    "scriptDraft": "角色在草地上奔跑",
                    "topicUses": [
                        {
                            "topic": "玩法展示",
                            "rationale": "用开场操作说明核心玩法",
                            "observationQuote": "角色在草地上奔跑",
                        }
                    ],
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "bb",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                },
            ],
            "gaps": [],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "contentSignature": "sig-right",
            "ready": True,
            "segments": [
                {
                    "runId": "run-1",
                    "sourceSha256": "bb",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 2_000_000,
                    "outputFrames": 60,
                },
            ],
            "gaps": [],
        },
    ]
    page.page.evaluate(
        """async ({plans, fps}) => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {PlanCompare, comparisonExportDocument, comparisonExportFilename} = await import('/assets/studio/compare.js');
        const host = document.createElement('div');
        document.body.replaceChildren(host);
        window.adoptedId = 'guide-steps';
        window.dirty = true;
        window.comparisonExportDocument = comparisonExportDocument;
        window.comparisonExportFilename = comparisonExportFilename;
        render(h(PlanCompare, {plans, adoptedId: window.adoptedId, fps, compareScope: 'project-one:work-a:job-1'}), host);
    }""",
        {"plans": plans, "fps": 30},
    )
    locator = page.page
    expect = page.expect
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-download")).to_be_visible()
    expect(locator.locator("#plan-compare-download")).to_have_text("下载对照 JSON")
    before = list(page.requests)
    with locator.expect_download() as pending:
        locator.locator("#plan-compare-download").click()
    download = pending.value
    assert download.suggested_filename == "plan-comparison-guide-steps-hook-first.json"
    payload = json.loads(Path(download.path()).read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == "plan-comparison-export-v1"
    assert payload["readonly"] is True
    assert payload["note"] == "只包含这次对照的差异和来源，不会写回报告、证据或偏好。"
    assert payload["left"]["planId"] == "guide-steps"
    assert payload["right"]["planId"] == "hook-first"
    assert payload["left"]["contentSignature"] == "sig-left"
    assert {row["sourceSha256"] for row in payload["sources"]} == {"aa", "bb"}
    assert any(row["status"] == "reordered" for row in payload["shotChanges"])
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "scriptDraft" not in dumped
    assert "按步骤展开" not in dumped
    assert "eventId" not in dumped
    assert locator.evaluate("window.adoptedId") == "guide-steps"
    assert locator.evaluate("window.dirty") is True
    expect(locator.locator("#plan-compare-view")).to_have_attribute("data-adopted", "guide-steps")
    new_requests = [url for url in page.requests[len(before) :]]
    assert all("/api/" not in url for url in new_requests)
    locator.locator("#plan-compare-close").click()
    expect(locator.locator("#plan-compare-download")).to_have_count(0)


def test_concatenable_alignment_does_not_claim_source_missing(page):
    plans = [
        {
            "id": "guide-steps",
            "structure": "按步骤展开",
            "ready": True,
            "gaps": [],
            "segments": [
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 3_000_000,
                    "outputFrames": 90,
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 3_000_000,
                    "endUs": 6_000_000,
                    "outputFrames": 90,
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 6_000_000,
                    "endUs": 9_000_000,
                    "outputFrames": 90,
                },
            ],
        },
        {
            "id": "hook-first",
            "structure": "最后一条先作开场，再回溯",
            "ready": True,
            "gaps": [],
            "segments": [
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 6_000_000,
                    "endUs": 9_000_000,
                    "outputFrames": 90,
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 0,
                    "endUs": 3_000_000,
                    "outputFrames": 90,
                },
                {
                    "runId": "run-1",
                    "sourceSha256": "aa",
                    "startUs": 3_000_000,
                    "endUs": 6_000_000,
                    "outputFrames": 90,
                },
            ],
        },
    ]
    _mount(page, plans, 30)
    locator = page.page
    locator.locator("#plan-compare-left").select_option("guide-steps")
    locator.locator("#plan-compare-right").select_option("hook-first")
    locator.locator("#plan-compare-open").click()
    expect(locator.locator("#plan-compare-view")).to_be_visible()
    left = locator.get_by_role("region", name="方案 A")
    right = locator.get_by_role("region", name="方案 B")
    expect(left).to_contain_text("镜头数 1")
    expect(right).to_contain_text("镜头数 2")
    alignment = locator.locator("#plan-compare-alignment")
    expect(alignment).to_contain_text("同一来源在这一侧的切分不同，不是缺少这趟素材")
    expect(alignment).not_to_contain_text("这一侧没有这个来源")
    changes = locator.locator("#plan-compare-changes")
    expect(changes.locator('li[data-change="reordered"]')).to_have_count(3)
    assert page.page.evaluate("window.adoptedId") == "guide-steps"
