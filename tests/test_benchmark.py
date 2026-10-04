import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from gamingcreator.application.benchmark import (
    BenchmarkCosts,
    BenchmarkHit,
    BenchmarkMedia,
    BenchmarkQuery,
    loads_manifest,
    parse_manifest,
    run_benchmark,
)


def document() -> dict[str, Any]:
    """Synthetic contract fixture, never real human quality evidence."""
    references = [
        {
            "humanEventId": f"human-{i}",
            "independenceGroup": f"action-{i}",
            "usableRanges": [{"startUs": i * 100, "endUs": i * 100 + 50}],
            "reason": "Synthetic reference used only to verify arithmetic.",
        }
        for i in range(10)
    ]
    labels = [
        {
            "eventId": f"candidate-{i}",
            "humanEventId": f"human-{i}" if i < 7 else None,
            "startUs": i * 100,
            "endUs": i * 100 + 50,
            "grade": 2 if i < 7 else 0,
            "reason": "Synthetic judgment; not an annotator's actual rating.",
        }
        for i in range(10)
    ]
    return {
        "schemaVersion": 1,
        "datasetId": "synthetic-contract-only",
        "labelVersion": "fixture-v1",
        "humanLabels": {
            "confirmed": True,
            "annotators": ["synthetic-fixture"],
            "reviewed": False,
            "frozenAt": "2026-01-01T00:00:00Z",
            "independentTestSet": True,
        },
        "media": [{"mediaId": "media", "runId": "run", "sha256": "a" * 64, "durationUs": 1000}],
        "queries": [
            {
                "id": "q1",
                "text": "Find a mechanic.",
                "kind": "main",
                "mediaId": "media",
                "runId": "run",
                "referenceEvents": references,
                "candidateLabels": labels,
            }
        ],
    }


def hits(count: int = 10) -> tuple[BenchmarkHit, ...]:
    return tuple(BenchmarkHit(f"candidate-{i}", i * 100, i * 100 + 50, i + 1) for i in range(count))


async def verified(media: BenchmarkMedia) -> None:
    assert media.media_id == "media"


def run(
    raw: dict[str, Any],
    returned: tuple[BenchmarkHit, ...],
    *,
    verify: bool = True,
    costs: BenchmarkCosts | None = None,
) -> dict[str, Any]:
    async def search(query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]:
        assert query.query_id
        return returned

    return asyncio.run(
        run_benchmark(
            parse_manifest(raw), search, verify_media=verified if verify else None, costs=costs
        )
    )


def test_seven_of_ten_passes_with_fixed_denominator_and_missing_human_events() -> None:
    report = run(document(), hits())
    query = report["queries"][0]
    assert query["usefulRateAt10"] == 0.7
    assert query["mainMetricPassed"] is True
    assert report["qualityGate"] is True
    assert len(query["slots"]) == 10
    assert query["missingHumanEventIds"] == ["human-7", "human-8", "human-9"]
    assert report["humanLabels"]["reviewed"] is False
    assert report["cost"]["coldCny"] is None
    assert report["cost"]["coldCostGateUnder5CnyPerHour"] is None


def test_one_result_is_one_tenth_and_missing_slots_do_not_shrink_denominator() -> None:
    report = run(document(), hits(1))
    query = report["queries"][0]
    assert query["usefulRateAt10"] == 0.1
    assert query["missingSlots"] == 9
    assert query["slots"][9] == {"slot": 10, "status": "missing", "useful": False}
    assert report["qualityGate"] is False


def test_same_human_event_with_different_candidate_ids_is_zero_duplicate_slot() -> None:
    raw = document()
    alias = copy.deepcopy(raw["queries"][0]["candidateLabels"][0])
    alias["eventId"] = "alias"
    raw["queries"][0]["candidateLabels"].append(alias)
    returned = hits(6) + (BenchmarkHit("alias", 0, 50, 7),) + hits()[7:]
    report = run(raw, returned)
    query = report["queries"][0]
    assert query["duplicateSlots"] == 1
    assert query["usefulRateAt10"] == 0.6
    assert query["slots"][6]["useful"] is False
    assert report["qualityGate"] is False


def test_duplicate_unknown_event_is_not_counted_twice_as_unjudged() -> None:
    report = run(document(), (BenchmarkHit("new", 0, 50, 1), BenchmarkHit("new", 0, 50, 2)))
    query = report["queries"][0]
    assert query["unjudgedSlots"] == 1
    assert query["duplicateSlots"] == 1
    assert query["usefulRateAt10"] is None
    assert report["qualityGate"] is None


def test_final_array_order_defines_slots_and_eleventh_result_cannot_fill_duplicate() -> None:
    returned = hits(6) + (BenchmarkHit("candidate-0", 0, 50, 99),) + hits()[7:]
    returned += (BenchmarkHit("candidate-6", 600, 650, 1),)
    query = run(document(), returned)["queries"][0]
    assert query["totalReturned"] == 11
    assert query["usefulRateAt10"] == 0.6
    assert query["slots"][6]["reportedRank"] == 99
    assert all(slot.get("eventId") != "candidate-6" for slot in query["slots"])


@pytest.mark.parametrize("bad", [True, False, 1.0, "1", -1, 4, None])
def test_grades_are_uncoerced_integers_zero_to_three(bad: object) -> None:
    raw = document()
    raw["queries"][0]["candidateLabels"][0]["grade"] = bad
    with pytest.raises(ValueError):
        parse_manifest(raw)


@pytest.mark.parametrize("field,bad", [("schemaVersion", True), ("schemaVersion", 1.0)])
def test_schema_version_rejects_boolean_and_float(field: str, bad: object) -> None:
    raw = document()
    raw[field] = bad
    with pytest.raises(ValueError):
        parse_manifest(raw)


@pytest.mark.parametrize("field,bad", [("durationUs", True), ("durationUs", "1000")])
def test_source_time_values_do_not_accept_bool_or_string(field: str, bad: object) -> None:
    raw = document()
    raw["media"][0][field] = bad
    with pytest.raises(ValueError):
        parse_manifest(raw)


def test_main_needs_ten_independent_references_before_inference() -> None:
    raw = document()
    raw["queries"][0]["referenceEvents"] = raw["queries"][0]["referenceEvents"][:7]
    with pytest.raises(ValueError, match="ten independent"):
        parse_manifest(raw)


def test_reference_groups_cannot_inflate_main_event_count() -> None:
    raw = document()
    raw["queries"][0]["referenceEvents"][1]["independenceGroup"] = "action-0"
    with pytest.raises(ValueError, match="groups"):
        parse_manifest(raw)


@pytest.mark.parametrize("field", ["id", "referenceEvents", "candidateLabels"])
def test_duplicate_query_reference_or_label_identity_is_rejected(field: str) -> None:
    raw = document()
    if field == "id":
        raw["queries"].append(copy.deepcopy(raw["queries"][0]))
    else:
        raw["queries"][0][field].append(copy.deepcopy(raw["queries"][0][field][0]))
    with pytest.raises(ValueError, match="unique"):
        parse_manifest(raw)


def test_useful_labels_must_match_frozen_human_reference() -> None:
    raw = document()
    raw["queries"][0]["candidateLabels"][0]["humanEventId"] = None
    with pytest.raises(ValueError, match="reference mapping"):
        parse_manifest(raw)


def test_changed_clip_range_loses_prior_judgment_and_cannot_pass() -> None:
    returned = (BenchmarkHit("candidate-0", 1, 50, 1),) + hits()[1:]
    report = run(document(), returned)
    assert report["queries"][0]["unjudgedSlots"] == 1
    assert report["qualityGate"] is None


def test_timecode_errors_use_human_usable_ranges_and_preserve_unknowns() -> None:
    raw = document()
    raw["queries"][0]["referenceEvents"][0]["usableRanges"] = [{"startUs": 10, "endUs": 40}]
    query = run(raw, hits(1))["queries"][0]
    assert query["slots"][0]["startErrorUs"] == 10
    assert query["slots"][0]["endErrorUs"] == 10
    assert query["timecodeErrors"]["startMedianUs"] == 10
    assert query["timecodeErrors"]["endP90Us"] == 10
    assert query["timecodeErrors"]["outOfBoundsSlots"] == 0
    assert run(document(), ())["queries"][0]["timecodeErrors"]["startMedianUs"] is None


def test_out_of_source_range_is_reported_and_never_counted_useful() -> None:
    returned = (BenchmarkHit("candidate-0", 0, 1001, 1),)
    report = run(document(), returned)
    query = report["queries"][0]
    assert query["timecodeErrors"]["outOfBoundsSlots"] == 1
    assert query["slots"][0]["useful"] is False
    assert report["qualityGate"] is None


@pytest.mark.parametrize("field,value", [("confirmed", False), ("independentTestSet", False)])
def test_human_confirmation_and_independent_test_set_are_required_for_gate(
    field: str, value: bool
) -> None:
    raw = document()
    raw["humanLabels"][field] = value
    assert run(raw, hits())["qualityGate"] is None


def test_unverified_source_identity_keeps_quality_and_cost_gate_unknown() -> None:
    costs = BenchmarkCosts(Decimal("0.000001"), Decimal(0), "estimated", True, "price-v1")
    report = run(document(), hits(), verify=False, costs=costs)
    assert report["qualityGate"] is None
    assert report["mediaVerified"] is False
    assert report["cost"]["coldCostGateUnder5CnyPerHour"] is None


def test_no_labels_is_a_runnable_unverified_demo() -> None:
    raw = document()
    raw["humanLabels"]["confirmed"] = False
    raw["humanLabels"]["annotators"] = []
    raw["humanLabels"]["frozenAt"] = None
    raw["labelVersion"] = None
    raw["queries"][0]["referenceEvents"] = []
    raw["queries"][0]["candidateLabels"] = []
    report = run(raw, hits())
    assert report["qualityGate"] is None
    assert report["queries"][0]["usefulRateAt10"] is None
    assert report["queries"][0]["usefulIndependentEvents"] is None


def test_sparse_and_negative_do_not_enter_main_macro_average() -> None:
    raw = document()
    sparse = copy.deepcopy(raw["queries"][0])
    sparse.update(id="sparse", kind="sparse")
    sparse["referenceEvents"] = sparse["referenceEvents"][:1]
    sparse["candidateLabels"] = sparse["candidateLabels"][:1]
    negative = copy.deepcopy(raw["queries"][0])
    negative.update(id="negative", kind="negative", referenceEvents=[], candidateLabels=[])
    raw["queries"].extend([sparse, negative])

    async def search(query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]:
        if query.kind == "sparse":
            return hits(1)
        return () if query.kind == "negative" else hits()

    report: Any = asyncio.run(run_benchmark(parse_manifest(raw), search, verify_media=verified))
    assert report["mainMacroUsefulRateAt10"] == 0.7
    assert report["queries"][1]["recallAt10"] == 1
    assert report["queries"][1]["usefulRateAt10"] == 0.1
    assert report["queries"][2]["negativeReturnedAny"] is False
    assert report["negativeThresholdGate"] is None


def test_negative_wrong_recommendation_is_visible_and_threshold_remains_unfrozen() -> None:
    raw = document()
    raw["queries"][0].update(kind="negative", referenceEvents=[])
    raw["queries"][0]["candidateLabels"] = raw["queries"][0]["candidateLabels"][-1:]
    query = run(raw, hits()[-1:])["queries"][0]
    assert query["negativeReturnedAny"] is True
    assert query["usefulRateAt10"] == 0
    assert query["mainMetricPassed"] is None


def test_search_failure_is_not_converted_to_empty_success_and_other_queries_run() -> None:
    raw = document()
    raw["queries"].append(copy.deepcopy(raw["queries"][0]))
    raw["queries"][1]["id"] = "q2"
    visited: list[str] = []

    async def search(query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]:
        visited.append(query.query_id)
        if query.query_id == "q1":
            raise RuntimeError("This private diagnostic must not enter the report.")
        return hits()

    report: Any = asyncio.run(run_benchmark(parse_manifest(raw), search, verify_media=verified))
    assert visited == ["q1", "q2"]
    assert report["qualityGate"] is None
    assert report["queries"][0]["status"] == "failed"
    assert report["queries"][1]["mainMetricPassed"] is True
    assert "private diagnostic" not in json.dumps(report)


def test_media_verification_failure_prevents_search_and_records_stable_failure() -> None:
    called = False

    async def search(query: BenchmarkQuery) -> tuple[BenchmarkHit, ...]:
        nonlocal called
        called = True
        return hits()

    async def invalid(media: BenchmarkMedia) -> None:
        raise ValueError("Bad source.")

    report: Any = asyncio.run(
        run_benchmark(parse_manifest(document()), search, verify_media=invalid)
    )
    assert called is False
    assert report["mediaVerified"] is False
    assert report["qualityGate"] is None
    assert report["mediaFailures"][0]["code"] == "benchmark.media_identity_failed"


@pytest.mark.parametrize(
    "kwargs", [{}, {"cost_status": "unverified"}, {"attempts_complete": False}]
)
def test_unknown_or_incomplete_cost_never_becomes_zero_or_pass(kwargs: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "cold_cny": Decimal("0.000001"),
        "cost_status": "estimated",
        "attempts_complete": True,
        "price_version": "price-v1",
    }
    if not kwargs:
        values["cold_cny"] = None
    values.update(kwargs)
    cost = run(document(), hits(), costs=BenchmarkCosts(**values))["cost"]
    assert cost["coldCostGateUnder5CnyPerHour"] is None
    assert cost["hotCny"] is None


def test_cold_and_hot_costs_use_full_source_duration_and_preserve_decimal_values() -> None:
    costs = BenchmarkCosts(Decimal("0.000001"), Decimal(0), "estimated", True, "price-v1")
    cost = run(document(), hits(), costs=costs)["cost"]
    assert Decimal(cost["coldCnyPerSourceHour"]) == Decimal("3.6")
    assert cost["hotCny"] == "0"
    assert cost["coldCostGateUnder5CnyPerHour"] is True
    assert cost["hardwareCostCny"] is None


def test_same_source_sha_cannot_inflate_cost_denominator() -> None:
    raw = document()
    raw["media"].append(dict(raw["media"][0], mediaId="alias", runId="other"))
    with pytest.raises(ValueError, match="SHA256"):
        parse_manifest(raw)


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal(-1), True, 0.1])
def test_cost_validation_rejects_invalid_values(bad: object) -> None:
    with pytest.raises(ValueError):
        BenchmarkCosts(cold_cny=bad)  # type: ignore[arg-type]


def test_duplicate_json_keys_unknown_fields_and_nan_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        loads_manifest('{"schemaVersion":1,"schemaVersion":1}')
    with pytest.raises(ValueError, match="Nonfinite"):
        loads_manifest('{"schemaVersion":NaN}')
    raw = document()
    raw["extra"] = "ignored?"
    with pytest.raises(ValueError, match="unknown fields"):
        parse_manifest(raw)


def test_future_freeze_timestamp_cannot_be_used_for_human_gate() -> None:
    raw = document()
    raw["humanLabels"]["frozenAt"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="after"):
        run(raw, hits())


@pytest.mark.parametrize("start,end,rank", [(True, 50, 1), (0, 50.0, 1), (0, 50, "1"), (50, 50, 1)])
def test_hit_identity_time_and_rank_are_strict(start: object, end: object, rank: object) -> None:
    with pytest.raises(ValueError):
        BenchmarkHit("event", start, end, rank)  # type: ignore[arg-type]


def test_example_is_valid_unlabelled_manifest_and_cannot_claim_pass() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = loads_manifest((root / "templates/phase0-benchmark.example.json").read_text("utf-8"))
    assert manifest.human_labels.confirmed is False
    assert manifest.label_version is None
