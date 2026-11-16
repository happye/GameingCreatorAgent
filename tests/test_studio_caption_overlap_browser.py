"""A05: clicking a caption in a transition overlap must not edit the wrong clip."""
# ruff: noqa: F811

from __future__ import annotations

import pytest
from test_creation_jobs import service  # noqa: F401
from test_narration_jobs import engine  # noqa: F401
from test_studio_audio_graph_browser import studio_audio  # noqa: F401
from test_studio_interaction_gaps_browser import enable_sidecar, select_clip

expect = pytest.importorskip("playwright.sync_api").expect
pytestmark = pytest.mark.browser


def test_clip_for_cue_overlap_and_unknown_id_seek_only(studio_audio):
    page = studio_audio
    rules = page.evaluate(
        """async () => {
            const {clipForCue} = await import("/assets/studio/multitrack.js");
            const items = [
                {clipId: "A", outStartUs: 0, outDurUs: 2000000},
                {clipId: "B", outStartUs: 1000000, outDurUs: 2000000},
            ];
            const id = (cue) => clipForCue(items, cue)?.clipId ?? null;
            return {
                uniqueA: id({startUs: 200000}),
                uniqueB: id({startUs: 2500000}),
                overlapNoId: id({startUs: 1500000}),
                trustedB: id({startUs: 1500000, clipId: "B"}),
                unknownOverlap: id({startUs: 1500000, clipId: "Z"}),
                unknownUnique: id({startUs: 200000, clipId: "Z"}),
            };
        }"""
    )
    assert rules == {
        "uniqueA": "A",
        "uniqueB": "B",
        "overlapNoId": None,
        "trustedB": "B",
        "unknownOverlap": None,
        "unknownUnique": None,
    }


def test_clicking_overlap_caption_does_not_edit_the_other_clip(studio_audio):
    page = studio_audio
    enable_sidecar(page)
    select_clip(page, 0).fill("甲镜字幕")
    expect(page.locator(".caption-block").first).to_contain_text("甲镜字幕", timeout=10_000)
    select_clip(page, 1).fill("乙镜字幕")
    expect(page.locator(".caption-block")).to_have_count(2, timeout=10_000)
    expect(page.locator(".caption-block").nth(1)).to_contain_text("乙镜字幕")

    # The second cue starts in the 30-frame crossfade, which also belongs to clip A.
    second = page.locator(".caption-block").nth(1)
    clip_id = second.get_attribute("data-clip-id")
    assert clip_id, clip_id
    select_clip(page, 0)
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("甲镜字幕")
    second.click()
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("乙镜字幕")
    field = page.get_by_label("镜头字幕", exact=True)
    field.fill("乙镜已改")
    expect(page.locator(".caption-block").nth(1)).to_contain_text("乙镜已改", timeout=10_000)
    select_clip(page, 0)
    expect(page.get_by_label("镜头字幕", exact=True)).to_have_value("甲镜字幕")
    expect(page.locator(".caption-block").first).to_contain_text("甲镜字幕")
