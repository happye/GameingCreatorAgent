"""Real Studio/save/reload with fake reasoning HTTP protocol; no model call."""

from copy import deepcopy

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401


def test_overlay_preview_cancel_apply_and_reopen(studio_audio):  # noqa: F811
    page = studio_audio
    expect = pytest.importorskip("playwright.sync_api").expect
    editors = []
    page.on(
        "response",
        lambda response: (
            editors.append(response.json())
            if "/edit?" in response.url and response.status == 200
            else None
        ),
    )
    page.get_by_role("tab", name="叠加", exact=True).click()
    page.get_by_label("叠加文字", exact=True).fill("图层保留")
    page.get_by_role("button", name="添加文字", exact=True).click()
    expect(page.get_by_label("结束秒", exact=True)).to_be_visible()
    page.get_by_label("结束秒", exact=True).fill("1")
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("tab", name="叠加", exact=True).click()
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("1")
    page.wait_for_function("() => !!document.querySelector('[data-overlay-id]')")
    _exercise_proposal(page, editors, expect)


def _exercise_proposal(page, editors, expect):
    original = deepcopy(editors[-1])
    overlay = original["overlays"]["items"][0]
    patch = dict(overlayId=overlay["overlayId"], endFrame=90, fadeOutFrames=15)
    expected = deepcopy(original["overlays"])
    expected["items"][0].update(endFrame=90, fadeOutFrames=15)
    calls = []

    def reasoning(route):
        body = route.request.post_data_json
        calls.append(body["action"])
        if body["action"] == "prepare":
            data = dict(preparedHash="a" * 64, snapshotFingerprint="b" * 64, maxCostCny="1")
        elif body["action"] == "validate":
            data = dict(clips=original["clips"], overlays=expected)
        else:
            data = {
                "proposal": {
                    "response": dict(
                        kind="overlay_edit_proposal",
                        message="延长并淡出",
                        overlayEdit=patch,
                        clips=[],
                        questions=[],
                    )
                }
            }
        route.fulfill(json=data)

    page.route(
        "**/api/creation/reasoning/config", lambda route: route.fulfill(json={"available": True})
    )
    page.route("**/api/creation/reasoning", reasoning)
    page.get_by_label("创作助手模式").select_option("ai")
    page.get_by_label("创作对话需求").fill("这行文字多留一会儿，然后慢慢消失")

    def preview():
        page.get_by_role("button", name="准备请求（不发送）").click()
        page.get_by_label("同意本次文字发送和费用上限").check()
        page.get_by_role("button", name="确认本次调用", exact=False).click()
        expect(page.get_by_text("图层预览：", exact=False)).to_be_visible()
        expect(page.get_by_label("结束秒", exact=True)).to_have_value("1")
        expect(page.get_by_text("有未保存的修改", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="保存版本", exact=True)).to_be_disabled()

    preview()
    page.locator(".viewer").click(position={"x": 10, "y": 10})
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    image = page.locator(".viewer img[data-overlay-id]")
    expect(image).to_have_css("opacity", "1")
    page.get_by_role("button", name="关闭本次建议", exact=True).click()
    expect(image).to_have_css("opacity", "0")
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("1")
    preview()
    page.get_by_role("button", name="应用AI建议", exact=True).click()
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("3")
    expect(page.get_by_label("淡出秒", exact=True)).to_have_value("0.5")
    page.get_by_role("button", name="保存版本", exact=True).click()
    expect(page.get_by_text("已保存的版本", exact=True)).to_be_visible()
    page.reload()
    page.get_by_role("tab", name="叠加", exact=True).click()
    expect(page.get_by_label("结束秒", exact=True)).to_have_value("3")
    assert editors[-1]["overlays"] == expected
    assert calls == ["prepare", "execute", "prepare", "execute", "validate"]


HARNESS = """<script type="module">
import {h,render} from '/assets/vendor/preact.module.js';
import {useEffect,useState} from '/assets/vendor/hooks.module.js';
import {useClipEditor} from '/assets/studio/clipedit.js';
import {ReasoningDock} from '/assets/studio/reasoning.js';
import {OverlayPreview} from '/assets/studio/overlays.js';
const noop=()=>{};
function App(){
 const editing=useClipEditor('p'), [preview,setPreview]=useState(null);
 useEffect(()=>{editing.load('job','plan','plan')},[]);
 window.editing=editing;
 return h('main',{},h('p',{id:'dirty'},String(editing.dirty)),
 h(OverlayPreview,{items:preview??editing.overlays,assets:editing.overlayAssets,outUs:2000000,fps:30,width:1280,height:720}),
 h('button',{onClick:()=>editing.save(async id=>({jobId:id,status:'completed'}))},'save'),
 h(ReasoningDock,{editing,onPreview:noop,onOverlayPreview:setPreview}));
}render(h(App),document.body);
</script>"""


def _harness_editor():
    item = dict(
        overlayId="a" * 32,
        assetId="b" * 32,
        assetReceiptSha256="c" * 64,
        kind="image",
        startFrame=0,
        endFrame=30,
        fadeInFrames=0,
        fadeOutFrames=0,
        x=0,
        y=0,
        width=1000,
    )
    return dict(
        parentJobId="job",
        planId="plan",
        expectedParentReceiptSha256="d" * 64,
        fps=30,
        clips=[
            dict(
                clipId="clip",
                startUs=0,
                endUs=6000000,
                speed=dict(numerator=1, denominator=1),
                transitionIn=dict(type="cut", frames=0),
            )
        ],
        overlays=dict(schemaVersion="creation-overlays-v1", items=[item]),
        overlayAssets=[
            dict(
                assetId="b" * 32,
                assetReceiptSha256="c" * 64,
                kind="image",
                width=16,
                height=16,
                imageUrl=f"/api/creation/overlay-assets/{'b' * 32}/image",
            )
        ],
    )


def _harness_route(route, editor, saved):
    from pathlib import Path
    from urllib.parse import urlparse

    path = urlparse(route.request.url).path
    if path == "/harness":
        return route.fulfill(body=HARNESS, content_type="text/html")
    if path.startswith("/assets/"):
        asset = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static" / path[8:]
        return route.fulfill(path=asset, content_type="text/javascript")
    if path.endswith("/image"):
        return route.fulfill(status=204)
    if path.endswith("/edit"):
        return route.fulfill(json={**editor, "parentJobId": path.split("/")[-2]})
    if path.endswith("/config"):
        return route.fulfill(json=dict(available=True))
    body = route.request.post_data_json
    if path.endswith("/revisions"):
        saved.append(body)
        editor.update(overlays=body["overlays"], clips=body["clips"], parentJobId="saved")
        return route.fulfill(json=dict(jobId="saved"))
    action = body["action"]
    if action == "prepare":
        data = dict(preparedHash="e" * 64, snapshotFingerprint="f" * 64, maxCostCny="1")
    elif action == "validate":
        items = deepcopy(editor["overlays"])
        items["items"][0].update(endFrame=90, fadeOutFrames=15)
        data = dict(clips=editor["clips"], overlays=items)
    else:
        data = dict(
            proposal=dict(
                response=dict(
                    kind="overlay_edit_proposal",
                    message="延长并淡出",
                    overlayEdit=dict(overlayId="a" * 32, endFrame=90, fadeOutFrames=15),
                )
            )
        )
    return route.fulfill(json=data)


def test_overlay_hook_protocol_without_backend():
    pw = pytest.importorskip("playwright.sync_api")
    editor, saved, errors = _harness_editor(), [], []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", lambda route: _harness_route(route, editor, saved))
        page.goto("http://studio.test/harness")
        image = page.locator("img[data-overlay-id]")
        pw.expect(image).to_have_css("opacity", "0")
        page.get_by_label("创作对话需求").fill("多留一会，然后淡出")
        for cancel in (True, False):
            page.get_by_role("button", name="准备请求（不发送）").click()
            page.get_by_label("同意本次文字发送和费用上限").check()
            page.get_by_role("button", name="确认本次调用", exact=False).click()
            pw.expect(image).to_have_css("opacity", "1")
            pw.expect(page.locator("#dirty")).to_have_text("false")
            assert page.evaluate("editing.overlays[0].endFrame") == 30
            if cancel:
                page.get_by_role("button", name="关闭本次建议").click()
                pw.expect(image).to_have_css("opacity", "0")
        page.get_by_role("button", name="应用AI建议").click()
        pw.expect(page.locator("#dirty")).to_have_text("true")
        pw.expect(image).to_have_css("opacity", "1")
        page.get_by_role("button", name="save", exact=True).click()
        pw.expect(page.locator("#dirty")).to_have_text("false")
        assert saved[0]["overlays"]["items"][0]["endFrame"] == 90
        page.reload()
        pw.expect(image).to_have_css("opacity", "1")
        assert page.evaluate("editing.overlays[0].fadeOutFrames") == 15
        rejected = page.evaluate("""async () => {
            const {overlayProposalItems}=await import('/assets/studio/reasoning.js');
            const patch={overlayId:'a'.repeat(32),endFrame:90,fadeOutFrames:15};
            return [ {endFrame:181}, {endFrame:0}, {endFrame:1.5},
                {fadeOutFrames:-1}, {fadeOutFrames:91}, {assetId:'forged'},
                {overlayId:'unknown'} ].map(change=>{
                try {overlayProposalItems(editing,{...patch,...change});return false;}
                catch {return true;}
            });
        }""")
        assert all(rejected)
        page.get_by_label("创作对话需求").fill("再次预览")
        page.get_by_role("button", name="准备请求（不发送）").click()
        page.get_by_label("同意本次文字发送和费用上限").check()
        page.get_by_role("button", name="确认本次调用", exact=False).click()
        pw.expect(page.get_by_role("button", name="应用AI建议")).to_be_visible()
        page.get_by_label("创作对话需求").fill("需求已经改变")
        pw.expect(page.get_by_role("button", name="应用AI建议")).to_have_count(0)
        assert not errors
        browser.close()
