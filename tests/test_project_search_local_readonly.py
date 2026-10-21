"""Readonly对照：demo-phase0 已落盘 project-searches 须通过现行项目检索投影合同.

Verification = pytest + 只读打开 artifacts JSON / read_project_search.
No DeepSeek / launcher / paid / browser. Missing artifacts => skip.
Does not claim F006 / gap clearance / TD closeout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.retrieval import (
    PROJECT_RETRIEVAL_VERSION,
    assert_project_search_document_contract,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.project_search_files import read_project_search

REPO = Path(__file__).resolve().parents[1]
DEMO_PHASE0 = REPO / "artifacts" / "demo-phase0"
PROJECT_SEARCHES = DEMO_PHASE0 / "project-searches"


def _require_project_search_dirs() -> list[Path]:
    if not PROJECT_SEARCHES.is_dir():
        pytest.skip(f"local project-searches missing: {PROJECT_SEARCHES}")
    dirs = sorted(path for path in PROJECT_SEARCHES.iterdir() if path.is_dir())
    if not dirs:
        pytest.skip(f"local project-searches empty: {PROJECT_SEARCHES}")
    return dirs


def test_local_demo_phase0_project_search_results_pass_document_contract() -> None:
    dirs = _require_project_search_dirs()
    assert len(dirs) >= 1
    for directory in dirs:
        result_path = directory / "result.json"
        receipt_path = directory / "receipt.json"
        assert result_path.is_file(), directory.name
        assert receipt_path.is_file(), directory.name
        document = json.loads(result_path.read_text(encoding="utf-8-sig"))
        assert document.get("schemaVersion") == "project-search-v1"
        assert document.get("scoreIsProbability") is False
        assert document.get("qualityGate") is None
        assert document.get("modelAnalysisCalls") == 0
        assert document.get("newReservations") == 0
        version = document.get("retrievalVersion")
        assert isinstance(version, str) and (
            version == PROJECT_RETRIEVAL_VERSION
            or version.startswith(PROJECT_RETRIEVAL_VERSION + "-saved-details-")
        )
        assert_project_search_document_contract(document)
        # Receipt linkage / inert counters are enforced by the reader.
        loaded = read_project_search(DEMO_PHASE0, directory.name)
        assert loaded["searchId"] == directory.name
        assert loaded["searchId"] == document["searchId"]


def test_assert_project_search_document_contract_rejects_foreign_run_and_paid_claims() -> None:
    dirs = _require_project_search_dirs()
    document = json.loads((dirs[0] / "result.json").read_text(encoding="utf-8-sig"))
    forged = json.loads(json.dumps(document))
    if forged.get("candidates"):
        forged["candidates"][0]["runId"] = "not-a-source-run"
        with pytest.raises(AppError) as owned:
            assert_project_search_document_contract(forged)
        assert owned.value.code == "retrieval.contract"
    paid = json.loads(json.dumps(document))
    paid["modelAnalysisCalls"] = 1
    with pytest.raises(AppError) as claimed:
        assert_project_search_document_contract(paid)
    assert claimed.value.code == "retrieval.contract"
    gated = json.loads(json.dumps(document))
    gated["qualityGate"] = True
    with pytest.raises(AppError) as gate:
        assert_project_search_document_contract(gated)
    assert gate.value.code == "retrieval.contract"