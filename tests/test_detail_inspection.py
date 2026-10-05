"""Offline sidecar inspection fixtures are engineering evidence, not human labels."""

import asyncio
import hashlib
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_inspection_http import get, workspace
from test_sqlite_store import CONFIG, bundle_fixture, event_fixture

from gamingcreator.application.detail_refinement import (
    RefinementSettings,
    default_refinement_identity,
    prepare_refinement,
    refinement_settings_hash,
)
from gamingcreator.application.detail_refinement_budget import (
    RESULT_SCHEMA_VERSION,
    canonical_detail_json,
    payload_hash,
)
from gamingcreator.domain.actor_details import (
    ActorDetail,
    AttributeKind,
    AttributeStatus,
    CandidateDetail,
    DetailAttribute,
    ShotDetail,
    source_range_for_evidence,
)
from gamingcreator.infrastructure.detail_refinement_sidecar import freeze_request, sidecar_directory
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.service import inspect_run


def seed_project(root: Path, *, completed: bool = True, visual: bool = True):
    source_root = root / "artifacts"
    source_root.mkdir(parents=True)
    bundle = bundle_fixture(source_root)
    image = replace(bundle.images[0], evidence_id=f"run-1:{bundle.asset.media_id}:image:000000")
    bundle = replace(bundle, images=(image,))
    from gamingcreator.application.media import SamplingParameters

    write_manifest(bundle, SamplingParameters())
    event = replace(
        event_fixture(bundle, event_id=f"run-1:{bundle.asset.media_id}:event:" + "ab" * 12),
        observable_facts=("画面左侧有白色头发的主体。",),
        modality="visual" if visual else "audio",
    )
    configuration = replace(
        CONFIG,
        analysis=replace(
            CONFIG.analysis,
            schema_version=2,
            price_version="fixture-price-v1",
            vision_prompt_hash="c" * 64,
        ),
    )
    project = source_root / "project"

    async def create():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-1", bundle.asset, configuration)
            await store.begin_stage("run-1", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-1", bundle)
            await store.begin_stage("run-1", "vision", "a" * 64)
            await store.persist_timeline("run-1", "vision", (event,), (), "b" * 64)
            if completed:
                await store.complete_run("run-1")
            return await store.load_timeline("run-1", require_completed=completed)
        finally:
            await store.close()

    return project, bundle, asyncio.run(create())


def publish_fixture(project, timeline, *, settings=None):
    prepared = prepare_refinement(timeline, timeline.events[0].event_id, settings=settings)
    request = prepared.request
    assert request is not None and request.base_prompt_hash is not None
    interval = source_range_for_evidence(request.evidence)
    ids = tuple(item.evidence_id for item in request.evidence)
    attributes = (
        DetailAttribute(
            "hair", AttributeKind.HAIR_COLOR, "white", AttributeStatus.OBSERVED, ids, interval
        ),
        DetailAttribute(
            "item", AttributeKind.HELD_CLASS, "staff", AttributeStatus.UNCERTAIN, ids, interval
        ),
    )
    actor = ActorDetail(
        "shot-1", "left", '<img src=x onerror="window.detailInjected=1"> 左侧主体', attributes
    )
    detail = CandidateDetail(
        request.run_id,
        timeline.run.asset.media_id,
        request.event_id,
        request.candidate_id,
        request.event_fingerprint,
        request.media_sha256,
        request.configuration_hash,
        request.pipeline_version,
        request.base_prompt_version,
        request.base_prompt_hash,
        request.identity.prompt_hash,
        request.source_range,
        request.evidence,
        (ShotDetail("shot-1", interval, ids, (), (actor,)),),
        ("具体持有物类别无法确认。",),
    )
    digest = freeze_request(project, request)
    directory = sidecar_directory(project, request.run_id, digest)
    document = {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "requestHash": digest,
        "payloadHash": payload_hash(detail),
        "payloadJson": canonical_detail_json(detail),
        "actualModel": None,
        "modelRevision": None,
        "costCny": None,
    }
    # Persist a synthetic typed output; no provider is ever instantiated.
    (directory / "result.json").write_text(json.dumps(document), encoding="utf-8")
    return directory, document, detail


def refuse_sends(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Inspection must not plan, write, or call a provider.")

    for name in ("send_refinement", "begin_attempt", "freeze_request"):
        monkeypatch.setattr(
            f"gamingcreator.infrastructure.detail_refinement_sidecar.{name}", forbidden
        )
    monkeypatch.setattr("httpx.AsyncClient.send", forbidden)


def test_missing_refresh_and_lexical_search_read_without_creating_sidecars(tmp_path, monkeypatch):
    project, _, timeline = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    reference = project.relative_to(tmp_path).as_posix()
    with workspace(tmp_path) as base:
        query = {"project": reference, "run": "run-1", "mode": "lexical"}
        for text in ("", "", "白色"):
            status, _, body = get(base, "/api/inspect?" + urlencode({**query, "query": text}))
            assert status == 200
            view = json.loads(body)
            row = view["timeline"][0]
            assert row["detailRefinement"]["status"] == "unverified"
            assert row["detailRefinement"]["availability"] == "missing"
            assert row["detailRefinement"]["detail"] is None
            prepared = prepare_refinement(timeline, row["eventId"])
            assert row["detailRefinement"]["requestHash"] == prepared.request_hash
            assert view["detailRefinementProfile"]["settingsHash"] == refinement_settings_hash(
                RefinementSettings()
            )
            assert (
                view["detailRefinementProfile"]["schemaVersion"]
                == default_refinement_identity().schema_version
            )
            if text:
                assert len(view["candidates"]) == 1
                assert view["candidates"][0]["detailRefinement"] == row["detailRefinement"]
                assert view["candidates"][0]["rank"] == 1
    assert not (project / "runs/run-1/detail-refinements").exists()
    assert not (project / "detail-refinement-budgets").exists()


def test_reused_detail_is_unverified_and_reads_do_not_rewrite_source_or_sidecar(
    tmp_path, monkeypatch
):
    project, _, timeline = seed_project(tmp_path)
    directory, _, detail = publish_fixture(project, timeline)
    before = {
        item.name: (item.read_bytes(), item.stat().st_mtime_ns) for item in directory.iterdir()
    }
    refuse_sends(monkeypatch)
    for query in ("", "白色", ""):
        view = asyncio.run(inspect_run(project, "run-1", query, tmp_path, mode="lexical"))
        row = view["timeline"][0]
        event = timeline.events[0]
        assert row["observableFacts"] == list(event.observable_facts)
        assert (row["startUs"], row["endUs"]) == (
            event.source_range.start_us,
            event.source_range.end_us,
        )
        assert row["evidenceIds"] == list(event.evidence_ids)
        payload = row["detailRefinement"]
        assert payload["status"] == "unverified" and payload["availability"] == "reused"
        assert payload["detail"]["eventFingerprint"] == detail.event_fingerprint
        assert payload["detail"]["shots"][0]["actors"][0]["attributes"][1]["status"] == "uncertain"
        assert payload["detail"]["unassignedEvidenceIds"] == []
        if query:
            assert view["candidates"][0]["detailRefinement"] == payload
    assert before == {
        item.name: (item.read_bytes(), item.stat().st_mtime_ns) for item in directory.iterdir()
    }
    assert not (project / "detail-refinement-budgets").exists()


@pytest.mark.parametrize(
    "damage", ["hash", "foreign", "future", "extra", "oversize", "request_version", "base_prompt"]
)
def test_damaged_sidecars_report_a_storage_error_over_http(tmp_path, damage):
    project, _, timeline = seed_project(tmp_path)
    directory, document, _ = publish_fixture(project, timeline)
    result_path = directory / "result.json"
    if damage == "hash":
        document["payloadHash"] = "0" * 64
    elif damage in ("foreign", "future", "extra"):
        payload = json.loads(document["payloadJson"])
        if damage == "foreign":
            payload["eventFingerprint"] = "d" * 64
        elif damage == "future":
            payload["schemaVersion"] = "actor-details-v999"
        else:
            payload["unrecognisedField"] = "cannot silently discard"
        document["payloadJson"] = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        document["payloadHash"] = hashlib.sha256(document["payloadJson"].encode()).hexdigest()
    elif damage in ("request_version", "base_prompt"):
        request_path = directory / "request.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request["schemaVersion" if damage == "request_version" else "basePromptHash"] = (
            999 if damage == "request_version" else "d" * 64
        )
        request_path.write_text(json.dumps(request), encoding="utf-8")
    if damage == "oversize":
        result_path.write_bytes(b" " * 1_048_577)
    else:
        result_path.write_text(json.dumps(document), encoding="utf-8")
    query = urlencode({"project": str(project), "run": "run-1"})
    with workspace(tmp_path) as base:
        status, _, body = get(base, "/api/inspect?" + query)
        assert status == 409
        assert json.loads(body)["code"].startswith("refinement.")


def test_reader_pins_settings_instead_of_picking_another_version(tmp_path):
    project, _, timeline = seed_project(tmp_path)
    publish_fixture(project, timeline, settings=RefinementSettings(max_output_tokens=4096))
    view = asyncio.run(inspect_run(project, "run-1", "", tmp_path))
    assert view["timeline"][0]["detailRefinement"]["availability"] == "missing"


@pytest.mark.parametrize(
    ("completed", "visual", "availability"),
    [(False, True, "run_incomplete"), (True, False, "unsupported")],
)
def test_unfinished_and_nonvisual_events_remain_unverified(
    tmp_path, completed, visual, availability
):
    project, _, _ = seed_project(tmp_path, completed=completed, visual=visual)
    view = asyncio.run(inspect_run(project, "run-1", "", tmp_path))
    assert view["timeline"][0]["detailRefinement"] == {
        "status": "unverified",
        "availability": availability,
        "requestHash": None,
        "detail": None,
    }


@pytest.mark.parametrize("source", [True, False])
def test_reuse_requires_intact_registered_source_and_evidence(tmp_path, source):
    project, bundle, timeline = seed_project(tmp_path)
    publish_fixture(project, timeline)
    path = bundle.asset.source_path if source else bundle.images[0].path
    path.write_bytes(b"tampered")
    with workspace(tmp_path) as base:
        status, _, body = get(
            base, "/api/inspect?" + urlencode({"project": str(project), "run": "run-1"})
        )
        assert status == 409 and json.loads(body)["code"] == "storage.integrity"


def test_sidecar_directory_junction_is_rejected_by_inspection(tmp_path):
    project, _, timeline = seed_project(tmp_path)
    prepared = prepare_refinement(timeline, timeline.events[0].event_id)
    assert prepared.request_hash is not None
    directory = sidecar_directory(project, "run-1", prepared.request_hash)
    directory.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, directory, target_is_directory=True)
    except OSError:
        linked = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(directory), str(outside)], capture_output=True
        )
        assert linked.returncode == 0
    with workspace(tmp_path) as base:
        status, _, body = get(
            base, "/api/inspect?" + urlencode({"project": str(project), "run": "run-1"})
        )
        assert status == 409 and json.loads(body)["code"] == "refinement.path"


@pytest.mark.parametrize("reused", [False, True])
def test_browser_details_are_safe_and_basket_exports_remain_original(tmp_path, reused):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    if reused:
        publish_fixture(project, timeline)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#timeline-list .clip-preview").click()
            playwright.expect(page.locator("#detail-status")).to_contain_text(
                "复合条件匹配未验证" if reused else "主体详情未验证"
            )
            if reused:
                page.locator("#actor-details summary").click()
                text = page.locator("#actor-detail-list").inner_text()
                assert "已观察 · 发色：白色" in text
                assert "待核对 · 持有物类别：权杖" in text and "支持源帧" in text
                assert page.locator("#actor-detail-list img").count() == 0
                assert page.evaluate("window.detailInjected === undefined")
            page.locator("#add-active").click()
            page.reload()
            playwright.expect(page.locator("#export-json")).to_be_enabled()
            page.locator("#selection-list .clip-preview").click()
            playwright.expect(page.locator("#detail-status")).to_contain_text(
                "复合条件匹配未验证" if reused else "主体详情未验证"
            )
            with page.expect_download() as download:
                page.locator("#export-json").click()
            document = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
            exported = document["selectedClips"][0]
            assert exported["observableFacts"] == list(timeline.events[0].observable_facts)
            assert exported["evidenceIds"] == list(timeline.events[0].evidence_ids)
            assert "detailRefinement" not in exported
            saved = page.evaluate("JSON.parse(localStorage.getItem(Object.keys(localStorage)[0]))")
            assert "detailRefinement" not in saved["entries"][0]["clip"]
            assert errors == []
        finally:
            browser.close()
