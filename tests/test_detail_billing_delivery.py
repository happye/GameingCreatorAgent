"""Public imports and actual workspace display keep human and API cost evidence separate."""

import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from test_detail_billing_confirmation import (
    failed,
    fixture,
    import_material,
    material,
    save_material,
)
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import snapshot
from test_inspection_http import workspace

from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history
from gamingcreator.infrastructure.detail_refinement_sidecar import begin_attempt

SPEC = importlib.util.spec_from_file_location(
    "confirm_detail_billing_script", Path(__file__).parents[1] / "scripts/confirm-detail-billing.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = script
SPEC.loader.exec_module(script)


def test_public_script_imports_exact_attempt_and_replay_has_no_new_effect(tmp_path, capsys):
    project, request, body, path = fixture(tmp_path)
    arguments = [
        "--project",
        str(project),
        "--run",
        request.run_id,
        "--budget",
        body["budgetId"],
        "--request",
        body["requestHash"],
        "--attempt",
        "1",
        "--material",
        str(path),
    ]
    assert script.main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["materialSha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["newProviderCalls"] == 0 and result["sendBudgetUnchanged"]
    assert result["sharedHumanBillingSummary"]["reconciledCommitmentCny"] == "0"
    saved = snapshot(project)
    assert script.main(arguments) == 0
    assert snapshot(project) == saved
    assert refinement_cost_history(project, request.run_id)["summary"]["unknownCostCount"] == 1


def test_public_script_wrong_attempt_refuses_without_writing(tmp_path, capsys):
    project, request, body, path = fixture(tmp_path)
    before = snapshot(project)
    assert (
        script.main(
            [
                "--project",
                str(project),
                "--run",
                request.run_id,
                "--budget",
                body["budgetId"],
                "--request",
                body["requestHash"],
                "--attempt",
                "2",
                "--material",
                str(path),
            ]
        )
        == 2
    )
    assert "人工费用确认无效" in capsys.readouterr().err
    assert snapshot(project) == before


@pytest.mark.parametrize("width", [1366, 390])
def test_browser_shows_confirmed_zero_and_original_unknown_separately(tmp_path, monkeypatch, width):
    playwright = pytest.importorskip("playwright.sync_api")
    project, _, timeline = seed_project(tmp_path)
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=provider_refinement_identity()
    ).request
    assert request is not None
    number = begin_attempt(
        project,
        request,
        budget_id="budget-a",
        ceiling=Decimal("20"),
        reservation=Decimal("2"),
        retry=False,
    )
    failed(project, request, number)
    body = material(project, request, number)
    import_material(project, body, save_material(tmp_path, body))
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base, playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(base)
            page.locator("#open-detail-costs").click()
            content = page.locator("#detail-cost-content")
            playwright.expect(content).to_contain_text("未知费用 1 次")
            playwright.expect(content).to_contain_text("承诺金额 ¥2")
            playwright.expect(content).to_contain_text("已由用户核实未扣费")
            playwright.expect(content).to_contain_text("人工核对释放的预留 ¥2")
            playwright.expect(content).to_contain_text("核对后占用 ¥0")
            playwright.expect(content).to_contain_text("核对后占用不代表允许新调用")
            page.locator(".detail-cost-attempt summary").click()
            playwright.expect(content).to_contain_text("用户已核实本次未扣费")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        finally:
            browser.close()
    assert snapshot(project) == before
