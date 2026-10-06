"""The local workspace displays saved temporal evidence without sending frames anywhere."""

import hashlib
import json
from urllib.parse import urlencode

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import publish_v2_fixture, snapshot
from test_detail_query_http import body, post
from test_detail_temporal_provider import temporal_model
from test_inspection_http import get, workspace

from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.application.detail_refinement_budget import (
    RESULT_SCHEMA_VERSION,
    canonical_detail_json,
    payload_hash,
)
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    parse_temporal_detail,
    provider_temporal_identity,
    temporal_refinement_settings,
)
from gamingcreator.infrastructure.detail_refinement_sidecar import freeze_request, sidecar_directory


def publish_temporal_fixture(project, timeline, *, object_uncertain=False):
    request = prepare_refinement(
        timeline,
        timeline.events[0].event_id,
        identity=provider_temporal_identity(),
        settings=temporal_refinement_settings(),
    ).request
    assert request is not None
    model = temporal_model(request)
    if object_uncertain:
        model["entities"][1]["classification"]["status"] = "uncertain"
    model["entities"][1]["description"] = (
        '近镜头物品 <img src=x onerror="window.temporalInjected=true">'
    )
    detail = parse_temporal_detail(json.dumps(model), request)
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
    (directory / "result.json").write_text(json.dumps(document), encoding="utf-8")
    return directory, document, detail


def inspect(base, project, stored, profile):
    return get(
        base,
        "/api/inspect?"
        + urlencode({"project": str(project), "run": stored.run.run_id, "detailProfile": profile}),
    )


def test_missing_v4_cannot_borrow_v2_or_create_requests(tmp_path, monkeypatch):
    project, _, stored = seed_project(tmp_path)
    publish_v2_fixture(project, stored)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, stored, "v4")
        assert status == 200
        view = json.loads(raw)
        assert (
            view["detailRefinementProfile"]["schemaVersion"] == "actor-detail-refinement-schema-v2"
        )
        assert view["timeline"][0]["detailRefinement"]["availability"] == "missing"
        status, _, raw = post(base, body(project, stored, profile="v4"))
        assert status == 200 and json.loads(raw)["result"]["status"] == "unverified"
    assert snapshot(project) == before


def test_saved_scene_identity_and_match_use_the_exact_v4_profile(tmp_path, monkeypatch):
    project, _, stored = seed_project(tmp_path)
    _, document, detail = publish_temporal_fixture(project, stored)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, stored, "v4")
        assert status == 200
        row = json.loads(raw)["timeline"][0]["detailRefinement"]
        assert row["payloadHash"] == document["payloadHash"]
        assert row["detail"]["temporalScene"]["entities"][1]["classification"]["kind"] == "object"
        assert len(row["detail"]["shots"][0]["actors"]) == 1
        status, _, raw = post(base, body(project, stored, profile="v4"))
        report = json.loads(raw)
        assert status == 200 and report["result"]["status"] == "full"
        assert report["result"]["matcherVersion"] == "actor-detail-matcher-v2"
        assert report["refinementPayloadHash"] == payload_hash(detail)
        assert report["humanLabels"] is report["qualityGate"] is None
        status, _, raw = inspect(base, project, stored, "v3")
        assert (
            status == 200
            and json.loads(raw)["timeline"][0]["detailRefinement"]["availability"] == "missing"
        )
    assert snapshot(project) == before


def test_forged_projection_is_rejected_even_when_payload_hash_is_recomputed(tmp_path, monkeypatch):
    project, _, stored = seed_project(tmp_path)
    directory, document, _ = publish_temporal_fixture(project, stored)
    payload = json.loads(document["payloadJson"])
    payload["shots"][0]["actors"][0]["description"] = "scene不支持的新主体描述"
    document["payloadJson"] = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    document["payloadHash"] = hashlib.sha256(document["payloadJson"].encode()).hexdigest()
    (directory / "result.json").write_text(json.dumps(document), encoding="utf-8")
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = inspect(base, project, stored, "v4")
        assert status == 409 and json.loads(raw)["code"] == "refinement.damaged"
        status, _, raw = post(base, body(project, stored, profile="v4"))
        assert status == 409 and json.loads(raw)["code"] == "refinement.damaged"
    assert snapshot(project) == before


@pytest.mark.parametrize(("width", "object_uncertain"), [(1366, False), (390, True)])
def test_browser_keeps_objects_separate_and_shows_safe_evidence_links(
    tmp_path, monkeypatch, width, object_uncertain
):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, stored = seed_project(tmp_path)
    publish_temporal_fixture(project, stored, object_uncertain=object_uncertain)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 800})
            errors = []
            external = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    external.append(request.url) if not request.url.startswith(base + "/") else None
                ),
            )
            page.goto(base)
            playwright.expect(page.locator("#timeline-count")).to_have_text("1")
            page.locator("#detail-profile").select_option("v4")
            playwright.expect(page.locator("#detail-profile")).to_be_enabled()
            page.locator("#timeline-list .clip-preview").click()
            playwright.expect(page.locator("#detail-status")).to_contain_text(
                "已读取保存的主体详情"
            )
            page.locator("#actor-details > summary").click()
            page.locator(".detail-temporal > summary").click()
            playwright.expect(page.locator(".detail-temporal")).to_contain_text(
                "物品 2 · 尚未确定" if object_uncertain else "物品 2 · 模型判断"
            )
            if object_uncertain:
                playwright.expect(page.locator(".detail-temporal")).to_contain_text(
                    "实体未确定 · 模型观察待核对"
                )
            playwright.expect(page.locator(".detail-temporal")).to_contain_text("有持有关系")
            assert page.evaluate("window.temporalInjected === undefined")
            assert not page.locator(".detail-temporal img").count()
            page.locator(".detail-temporal .text-button").first.click()
            playwright.expect(page.locator("#evidence-dialog")).to_be_visible()
            assert (
                page.locator("#evidence-full")
                .get_attribute("src")
                .startswith(("/api/evidence?", base + "/api/evidence?"))
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors and not external
        finally:
            browser.close()
    assert snapshot(project) == before
