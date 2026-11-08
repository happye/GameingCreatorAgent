"""Adversarial downloads against the real EditWorkspace, with ineffective fetch abort."""

# ruff: noqa: F811
import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


@pytest.fixture
def timeline_view(studio_audio):
    page = studio_audio
    page.evaluate("""async () => {
        const {h,render}=await import('/assets/vendor/preact.module.js');
        const {EditWorkspace}=await import('/assets/studio/edit.js');
        const last=JSON.parse(localStorage.getItem('studio-last-job-v1'))['artifacts/project'];
        const revision=await (await fetch(`/api/creation/jobs/${last.id}`)).json();
        const host=document.createElement('div'); host.id='timeline-harness';
        host.style='position:fixed;inset:0;background:white;z-index:9999';document.body.append(host);
        let props={project:'artifacts/project',runs:[],open:last,onWorksChanged(){},
            layout:{insp:true,brief:true},basket:{items:[]},onBasketSeen(){}};
        const original=window.fetch, create=URL.createObjectURL.bind(URL), pending=[];
        const observations={urls:0,clicks:0};
        URL.createObjectURL=(blob)=>{observations.urls++;return create(blob);};
        host.addEventListener('click',e=>{if(e.target.closest('a[download]'))observations.clicks++;});
        window.fetch=(url,options)=>String(url).includes('/timeline?')
            ? new Promise((resolve,reject)=>pending.push({resolve,reject,signal:options.signal}))
            : original(url,options);
        window.timelineHarness={pending,observations,
            change(kind){if(kind==='unmount'){render(null,host);return;}
                if(kind==='project')props={...props,project:'artifacts/other',open:null};
                if(kind==='base')props={...props,open:{id:revision.parentJobId,kind:'plan',planId:'hook-first'}};
                render(h(EditWorkspace,props),host);},
            finish(error,status=200){if(error)pending[0].reject(new Error('迟到错误'));
                else pending[0].resolve(new Response(status===200?'<xmeml/>':JSON.stringify({message:'下载被拒绝'}),
                    {status,headers:{'Content-Type':status===200?'application/xml':'application/json'}}));}
        };
        render(h(EditWorkspace,props),host);
    }""")
    view = page.locator("#timeline-harness")
    view.get_by_role("tab", name="导出", exact=True).click()
    expect(view.get_by_role("button", name="下载 Premiere XML", exact=True)).to_be_enabled()
    return page, view


@pytest.mark.parametrize("identity", ["project", "base", "unmount"])
@pytest.mark.parametrize("outcome", ["success", "error"])
def test_late_download_is_rejected(timeline_view, identity, outcome):
    page, view = timeline_view
    downloads = []
    page.on("download", lambda download: downloads.append(download))
    view.get_by_role("button", name="下载 Premiere XML", exact=True).click()
    page.wait_for_function("timelineHarness.pending.length === 1")
    page.evaluate("kind=>timelineHarness.change(kind)", identity)
    if identity == "base":
        expect(view.get_by_text("方案原样", exact=True)).to_be_visible()
    elif identity == "project":
        expect(view.locator(".timeline .clip")).to_have_count(0)
    else:
        expect(view).to_be_empty()
    page.evaluate("error=>timelineHarness.finish(error)", outcome == "error")
    page.wait_for_timeout(100)
    assert page.evaluate("timelineHarness.observations.urls") == 0
    assert not downloads
    expect(view).not_to_contain_text("迟到错误")
    expect(view).not_to_contain_text("时间线已下载")


@pytest.mark.parametrize("status", [400, 403, 409])
def test_http_error_has_no_blob_or_download(timeline_view, status):
    page, view = timeline_view
    downloads = []
    page.on("download", lambda download: downloads.append(download))
    view.get_by_role("button", name="下载 Premiere XML", exact=True).click()
    page.wait_for_function("timelineHarness.pending.length === 1")
    page.evaluate("status=>timelineHarness.finish(false,status)", status)
    expect(view.get_by_label("时间线下载状态")).to_have_text("下载被拒绝")
    assert page.evaluate("timelineHarness.observations.urls") == 0
    assert not downloads


@pytest.mark.parametrize("state", ["assistant", "busy"])
def test_processing_disables_timeline(timeline_view, state):
    page, view = timeline_view
    if state == "assistant":
        view.get_by_label("一句话修改镜头").fill("第1个镜头慢放")
        view.get_by_role("button", name="预览改动").click()
        expect(view.locator(".timeline .clip.changed")).to_have_count(1)
        reason = "请先应用或取消创作助手的改动"
    else:
        page.route("**/api/creation/renders", lambda route: None)
        view.get_by_role("button", name="导出成片", exact=True).evaluate("e => e.click()")
        reason = "任务正在处理"
    expect(view.get_by_label("时间线下载状态")).to_have_text(reason)
    for name in ("下载 FCPXML", "下载 OTIO", "下载 Premiere XML"):
        expect(view.get_by_role("button", name=name, exact=True)).to_be_disabled()
    assert page.evaluate("timelineHarness.pending.length") == 0
