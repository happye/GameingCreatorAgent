"""TD009 readonly对照：demo-phase0 detail-refinements request/result 侧车合同.

Verification = pytest + 只读打开 artifacts JSON.
No DeepSeek / launcher / paid / browser. Missing artifacts => skip.
Does not claim F006 / F010 / TD009 closeout or gap clearance.
Does not rewrite old sidecar JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.detail_refinement_budget import (
    RESULT_SCHEMA_VERSION,
    assert_refinement_request_document_contract,
    assert_refinement_result_document_contract,
    assert_refinement_sidecar_pair_contract,
    refinement_sidecar_contract_gaps,
)
from gamingcreator.domain.errors import AppError

REPO = Path(__file__).resolve().parents[1]
DEMO_PHASE0 = REPO / "artifacts" / "demo-phase0"


def _sidecar_dirs() -> list[Path]:
    if not DEMO_PHASE0.is_dir():
        return []
    return sorted(
        path.parent
        for path in DEMO_PHASE0.rglob("detail-refinements/*/request.json")
        if path.is_file()
    )


def _require_sidecar_dirs() -> list[Path]:
    dirs = _sidecar_dirs()
    if not dirs:
        pytest.skip(f"local detail-refinements missing under {DEMO_PHASE0}")
    return dirs


def test_local_demo_phase0_refinement_request_result_pairs_pass_contract() -> None:
    dirs = _require_sidecar_dirs()
    assert len(dirs) >= 1
    with_result = 0
    for directory in dirs:
        request_path = directory / "request.json"
        assert request_path.is_file(), directory
        request_doc = json.loads(request_path.read_text(encoding="utf-8-sig"))
        assert directory.name == request_doc["requestHash"]
        result_path = directory / "result.json"
        result_doc = None
        if result_path.is_file():
            result_doc = json.loads(result_path.read_text(encoding="utf-8-sig"))
            with_result += 1
            assert result_doc.get("schemaVersion") == RESULT_SCHEMA_VERSION
        assert_refinement_sidecar_pair_contract(request_doc, result_doc)
        assert refinement_sidecar_contract_gaps(request_doc, result_doc) == ()
    assert with_result >= 1


def test_assert_refinement_request_document_contract_rejects_hash_drift_and_acceptance() -> None:
    dirs = _require_sidecar_dirs()
    document = json.loads((dirs[0] / "request.json").read_text(encoding="utf-8-sig"))
    drifted = json.loads(json.dumps(document))
    drifted["requestHash"] = "0" * 64
    with pytest.raises(AppError) as owned:
        assert_refinement_request_document_contract(drifted)
    assert owned.value.code == "refinement.contract"
    forged = json.loads(json.dumps(document))
    forged["qualityGate"] = True
    forged["humanLabels"] = {"reviewer": "bot"}
    with pytest.raises(AppError) as claimed:
        assert_refinement_request_document_contract(forged)
    assert claimed.value.code == "refinement.contract"


def test_assert_refinement_result_document_contract_rejects_payload_and_acceptance_forgeries() -> None:
    dirs = [path for path in _require_sidecar_dirs() if (path / "result.json").is_file()]
    if not dirs:
        pytest.skip("local detail-refinements results missing")
    document = json.loads((dirs[0] / "result.json").read_text(encoding="utf-8-sig"))
    assert_refinement_result_document_contract(document)
    broken = json.loads(json.dumps(document))
    broken["payloadHash"] = "f" * 64
    with pytest.raises(AppError) as hashed:
        assert_refinement_result_document_contract(broken)
    assert hashed.value.code == "refinement.contract"
    gated = json.loads(json.dumps(document))
    gated["formalAcceptancePassed"] = True
    with pytest.raises(AppError) as gate:
        assert_refinement_result_document_contract(gated)
    assert gate.value.code == "refinement.contract"


def test_assert_refinement_sidecar_pair_contract_rejects_cross_request_result() -> None:
    dirs = _require_sidecar_dirs()
    with_result = [path for path in dirs if (path / "result.json").is_file()]
    without_result = [path for path in dirs if not (path / "result.json").is_file()]
    if not with_result or not without_result:
        pytest.skip("need both completed and pending sidecars locally")
    request_doc = json.loads((without_result[0] / "request.json").read_text(encoding="utf-8-sig"))
    result_doc = json.loads((with_result[0] / "result.json").read_text(encoding="utf-8-sig"))
    with pytest.raises(AppError) as mismatched:
        assert_refinement_sidecar_pair_contract(request_doc, result_doc)
    assert mismatched.value.code == "refinement.contract"
    gaps = refinement_sidecar_contract_gaps(request_doc, result_doc)
    assert gaps


def test_assert_refinement_request_rejects_canonical_identity_interval_evidence_drift() -> None:
    dirs = _require_sidecar_dirs()
    document = json.loads((dirs[0] / "request.json").read_text(encoding="utf-8-sig"))
    assert_refinement_request_document_contract(document)

    bad_media = json.loads(json.dumps(document))
    payload = json.loads(bad_media["canonicalJson"])
    payload["mediaSha256"] = "0" * 64
    bad_media["canonicalJson"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Keep requestHash pointing at old body so either hash or field check fails.
    with pytest.raises(AppError) as media:
        assert_refinement_request_document_contract(bad_media)
    assert media.value.code == "refinement.contract"

    # Re-hash so identity field checks run after hash gate.
    aligned = json.loads(json.dumps(document))
    payload = json.loads(aligned["canonicalJson"])
    payload["mediaSha256"] = "0" * 64
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    # Use exact canonical string style from file when possible.
    original = aligned["canonicalJson"]
    payload = json.loads(original)
    payload["candidateId"] = ""
    # Preserve formatting by round-tripping through loads/dumps of original structure.
    import hashlib

    rewritten = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    # Prefer keeping original key order via replace on parsed then dump with same separators as stored.
    # Fallback: dump sorted; update hash to match.
    aligned["canonicalJson"] = rewritten
    aligned["requestHash"] = hashlib.sha256(rewritten.encode("utf-8")).hexdigest()
    # eventFingerprint in envelope still matches payload fingerprint field
    with pytest.raises(AppError) as empty_candidate:
        assert_refinement_request_document_contract(aligned)
    assert empty_candidate.value.code == "refinement.contract"

    interval_bad = json.loads(json.dumps(document))
    payload = json.loads(interval_bad["canonicalJson"])
    payload["interval"]["endUs"] = payload["interval"]["startUs"]
    rewritten = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    interval_bad["canonicalJson"] = rewritten
    interval_bad["requestHash"] = hashlib.sha256(rewritten.encode("utf-8")).hexdigest()
    with pytest.raises(AppError) as spanned:
        assert_refinement_request_document_contract(interval_bad)
    assert spanned.value.code == "refinement.contract"

    claimed = json.loads(json.dumps(document))
    payload = json.loads(claimed["canonicalJson"])
    payload["qualityGate"] = True
    rewritten = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    claimed["canonicalJson"] = rewritten
    claimed["requestHash"] = hashlib.sha256(rewritten.encode("utf-8")).hexdigest()
    with pytest.raises(AppError) as gate:
        assert_refinement_request_document_contract(claimed)
    assert gate.value.code == "refinement.contract"


def test_assert_refinement_sidecar_pair_rejects_range_and_prompt_drift() -> None:
    dirs = [path for path in _require_sidecar_dirs() if (path / "result.json").is_file()]
    if not dirs:
        pytest.skip("local detail-refinements results missing")
    request_doc = json.loads((dirs[0] / "request.json").read_text(encoding="utf-8-sig"))
    result_doc = json.loads((dirs[0] / "result.json").read_text(encoding="utf-8-sig"))
    assert_refinement_sidecar_pair_contract(request_doc, result_doc)

    prompt_drift = json.loads(json.dumps(request_doc))
    prompt_drift["basePromptHash"] = "a" * 64
    with pytest.raises(AppError) as prompt:
        assert_refinement_sidecar_pair_contract(prompt_drift, result_doc)
    assert prompt.value.code == "refinement.contract"

    version_drift = json.loads(json.dumps(request_doc))
    version_drift["basePromptVersion"] = "not-the-result-prompt"
    with pytest.raises(AppError) as version:
        assert_refinement_sidecar_pair_contract(version_drift, result_doc)
    assert version.value.code == "refinement.contract"
