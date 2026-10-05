"""Workspace cost history distinguishes missing, known and reserved attempts without sending."""

import json
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import snapshot
from test_inspection_http import get, workspace

from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.application.providers import (
    CostStatus,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.detail_refinement_sidecar import begin_attempt, finish_attempt


def cost_fixture(project, timeline, *, known):
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=provider_refinement_identity()
    ).request
    number = begin_attempt(
        project,
        request,
        budget_id="fixture-budget",
        ceiling=Decimal("20"),
        reservation=Decimal("2"),
        retry=False,
    )
    if known:
        metadata = InvocationMetadata(
            request.identity.provider,
            request.identity.requested_model,
            "deepseek-flash",
            None,
            request.identity.prompt_version,
            request.identity.schema_version,
            1,
            ProviderUsage(
                120, 40, 20, Decimal("0.015"), "CNY", Decimal("0.015"), CostStatus.ESTIMATED
            ),
            230,
            "fixture-price-v1",
            '<img src=x onerror="window.costInjected=1">',
        )
        finish_attempt(
            project,
            request,
            number,
            budget_id="fixture-budget",
            reservation=Decimal("2"),
            result=ProviderResult(
                ProviderStatus.FAILED, None, metadata, ProviderFailure("provider.schema", False)
            ),
        )


@pytest.mark.parametrize("known", [False, True])
def test_http_costs_preserve_unknown_and_read_without_repair(tmp_path, monkeypatch, known):
    project, _, timeline = seed_project(tmp_path)
    cost_fixture(project, timeline, known=known)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = get(
            base, "/api/detail-cost-history?" + urlencode({"project": str(project), "run": "run-1"})
        )
        report = json.loads(raw)
        assert status == 200 and report["runId"] == "run-1"
        assert report["summary"]["knownEstimatedCostCny"] == ("0.015" if known else "0")
        assert report["summary"]["unknownCostCount"] == (0 if known else 1)
        assert report["summary"]["unknownReservedCny"] == ("0" if known else "2")
    assert snapshot(project) == before


def test_missing_and_wrong_run_cost_history_never_create_records(tmp_path, monkeypatch):
    project, _, _ = seed_project(tmp_path, completed=False)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        query = {"project": str(project), "run": "run-1"}
        status, _, raw = get(base, "/api/detail-cost-history?" + urlencode(query))
        assert status == 200 and json.loads(raw)["attempts"] == []
        assert (
            get(base, "/api/detail-cost-history?" + urlencode(dict(query, run="other")))[0] == 404
        )
    assert snapshot(project) == before


def test_damaged_history_is_an_explicit_http_storage_error(tmp_path):
    project, _, timeline = seed_project(tmp_path)
    cost_fixture(project, timeline, known=False)
    ledger = project / "detail-refinement-budgets/fixture-budget/ledger.jsonl"
    ledger.write_text("{broken}")
    before = snapshot(project)
    with workspace(tmp_path) as base:
        status, _, raw = get(
            base, "/api/detail-cost-history?" + urlencode({"project": str(project), "run": "run-1"})
        )
        assert status == 409 and json.loads(raw)["code"] == "refinement.damaged"
    assert snapshot(project) == before


@pytest.mark.parametrize("known", [False, True])
def test_browser_cost_history_keeps_reservations_and_escapes_metadata(tmp_path, monkeypatch, known):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    cost_fixture(project, timeline, known=known)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(base)
            page.locator("#open-detail-costs").click()
            playwright.expect(page.locator("#detail-cost-content")).to_contain_text(
                "本项目全部精分析"
            )
            if known:
                playwright.expect(page.locator("#detail-cost-content")).to_contain_text(
                    "已知估价 ¥0.015"
                )
                page.locator(".detail-cost-attempt summary").click()
                playwright.expect(page.locator("#detail-cost-content")).to_contain_text(
                    "provider.schema"
                )
                assert page.evaluate("window.costInjected === undefined")
                assert page.locator("#detail-cost-content img").count() == 0
            else:
                playwright.expect(page.locator("#detail-cost-content")).to_contain_text(
                    "未知费用 1 次 · 保留预留 ¥2"
                )
                playwright.expect(page.locator("#detail-cost-content")).to_contain_text(
                    "承诺金额 ¥2"
                )
            box = page.locator("#detail-cost-dialog").bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= 391
            page.locator("#close-detail-costs").click()
            page.locator("#run-select").dispatch_event("change")
            playwright.expect(page.locator("#detail-cost-content")).to_be_empty()
        finally:
            browser.close()
    assert snapshot(project) == before
