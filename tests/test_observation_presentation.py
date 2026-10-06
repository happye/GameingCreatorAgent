import asyncio
import csv
import hashlib
import json
from contextlib import closing
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest
from test_inspection_http import workspace
from test_retrieval import SynonymFixture, event, search, timeline
from test_retrieval_persistence import open_db, seed, transaction
from test_sqlite_store import CONFIG, bundle_fixture, event_fixture

from gamingcreator.application.observation_text import (
    FACTS_PROJECTION_VERSION,
    clean_observation_text,
    display_facts,
)
from gamingcreator.application.retrieval import RETRIEVAL_VERSION
from gamingcreator.domain.models import Embedding, EmbeddingSpace
from gamingcreator.infrastructure.retrieval_persistence import load_embeddings, persist_embedding
from gamingcreator.infrastructure.sqlite_schema import migrate
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.service import _analysis_profile, inspect_run


@pytest.mark.parametrize("index", range(9))
def test_exact_alias_next_to_chinese_is_neutral_not_a_guessed_source_clock(index):
    assert clean_observation_text(f"f{index}中角色起跳") == "对应画面中角色起跳"
    assert clean_observation_text(f"在f{index}时落地") == "在对应画面时落地"


@pytest.mark.parametrize("separator", ["-", "→", "至", "到", "/", "、", " 和 "])
def test_legacy_alias_sequences_are_compacted_without_inventing_duration(separator):
    assert clean_observation_text(f"f0{separator}f8显示角色移动") == "对应画面序列显示角色移动"


def test_identifiers_uppercase_keyboard_keys_and_unknown_aliases_are_preserved():
    text = "f0o foo_f1 image-f2 run:f3 image/f4 f5.png item-f0 f0-name F1 F8 f9 f10"
    assert clean_observation_text(text) == text
    assert clean_observation_text("(f0). Then f1.") == "(对应画面). Then 对应画面."


def test_projection_is_immutable_and_idempotent():
    raw = ("f0时角色拿着蓝色权杖", "f1至f8的背景是石头竞技场")
    projected = display_facts(raw)
    assert raw == ("f0时角色拿着蓝色权杖", "f1至f8的背景是石头竞技场")
    assert projected == ("对应画面时角色拿着蓝色权杖", "对应画面序列的背景是石头竞技场")
    assert display_facts(projected) == projected


@pytest.mark.parametrize(
    ("prompt", "profile"),
    [
        ("phase0-vision-v5", "detailed"),
        ("phase0-vision-v6", "detailed"),
        ("phase0-vision-v4", "temporal"),
        ("phase0-vision-v3", "temporal"),
        ("phase0-vision-v2", "frame_observations"),
        ("future-unknown", "frame_observations"),
    ],
)
def test_analysis_profile_preserves_legacy_and_unknown_fallback(prompt, profile):
    assert _analysis_profile(prompt) == profile


def test_retrieval_does_not_match_internal_alias_and_keeps_raw_candidate_identity():
    observed = event("jump", 0, 1, "f0到f8角色跳跃落地", "jump")
    data = timeline((observed,))
    assert search(data, "f0", mode="lexical").candidates == ()
    assert search(data, "f8", mode="lexical").candidates == ()
    result = search(data, "跳跃", mode="lexical")
    assert result.retrieval_version == RETRIEVAL_VERSION == "bm25-e5-rrf-v6"
    candidate = result.candidates[0]
    assert candidate.observable_facts == observed.observable_facts
    assert candidate.source_range == observed.source_range
    assert candidate.event_id == observed.event_id
    assert candidate.evidence_ids == observed.evidence_ids


def test_cli_search_projects_facts_without_rewriting_canonical_candidate():
    from gamingcreator.cli.main import _search_document

    observed = event("jump", 0, 1, "f0到f8角色跳跃落地", "jump")
    result = search(timeline((observed,)), "跳跃", mode="lexical")
    document = _search_document(result, 1, {observed.event_id: "f1持有物类别不明确"})
    candidate = document["candidates"][0]
    assert candidate["observableFacts"] == list(observed.observable_facts)
    assert candidate["displayFacts"] == ["对应画面序列角色跳跃落地"]
    assert document["factsProjectionVersion"] == FACTS_PROJECTION_VERSION
    assert candidate["uncertainty"] == "f1持有物类别不明确"
    assert candidate["displayUncertainty"] == "对应画面持有物类别不明确"
    assert result.candidates[0].observable_facts == observed.observable_facts


def test_embedding_passage_hash_tracks_projection_but_subject_stays_event():
    observed = event("jump", 0, 1, "f0到f8角色跳跃落地", "jump")
    data = timeline((observed,))
    result = search(data, "跳跃", embedding_provider=SynonymFixture())
    embedding = result.event_embeddings[0]
    projected = "passage: 对应画面序列角色跳跃落地\njump"
    raw = "passage: f0到f8角色跳跃落地\njump"
    assert embedding.text_hash == hashlib.sha256(projected.encode()).hexdigest()
    assert embedding.text_hash != hashlib.sha256(raw.encode()).hexdigest()
    assert embedding.subject_id == observed.event_id
    assert data.events == (observed,)


def test_old_and_projected_embedding_hashes_coexist_for_same_persisted_event():
    space = EmbeddingSpace("fixture", "fixture", "fixed-test-only", 2, "l2")
    raw = "passage: f0到f8角色跳跃落地\njump"
    projected = "passage: 对应画面序列角色跳跃落地\njump"
    old = Embedding("event1", space, (1.0, 0.0), hashlib.sha256(raw.encode()).hexdigest())
    new = Embedding("event1", space, (0.0, 1.0), hashlib.sha256(projected.encode()).hexdigest())
    with closing(open_db()) as connection:
        migrate(connection)
        seed(connection)
        with transaction(connection):
            old_id = persist_embedding(connection, "r1", old)
            new_id = persist_embedding(connection, "r1", new)
        assert old_id != new_id
        assert set(load_embeddings(connection, "r1", space)) == {old, new}
        assert connection.execute("SELECT DISTINCT event_id FROM embeddings").fetchall() == [
            ("event1",)
        ]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_denied_gameplay_and_unconfirmed_attributes_do_not_become_positive_hits():
    denied = replace(
        event("static", 0, 1, "f0到f8中未观察到跳跃动作", "static"),
        uncertainty="f2中是否存在恶魔领主或权杖无法确认",
    )
    data = timeline((denied,))
    assert search(data, "跳跃", mode="lexical").candidates == ()
    assert search(data, "权杖", mode="lexical").candidates == ()
    assert search(data, "没有跳跃", mode="lexical").candidates
    assert search(data, "汽车维修", mode="lexical").candidates == ()


async def _legacy_project(root):
    source = root / "artifacts"
    source.mkdir(parents=True)
    bundle = bundle_fixture(source)
    project = source / "project"
    raw = replace(
        event_fixture(bundle),
        observable_facts=("f0到f8中红衣角色跳跃，右手拿着蓝色权杖",),
        uncertainty="f2中的敌人身份无法确认",
    )
    store = await SqliteTimelineStore.open(project)
    try:
        await store.create_run("run-1", bundle.asset, CONFIG)
        await store.begin_stage("run-1", "media", bundle.asset.sha256)
        await store.persist_media_bundle("run-1", bundle)
        await store.begin_stage("run-1", "vision", "a" * 64)
        await store.persist_timeline("run-1", "vision", (raw,), (), "b" * 64)
        await store.complete_run("run-1")
    finally:
        await store.close()
    return project, raw


def test_payload_exposes_display_and_uncertainty_without_rewriting_completed_event(tmp_path):
    async def scenario():
        project, raw = await _legacy_project(tmp_path)
        view = await inspect_run(project, "run-1", "蓝色权杖", tmp_path, mode="lexical")
        assert view["factsProjectionVersion"] == FACTS_PROJECTION_VERSION
        for row in (*view["timeline"], *view["candidates"]):
            assert row["observableFacts"] == list(raw.observable_facts)
            assert row["displayFacts"] == list(display_facts(raw.observable_facts))
            assert row["uncertainty"] == raw.uncertainty
            assert row["eventId"] == raw.event_id
            assert row["evidenceIds"] == list(raw.evidence_ids)
        reader = await SqliteTimelineStore.open(project, read_only=True)
        try:
            after = await reader.load_completed_timeline("run-1")
        finally:
            await reader.close()
        assert after.events == (raw,)
        assert after.run.configuration == CONFIG
        assert after.checkpoints[-1].output_hash == "b" * 64

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["event", "candidate"])
def test_real_browser_legacy_basket_display_export_and_raw_revalidation(tmp_path, kind):
    playwright = pytest.importorskip("playwright.sync_api")
    project, raw = asyncio.run(_legacy_project(tmp_path))
    reference = project.relative_to(tmp_path).as_posix()
    view = asyncio.run(inspect_run(project, "run-1", "", tmp_path, mode="lexical"))
    clip = dict(view["timeline"][0])
    clip.pop("displayFacts")
    clip.pop("uncertainty")
    if kind == "candidate":
        clip.update({"candidateId": "legacy-candidate", "rank": 2})
    key = json.dumps(
        [raw.event_id, raw.source_range.start_us, raw.source_range.end_us], separators=(",", ":")
    )
    old_basket = {
        "schemaVersion": 1,
        "project": reference,
        "runId": "run-1",
        "mediaId": view["media"]["id"],
        "entries": [
            {
                "key": key,
                "kind": kind,
                "clip": clip,
                "source": {
                    "query": "蓝色权杖" if kind == "candidate" else None,
                    "mode": "lexical" if kind == "candidate" else None,
                    "retrievalVersion": "bm25-e5-rrf-v4" if kind == "candidate" else None,
                },
            }
        ],
    }
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            # Restore the pre-projection basket, then revalidate against fresh source rows.
            page.evaluate(
                "basket => localStorage.setItem('gamingcreator.selection.v1:' + encodeURIComponent(basket.project) + ':run-1', JSON.stringify(basket))",
                old_basket,
            )
            page.reload()
            playwright.expect(page.locator("#export-json")).to_be_enabled()
            for selector in ("#timeline-list", "#selection-list"):
                text = page.locator(selector).inner_text()
                assert "f0" not in text and "f8" not in text and "f2" not in text
                assert "蓝色权杖" in text and "待核对" in text
            page.locator("#timeline-list .clip-preview").click()
            detail = page.locator("#active-facts").inner_text()
            assert "f0" not in detail and "待核对" in detail
            page.locator("#mode").select_option("lexical")
            page.locator("#query").fill("蓝色权杖")
            page.locator("#search-button").click()
            playwright.expect(page.locator("#candidate-count")).to_have_text("1")
            candidate_text = page.locator("#candidate-list").inner_text()
            assert (
                "f0" not in candidate_text
                and "f8" not in candidate_text
                and "f2" not in candidate_text
            )
            assert "蓝色权杖" in candidate_text and "待核对" in candidate_text
            with page.expect_download() as download:
                page.locator("#export-json").click()
            document = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            exported = document["selectedClips"][0]
            assert document["factsProjectionVersion"] == FACTS_PROJECTION_VERSION
            assert exported["observableFacts"] == list(display_facts(raw.observable_facts))
            assert exported["uncertainty"] == clean_observation_text(raw.uncertainty)
            assert exported["evidenceIds"] == list(raw.evidence_ids)
            with page.expect_download() as download:
                page.locator("#export-csv").click()
            rows = list(
                csv.DictReader(
                    StringIO(Path(download.value.path()).read_text(encoding="utf-8-sig"))
                )
            )
            assert json.loads(rows[0]["observableFacts"]) == exported["observableFacts"]
            assert rows[0]["uncertainty"] == exported["uncertainty"]
            persisted = page.evaluate(
                "JSON.parse(localStorage.getItem('gamingcreator.selection.v1:' + encodeURIComponent(document.querySelector('#project-select').value) + ':run-1'))"
            )
            assert persisted["entries"][0]["clip"]["observableFacts"] == list(raw.observable_facts)
            # A human projection cannot substitute for canonical facts during validation.
            old_basket["entries"][0]["clip"]["observableFacts"] = exported["observableFacts"]
            page.evaluate(
                "basket => localStorage.setItem('gamingcreator.selection.v1:' + encodeURIComponent(basket.project) + ':run-1', JSON.stringify(basket))",
                old_basket,
            )
            page.reload()
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            assert page.locator("#export-json").is_disabled()
            assert page.locator("#selection-warning").is_visible()
            assert errors == []
        finally:
            browser.close()


def test_real_browser_prefers_completed_details_and_labels_unknown_normally(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    asyncio.run(_legacy_project(tmp_path))
    runs = [
        {"id": "old", "status": "completed", "analysisKind": "temporal"},
        {
            "id": "incomplete-details",
            "status": "failed",
            "analysisKind": "temporal",
            "analysisProfile": "detailed",
        },
        {
            "id": "run-1",
            "status": "completed",
            "analysisKind": "temporal",
            "analysisProfile": "detailed",
        },
        {
            "id": "unknown",
            "status": "completed",
            "analysisKind": "unknown",
            "analysisProfile": "future-profile",
        },
    ]
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            # The stored fixture remains immutable; this controls menu metadata only.
            page.route("**/api/runs?*", lambda route: route.fulfill(json={"runs": runs}))
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            assert page.locator("#run-select").input_value() == "run-1"
            assert "细节动作（试验）" in page.locator("#run-select option:checked").inner_text()
            assert "画面观察" in page.locator("#run-select option[value='unknown']").inner_text()
            assert (
                "连续动作（试验）" in page.locator("#run-select option[value='old']").inner_text()
            )
        finally:
            browser.close()
