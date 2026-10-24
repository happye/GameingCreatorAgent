"""Readonly对照：demo-phase0 SQLite retrieval_runs 须通过持久化检索信封合同.

Verification = pytest + SqliteTimelineStore(read_only=True).
No DeepSeek / launcher / paid / browser. Missing artifacts => skip.
Does not claim F006 / gap clearance / TD closeout.
Does not rewrite SQLite rows.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from gamingcreator.application.retrieval import (
    RETRIEVAL_VERSION,
    assert_persisted_retrieval_contract,
    assert_run_search_document_contract,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

REPO = Path(__file__).resolve().parents[1]
DEMO_PHASE0 = REPO / "artifacts" / "demo-phase0"

_OPENED: list[SqliteTimelineStore] = []


async def _open(project: Path) -> SqliteTimelineStore:
    store = await SqliteTimelineStore.open(project, read_only=True)
    _OPENED.append(store)
    return store


@pytest.fixture(autouse=True)
def _close_opened_stores():
    # Close read-only stores opened inside asyncio.run so -W error never sees a leak.
    yield
    while _OPENED:
        asyncio.run(_OPENED.pop().close())


def _require_sqlite() -> Path:
    db = DEMO_PHASE0 / "timeline.sqlite3"
    if not db.is_file():
        pytest.skip(f"local artifact DB missing: {db}")
    return db


def _retrieval_ids(db: Path) -> list[str]:
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return [
            row[0]
            for row in con.execute(
                "SELECT retrieval_id FROM retrieval_runs ORDER BY created_at, retrieval_id"
            )
        ]
    finally:
        con.close()


def test_local_demo_phase0_sqlite_retrieval_runs_pass_persisted_contract() -> None:
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")
    assert len(ids) >= 1

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        for retrieval_id in ids:
            document = await store.load_retrieval(retrieval_id)
            assert_persisted_retrieval_contract(document)
            assert document["retrievalId"] == retrieval_id
            result = document["result"]
            assert isinstance(result, dict)
            assert_run_search_document_contract(result, expected_run_id=str(document["runId"]))

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_hit_drift_and_acceptance() -> None:
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        # Prefer a row with candidates for drift checks.
        document = None
        for retrieval_id in ids:
            loaded = await store.load_retrieval(retrieval_id)
            if loaded["result"].get("candidates"):
                document = loaded
                break
        assert document is not None
        assert_persisted_retrieval_contract(document)

        drifted = json.loads(json.dumps(document))
        drifted["hits"][0]["event_id"] = "not-this-run:event:deadbeef"
        with pytest.raises(AppError) as owned:
            assert_persisted_retrieval_contract(drifted)
        assert owned.value.code == "retrieval.contract"

        gated = json.loads(json.dumps(document))
        gated["result"]["qualityGate"] = True
        with pytest.raises(AppError) as gate:
            assert_persisted_retrieval_contract(gated)
        assert gate.value.code == "retrieval.contract"

        bad_hash = json.loads(json.dumps(document))
        bad_hash["queryHash"] = "0" * 64
        with pytest.raises(AppError) as hashed:
            assert_persisted_retrieval_contract(bad_hash)
        assert hashed.value.code == "retrieval.contract"

        assert RETRIEVAL_VERSION.startswith("bm25-e5-rrf-v")

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_evidence_and_range_drift() -> None:
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        document = None
        for retrieval_id in ids:
            loaded = await store.load_retrieval(retrieval_id)
            if loaded["result"].get("candidates"):
                document = loaded
                break
        assert document is not None

        evidence_drift = json.loads(json.dumps(document))
        evidence_drift["hits"][0]["evidence_ids"] = ["forged-evidence"]
        with pytest.raises(AppError) as evidence:
            assert_persisted_retrieval_contract(evidence_drift)
        assert evidence.value.code == "retrieval.contract"

        range_drift = json.loads(json.dumps(document))
        range_drift["hits"][0]["start_us"] = int(range_drift["hits"][0]["start_us"]) + 1
        with pytest.raises(AppError) as spanned:
            assert_persisted_retrieval_contract(range_drift)
        assert spanned.value.code == "retrieval.contract"

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_media_why_timecode_drift() -> None:
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        document = None
        for retrieval_id in ids:
            loaded = await store.load_retrieval(retrieval_id)
            if loaded["result"].get("candidates"):
                document = loaded
                break
        assert document is not None

        media_drift = json.loads(json.dumps(document))
        media_drift["result"]["candidates"][0]["mediaId"] = "not-the-envelope-media"
        with pytest.raises(AppError) as media:
            assert_persisted_retrieval_contract(media_drift)
        assert media.value.code == "retrieval.contract"

        why_missing = json.loads(json.dumps(document))
        why_missing["result"]["candidates"][0]["why"] = "cosine=0.9"
        with pytest.raises(AppError) as why:
            assert_persisted_retrieval_contract(why_missing)
        assert why.value.code == "retrieval.contract"

        tc_missing = json.loads(json.dumps(document))
        tc_missing["result"]["candidates"][0]["startTimecode"] = ""
        with pytest.raises(AppError) as tc:
            assert_persisted_retrieval_contract(tc_missing)
        assert tc.value.code == "retrieval.contract"

        prefix_drift = json.loads(json.dumps(document))
        run_id = str(document["runId"])
        media_id = str(document["mediaId"])
        # Keep run ownership prefix but swap media segment.
        prefix_drift["result"]["candidates"][0]["eventId"] = f"{run_id}:other-media:event:deadbeef"
        prefix_drift["hits"][0]["event_id"] = prefix_drift["result"]["candidates"][0]["eventId"]
        with pytest.raises(AppError) as owned:
            assert_persisted_retrieval_contract(prefix_drift)
        assert owned.value.code == "retrieval.contract"
        assert media_id  # envelope media retained for clarity

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_mode_rank_elapsed_and_empty_span() -> None:
    """Deeper envelope gates: mode, contiguous ranks 1..n, elapsedMs align, nonempty hit span."""
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        document = None
        for retrieval_id in ids:
            loaded = await store.load_retrieval(retrieval_id)
            if loaded["result"].get("candidates"):
                document = loaded
                break
        assert document is not None
        assert_persisted_retrieval_contract(document)

        bad_mode = json.loads(json.dumps(document))
        bad_mode["result"]["mode"] = "not-a-mode"
        with pytest.raises(AppError) as mode_err:
            assert_persisted_retrieval_contract(bad_mode)
        assert mode_err.value.code == "retrieval.contract"

        bad_rank = json.loads(json.dumps(document))
        bad_rank["hits"][0]["rank"] = 99
        bad_rank["result"]["candidates"][0]["rank"] = 99
        with pytest.raises(AppError) as rank_err:
            assert_persisted_retrieval_contract(bad_rank)
        assert rank_err.value.code == "retrieval.contract"

        if "elapsedMs" in document and "elapsedMs" in document["result"]:
            bad_elapsed = json.loads(json.dumps(document))
            bad_elapsed["elapsedMs"] = int(bad_elapsed["elapsedMs"]) + 7
            with pytest.raises(AppError) as elapsed_err:
                assert_persisted_retrieval_contract(bad_elapsed)
            assert elapsed_err.value.code == "retrieval.contract"

        empty_span = json.loads(json.dumps(document))
        start = empty_span["hits"][0]["start_us"]
        empty_span["hits"][0]["end_us"] = start
        empty_span["result"]["candidates"][0]["endUs"] = start
        with pytest.raises(AppError) as span_err:
            assert_persisted_retrieval_contract(empty_span)
        assert span_err.value.code == "retrieval.contract"

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_parameters_and_embedding_space_drift() -> None:
    """parameters.mode／topK 与 embeddingSpace 形态须与 result／mode 对齐。"""
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        hybrid_doc = None
        lexical_doc = None
        for retrieval_id in ids:
            loaded = await store.load_retrieval(retrieval_id)
            mode = loaded["result"].get("mode")
            if mode == "hybrid" and hybrid_doc is None:
                hybrid_doc = loaded
            if mode == "lexical" and lexical_doc is None:
                lexical_doc = loaded
            if hybrid_doc is not None and lexical_doc is not None:
                break
        assert hybrid_doc is not None

        mode_drift = json.loads(json.dumps(hybrid_doc))
        mode_drift["parameters"] = dict(mode_drift["parameters"])
        mode_drift["parameters"]["mode"] = "lexical"
        with pytest.raises(AppError) as mismatched:
            assert_persisted_retrieval_contract(mode_drift)
        assert mismatched.value.code == "retrieval.contract"

        topk_drift = json.loads(json.dumps(hybrid_doc))
        topk_drift["parameters"] = dict(topk_drift["parameters"])
        topk_drift["parameters"]["topK"] = 0
        with pytest.raises(AppError) as topk:
            assert_persisted_retrieval_contract(topk_drift)
        assert topk.value.code == "retrieval.contract"

        # candidates exceed topK
        overflow = json.loads(json.dumps(hybrid_doc))
        overflow["parameters"] = dict(overflow["parameters"])
        overflow["parameters"]["topK"] = 1
        if len(overflow["result"]["candidates"]) <= 1:
            # synthesize second candidate clone for overflow when only one hit
            if overflow["result"]["candidates"]:
                overflow["result"]["candidates"] = overflow["result"]["candidates"] * 2
                overflow["hits"] = overflow["hits"] * 2
                # ranks will also break — still contract fail
        with pytest.raises(AppError) as over:
            assert_persisted_retrieval_contract(overflow)
        assert over.value.code == "retrieval.contract"

        emb_missing = json.loads(json.dumps(hybrid_doc))
        emb_missing["embeddingSpace"] = None
        with pytest.raises(AppError) as missing:
            assert_persisted_retrieval_contract(emb_missing)
        assert missing.value.code == "retrieval.contract"

        emb_bad_norm = json.loads(json.dumps(hybrid_doc))
        emb_bad_norm["embeddingSpace"] = dict(emb_bad_norm["embeddingSpace"])
        emb_bad_norm["embeddingSpace"]["normalization"] = "none"
        with pytest.raises(AppError) as normed:
            assert_persisted_retrieval_contract(emb_bad_norm)
        assert normed.value.code == "retrieval.contract"

        if lexical_doc is not None:
            lexical_emb = json.loads(json.dumps(lexical_doc))
            lexical_emb["embeddingSpace"] = {
                "dimension": 384,
                "model": "Xenova/multilingual-e5-small",
                "normalization": "l2",
                "provider": "local-onnx-e5",
                "revision_scope": "forged",
            }
            with pytest.raises(AppError) as lexical:
                assert_persisted_retrieval_contract(lexical_emb)
            assert lexical.value.code == "retrieval.contract"

        margin_drift = json.loads(json.dumps(hybrid_doc))
        margin_drift["parameters"] = dict(margin_drift["parameters"])
        margin_drift["parameters"]["minSimilarity"] = 0.123456
        with pytest.raises(AppError) as margin:
            assert_persisted_retrieval_contract(margin_drift)
        assert margin.value.code == "retrieval.contract"

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_created_at_timezone_drift() -> None:
    """createdAt must be timezone-aware ISO-8601."""
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await _open(DEMO_PHASE0)
        document = await store.load_retrieval(ids[0])
        assert_persisted_retrieval_contract(document)

        missing = json.loads(json.dumps(document))
        missing["createdAt"] = None
        with pytest.raises(AppError) as absent:
            assert_persisted_retrieval_contract(missing)
        assert absent.value.code == "retrieval.contract"

        naive = json.loads(json.dumps(document))
        naive["createdAt"] = "2026-10-04T15:49:21.250437"
        with pytest.raises(AppError) as no_tz:
            assert_persisted_retrieval_contract(naive)
        assert no_tz.value.code == "retrieval.contract"

        garbage = json.loads(json.dumps(document))
        garbage["createdAt"] = "not-a-timestamp"
        with pytest.raises(AppError) as bad:
            assert_persisted_retrieval_contract(garbage)
        assert bad.value.code == "retrieval.contract"

        # Z suffix still accepted.
        zulu = json.loads(json.dumps(document))
        zulu["createdAt"] = "2026-10-04T07:49:21.250437Z"
        assert_persisted_retrieval_contract(zulu)

    asyncio.run(run())
