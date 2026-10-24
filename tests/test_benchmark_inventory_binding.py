"""Freeze v2 binds a source-inventory report; v1 freezes must stay byte-identical and readable."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from test_benchmark_preparation import plan_fixture, timelines
from test_sqlite_store import bundle_fixture

from gamingcreator.application.benchmark_inventory_binding import (
    MAX_INVENTORY_BYTES,
    derive_source_inventory,
    inventory_blockers,
    parse_inventory,
)
from gamingcreator.application.benchmark_preparation import (
    bind_manifest,
    canonical_json,
    freeze_document,
    freeze_document_v2,
    loads_plan,
)
from gamingcreator.application.source_inventory import LIMITATIONS
from gamingcreator.cli import main as cli
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.infrastructure.benchmark_preparation_files import read_freeze, write_freeze

# Pinned with the pre-v2 code: a fixed v1 fixture must keep producing exactly these bytes.
V1_FREEZE_SHA256 = "444c176f557c8e1c68950b0bbb64e41ded7fcd4b04ce129914ae3ec751e41109"
FIXED_TIME = "2026-10-07T10:00:00+08:00"


def v1_fixture() -> tuple[dict[str, object], dict[str, MediaAsset]]:
    sources, queries, assets = [], [], {}
    streams = (MediaStream(0, "video", Fraction(1, 1000), 1000, 2000),)
    for index in range(10):
        identifier = f"source-{index}"
        digest = hashlib.sha256(f"pinned synthetic source {index}".encode()).hexdigest()
        assets[identifier] = MediaAsset(
            identifier,
            Path(f"pinned-fixture/素材-{index}.mp4"),
            digest,
            streams,
            Fraction(1),
            2_000_000,
            "fixture",
        )
        sources.append(
            {
                "id": identifier,
                "path": f"素材-{index}.mp4",
                "recordingGroup": f"recording-{index}",
                "partition": "test" if index else "development",
                "modelResultsViewed": False,
            }
        )
        queries.append(
            {
                "id": f"query-{index}",
                "text": "寻找闪避片段",
                "kind": "main",
                "sourceId": identifier,
                "family": f"family-{index}",
                "referenceEvents": [
                    {
                        "humanEventId": f"human-{index}-{i}",
                        "independenceGroup": f"action-{index}-{i}",
                        "usableRanges": [{"startUs": i * 1000, "endUs": i * 1000 + 500}],
                        "reason": "Synthetic reference, no human acceptance.",
                    }
                    for i in range(10)
                ],
            }
        )
    raw = {
        "schemaVersion": "benchmark-plan-v1",
        "datasetId": "pinned-v1-compat",
        "labelVersion": "synthetic-v1",
        "humanReferences": {"confirmed": True, "annotators": ["fixture"], "reviewed": False},
        "sources": sources,
        "queries": queries,
    }
    return raw, assets


def test_v1_freeze_bytes_are_pinned() -> None:
    raw, assets = v1_fixture()
    frozen = freeze_document(loads_plan(json.dumps(raw)), assets, FIXED_TIME)
    assert frozen["schemaVersion"] == "benchmark-freeze-v1"
    assert hashlib.sha256(canonical_json(frozen)).hexdigest() == V1_FREEZE_SHA256


# ---- v2 behaviour -------------------------------------------------------------------------


def candidate(first, second, paths, **changes):
    row = {
        "sourceA": first,
        "sourceB": second,
        "pathA": paths[0],
        "pathB": paths[1],
        "offsetSamples": 40,
        "offsetSeconds": 20.0,
        "comparedVotes": 100,
        "matchedVotes": 60,
        "matchRate": 0.6,
        "matchedFramesA": 30,
        "clusterCount": 1,
        "backgroundMatchRate": 0.05,
        "correctedPValue": 1e-9,
        "log10CorrectedPValue": -9.0,
        "aFirstSeconds": 1.0,
        "aLastSeconds": 40.0,
        "bFirstSeconds": 21.0,
        "bLastSeconds": 60.0,
    }
    return {**row, **changes}


VIDEO = {"codec": "h264", "width": 1920, "height": 1080, "frameRate": "30/1"}


def report_for(assets, *, skip=(), fail=(), drop=(), pairs=(), extra=()):
    """Synthetic source-inventory-v1 report; ``pairs`` are 1-based indexes of covered sources."""
    entries, skipped, failed = [], [], []
    for index, (key, asset) in enumerate(assets.items(), 1):
        identifier = f"source-{index:03d}"
        if key in drop:
            continue
        if key in fail:
            failed.append(
                {
                    "sourceId": identifier,
                    "path": str(asset.source_path).swapcase(),
                    "code": "input.video",
                    "message": "无法读取源文件。",
                }
            )
            continue
        entries.append(
            {
                "sourceId": identifier,
                "path": str(asset.source_path),
                "byteSize": 10,
                "sha256": asset.sha256,
                "durationUs": asset.duration_us,
                "video": VIDEO,
                "sampledFrames": 100,
                "informativeFrames": 5 if key in skip else 90,
            }
        )
        if key in skip:
            skipped.append(
                {
                    "sourceId": identifier,
                    "path": str(asset.source_path),
                    "informativeFrames": 5,
                    "sampledFrames": 100,
                    "reason": "有效画面不足 20 个采样，未参与比较。",
                }
            )
    for position, sha in enumerate(extra, len(assets) + 1):
        entries.append(
            {
                "sourceId": f"source-{position:03d}",
                "path": f"C:\\elsewhere\\{position}.mp4",
                "byteSize": 10,
                "sha256": sha,
                "durationUs": 5_000_000,
                "video": VIDEO,
                "sampledFrames": 100,
                "informativeFrames": 90,
            }
        )
    by_id = {row["sourceId"]: row for row in entries}
    candidates = [
        candidate(
            f"source-{a:03d}",
            f"source-{b:03d}",
            (by_id[f"source-{a:03d}"]["path"], by_id[f"source-{b:03d}"]["path"]),
        )
        for a, b in pairs
    ]
    return {
        "schemaVersion": "source-inventory-v1",
        "humanDecisionRequired": True,
        "parameters": {"samplesPerSecond": 2, "hash": "dhash-64"},
        "ffmpegVersion": "synthetic ffmpeg",
        "sources": entries,
        "duplicateGroups": [],
        "notComparable": skipped,
        "failedSources": failed,
        "sharedFootageCandidates": candidates,
        "limitations": list(LIMITATIONS),
    }


def encode(report) -> bytes:
    return (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()


def frozen_v2(raw, assets, report=None):
    data = None if report is None else encode(report)
    return freeze_document_v2(loads_plan(json.dumps(raw)), assets, FIXED_TIME, data), data


def ready_fixture(tmp_path, count=11):
    return plan_fixture(tmp_path, count, confirmed=True)


def test_v2_without_report_is_blocked_and_never_independent(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    frozen, _ = frozen_v2(raw, assets)
    assert frozen["schemaVersion"] == "benchmark-freeze-v2" and frozen["sourceInventory"] is None
    assert frozen["preparation"]["blockers"] == ["source_inventory_missing"]
    assert frozen["preparation"]["readyForIndependentEvaluation"] is False
    manifest = bind_manifest(frozen, timelines(assets), "test")
    assert manifest["humanLabels"]["independentTestSet"] is False


def test_full_coverage_without_evidence_has_no_inventory_blocker(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    frozen, _ = frozen_v2(raw, assets, report_for(assets))
    assert frozen["preparation"]["blockers"] == []
    assert frozen["preparation"]["readyForIndependentEvaluation"] is True
    derived = frozen["sourceInventory"]
    assert derived["sharedFootage"] == [] and derived["absenceIsNotIndependence"] is True
    assert derived["humanDecisionRequired"] is True
    assert [row["status"] for row in derived["sources"]] == ["compared"] * 10
    assert derived["limitations"] == list(LIMITATIONS)
    manifest = bind_manifest(frozen, timelines(assets), "test")
    assert manifest["humanLabels"]["independentTestSet"] is True


def test_shared_footage_in_same_group_and_partition_is_not_blocked(tmp_path):
    raw, assets = ready_fixture(tmp_path)
    raw["sources"][1]["recordingGroup"] = raw["sources"][0]["recordingGroup"]
    frozen, _ = frozen_v2(raw, assets, report_for(assets, pairs=[(1, 2)]))
    assert frozen["preparation"]["blockers"] == []
    pair = frozen["sourceInventory"]["sharedFootage"][0]
    assert (pair["sourceA"], pair["sourceB"]) == ("source-0", "source-1")
    assert (pair["offsetSeconds"], pair["matchedVotes"], pair["comparedVotes"]) == (20.0, 60, 100)
    assert pair["log10CorrectedPValue"] == -9.0


def test_shared_footage_with_different_groups_or_partitions_blocks(tmp_path):
    raw, assets = ready_fixture(tmp_path)
    frozen, _ = frozen_v2(raw, assets, report_for(assets, pairs=[(1, 2)]))
    assert frozen["preparation"]["blockers"] == ["shared_footage_has_different_recording_groups"]
    raw["sources"][1]["partition"] = "development"
    frozen, _ = frozen_v2(raw, assets, report_for(assets, pairs=[(1, 2)]))
    assert {
        "shared_footage_has_different_recording_groups",
        "shared_footage_crosses_partitions",
    } <= set(frozen["preparation"]["blockers"])
    test_assets = {key: value for key, value in assets.items() if key != "source-1"}
    manifest = bind_manifest(frozen, timelines(test_assets), "test")
    assert manifest["humanLabels"]["independentTestSet"] is False


def test_same_group_crossing_partitions_reports_the_shared_footage_blocker(tmp_path):
    raw, assets = ready_fixture(tmp_path)
    raw["sources"][1]["recordingGroup"] = raw["sources"][0]["recordingGroup"]
    raw["sources"][1]["partition"] = "development"
    frozen, _ = frozen_v2(raw, assets, report_for(assets, pairs=[(1, 2)]))
    blockers = frozen["preparation"]["blockers"]
    assert "shared_footage_crosses_partitions" in blockers
    assert "shared_footage_has_different_recording_groups" not in blockers


@pytest.mark.parametrize(
    "change,status,blocker",
    [
        ("skip", "notComparable", "source_inventory_not_comparable"),
        ("fail", "failed", "source_inventory_incomplete"),
        ("drop", "absent", "source_inventory_incomplete"),
    ],
)
def test_uncovered_sources_block_with_explicit_status(tmp_path, change, status, blocker):
    raw, assets = ready_fixture(tmp_path, 10)
    frozen, _ = frozen_v2(raw, assets, report_for(assets, **{change: ("source-3",)}))
    assert frozen["preparation"]["blockers"] == [blocker]
    row = frozen["sourceInventory"]["sources"][3]
    assert row["id"] == "source-3" and row["status"] == status
    assert (row["inventorySourceIds"] == ["source-004"]) is (change != "drop")


def test_pair_to_unplanned_source_is_counted_not_mapped(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    report = report_for(assets, extra=["e" * 64], pairs=[(1, 11)])
    frozen, _ = frozen_v2(raw, assets, report)
    derived = frozen["sourceInventory"]
    assert derived["sharedFootage"] == [] and derived["unplannedSourceEvidenceCount"] == 1
    assert frozen["preparation"]["blockers"] == []


def test_same_sha_with_different_duration_is_a_hard_input_error(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    report = report_for(assets)
    report["sources"][0]["durationUs"] += 1
    with pytest.raises(ValueError, match="时长"):
        frozen_v2(raw, assets, report)


def test_duplicate_frozen_content_maps_to_every_frozen_id(tmp_path):
    _, assets = ready_fixture(tmp_path, 11)
    assets["source-10"] = replace(assets["source-10"], sha256=assets["source-0"].sha256)
    derived = derive_source_inventory(
        encode(report_for(assets, pairs=[(1, 2)])),
        [
            {
                "id": key,
                "path": str(value.source_path),
                "sha256": value.sha256,
                "durationUs": value.duration_us,
            }
            for key, value in assets.items()
        ],
    )
    assert {(p["sourceA"], p["sourceB"]) for p in derived["sharedFootage"]} == {
        ("source-0", "source-1"),
        ("source-10", "source-1"),
    }


def test_blockers_reject_inconsistent_source_set(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    frozen, _ = frozen_v2(raw, assets, report_for(assets))
    with pytest.raises(ValueError):
        inventory_blockers(frozen["sourceInventory"], {"source-0": ("g", "test")})


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "version",
        "human",
        "limitations",
        "sha",
        "duplicate_id",
        "unknown_candidate",
        "same_sha_candidate",
        "votes",
        "path",
        "failed_reuse",
        "frames",
        "ffmpeg",
    ],
)
def test_report_is_parsed_strictly(tmp_path, mutation):
    _, assets = ready_fixture(tmp_path, 10)
    report = report_for(assets, pairs=[(1, 2)])
    if mutation == "extra":
        report["recordingGroup"] = "suggested"
    if mutation == "version":
        report["schemaVersion"] = "source-inventory-v2"
    if mutation == "human":
        report["humanDecisionRequired"] = False
    if mutation == "limitations":
        report["limitations"] = report["limitations"][:-1]
    if mutation == "sha":
        report["sources"][0]["sha256"] = "A" * 64
    if mutation == "duplicate_id":
        report["sources"][1]["sourceId"] = report["sources"][0]["sourceId"]
    if mutation == "unknown_candidate":
        report["sharedFootageCandidates"][0]["sourceB"] = "source-999"
    if mutation == "same_sha_candidate":
        report["sources"][1]["sha256"] = report["sources"][0]["sha256"]
    if mutation == "votes":
        report["sharedFootageCandidates"][0]["matchedVotes"] = 101
    if mutation == "path":
        report["sharedFootageCandidates"][0]["pathA"] = "other.mp4"
    if mutation == "failed_reuse":
        report["failedSources"].append(
            {"sourceId": "source-001", "path": "x", "code": "c", "message": "m"}
        )
    if mutation == "frames":
        report["sources"][0]["informativeFrames"] = 101
    if mutation == "ffmpeg":
        report["ffmpegVersion"] = ""
    with pytest.raises(ValueError, match="素材盘点报告无效"):
        parse_inventory(encode(report))


@pytest.mark.parametrize(
    "text",
    ['{"schemaVersion":"a","schemaVersion":"b"}', '{"schemaVersion":NaN}', "[]", "not json"],
)
def test_duplicate_nonfinite_and_non_object_reports_are_refused(text):
    with pytest.raises(ValueError, match="素材盘点报告无效"):
        parse_inventory(text.encode())


def test_oversized_report_is_refused_not_truncated():
    with pytest.raises(ValueError, match="4MiB"):
        parse_inventory(b" " * (MAX_INVENTORY_BYTES + 1))


def write_v2(tmp_path, raw, assets, report):
    plan_path = tmp_path / "plan.json"
    data = canonical_json(raw)
    plan_path.write_bytes(data)
    frozen, inventory_bytes = frozen_v2(raw, assets, report)
    inventory = None
    if inventory_bytes is not None:
        inventory_path = tmp_path / "inventory.json"
        inventory_path.write_bytes(inventory_bytes)
        inventory = (inventory_path, inventory_bytes)
    output = tmp_path / "frozen"
    hashes = write_freeze(plan_path, data, frozen, output, inventory)
    return frozen, output, hashes


def retarget(directory, name, content):
    """Rewrite one bundle file and its receipt hash so only the semantic check can reject it."""
    (directory / name).write_bytes(content)
    receipt = json.loads((directory / "receipt.json").read_bytes())
    receipt["files"][name] = hashlib.sha256(content).hexdigest()
    (directory / "receipt.json").write_bytes(canonical_json(receipt))


def test_v2_bundle_keeps_report_bytes_and_reads_back(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    report = report_for(assets)
    frozen, output, hashes = write_v2(tmp_path, raw, assets, report)
    assert set(hashes) == {"plan-input.json", "freeze.json", "source-inventory.json"}
    assert (output / "source-inventory.json").read_bytes() == encode(report)
    assert read_freeze(output)[0] == frozen


def test_v2_bundle_without_report_has_two_files_and_reads_back(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    frozen, output, hashes = write_v2(tmp_path, raw, assets, None)
    assert set(hashes) == {"plan-input.json", "freeze.json"}
    assert read_freeze(output)[0] == frozen


@pytest.mark.parametrize(
    "tamper", ["report", "derived", "missing_key", "preparation", "null", "forged_without_file"]
)
def test_v2_read_freeze_rejects_tampering(tmp_path, tamper):
    raw, assets = ready_fixture(tmp_path, 10)
    report = report_for(assets, pairs=[(1, 2)])
    if tamper == "forged_without_file":
        # No report was saved, yet freeze.json claims full coverage and a ready preparation.
        frozen, output, _ = write_v2(tmp_path, raw, assets, None)
        forged, _ = frozen_v2(raw, assets, report_for(assets))
        assert forged["preparation"]["readyForIndependentEvaluation"] is True
        retarget(output, "freeze.json", canonical_json(forged))
        with pytest.raises(ValueError):
            read_freeze(output)
        return
    frozen, output, _ = write_v2(tmp_path, raw, assets, report)
    if tamper == "report":
        report["ffmpegVersion"] = "other"
        retarget(output, "source-inventory.json", encode(report))
    if tamper == "derived":
        frozen["sourceInventory"]["sharedFootage"] = []
    if tamper == "missing_key":
        del frozen["sourceInventory"]
    if tamper == "preparation":
        frozen["preparation"]["blockers"] = []
        frozen["preparation"]["readyForIndependentEvaluation"] = True
    if tamper == "null":
        frozen["sourceInventory"] = None
    if tamper != "report":
        retarget(output, "freeze.json", canonical_json(frozen))
    with pytest.raises(ValueError):
        read_freeze(output)


def test_v1_receipt_with_inventory_file_is_rejected_and_v1_stays_readable(tmp_path):
    raw, assets = plan_fixture(tmp_path)
    plan_path = tmp_path / "plan.json"
    data = canonical_json(raw)
    plan_path.write_bytes(data)
    frozen = freeze_document(loads_plan(json.dumps(raw)), assets, FIXED_TIME)
    output = tmp_path / "frozen"
    write_freeze(plan_path, data, frozen, output)
    assert read_freeze(output)[0] == frozen and "sourceInventory" not in frozen
    retarget(output, "source-inventory.json", encode(report_for(assets)))
    with pytest.raises(ValueError):
        read_freeze(output)


def test_v1_rebinding_matches_original_binding(tmp_path):
    raw, assets = plan_fixture(tmp_path, 10, confirmed=True)
    plan_path = tmp_path / "plan.json"
    data = canonical_json(raw)
    plan_path.write_bytes(data)
    frozen = freeze_document(loads_plan(json.dumps(raw)), assets, FIXED_TIME)
    output = tmp_path / "frozen"
    write_freeze(plan_path, data, frozen, output)
    reread, _ = read_freeze(output)
    assert reread["preparation"]["readyForIndependentEvaluation"] is True
    assert bind_manifest(reread, timelines(assets), "test") == bind_manifest(
        frozen, timelines(assets), "test"
    )


def test_write_freeze_refuses_mismatched_or_changed_inventory(tmp_path):
    raw, assets = ready_fixture(tmp_path, 10)
    plan_path = tmp_path / "plan.json"
    data = canonical_json(raw)
    plan_path.write_bytes(data)
    frozen, inventory_bytes = frozen_v2(raw, assets, report_for(assets))
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(inventory_bytes + b" ")
    output = tmp_path / "frozen"
    with pytest.raises(ValueError, match="素材盘点"):
        write_freeze(plan_path, data, frozen, output, (inventory_path, inventory_bytes))
    assert not output.exists()
    inventory_path.write_bytes(inventory_bytes)
    for bad in (None, (inventory_path, inventory_bytes + b" ")):
        with pytest.raises(ValueError):
            write_freeze(plan_path, data, frozen, output, bad)
    assert not output.exists()
    v1 = freeze_document(loads_plan(json.dumps(raw)), assets, FIXED_TIME)
    with pytest.raises(ValueError):
        write_freeze(plan_path, data, v1, output, (inventory_path, inventory_bytes))
    assert not output.exists()
    forged = {**frozen, "sourceInventory": {**frozen["sourceInventory"], "reportSha256": "0" * 64}}
    with pytest.raises(ValueError, match="素材盘点"):
        write_freeze(plan_path, data, forged, output, (inventory_path, inventory_bytes))
    assert not output.exists()


def cli_fixture(tmp_path, monkeypatch):
    bundle = bundle_fixture(tmp_path)
    raw, assets = plan_fixture(tmp_path, bundle=bundle)
    raw["sources"][0]["path"] = str(bundle.asset.source_path)
    assets["source-0"] = bundle.asset
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(canonical_json(raw))

    class ProbeOnly:
        def __init__(self, repository):
            pass

        async def probe(self, path, context):
            return bundle.asset

    monkeypatch.setattr(cli, "FfmpegMediaProcessor", ProbeOnly)
    return plan_path, assets


def test_cli_freeze_writes_v2_with_and_without_inventory(tmp_path, monkeypatch, capsys):
    plan_path, assets = cli_fixture(tmp_path, monkeypatch)
    plain = tmp_path / "plain"
    assert cli.main(["freeze-benchmark", "--input", str(plan_path), "--output", str(plain)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sourceInventory"]["provided"] is False
    assert "source_inventory_missing" in result["preparation"]["blockers"]
    assert read_freeze(plain)[0]["schemaVersion"] == "benchmark-freeze-v2"
    assert not (plain / "source-inventory.json").exists()
    report = encode(report_for(assets))
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(report)
    covered = tmp_path / "covered"
    args = ["freeze-benchmark", "--input", str(plan_path), "--output", str(covered)]
    assert cli.main([*args, "--inventory", str(inventory)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["sourceInventory"]["sourceStatusCounts"]["compared"] == 1
    assert "无证据" in result["sourceInventory"]["note"]
    assert "source_inventory_missing" not in result["preparation"]["blockers"]
    assert result["paidRequestsSent"] == 0 and result["qualityGate"] is None
    assert (covered / "source-inventory.json").read_bytes() == report


def test_cli_freeze_refuses_bad_inventory_without_output(tmp_path, monkeypatch, capsys):
    plan_path, _ = cli_fixture(tmp_path, monkeypatch)
    inventory = tmp_path / "inventory.json"
    inventory.write_bytes(b"{}")
    output = tmp_path / "frozen"
    base = ["freeze-benchmark", "--input", str(plan_path), "--output", str(output)]
    assert cli.main([*base, "--inventory", str(inventory)]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().err)["code"] == "input.benchmark_preparation"
    assert cli.main([*base, "--inventory", str(tmp_path / "absent.json")]) == 2
    assert not output.exists()


def test_v1_freeze_never_binds_an_independent_test_set(tmp_path):
    raw, assets = plan_fixture(tmp_path, 10, confirmed=True)
    frozen = freeze_document(loads_plan(json.dumps(raw)), assets, FIXED_TIME)
    assert frozen["preparation"]["readyForIndependentEvaluation"] is True
    manifest = bind_manifest(frozen, timelines(assets), "test")
    assert manifest["humanLabels"]["confirmed"] is True
    assert manifest["humanLabels"]["independentTestSet"] is False
