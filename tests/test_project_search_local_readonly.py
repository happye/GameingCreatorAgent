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


def test_assert_project_search_document_contract_rejects_media_sha_timecode_and_mode() -> None:
    """Deeper gates: mode/query/topK, source media/sha, candidate align, owned eventId, timecode.

    Transcript-only candidates may keep eventId=None; empty string still refuses.
    """
    dirs = _require_project_search_dirs()
    document = json.loads((dirs[0] / "result.json").read_text(encoding="utf-8-sig"))
    assert_project_search_document_contract(document)

    bad_mode = json.loads(json.dumps(document))
    bad_mode["mode"] = "not-a-mode"
    with pytest.raises(AppError) as mode_err:
        assert_project_search_document_contract(bad_mode)
    assert mode_err.value.code == "retrieval.contract"

    bad_top = json.loads(json.dumps(document))
    bad_top["topK"] = 0
    with pytest.raises(AppError) as top_err:
        assert_project_search_document_contract(bad_top)
    assert top_err.value.code == "retrieval.contract"

    if not document.get("sources") or not document.get("candidates"):
        pytest.skip("demo project-search has no sources/candidates to forge")

    bad_sha = json.loads(json.dumps(document))
    bad_sha["sources"][0]["sourceSha256"] = "0" * 63 + "g"
    with pytest.raises(AppError) as sha_err:
        assert_project_search_document_contract(bad_sha)
    assert sha_err.value.code == "retrieval.contract"

    drift_media = json.loads(json.dumps(document))
    drift_media["candidates"][0]["mediaId"] = "not-the-source-media"
    with pytest.raises(AppError) as media_err:
        assert_project_search_document_contract(drift_media)
    assert media_err.value.code == "retrieval.contract"

    drift_sha = json.loads(json.dumps(document))
    drift_sha["candidates"][0]["sourceSha256"] = "a" * 64
    with pytest.raises(AppError) as cand_sha_err:
        assert_project_search_document_contract(drift_sha)
    assert cand_sha_err.value.code == "retrieval.contract"

    owned = json.loads(json.dumps(document))
    run_id = owned["candidates"][0]["runId"]
    owned["candidates"][0]["eventId"] = f"foreign-run:{owned['candidates'][0]['mediaId']}:event:x"
    with pytest.raises(AppError) as owned_err:
        assert_project_search_document_contract(owned)
    assert owned_err.value.code == "retrieval.contract"

    empty_event = json.loads(json.dumps(document))
    empty_event["candidates"][0]["eventId"] = ""
    with pytest.raises(AppError) as empty_err:
        assert_project_search_document_contract(empty_event)
    assert empty_err.value.code == "retrieval.contract"

    # None remains legal for transcript-only joint hits.
    none_event = json.loads(json.dumps(document))
    none_event["candidates"][0]["eventId"] = None
    assert_project_search_document_contract(none_event)

    bad_tc = json.loads(json.dumps(document))
    bad_tc["candidates"][0]["startTimecode"] = ""
    with pytest.raises(AppError) as tc_err:
        assert_project_search_document_contract(bad_tc)
    assert tc_err.value.code == "retrieval.contract"
