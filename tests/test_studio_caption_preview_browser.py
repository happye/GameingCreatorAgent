"""Browser preview uses paused output time and rejects stale draft responses."""

# ruff: noqa: F811
import pytest
from test_clip_replacement_jobs import replacements  # noqa: F401
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401
from test_studio_caption_editor_browser import select_shot

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def test_caption_preview_debounce_and_immediate_clear(studio_audio):
    page = studio_audio
    field = select_shot(page)
    page.get_by_role("tab", name="导出", exact=True).click()
    page.locator("select").filter(has=page.locator('option[value="burn"]')).select_option("burn")
    field = select_shot(page)
    field.fill("暂停可见字幕")
    expect(page.get_by_label("字幕预览", exact=True)).to_contain_text("暂停可见字幕", timeout=20000)
    calls = []
    page.on(
        "request",
        lambda request: calls.append(request) if "/subtitle-preview" in request.url else None,
    )
    field.fill("防抖一")
    field.fill("防抖二")
    field.fill("防抖三")
    expect(page.get_by_label("字幕预览", exact=True)).not_to_contain_text("暂停可见字幕")
    expect(page.get_by_label("字幕预览", exact=True)).to_contain_text("防抖三")
    assert len(calls) == 1
    page.locator(".timeline .clip").nth(1).focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(350)
    assert len(calls) == 1

    page.get_by_role("tab", name="导出", exact=True).click()
    page.locator("select").filter(has=page.locator('option[value="burn"]')).select_option("none")
    expect(page.get_by_label("字幕预览", exact=True)).to_be_empty()


@pytest.mark.parametrize("identity", ["project", "parent", "none"])
@pytest.mark.parametrize("outcome", ["success", "error"])
def test_late_response_with_ineffective_abort(studio_audio, identity, outcome):
    page = studio_audio
    page.evaluate("""async () => {
        const {h, render} = await import('/assets/vendor/preact.module.js');
        const {useSubtitlePreview, SubtitlePreview} = await import('/assets/studio/subtitles.js');
        const host = document.createElement('div'); document.body.append(host);
        const original = window.fetch, pending = [];
        window.fetch = (url, options) => String(url).includes('/subtitle-preview')
            ? new Promise((resolve, reject) => pending.push({resolve, reject})) : original(url, options);
        let settings = {project: 'A', parent: 'parent-a', mode: 'burn'};
        function View() {
            const editing = {status:'ready', base:{jobId:settings.parent, planId:'plan'},
                editor:{expectedParentReceiptSha256:'a'.repeat(64)}, subtitleOverrides:[], replacements:{}};
            const state = useSubtitlePreview(settings.project, editing,
                [{clipId:'clip', startUs:0, endUs:1000000, speed:{numerator:1, denominator:1}, transitionIn:{type:'cut', frames:0}}], settings.mode);
            return h('div', {id:'late-preview'}, h(SubtitlePreview, {cues:state.cues, outUs:100000}),
                h('span', {id:'late-status'}, state.status));
        }
        window.latePreview = {
            pending, update(value) {settings={...settings,...value}; render(h(View),host);},
            finish(index, error, text) {const p=pending[index];
                if(error) p.reject(new Error('迟到错误'));
                else p.resolve({ok:true,json:async()=>({cues:[{startUs:0,endUs:1000000,text,lifted:false}]})});}
        };
        render(h(View),host);
    }""")
    page.wait_for_function("() => latePreview.pending.length === 1")
    change = {
        "project": {"project": "B"},
        "parent": {"parent": "parent-b"},
        "none": {"mode": "none"},
    }[identity]
    page.evaluate("value => latePreview.update(value)", change)
    if identity != "none":
        page.wait_for_function("() => latePreview.pending.length === 2")
        page.evaluate("latePreview.finish(1, false, '当前字幕')")
        expect(page.locator("#late-preview")).to_contain_text("当前字幕")
    page.evaluate("error => latePreview.finish(0, error, '过期字幕')", outcome == "error")
    page.wait_for_timeout(100)
    expect(page.locator("#late-preview")).not_to_contain_text("过期字幕")
    expect(page.locator("#late-preview")).not_to_contain_text("迟到错误")
    if identity == "none":
        expect(page.locator("#late-status")).to_have_text("不加字幕")
    else:
        expect(page.locator("#late-preview")).to_contain_text("当前字幕")
