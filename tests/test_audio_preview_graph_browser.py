"""Capture actual live MediaElementSource PCM; no cloud, footage or paid models."""

import array
import functools
import math
import threading
import wave
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

import pytest
from browser_http import browser_server

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/gamingcreator/ui/static/studio"


@pytest.fixture(scope="module")
def live_graph(tmp_path_factory):
    pw = pytest.importorskip("playwright.sync_api")
    root = tmp_path_factory.mktemp("audio-graph")
    for name, frequency, amplitude in (
        ("source", 337, 0.4),
        ("music", 907, 0.1),
        ("voice", 587, 0.3),
    ):
        samples = array.array("h")
        for i in range(48000):
            value = round(32767 * amplitude * math.sin(2 * math.pi * frequency * i / 48000))
            samples.extend((value, value))
        for suffix, copies in (("", 1), ("-steady", 4)):
            with wave.open(str(root / f"{name}{suffix}.wav"), "wb") as output:
                output.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
                output.writeframes(samples.tobytes() * copies)

    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            if path.startswith("/assets/studio/"):
                return str(STATIC / path.split("/")[-1])
            if path.startswith("/assets/"):
                return str(STATIC.parent / path.removeprefix("/assets/"))
            if path.startswith("/api/creation/music/"):
                return str(root / "music.wav")
            return super().translate_path(path)

    server = browser_server(functools.partial(Handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(
                headless=True, args=["--autoplay-policy=no-user-gesture-required"]
            )
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            yield page
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


CAPTURE = """async settings => {
    const {AudioPreviewGraph} = await import('/assets/studio/audio-preview-graph.js');
    const elements = ['source', 'source', 'music', 'voice'].map(name => {
        // Steady-state detector checks avoid the phase discontinuity of a 1s media
        // element loop. The hook tests below retain the original 1s looping files.
        const el=document.createElement('audio'); el.src=`/${name}-steady.wav`; el.loop=false;
        document.body.append(el); return el;
    });
    const errors=[];
    const graph=new AudioPreviewGraph(elements, message=>errors.push(message));
    let captured; let timer; let recorder;
    try {
        await graph.ready;
        graph.configure(settings);
        graph.slot(elements[0],1); graph.slot(elements[1],0);
        // Capture on the render thread: ScriptProcessor callbacks queued during a
        // main-thread stall can deliver stale/repeated input blocks as fresh PCM.
        const captureModule=URL.createObjectURL(new Blob([`
            class Capture extends AudioWorkletProcessor {
                constructor() {
                    super(); this.samples=[]; this.recording=false; this.firstFrame=null;
                    this.port.onmessage=()=>{this.recording=true;};
                }
                process(inputs) {
                    if(this.recording && inputs[0]?.[0]) {
                        if(this.firstFrame===null) this.firstFrame=currentFrame;
                        this.samples.push(...inputs[0][0]);
                        if(this.samples.length>=sampleRate*.8) {
                            this.port.postMessage({samples:this.samples,firstFrame:this.firstFrame,
                                endFrame:currentFrame+inputs[0][0].length});
                            this.recording=false;
                        }
                    }
                    return true;
                }
            }
            registerProcessor('capture',Capture);
        `],{type:'text/javascript'}));
        try {
            await graph.context.audioWorklet.addModule(captureModule);
        } finally {
            URL.revokeObjectURL(captureModule);
        }
        recorder=new AudioWorkletNode(graph.context,'capture');
        const done=new Promise(resolve=>{recorder.port.onmessage=e=>resolve(e.data);});
        graph.gate.connect(recorder); recorder.connect(graph.context.destination);
        await graph.context.resume();
        await Promise.all([elements[0],elements[2],elements[3]].map(el=>el.play()));
        // play() can resolve before the three media clocks have all advanced. Keep
        // startup scheduling out of the steady-state detector measurement window.
        await Promise.all([elements[0],elements[2],elements[3]].map(el=>new Promise((resolve,reject)=>{
            const check=()=>{if(el.currentTime>=.25){clearTimeout(timer);el.removeEventListener('timeupdate',check);resolve();}};
            const timer=setTimeout(()=>{el.removeEventListener('timeupdate',check);reject(new Error('Media clock did not advance'));},5000);
            el.addEventListener('timeupdate',check);check();
        })));
        if([elements[0],elements[2],elements[3]].some(el=>el.duration-el.currentTime<.8))
            throw new Error('Insufficient media remains for capture');
        graph.enable(true);
        recorder.port.postMessage('record');
        captured=await Promise.race([done,new Promise((_,reject)=>{
            timer=setTimeout(()=>reject(new Error('Audio capture timed out')),5000);
        })]);
        if([elements[0],elements[2],elements[3]].some(el=>el.ended))
            throw new Error('Media ended during capture');
    } finally {
        clearTimeout(timer);
        graph.reset();
        recorder?.disconnect(); graph.dispose();
        elements.forEach(el=>el.remove());
    }
    const ended=elements.every(el=>el.paused);
    return {...captured,rate:graph.context.sampleRate,errors,ended,state:graph.context.state};
}"""


def amplitude(samples, rate, frequency):
    # Phase independent projection, measured after limiter lookahead and RMS attack.
    window = samples[round(rate * 0.3) : round(rate * 0.7)]
    # Fit all three known tones together: simple projection leaks the loud raw key
    # through the finite window and falsely makes its user gain alter the music.
    columns = [
        [fn(2 * math.pi * f * i / rate) for i in range(len(window))]
        for f in (337, 587, 907)
        for fn in (math.sin, math.cos)
    ]
    matrix = [
        [sum(a * b for a, b in zip(left, right, strict=True)) for right in columns]
        + [sum(a * b for a, b in zip(left, window, strict=True))]
        for left in columns
    ]
    for i in range(6):
        pivot = max(range(i, 6), key=lambda row: abs(matrix[row][i]))
        matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
        divisor = matrix[i][i]
        matrix[i] = [x / divisor for x in matrix[i]]
        for row in range(6):
            if row == i:
                continue
            factor = matrix[row][i]
            matrix[row] = [x - factor * y for x, y in zip(matrix[row], matrix[i], strict=True)]
    index = (337, 587, 907).index(frequency) * 2
    return math.hypot(matrix[index][-1], matrix[index + 1][-1])


def test_actual_media_graph_two_ducking_switches(live_graph):
    measured = {}
    for source_duck, voice_duck in ((False, False), (True, False), (False, True), (True, True)):
        result = live_graph.evaluate(
            CAPTURE,
            dict(
                mix=dict(
                    sourceGainDb=-24,
                    bgm=dict(gainDb=0),
                    ducking="source-v1" if source_duck else "off",
                ),
                narration=dict(gainDb=-24, ducking="narration-v1" if voice_duck else "off"),
            ),
        )
        assert result["errors"] == []
        assert result["ended"] and result["state"] == "closed"
        assert max(abs(x) for x in result["samples"]) <= 0.951
        measured[source_duck, voice_duck] = amplitude(result["samples"], result["rate"], 907)
    baseline = measured[False, False]
    assert baseline == pytest.approx(0.1, abs=0.003)
    assert measured[True, False] < baseline * 0.2
    assert measured[False, True] < baseline * 0.2
    assert measured[True, True] < min(measured[True, False], measured[False, True]) * 0.3


HOOK = """async () => {
    const {h,render}=await import('/assets/vendor/preact.module.js');
    const {useRef,useState}=await import('/assets/vendor/hooks.module.js');
    const {useAudioPreview}=await import('/assets/studio/audio.js');
    const root=document.createElement('div'); document.body.append(root);
    const audio={mix:{sourceGainDb:-60,bgm:{trackId:'test',gainDb:0},ducking:'off'},
        narration:{assetJobId:'voice',startFrame:30,gainDb:-60,ducking:'narration-v1'},
        asset:{audioUrl:'/voice.wav'}};
    function App() {
        const video=useRef(null), [player,setPlayer]=useState({playing:false,buffering:false,outUs:0});
        window.setAudioPlayer=value=>setPlayer(old=>({...old,...value}));
        const sound=useAudioPreview(player,audio,30,video,[{trackId:'test',trackReceiptSha256:'test'}],'test');
        return h('div',{},h('video',{ref:video,'data-preview-slot':'',src:'/source.wav',loop:true}),
            h('video',{'data-preview-slot':'',src:'/source.wav',loop:true}),sound);
    }
    render(h(App),root); window.audioHarness={root,render};
}"""

HOOK_CAPTURE = """async () => {
    const graph=audioHarness.root.querySelector('video').studioAudioGraph;
    const recorder=graph.context.createScriptProcessor(1024,2,2), samples=[];
    const done=new Promise(resolve=>{recorder.onaudioprocess=e=>{
        samples.push(...e.inputBuffer.getChannelData(0));
        if(samples.length>graph.context.sampleRate*.4) resolve();
    }});
    graph.gate.connect(recorder); recorder.connect(graph.context.destination);
    await done; graph.gate.disconnect(recorder); recorder.disconnect();
    return {samples,rate:graph.context.sampleRate,
        paused:[...audioHarness.root.querySelectorAll('audio')].map(el=>el.paused)};
}"""


def test_real_hook_narration_offset_pause_seek_loop_and_unmount(live_graph):
    page = live_graph
    page.evaluate(HOOK)
    page.wait_for_function("audioHarness.root.querySelector('video').studioAudioGraph?.node")
    page.evaluate("audioHarness.root.querySelector('video').studioAudioGraph.context.resume()")
    page.evaluate("setAudioPlayer({playing:true,outUs:500000})")
    page.wait_for_function("!audioHarness.root.querySelectorAll('audio')[1].paused")
    before = page.evaluate(HOOK_CAPTURE)
    assert before["paused"][0]
    assert amplitude(before["samples"], before["rate"], 907) == pytest.approx(0.1, abs=0.004)
    page.evaluate("setAudioPlayer({outUs:1250000})")
    page.wait_for_function("!audioHarness.root.querySelectorAll('audio')[0].paused")
    during = page.evaluate(HOOK_CAPTURE)
    assert amplitude(during["samples"], during["rate"], 907) < 0.02
    page.evaluate("setAudioPlayer({buffering:true})")
    silent = page.evaluate(HOOK_CAPTURE)
    assert all(silent["paused"])
    assert max(abs(x) for x in silent["samples"][2048:]) < 1e-8
    page.evaluate("setAudioPlayer({buffering:false,outUs:2250000})")
    page.wait_for_function("!audioHarness.root.querySelectorAll('audio')[1].paused")
    page.wait_for_function(
        "audioHarness.root.querySelectorAll('audio')[1].currentTime >= .15", timeout=2000
    )
    assert page.evaluate(
        "audioHarness.root.querySelectorAll('audio')[1].currentTime"
    ) == pytest.approx(0.25, abs=0.15)
    page.evaluate("setAudioPlayer({playing:false})")
    paused = page.evaluate(HOOK_CAPTURE)
    assert max(abs(x) for x in paused["samples"][2048:]) < 1e-8
    assert (
        page.evaluate("""() => {
        const graph=audioHarness.root.querySelector('video').studioAudioGraph;
        audioHarness.render(null,audioHarness.root); audioHarness.root.remove();
        return graph.context.state;
    }""")
        == "closed"
    )
    # A new mounted editor has fresh elements/context and exactly one audible bed.
    page.evaluate(HOOK)
    page.wait_for_function("audioHarness.root.querySelector('video').studioAudioGraph?.node")
    page.evaluate("audioHarness.root.querySelector('video').studioAudioGraph.context.resume()")
    page.evaluate("setAudioPlayer({playing:true,outUs:500000})")
    page.wait_for_function("!audioHarness.root.querySelectorAll('audio')[1].paused")
    remounted = page.evaluate(HOOK_CAPTURE)
    assert amplitude(remounted["samples"], remounted["rate"], 907) == pytest.approx(0.1, abs=0.004)
    page.evaluate("audioHarness.render(null,audioHarness.root); audioHarness.root.remove()")


@pytest.mark.parametrize("control,key_amplitude", [("source", 0.4), ("narration", 0.3)])
def test_live_graph_raw_keys_ignore_user_gain(live_graph, tmp_path, control, key_amplitude):
    gains = []
    for db in (0, -24, -60):
        settings = dict(
            mix=dict(
                sourceGainDb=db if control == "source" else -60,
                bgm=dict(gainDb=0),
                ducking="source-v1" if control == "source" else "off",
            ),
            narration=dict(
                gainDb=db if control == "narration" else -60,
                ducking="narration-v1" if control == "narration" else "off",
            ),
        )
        result = live_graph.evaluate(CAPTURE, settings)
        gains.append(amplitude(result["samples"], result["rate"], 907) / 0.1)
    from test_audio_ducking_browser import reference as ffmpeg_reference

    output = ffmpeg_reference(tmp_path, -60, 1, True, key_amplitude)[0]
    reference = sum(output[19200:38400]) / 19200 / 0.1
    assert all(abs(20 * math.log10(gain / reference)) < 1 for gain in gains), (gains, reference)
    assert (
        max(20 * math.log10(gain) for gain in gains) - min(20 * math.log10(gain) for gain in gains)
        < 0.2
    )


def test_browser_servers_do_not_share_a_live_windows_port():
    first = browser_server(SimpleHTTPRequestHandler)
    try:
        second = browser_server(SimpleHTTPRequestHandler)
        try:
            assert first.server_port != second.server_port
        finally:
            second.server_close()
    finally:
        first.server_close()


@pytest.mark.parametrize("boundary", ["startup", "recording"])
def test_render_clock_capture_survives_main_thread_stall(live_graph, boundary):
    stall = "const until=performance.now()+600; while(performance.now()<until){};"
    marker = (
        "graph.enable(true);" if boundary == "startup" else "recorder.port.postMessage('record');"
    )
    capture = CAPTURE.replace(marker, stall + marker if boundary == "startup" else marker + stall)
    result = live_graph.evaluate(
        capture,
        dict(
            mix=dict(sourceGainDb=-24, bgm=dict(gainDb=0), ducking="off"),
            narration=dict(gainDb=-24, ducking="off"),
        ),
    )
    assert result["endFrame"] - result["firstFrame"] == len(result["samples"])
    assert result["rate"] * 0.8 <= len(result["samples"]) < result["rate"] * 0.8 + 128
    assert amplitude(result["samples"], result["rate"], 907) == pytest.approx(0.1, abs=0.003)
    assert result["ended"] and result["state"] == "closed"


def test_render_clock_capture_rejects_insufficient_media(live_graph):
    capture = CAPTURE.replace(
        "    if([elements[0],elements[2],elements[3]].some(el=>el.duration-el.currentTime<.8))",
        "    const until=performance.now()+3900; while(performance.now()<until){};\n"
        "    if([elements[0],elements[2],elements[3]].some(el=>el.duration-el.currentTime<.8))",
    )
    pw = pytest.importorskip("playwright.sync_api")
    with pytest.raises(pw.Error, match="Insufficient media remains for capture"):
        live_graph.evaluate(capture, dict(mix=dict(bgm=dict(gainDb=0)), narration={}))
    assert live_graph.locator("audio").count() == 0


def test_render_clock_capture_cleans_up_rejected_module(live_graph):
    result = live_graph.evaluate(
        """async capture => {
            const contexts=[],created=[],revoked=[];
            const NativeContext=window.AudioContext;
            const nativeAdd=AudioWorklet.prototype.addModule;
            const nativeCreate=URL.createObjectURL, nativeRevoke=URL.revokeObjectURL;
            window.AudioContext=new Proxy(NativeContext,{
                construct(target,args){const context=new target(...args);contexts.push(context);return context;}
            });
            AudioWorklet.prototype.addModule=function(url,...args){
                if(String(url).startsWith('blob:')) return Promise.reject(new Error('Capture module rejected'));
                return nativeAdd.call(this,url,...args);
            };
            URL.createObjectURL=function(blob){const url=nativeCreate.call(this,blob);created.push(url);return url;};
            URL.revokeObjectURL=function(url){revoked.push(url);return nativeRevoke.call(this,url);};
            let error;
            try {
                await (0,eval)(`(${capture})`)({mix:{bgm:{gainDb:0}},narration:{}});
            } catch(reason) {error=reason.message;}
            finally {
                window.AudioContext=NativeContext;
                AudioWorklet.prototype.addModule=nativeAdd;
                URL.createObjectURL=nativeCreate; URL.revokeObjectURL=nativeRevoke;
            }
            return {error,created,revoked,states:contexts.map(context=>context.state),
                elements:document.querySelectorAll('audio').length};
        }""",
        CAPTURE,
    )
    assert result["error"] == "Capture module rejected"
    assert len(result["created"]) == 1
    assert result["created"] == result["revoked"]
    assert result["states"] == ["closed"]
    assert result["elements"] == 0
