"""Real AudioWorklet PCM versus installed FFmpeg, synthetic signals only."""

import array
import functools
import math
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

import pytest
from browser_http import browser_server

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
COUNT = RATE * 2
RENDER = """async spec => {
  const ctx = new OfflineAudioContext(2, 96000, 48000);
  await ctx.audioWorklet.addModule('/audio-ducking-processor.js');
  const node = new AudioWorkletNode(ctx, 'studio-audio-ducking', {
    numberOfInputs: 4, numberOfOutputs: 1, outputChannelCount: [2],
    parameterData: spec.parameters,
  });
  for (let slot=0; slot<4; slot++) {
    const b = ctx.createBuffer(2, 96000, 48000);
    for (let c=0; c<2; c++) {
      const samples = b.getChannelData(c);
      for (let i=0; i<96000; i++) {
        const key = i>=12000 && i<48000 ? .4*Math.sin(2*Math.PI*337*i/48000) : 0;
        samples[i] = (slot===spec.keySlot || (spec.twoSources && slot===1)) ? key*(c===1?spec.right:1)
          : slot===spec.bedSlot ? spec.amplitude : 0;
      }
    }
    const src=ctx.createBufferSource(); src.buffer=b; src.connect(node,0,slot); src.start();
  }
  if (spec.reset) node.port.postMessage({type:'reset'});
  node.connect(ctx.destination);
  const result=await ctx.startRendering();
  return [Array.from(result.getChannelData(0)),Array.from(result.getChannelData(1))];
}"""


@pytest.fixture(scope="module")
def pcm_browser():
    pw = pytest.importorskip("playwright.sync_api")
    handler = functools.partial(
        SimpleHTTPRequestHandler,
        directory=str(ROOT / "src/gamingcreator/ui/static/studio"),
    )
    server = browser_server(handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            yield page
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def reference(tmp_path, gain_db, right, enabled, key_amplitude=0.4):
    """Two 768kB PCM inputs and one output, safely below 10MB each."""
    key = array.array("f")
    for i in range(COUNT):
        sample = key_amplitude * math.sin(2 * math.pi * 337 * i / RATE) if 12000 <= i < 48000 else 0
        key.extend((sample, sample * right))
    (tmp_path / "key.f32").write_bytes(key.tobytes())
    (tmp_path / "bed.f32").write_bytes(array.array("f", [0.1] * (COUNT * 2)).tobytes())
    inputs = []
    for name in ("bed", "key"):
        inputs += ["-f", "f32le", "-ar", str(RATE), "-ac", "2", "-i", str(tmp_path / f"{name}.f32")]
    compressor = (
        "[b][k]sidechaincompress=threshold=0.015:ratio=12:attack=10:"
        "release=200:makeup=1:knee=1:detection=rms[out]"
        if enabled
        else "[k]anullsink;[b]anull[out]"
    )
    compressor = "[0:a]asetnsamples=n=128[b];[1:a]asetnsamples=n=128[k];" + compressor
    subprocess.run(
        [
            str(ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"),
            "-v",
            "error",
            "-y",
            "-filter_complex_threads",
            "1",
            *inputs,
            "-filter_complex",
            compressor,
            "-map",
            "[out]",
            "-f",
            "f32le",
            str(tmp_path / "out.f32"),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    output = array.array("f")
    output.frombytes((tmp_path / "out.f32").read_bytes())
    assert len(output) == COUNT * 2
    gain = 10 ** (gain_db / 20)
    return [[output[i] + key[i] * gain for i in range(c, len(output), 2)] for c in range(2)]


@pytest.mark.parametrize(
    "key_slot,gain,right,enabled",
    [
        (0, -60, 1, True),
        (0, -24, 0, True),
        (0, 0, 1, False),
        (0, 0, 1, True),
        (3, -60, 0.3, True),
        (3, -24, 1, True),
        (3, 0, 1, False),
        (3, 0, 1, True),
    ],
)
def test_worklet_matches_ffmpeg_pcm(pcm_browser, tmp_path, key_slot, gain, right, enabled):
    control = "source" if key_slot == 0 else "narration"
    parameters = {f"{control}GainDb": gain, f"{control}Ducking": int(enabled)}
    actual = pcm_browser.evaluate(
        RENDER,
        dict(
            keySlot=key_slot,
            bedSlot=2,
            right=right,
            amplitude=0.1,
            parameters=parameters,
        ),
    )
    expected = reference(tmp_path, gain, right, enabled)
    # Sample comparison covers attack, release, steady state and asymmetric stereo keys.
    error = max(
        abs(a - b)
        for ac, ec in zip(actual, expected, strict=True)
        for a, b in zip(ac, ec, strict=True)
    )
    worst = max(range(COUNT), key=lambda i: abs(actual[0][i] - expected[0][i]))
    assert error < 0.00001, (
        f"maximum PCM error {error}, at {worst}: {actual[0][worst]} vs {expected[0][worst]}"
    )


@pytest.mark.parametrize("bed,final", [(1, 0), (0, 1), (1, 1)])
@pytest.mark.parametrize("amplitude", [0.2, 2])
def test_worklet_limiter_uses_lookahead_and_preserves_quiet_samples(
    pcm_browser, bed, final, amplitude
):
    actual = pcm_browser.evaluate(
        RENDER,
        dict(
            keySlot=0,
            bedSlot=2,
            right=1,
            amplitude=amplitude,
            parameters=dict(sourceGainDb=-60, bedLimiter=bed, finalLimiter=final),
            reset=True,
        ),
    )
    assert max(abs(x) for channel in actual for x in channel) <= 0.950001
    delay = 240 * (bed + final)
    assert actual[0][:delay] == [0] * delay
    expected = min(amplitude, 0.95)
    assert max(abs(x - expected) for x in actual[0][delay:12000]) < 0.00001


def test_source_key_uses_both_triangular_slots_before_user_gain(pcm_browser):
    baseline = None
    for gain in (0, -24, -60):
        actual = pcm_browser.evaluate(
            RENDER,
            dict(
                keySlot=0,
                bedSlot=2,
                right=1,
                amplitude=0.1,
                twoSources=True,
                parameters=dict(sourceGainDb=gain, slotAGain=0.25, slotBGain=0.75, sourceDucking=1),
            ),
        )[0]
        residual = []
        for i, value in enumerate(actual):
            key = 0.4 * math.sin(2 * math.pi * 337 * i / RATE) if 12000 <= i < 48000 else 0
            residual.append(value - key * 10 ** (gain / 20))
        if baseline is not None:
            assert max(abs(a - b) for a, b in zip(residual, baseline, strict=True)) < 0.000001
        baseline = residual
