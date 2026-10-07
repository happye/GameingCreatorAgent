"""Synthetic arithmetic and saved-ranking behavior; never actual human acceptance."""

import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_benchmark_review import build, review_fixture, script, seed_script_project
from test_detail_query import snapshot

from gamingcreator.application.benchmark import BenchmarkCosts
from gamingcreator.application.benchmark_analysis_costs import benchmark_analysis_costs
from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.application.benchmark_review_scoring import score_saved_review
from gamingcreator.application.providers import CostStatus
from gamingcreator.cli import main as cli
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def scoring_fixture(tmp_path, count=10, *, failed=False, kind="main"):
    fixture = review_fixture(tmp_path, count, failed=failed)
    raw, report, _, retrievals, _ = fixture
    raw["queries"][0]["kind"] = kind
    report["queries"][0]["kind"] = kind
    if kind == "negative":
        raw["queries"][0]["referenceEvents"] = []
    elif kind == "sparse":
        raw["queries"][0]["referenceEvents"] = raw["queries"][0]["referenceEvents"][:3]
    if not failed:
        retrieval = retrievals["retrieval-1"]
        for i, (hit, candidate) in enumerate(
            zip(retrieval["hits"], retrieval["result"]["candidates"], strict=True)
        ):
            hit["event_id"] = candidate["eventId"] = f"event-{i}"
            if i < 10:
                report["queries"][0]["slots"][i]["eventId"] = f"event-{i}"
    report["elapsedMs"] = 1234.5
    report["retrievalWallclockToSourceRatio"] = 1234.5 * 1000 / report["sourceDurationUs"]
    report["queries"][0]["elapsedMs"] = 12.75
    return fixture


def score(fixture, *, useful=7, duplicate_human=False, leave_last=False, costs=None):
    context, template = build(fixture)
    record = deepcopy(template)
    record.update({"recordedOn": "2026-10-07", "reviewer": "synthetic-score-only"})
    for index, slot in enumerate(record["queries"][0]["slots"]):
        if slot["state"] != "candidate":
            continue
        if leave_last and index == 9:
            continue
        slot.update(
            {
                "grade": 2 if index < useful else 0,
                "humanEventId": f"human-{index}" if index < useful else None,
                "reason": "Synthetic calculation only, not human evidence.",
            }
        )
    if duplicate_human:
        record["queries"][0]["slots"][1]["humanEventId"] = "human-0"
    return asyncio.run(
        score_saved_review(
            context, record, canonical_json(fixture[1]), costs=costs or BenchmarkCosts()
        )
    )


@pytest.mark.parametrize("count,useful,expected", [(10, 7, 0.7), (7, 7, 0.7), (6, 6, 0.6)])
def test_original_fixed_denominator_missing_slots_and_exact_ranks(
    tmp_path, count, useful, expected
):
    fixture = scoring_fixture(tmp_path, count)
    report = score(fixture, useful=useful)
    row = report["queries"][0]
    assert row["usefulRateAt10"] == expected and len(row["slots"]) == 10
    assert row["missingSlots"] == 10 - count
    assert report["qualityGate"] is (expected >= 0.7)
    assert [slot["eventId"] for slot in row["slots"][:count]] == [
        f"event-{i}" for i in range(count)
    ]
    assert row["retrievalId"] == "retrieval-1" and report["scoring"]["ordinarySearches"] == 0


def test_same_human_event_counts_once_and_no_unjudged_or_independence_upgrade(tmp_path):
    fixture = scoring_fixture(tmp_path)
    report = score(fixture, duplicate_human=True)
    assert report["queries"][0]["usefulRateAt10"] == 0.6
    assert report["queries"][0]["duplicateSlots"] == 1 and report["qualityGate"] is False
    assert score(fixture, leave_last=True)["qualityGate"] is None
    fixture[0]["humanLabels"]["independentTestSet"] = False
    fixture[1]["humanLabels"]["independentTestSet"] = False
    report = score(fixture)
    assert report["queries"][0]["usefulRateAt10"] == 0.7 and report["qualityGate"] is None
    fixture[0]["humanLabels"]["confirmed"] = False
    fixture[1]["humanLabels"]["confirmed"] = False
    report = score(fixture)
    assert report["queries"][0]["usefulRateAt10"] is None and report["qualityGate"] is None


def test_original_model_duplicate_and_eleventh_hit_never_refill(tmp_path):
    fixture = review_fixture(tmp_path, 11)
    context, record = build(fixture)
    record = deepcopy(record)
    record.update({"recordedOn": "2026-10-07", "reviewer": "synthetic-only"})
    for slot in record["queries"][0]["slots"]:
        if slot["state"] == "candidate":
            slot.update({"grade": 0, "reason": "Synthetic irrelevant fixture."})
    report = asyncio.run(
        score_saved_review(context, record, canonical_json(fixture[1]), costs=BenchmarkCosts())
    )
    row = report["queries"][0]
    assert row["totalReturned"] == 11 and row["returnedTop10"] == 10
    assert row["duplicateSlots"] == 1 and row["slots"][1]["status"] == "duplicate"
    assert row["slots"][-1]["eventId"] == "event-9"


@pytest.mark.parametrize("kind", ["sparse", "negative"])
def test_sparse_and_negative_queries_remain_separate_from_main_gate(tmp_path, kind):
    fixture = scoring_fixture(tmp_path, 3 if kind == "sparse" else 0, kind=kind)
    report = score(fixture, useful=3 if kind == "sparse" else 0)
    assert report["mainMacroUsefulRateAt10"] is None and report["qualityGate"] is None
    assert report["queries"][0]["kind"] == kind
    if kind == "negative":
        assert report["queries"][0]["negativeReturnedAny"] is False
        assert report["negativeThresholdGate"] is None


def test_saved_failed_query_remains_failed_and_cannot_pass(tmp_path):
    report = score(scoring_fixture(tmp_path, 0, failed=True))
    assert report["queries"][0]["status"] == "failed"
    assert report["queries"][0]["retrievalId"] is None
    assert report["qualityGate"] is None


def test_original_search_time_and_authoritative_unknown_cost_are_preserved(tmp_path):
    fixture = scoring_fixture(tmp_path)
    fixture[1]["cost"].update({"coldCny": "0", "coldCostGateUnder5CnyPerHour": True})
    report = score(fixture, costs=BenchmarkCosts())
    assert report["elapsedMs"] == 1234.5 and report["queries"][0]["elapsedMs"] == 12.75
    assert report["startedAt"] == fixture[1]["startedAt"]
    assert (
        report["retrievalWallclockToSourceRatio"] == fixture[1]["retrievalWallclockToSourceRatio"]
    )
    assert report["scoringElapsedMs"] >= 0 and report["queries"][0]["scoringElapsedMs"] >= 0
    assert report["scoredAt"] >= report["startedAt"]
    assert report["cost"]["coldCny"] is None
    assert report["cost"]["coldCostGateUnder5CnyPerHour"] is None
    assert (
        report["scoring"]["originalReportSha256"]
        == hashlib.sha256(canonical_json(fixture[1])).hexdigest()
    )


@pytest.mark.parametrize(
    "change",
    [
        "negative_time",
        "bool_time",
        "string_time",
        "ratio",
        "duration",
        "future",
        "naive",
        "before_freeze",
    ],
)
def test_invalid_original_timing_cannot_be_reported_as_current_search_performance(tmp_path, change):
    fixture = scoring_fixture(tmp_path)
    report = fixture[1]
    if change in ("negative_time", "bool_time", "string_time"):
        report["elapsedMs"] = {"negative_time": -1, "bool_time": True, "string_time": "1"}[change]
    elif change == "ratio":
        report["retrievalWallclockToSourceRatio"] += 1
    elif change == "duration":
        report["sourceDurationUs"] += 1
    else:
        report["startedAt"] = {
            "future": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "naive": "2026-10-07T01:00:00",
            "before_freeze": "2025-01-01T00:00:00Z",
        }[change]
    with pytest.raises(ValueError):
        score(fixture)


def test_record_or_report_changes_are_refused_before_scoring(tmp_path):
    fixture = scoring_fixture(tmp_path)
    context, record = build(fixture)
    record = deepcopy(record)
    with pytest.raises(ValueError):
        asyncio.run(
            score_saved_review(
                context, record, canonical_json(fixture[1]) + b" ", costs=BenchmarkCosts()
            )
        )
    record["queries"][0]["slots"][0]["endUs"] += 1
    with pytest.raises(ValueError):
        asyncio.run(
            score_saved_review(context, record, canonical_json(fixture[1]), costs=BenchmarkCosts())
        )


@pytest.mark.parametrize("unknown", [False, True])
def test_base_cost_summary_keeps_unknown_and_partial_runs_unknown(unknown):
    usage = SimpleNamespace(
        cost_cny=None if unknown else Decimal("0.02"),
        cost_status=CostStatus.UNVERIFIED if unknown else CostStatus.ESTIMATED,
    )
    metadata = SimpleNamespace(usage=usage, provider="deepseek", price_version="frozen-price")
    timeline = SimpleNamespace(invocations=(SimpleNamespace(metadata=metadata),))
    costs = benchmark_analysis_costs([timeline])
    assert costs.cold_cny == (None if unknown else Decimal("0.02"))
    assert costs.attempts_complete is not unknown and costs.hot_cny == 0
    assert benchmark_analysis_costs([timeline], all_runs_loaded=False).cold_cny is None
    metadata.price_version = None
    assert benchmark_analysis_costs([timeline]).cold_cny is None


def test_mixed_price_versions_do_not_acquire_a_verified_price_identity():
    def timeline(version):
        usage = SimpleNamespace(cost_cny=Decimal("0.02"), cost_status=CostStatus.ESTIMATED)
        metadata = SimpleNamespace(usage=usage, provider="deepseek", price_version=version)
        return SimpleNamespace(invocations=(SimpleNamespace(metadata=metadata),))

    costs = benchmark_analysis_costs([timeline("old"), timeline("new")])
    assert costs.cold_cny == Decimal("0.04") and costs.price_version is None
    assert costs.attempts_complete is True


def test_audio_only_candidate_uses_original_saved_candidate_identity(tmp_path):
    fixture = scoring_fixture(tmp_path, 1)
    retrieval = fixture[3]["retrieval-1"]
    retrieval["hits"][0]["event_id"] = None
    retrieval["result"]["candidates"][0]["eventId"] = None
    fixture[1]["queries"][0]["slots"][0]["eventId"] = "candidate-0"
    report = score(fixture, useful=1)
    assert report["queries"][0]["slots"][0]["eventId"] == "candidate-0"
    assert report["queries"][0]["usefulRateAt10"] == 0.1


def test_sqlite_score_import_is_read_only_and_exit_six_preserves_report(
    tmp_path, monkeypatch, capsys
):
    project, binding, original = seed_script_project(tmp_path)
    context, record, _, _, _ = asyncio.run(script.prepare(project, original, binding))
    record_path = tmp_path / "blank-human-record.json"
    record_path.write_bytes(canonical_json(record))
    before = snapshot(project)

    def forbidden(*args, **kwargs):
        pytest.fail("fixed scoring attempted new search, model or budget")

    for name in (
        "execute_search",
        "search_timeline",
        "LocalAsrProvider",
        "LocalEmbeddingProvider",
        "vision_for_run",
        "BudgetLedger",
        "HttpxVisionTransport",
    ):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(SqliteTimelineStore, "persist_search", forbidden)
    output = tmp_path / "fixed-score"
    args = [
        "--project",
        str(project),
        "--binding",
        str(binding),
        "--report",
        str(original),
        "--record",
        str(record_path),
        "--score",
        "--output",
        str(output),
    ]
    assert script.main(args) == 6
    result = json.loads(capsys.readouterr().out)
    assert result["schemaVersion"] == "benchmark-fixed-score-result-v1"
    assert result["qualityGate"] is None and result["paidRequestsSent"] == 0
    report = json.loads((output / "benchmark-fixed-report.json").read_bytes())
    assert report["qualityGate"] is None
    assert report["queries"][0]["retrievalId"] == context["queries"][0]["retrievalId"]
    assert snapshot(project) == before
    assert script.main(args) == 2 and snapshot(project) == before
    capsys.readouterr()
    record["queries"][0]["slots"][0]["startUs"] += 1
    record_path.write_bytes(canonical_json(record))
    args[-1] = str(tmp_path / "bad-record")
    assert script.main(args) == 2 and not (tmp_path / "bad-record").exists()
    assert snapshot(project) == before


def test_score_without_record_is_refused_before_any_source_read(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("missing record opened source storage")

    monkeypatch.setattr(SqliteTimelineStore, "open", forbidden)
    with pytest.raises(SystemExit) as error:
        script.main(
            [
                "--project",
                str(tmp_path),
                "--binding",
                str(tmp_path),
                "--report",
                str(tmp_path / "report.json"),
                "--score",
                "--output",
                str(tmp_path / "output"),
            ]
        )
    assert error.value.code == 2 and not (tmp_path / "output").exists()
