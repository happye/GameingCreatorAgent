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


def test_assert_run_search_document_contract_rejects_media_why_timecode() -> None:
    files = _require_search_files()
    document = None
    run_id = None
    for path in files:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        if loaded.get("candidates"):
            document = loaded
            run_id = path.parts[-3]
            break
    assert document is not None and run_id is not None
    assert_run_search_document_contract(document, expected_run_id=run_id)

    bad_why = json.loads(json.dumps(document))
    bad_why["candidates"][0]["why"] = "cosine only"
    with pytest.raises(AppError) as why:
        assert_run_search_document_contract(bad_why, expected_run_id=run_id)
    assert why.value.code == "retrieval.contract"

    bad_tc = json.loads(json.dumps(document))
    bad_tc["candidates"][0]["endTimecode"] = ""
    with pytest.raises(AppError) as tc:
        assert_run_search_document_contract(bad_tc, expected_run_id=run_id)
    assert tc.value.code == "retrieval.contract"

    media = str(document["candidates"][0]["mediaId"])
    bad_prefix = json.loads(json.dumps(document))
    bad_prefix["candidates"][0]["eventId"] = f"{run_id}:not-{media}:event:x"
    with pytest.raises(AppError) as owned:
        assert_run_search_document_contract(bad_prefix, expected_run_id=run_id)
    assert owned.value.code == "retrieval.contract"


def test_assert_run_search_document_contract_accepts_none_event_id_for_transcript_hits() -> None:
    """Transcript-only candidates omit eventId; ownership gates apply only when present."""
    runs_root = DEMO_PHASE0 / "runs"
    if not runs_root.is_dir():
        pytest.skip(f"local runs missing: {runs_root}")
    search_files = sorted(runs_root.glob("*/searches/*.json"))
    if not search_files:
        pytest.skip("no local run search JSON")
    document = json.loads(search_files[0].read_text(encoding="utf-8-sig"))
    run_id = document["runId"]
    assert_run_search_document_contract(document, expected_run_id=run_id)
    none_event = json.loads(json.dumps(document))
    if not none_event.get("candidates"):
        pytest.skip("no candidates")
    none_event["candidates"][0]["eventId"] = None
    assert_run_search_document_contract(none_event, expected_run_id=run_id)
    empty = json.loads(json.dumps(document))
    empty["candidates"][0]["eventId"] = ""
    with pytest.raises(AppError) as empty_err:
        assert_run_search_document_contract(empty, expected_run_id=run_id)
    assert empty_err.value.code == "retrieval.contract"


def test_assert_search_document_contract_rejects_base_rank_media_span_and_score_kind() -> None:
    """Shared search JSON gates: contiguous rank, mediaId, nonempty us span, scoreKind."""
    files = _require_search_files()
    document = None
    for path in files:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        if loaded.get("candidates"):
            document = loaded
            break
    if document is None:
        pytest.skip("no local run search with candidates")
    assert_search_document_contract(document)

    bad_rank = json.loads(json.dumps(document))
    bad_rank["candidates"][0]["rank"] = 99
    with pytest.raises(AppError) as rank_err:
        assert_search_document_contract(bad_rank)
    assert rank_err.value.code == "retrieval.contract"

    bad_media = json.loads(json.dumps(document))
    bad_media["candidates"][0]["mediaId"] = ""
    with pytest.raises(AppError) as media_err:
        assert_search_document_contract(bad_media)
    assert media_err.value.code == "retrieval.contract"

    bad_span = json.loads(json.dumps(document))
    start = bad_span["candidates"][0]["startUs"]
    bad_span["candidates"][0]["endUs"] = start
    with pytest.raises(AppError) as span_err:
        assert_search_document_contract(bad_span)
    assert span_err.value.code == "retrieval.contract"

    bad_kind = json.loads(json.dumps(document))
    bad_kind["candidates"][0]["scoreKind"] = "probability"
    with pytest.raises(AppError) as kind_err:
        assert_search_document_contract(bad_kind)
    assert kind_err.value.code == "retrieval.contract"

    bad_tc = json.loads(json.dumps(document))
    bad_tc["candidates"][0]["startTimecode"] = ""
    with pytest.raises(AppError) as tc_err:
        assert_search_document_contract(bad_tc)
    assert tc_err.value.code == "retrieval.contract"


def test_assert_run_search_document_contract_rejects_embedding_mode_and_threshold_drift() -> None:
    files = _require_search_files()
    hybrid = None
    lexical = None
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        mode = document.get("mode")
        if mode == "hybrid" and hybrid is None:
            hybrid = document
        if mode == "lexical" and lexical is None:
            lexical = document
        if hybrid is not None and lexical is not None:
            break
    assert hybrid is not None and lexical is not None

    missing = json.loads(json.dumps(hybrid))
    missing["embedding"] = None
    with pytest.raises(AppError) as missing_emb:
        assert_run_search_document_contract(missing)
    assert missing_emb.value.code == "retrieval.contract"

    lexical_emb = json.loads(json.dumps(lexical))
    lexical_emb["embedding"] = {
        "provider": "local-onnx-e5",
        "requested_model": "Xenova/multilingual-e5-small",
        "actual_model": "Xenova/multilingual-e5-small",
        "schema_version": "embedding-v1",
    }
    with pytest.raises(AppError) as lexical_has:
        assert_run_search_document_contract(lexical_emb)
    assert lexical_has.value.code == "retrieval.contract"

    model_drift = json.loads(json.dumps(hybrid))
    model_drift["embedding"] = dict(model_drift["embedding"])
    model_drift["embedding"]["actual_model"] = "forged-other-model"
    with pytest.raises(AppError) as mismatched:
        assert_run_search_document_contract(model_drift)
    assert mismatched.value.code == "retrieval.contract"

    bad_elapsed = json.loads(json.dumps(hybrid))
    bad_elapsed["elapsedMs"] = -1
    with pytest.raises(AppError) as elapsed:
        assert_run_search_document_contract(bad_elapsed)
    assert elapsed.value.code == "retrieval.contract"

    bad_margin = json.loads(json.dumps(hybrid))
    bad_margin["minSemanticMargin"] = "not-a-number"
    with pytest.raises(AppError) as margin:
        assert_run_search_document_contract(bad_margin)
    assert margin.value.code == "retrieval.contract"


def test_assert_run_search_document_contract_rejects_facts_projection_version_and_quality_gate() -> None:
    files = _require_search_files()
    with_fpv = None
    without_fpv = None
    for path in files:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        if document.get("factsProjectionVersion") is not None and with_fpv is None:
            with_fpv = document
        if document.get("factsProjectionVersion") is None and without_fpv is None:
            without_fpv = document
        if with_fpv is not None and without_fpv is not None:
            break
    assert with_fpv is not None and without_fpv is not None
    assert_run_search_document_contract(with_fpv)
    assert_run_search_document_contract(without_fpv)

    forged = json.loads(json.dumps(with_fpv))
    forged["factsProjectionVersion"] = "forged-facts-projection-v0"
    with pytest.raises(AppError) as bad:
        assert_run_search_document_contract(forged)
    assert bad.value.code == "retrieval.contract"

    empty = json.loads(json.dumps(with_fpv))
    empty["factsProjectionVersion"] = ""
    with pytest.raises(AppError) as blank:
        assert_run_search_document_contract(empty)
    assert blank.value.code == "retrieval.contract"

    gated = json.loads(json.dumps(without_fpv))
    gated["qualityGate"] = True
    with pytest.raises(AppError) as gate:
        assert_run_search_document_contract(gated)
    assert gate.value.code == "retrieval.contract"
