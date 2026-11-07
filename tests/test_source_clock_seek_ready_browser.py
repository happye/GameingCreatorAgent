"""Seek-range readiness must precede precise canonical positioning."""

from pathlib import Path

import pytest


def test_strict_seek_waits_for_range_and_keeps_failure_boundaries():
    pw = pytest.importorskip("playwright.sync_api")
    script = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static/source-clock.js"
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_script_tag(path=str(script))
            result = page.evaluate("""async () => {
                function player(end=.2, wrong=false) {
                    const v=new EventTarget(); let t=0, range=end;
                    v.currentSrc='file:///fixture.mp4'; v.readyState=4; v.seeking=false; v.writes=[];
                    v.seekable={length:1,start:()=>0,end:()=>range};
                    v.extend=value=>{range=value;v.dispatchEvent(new Event('progress'));};
                    Object.defineProperty(v,'currentTime',{get:()=>t,set(value){
                        v.writes.push(value);v.seeking=true;
                        setTimeout(()=>{t=Math.min(value,range)-(wrong?.05:0);v.seeking=false;
                            v.dispatchEvent(new Event('seeked'));},15);
                    }});
                    return v;
                }
                const grow=player(), unavailable=player(), stale=player(), reload=player(1), wrong=player(1,true);
                let current=true;
                const tasks=[
                    SourceClock.settleExact(grow,.7,{timeoutMs:150}),
                    SourceClock.settleExact(unavailable,.7,{timeoutMs:50}),
                    SourceClock.settleExact(stale,.7,{timeoutMs:100,isCurrent:()=>current}),
                    SourceClock.settleExact(reload,.7,{timeoutMs:100}),
                    SourceClock.settleExact(wrong,.7,{timeoutMs:100}),
                    SourceClock.settle(player(),.7,100)
                ];
                setTimeout(()=>grow.extend(.8),20);
                setTimeout(()=>{current=false;stale.extend(.8);},10);
                setTimeout(()=>reload.dispatchEvent(new Event('loadstart')),5);
                const values=await Promise.all(tasks);
                return {values,writes:[grow.writes,unavailable.writes,stale.writes]};
            }""")
        finally:
            browser.close()
    assert result == {"values": [0.7, None, None, None, None, 0.2], "writes": [[0.7], [], []]}


def test_reference_failed_position_restore_stays_unavailable(tmp_path):
    from test_benchmark_source_clock_browser import clock_case

    pw = pytest.importorskip("playwright.sync_api")
    case = clock_case(tmp_path, "zero")
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.add_init_script("""(() => {
                const load=HTMLMediaElement.prototype.load;
                HTMLMediaElement.prototype.load=function(){
                    if(!this.isConnected)setTimeout(()=>load.call(this),400);else load.call(this);
                };
            })();""")
            page.goto(case.reference_page.as_uri())
            page.evaluate("""() => {
                const v=document.getElementById('source-video');
                const d=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'currentTime');
                v.currentTime=.5;
                let axisSeen=false;
                Object.defineProperty(v,'currentTime',{get:()=>d.get.call(v),set(value){
                    if(value<.00001)axisSeen=true;
                    if(axisSeen && value===.5){v.dataset.restoreFailed='true';d.set.call(v,.25);}
                    else d.set.call(v,value);
                }});
            }""")
            pw.expect(page.locator("#clock-state")).to_contain_text(
                "原片定位没有完成", timeout=15000
            )
            assert page.locator("#source-video").get_attribute("data-restore-failed") == "true"
            pw.expect(page.locator("#capture-start")).to_be_disabled()
            # A prior retry used to erase the failed target and approve the probe's origin.
            page.wait_for_timeout(3000)
            pw.expect(page.locator("#clock-state")).to_contain_text("原片定位没有完成")
            pw.expect(page.locator("#capture-start")).to_be_disabled()
        finally:
            browser.close()
