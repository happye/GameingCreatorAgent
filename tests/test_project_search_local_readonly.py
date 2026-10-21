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


def test_assert_project_search_document_contract_rejects_embedding_and_topk_overflow() -> None:
    dirs = _require_project_search_dirs()
    hybrid = None
    lexical = None
    for directory in dirs:
        result_path = directory / "result.json"
        if not result_path.is_file():
            continue
        document = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if document.get("schemaVersion") != "project-search-v1":
            continue
        mode = document.get("mode")
        if mode == "hybrid" and hybrid is None:
            hybrid = document
        if mode == "lexical" and lexical is None:
            lexical = document
        if hybrid is not None and lexical is not None:
            break
    assert hybrid is not None

    missing = json.loads(json.dumps(hybrid))
    missing["embedding"] = None
    with pytest.raises(AppError) as missing_emb:
        assert_project_search_document_contract(missing)
    assert missing_emb.value.code == "retrieval.contract"

    overflow = json.loads(json.dumps(hybrid))
    overflow["topK"] = 1
    if len(overflow.get("candidates") or []) <= 1 and overflow.get("candidates"):
        overflow["candidates"] = list(overflow["candidates"]) + list(overflow["candidates"])
    with pytest.raises(AppError) as over:
        assert_project_search_document_contract(overflow)
    assert over.value.code == "retrieval.contract"

    if lexical is not None:
        lexical_emb = json.loads(json.dumps(lexical))
        lexical_emb["embedding"] = {
            "provider": "local-onnx-e5",
            "requested_model": "Xenova/multilingual-e5-small",
            "actual_model": "Xenova/multilingual-e5-small",
            "schema_version": "embedding-v1",
        }
        with pytest.raises(AppError) as lexical_has:
            assert_project_search_document_contract(lexical_emb)
        assert lexical_has.value.code == "retrieval.contract"

    model_drift = json.loads(json.dumps(hybrid))
    model_drift["embedding"] = dict(model_drift["embedding"])
    model_drift["embedding"]["actual_model"] = "forged-other-model"
    with pytest.raises(AppError) as mismatched:
        assert_project_search_document_contract(model_drift)
    assert mismatched.value.code == "retrieval.contract"


def test_assert_project_search_document_contract_rejects_started_at_and_validation_timing_drift() -> None:
    dirs = _require_project_search_dirs()
    document = None
    for directory in dirs:
        result_path = directory / "result.json"
        if not result_path.is_file():
            continue
        loaded = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if loaded.get("schemaVersion") == "project-search-v1":
            document = loaded
            break
    assert document is not None
    assert_project_search_document_contract(document)

    naive = json.loads(json.dumps(document))
    naive["startedAt"] = "2026-10-07T17:12:25.896681"
    with pytest.raises(AppError) as no_tz:
        assert_project_search_document_contract(naive)
    assert no_tz.value.code == "retrieval.contract"

    bad_svm = json.loads(json.dumps(document))
    bad_svm["sourceValidationMs"] = -1
    with pytest.raises(AppError) as svm:
        assert_project_search_document_contract(bad_svm)
    assert svm.value.code == "retrieval.contract"

    gated = json.loads(json.dumps(document))
    gated["qualityGate"] = True
    with pytest.raises(AppError) as gate:
        assert_project_search_document_contract(gated)
    assert gate.value.code == "retrieval.contract"

    bad_path = json.loads(json.dumps(document))
    bad_path["recordPath"] = "G:/elsewhere/not-this-search/result.json"
    with pytest.raises(AppError) as path_err:
        assert_project_search_document_contract(bad_path)
    assert path_err.value.code == "retrieval.contract"

    zulu = json.loads(json.dumps(document))
    zulu["startedAt"] = "2026-10-07T09:12:25.896681Z"
    assert_project_search_document_contract(zulu)
