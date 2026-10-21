"""Readonly对照：demo-phase0 单任务 searches JSON 须通过 run 归属合同.

Verification = pytest + 只读打开 artifacts JSON.
No DeepSeek / launcher / paid / browser. Missing artifacts => skip.
Does not claim F006 / gap clearance / TD closeout.
Does not rewrite old search JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.retrieval import (
    RETRIEVAL_VERSION,
    RETRIEVAL_VERSION_PREFIX,
    assert_run_search_document_contract,
    assert_search_document_contract,
)
from gamingcreator.domain.errors import AppError

REPO = Path(__file__).resolve().parents[1]
DEMO_PHASE0 = REPO / "artifacts" / "demo-phase0"


def _search_files() -> list[Path]:
    if not DEMO_PHASE0.is_dir():
        return []
    return sorted(DEMO_PHASE0.glob("runs/*/searches/*.json"))


def _require_search_files() -> list[Path]:
    files = _search_files()
    if not files:
        pytest.skip(f"local run searches missing under {DEMO_PHASE0}")
    return files


def test_local_demo_phase0_run_searches_pass_run_document_contract() -> None:
    files = _require_search_files()
    assert len(files) >= 1
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        run_id = path.parts[-3]
        assert_run_search_document_contract(document, expected_run_id=run_id)
        version = document["retrievalVersion"]
        assert isinstance(version, str) and version.startswith(RETRIEVAL_VERSION_PREFIX)
        assert document.get("scoreIsProbability") is False


def test_assert_run_search_document_contract_rejects_foreign_event_and_acceptance() -> None:
    files = _require_search_files()
    with_candidates = [
        path
        for path in files
        if json.loads(path.read_text(encoding="utf-8-sig")).get("candidates")
    ]
    if not with_candidates:
        pytest.skip("no local run searches with candidates")
    path = with_candidates[0]
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    run_id = path.parts[-3]
    assert_run_search_document_contract(document, expected_run_id=run_id)

    foreign = json.loads(json.dumps(document))
    foreign["candidates"][0]["eventId"] = "not-this-run:event:deadbeef"
    with pytest.raises(AppError) as owned:
        assert_run_search_document_contract(foreign, expected_run_id=run_id)
    assert owned.value.code == "retrieval.contract"

    wrong_run = json.loads(json.dumps(document))
    with pytest.raises(AppError) as path_mismatch:
        assert_run_search_document_contract(wrong_run, expected_run_id="definitely-not-" + run_id)
    assert path_mismatch.value.code == "retrieval.contract"

    gated = json.loads(json.dumps(document))
    gated["qualityGate"] = True
    with pytest.raises(AppError) as gate:
        assert_run_search_document_contract(gated, expected_run_id=run_id)
    assert gate.value.code == "retrieval.contract"

    bad_kind = json.loads(json.dumps(document))
    bad_kind["candidates"][0]["scoreKind"] = "probability"
    with pytest.raises(AppError) as kind:
        assert_run_search_document_contract(bad_kind, expected_run_id=run_id)
    assert kind.value.code == "retrieval.contract"

    # Base contract still composes.
    assert_search_document_contract(document)
    assert RETRIEVAL_VERSION.startswith(RETRIEVAL_VERSION_PREFIX)
