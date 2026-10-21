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
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
        for retrieval_id in ids:
            document = await store.load_retrieval(retrieval_id)
            assert_persisted_retrieval_contract(document)
            assert document["retrievalId"] == retrieval_id
            result = document["result"]
            assert isinstance(result, dict)
            assert_run_search_document_contract(
                result, expected_run_id=str(document["runId"])
            )

    asyncio.run(run())


def test_assert_persisted_retrieval_contract_rejects_hit_drift_and_acceptance() -> None:
    db = _require_sqlite()
    ids = _retrieval_ids(db)
    if not ids:
        pytest.skip("local retrieval_runs empty")

    async def run() -> None:
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
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
        store = await SqliteTimelineStore.open(DEMO_PHASE0, read_only=True)
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

