"""Step-7 scoring aids: the live tally must agree with step-8 scoring; nothing is pre-filled."""

import asyncio
import json
from pathlib import Path

import pytest
from test_benchmark_review import build, review_fixture

from gamingcreator.application.benchmark import parse_manifest, run_benchmark
from gamingcreator.application.benchmark_review import judged_manifest, validate_review
from gamingcreator.ui.benchmark_review import render_benchmark_review

# (slot, grade, human event) as a reviewer might fill them; slot 2 is a known duplicate.
LABELS = (
    (1, "2", "human-0"),
    (3, "3", "human-0"),  # same independent event as slot 1: a duplicate at step 8
    (4, "1", ""),
    (5, "2", "human-4"),
    (6, "0", ""),
    (7, "3", "human-5"),
)


@pytest.mark.parametrize("width", [1366, 390])
def test_live_tally_matches_step_eight_scoring_and_never_prefills(tmp_path, width):
    playwright = pytest.importorskip("playwright.sync_api")
    fixture = review_fixture(tmp_path, 11)
    raw = fixture[0]
    # One frozen reference overlaps every candidate interval (100-800 ms) in time.
    raw["queries"][0]["referenceEvents"][3]["usableRanges"] = [
        {"startUs": 500_000, "endUs": 900_000}
    ]
    context, template = build(fixture)
    path = tmp_path / "review.html"
    path.write_text(render_benchmark_review(context, template), encoding="utf-8")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900}, accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(path.as_uri())
            tally = page.locator("[data-tally]").first
            playwright.expect(tally).to_contain_text("评为可用的不同独立事件 0 个")
            # No pass threshold while grading: the count must not steer judgments.
            for word in ("门槛", "还差", "已够", "7 个"):
                playwright.expect(tally).not_to_contain_text(word)
            # Overlap notes name the reference but never fill anything in.
            playwright.expect(page.locator(".overlap").first).to_contain_text("human-3")
            assert all(
                value == ""
                for value in page.locator('[data-field="grade"]').evaluate_all(
                    "nodes => nodes.map(node => node.value)"
                )
            )
            assert page.locator(".reference-replay").count() == 10
            # Without a verified clock, reference replays stay disabled and say why.
            assert all(
                page.locator(".reference-replay").evaluate_all(
                    "nodes => nodes.map(node => node.disabled)"
                )
            )
            playwright.expect(page.locator('[data-clock="reference-note"]').first).not_to_be_empty()
            page.locator("#recordedOn").fill("2026-10-27")
            page.locator("#reviewer").fill("synthetic-browser-only")
            page.locator("#reviewed").check()
            for slot, grade, human in LABELS:
                card = page.locator(f'.slot[data-slot="{slot}"]')
                card.locator('[data-field="grade"]').select_option(grade)
                card.locator('[data-field="humanEventId"]').select_option(human)
                card.locator('[data-field="reason"]').fill("Synthetic judgment, never real.")
            warning = page.locator('.slot[data-slot="3"] .slot-warning')
            playwright.expect(warning).to_be_visible()
            playwright.expect(warning).to_contain_text("第1位")
            playwright.expect(warning).not_to_contain_text("0分")
            shown = tally.evaluate("node => ({...node.dataset})")
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            saved = Path(pending.value.path()).read_bytes()
            record = validate_review(saved, template, context)
            # J/K walk the scorable positions; the known duplicate slot 2 is skipped.
            page.locator('.slot[data-slot="1"] [data-field="grade"]').focus()
            page.keyboard.press("k")
            focused = page.evaluate("() => document.activeElement.closest('.slot').dataset.slot")
            assert focused == "3"
            page.keyboard.press("j")
            assert (
                page.evaluate("() => document.activeElement.closest('.slot').dataset.slot") == "1"
            )
            # The event drop-down keeps its type-ahead; P replays (no clock here: a reason).
            page.locator('.slot[data-slot="1"] [data-field="humanEventId"]').focus()
            page.keyboard.press("k")
            assert page.evaluate("() => document.activeElement.dataset.field") == "humanEventId"
            initial = page.locator("#play-state").inner_text()
            page.locator('.slot[data-slot="1"] [data-field="grade"]').focus()
            page.keyboard.press("p")
            playwright.expect(page.locator("#play-state")).not_to_have_text(initial)
            playwright.expect(page.locator("#play-state")).to_contain_text("原片")
            # Reloading the saved record restores the same counts.
            page.locator("#load-record").set_input_files(
                {"name": "saved.json", "mimeType": "application/json", "buffer": saved}
            )
            playwright.expect(page.locator("#status")).to_contain_text("已载入")
            assert tally.evaluate("node => ({...node.dataset})") == shown
            # Typing in the reason box never moves between positions.
            page.locator('.slot[data-slot="1"] [data-field="reason"]').press("k")
            assert (
                page.evaluate("() => document.activeElement.closest('.slot').dataset.slot") == "1"
            )
            assert not errors
        finally:
            browser.close()
    hits = fixture[-1]

    async def search(query):
        return hits

    async def verify(media):
        return None

    report = asyncio.run(
        run_benchmark(parse_manifest(judged_manifest(context, record)), search, verify_media=verify)
    )
    scored = report["queries"][0]
    useful = {row["humanEventId"] for row in scored["slots"] if row["useful"] is True}
    assert int(shown["useful"]) == len(useful) == 3
    assert int(shown["duplicates"]) == scored["duplicateSlots"] == 2
    assert int(shown["unjudged"]) == scored["unjudgedSlots"] == 3
    assert int(shown["missing"]) == scored["missingSlots"] == 0
    assert json.loads(json.dumps(record))["queries"][0]["slots"][1]["grade"] is None
