"""A09: looped preview music stays on the output clock, including at the wrap and after a controlled offset."""
# ruff: noqa: F811

from __future__ import annotations

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser

# Keep the official dissolve assertion band. Do not loosen it, and do not retry the test to pass.
TOLERANCE = 0.12


def test_looped_music_wrap_and_controlled_offset_stay_on_output_clock(studio_audio):
    page = studio_audio
    page.get_by_role("button", name="预览方案", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('[data-preview-slot]').studioAudioGraph?.node && "
        "document.querySelector('[data-preview-slot]').studioAudioGraph.elements[2]?.duration > 0"
    )

    observed = page.evaluate(
        """async () => {
            const rows = [];
            const started = performance.now();
            while (performance.now() - started < 2200) {
                const scroll = document.querySelector(".track-scroll");
                const head = document.querySelector("[data-track='picture'] .playhead");
                const music = document.querySelector("[data-preview-slot]").studioAudioGraph.elements[2];
                if (scroll && head && music && Number.isFinite(music.duration) && music.duration > 0) {
                    const outS = parseFloat(head.style.left) / Number(scroll.dataset.scale) / 1e6;
                    const expected = ((outS % music.duration) + music.duration) % music.duration;
                    const drift = Math.abs(music.currentTime - expected);
                    const phase = Math.min(drift, Math.abs(drift - music.duration));
                    const wrap = expected < 0.08 || expected > music.duration - 0.08;
                    rows.push({outS, expected, current: music.currentTime, duration: music.duration, phase, wrap});
                }
                await new Promise((resolve) => requestAnimationFrame(resolve));
            }
            return rows;
        }"""
    )
    assert len(observed) > 20, observed[:3]
    assert any(row["wrap"] for row in observed), "没有采到循环配乐绕回附近的样本"
    worst = max(row["phase"] for row in observed)
    assert worst < TOLERANCE, (worst, [row for row in observed if row["phase"] >= TOLERANCE][:5])

    injected = page.evaluate(
        """() => {
            const scroll = document.querySelector(".track-scroll");
            const head = document.querySelector("[data-track='picture'] .playhead");
            const music = document.querySelector("[data-preview-slot]").studioAudioGraph.elements[2];
            const outS = parseFloat(head.style.left) / Number(scroll.dataset.scale) / 1e6;
            const expected = ((outS % music.duration) + music.duration) % music.duration;
            const off = (expected + 0.45) % music.duration;
            music.currentTime = off;
            const drift = Math.abs(music.currentTime - expected);
            const phase = Math.min(drift, Math.abs(drift - music.duration));
            return {expected, off, current: music.currentTime, duration: music.duration, phase};
        }"""
    )
    assert injected["phase"] > 0.2, injected

    page.wait_for_function(
        """tolerance => {
            const scroll = document.querySelector(".track-scroll");
            const head = document.querySelector("[data-track='picture'] .playhead");
            const music = document.querySelector("[data-preview-slot]").studioAudioGraph.elements[2];
            const outS = parseFloat(head.style.left) / Number(scroll.dataset.scale) / 1e6;
            const expected = ((outS % music.duration) + music.duration) % music.duration;
            const drift = Math.abs(music.currentTime - expected);
            const phase = Math.min(drift, Math.abs(drift - music.duration));
            return phase < tolerance;
        }""",
        arg=TOLERANCE,
        timeout=2000,
    )
