"""Synthetic freeze/binding contracts, never independent human acceptance evidence."""

import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_detail_query import snapshot
from test_material_tasks import CONFIG
from test_sqlite_store import HASH, bundle_fixture, event_fixture, media_ready

from gamingcreator.application.benchmark import BenchmarkHit, loads_manifest, run_benchmark
from gamingcreator.application.benchmark_preparation import (
    bind_manifest,
    canonical_json,
    freeze_document,
    loads_plan,
)
from gamingcreator.application.storage import RunStatus, StoredRun, StoredTimeline
from gamingcreator.cli import main as cli
from gamingcreator.infrastructure.benchmark_preparation_files import (
    read_freeze,
    validate_bound_manifest,
    write_binding,
    write_freeze,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def plan_fixture(tmp_path, count=1, *, confirmed=False, bundle=None):
    bundle = bundle if bundle is not None else bundle_fixture(tmp_path)
    sources, queries, assets = [], [], {}
    for index in range(count):
        identifier = f"source-{index}"
        path = tmp_path / f"素材-{index}.fixture"
        path.write_bytes(f"synthetic source {index}".encode())
        assets[identifier] = replace(
            bundle.asset,
            source_path=path.resolve(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            media_id=identifier,
        )
        sources.append(
            {
                "id": identifier,
                "path": path.name,
                "recordingGroup": f"recording-{index}",
                "partition": "test",
                "modelResultsViewed": False,
            }
        )
        references = (
            [
                {
                    "humanEventId": f"human-{index}-{i}",
                    "independenceGroup": f"action-{index}-{i}",
                    "usableRanges": [{"startUs": i * 1000, "endUs": i * 1000 + 500}],
                    "reason": "Synthetic reference, no human acceptance.",
                }
                for i in range(10)
            ]
            if confirmed
            else []
        )
        queries.append(
            {
                "id": f"query-{index}",
                "text": "寻找闪避片段",
                "kind": "main",
                "sourceId": identifier,
                "family": f"family-{index}",
                "referenceEvents": references,
            }
        )
    raw = {
        "schemaVersion": "benchmark-plan-v1",
        "datasetId": "synthetic-contract-only",
        "labelVersion": "synthetic-v1" if confirmed else None,
        "humanReferences": {
            "confirmed": confirmed,
            "annotators": ["synthetic-fixture"] if confirmed else [],
            "reviewed": False,
        },
        "sources": sources,
        "queries": queries,
    }
    return raw, assets


def freeze(raw, assets):
    return freeze_document(loads_plan(json.dumps(raw)), assets, "2026-10-07T10:00:00+08:00")


def timelines(assets):
    return {
        key: StoredTimeline(
            StoredRun(f"run-{key}", asset, CONFIG, "f" * 64, RunStatus.COMPLETED, None),
            (),
            (),
            (),
            (),
            (),
        )
        for key, asset in assets.items()
    }


def test_draft_freeze_bind_cannot_create_human_ratings_or_quality_gate(tmp_path):
    raw, assets = plan_fixture(tmp_path)
    frozen = freeze(raw, assets)
    assert frozen["preparation"]["readyForIndependentEvaluation"] is False
    manifest = bind_manifest(frozen, timelines(assets), "test")
    assert manifest["humanLabels"]["confirmed"] is False
    assert manifest["humanLabels"]["independentTestSet"] is False
    assert manifest["queries"][0]["candidateLabels"] == []
    assert manifest["queries"][0]["text"] == raw["queries"][0]["text"]


def test_ready_plan_still_needs_candidate_judgments_for_quality(tmp_path):
    raw, assets = plan_fixture(tmp_path, 10, confirmed=True)
    frozen = freeze(raw, assets)
    assert frozen["preparation"]["readyForIndependentEvaluation"] is True
    manifest = loads_manifest(
        canonical_json(bind_manifest(frozen, timelines(assets), "test")).decode()
    )
    assert manifest.human_labels.confirmed and manifest.human_labels.independent_test_set

    async def search(query):
        return (BenchmarkHit("unjudged-model-event", 0, 500, 1),)

    async def verify(media):
        return None

    report = asyncio.run(run_benchmark(manifest, search, verify_media=verify))
    assert report["qualityGate"] is None


@pytest.mark.parametrize(
    "kind,count,ready",
    [
        ("main", 9, False),
        ("main", 10, True),
        ("sparse", 0, False),
        ("sparse", 1, True),
        ("sparse", 9, True),
        ("sparse", 10, False),
        ("negative", 0, True),
    ],
)
def test_reference_group_contract_controls_confirmation(tmp_path, kind, count, ready):
    raw, assets = plan_fixture(tmp_path, confirmed=True)
    raw["queries"][0]["kind"] = kind
    raw["queries"][0]["referenceEvents"] = raw["queries"][0]["referenceEvents"][:count]
    result = bind_manifest(freeze(raw, assets), timelines(assets), "test")
    assert result["humanLabels"]["confirmed"] is ready
    assert result["humanLabels"]["independentTestSet"] is False


@pytest.mark.parametrize(
    "mutation,blocker",
    [
        ("group", "recording_group_crosses_partitions"),
        ("content", "same_content_crosses_partitions"),
        ("family", "query_family_crosses_partitions"),
        ("viewed", "test_results_already_viewed"),
        ("unknown", "recording_group_missing"),
        ("unused", "test_source_has_no_query"),
    ],
)
def test_leakage_is_saved_as_explicit_blocked_preparation(tmp_path, mutation, blocker):
    raw, assets = plan_fixture(tmp_path, 10, confirmed=True)
    raw["sources"][0]["partition"] = "development"
    if mutation == "group":
        raw["sources"][1]["recordingGroup"] = raw["sources"][0]["recordingGroup"]
    if mutation == "content":
        assets["source-1"] = replace(assets["source-1"], sha256=assets["source-0"].sha256)
    if mutation == "family":
        raw["queries"][1]["family"] = raw["queries"][0]["family"]
    if mutation == "viewed":
        raw["sources"][1]["modelResultsViewed"] = True
    if mutation == "unknown":
        raw["sources"][1]["recordingGroup"] = None
    if mutation == "unused":
        raw["queries"].pop()
    status = freeze(raw, assets)["preparation"]
    assert status["readyForIndependentEvaluation"] is False
    assert blocker in status["blockers"]


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "candidate",
        "bool",
        "query_source",
        "duplicate_id",
        "duration",
        "duplicate_group",
        "label_version",
    ],
)
def test_invalid_plan_or_reference_is_rejected_before_save(tmp_path, mutation):
    raw, assets = plan_fixture(tmp_path, confirmed=True)
    if mutation == "extra":
        raw["secret"] = "invalid"
    if mutation == "candidate":
        raw["queries"][0]["candidateLabels"] = []
    if mutation == "bool":
        raw["humanReferences"]["confirmed"] = 1
    if mutation == "query_source":
        raw["queries"][0]["sourceId"] = "missing"
    if mutation == "duplicate_id":
        raw["sources"].append(raw["sources"][0])
    if mutation == "duration":
        raw["queries"][0]["referenceEvents"][0]["usableRanges"][0]["endUs"] = 9_000_000
    if mutation == "duplicate_group":
        raw["queries"][0]["referenceEvents"][1]["independenceGroup"] = "action-0-0"
    if mutation == "label_version":
        raw["labelVersion"] = None
    with pytest.raises(ValueError):
        freeze(raw, assets)


@pytest.mark.parametrize(
    "text", ['{"schemaVersion":1,"schemaVersion":2}', '{"schemaVersion":NaN}', "[]"]
)
def test_duplicate_and_nonfinite_json_is_not_silently_accepted(text):
    with pytest.raises(ValueError):
        loads_plan(text)


@pytest.mark.parametrize("mutation", ["hash", "duration", "status", "missing", "extra"])
def test_binding_refuses_changed_source_or_wrong_run_mapping(tmp_path, mutation):
    raw, assets = plan_fixture(tmp_path)
    frozen, runs = freeze(raw, assets), timelines(assets)
    if mutation in ("hash", "duration", "status"):
        run = runs["source-0"].run
        if mutation == "hash":
            run = replace(run, asset=replace(run.asset, sha256="a" * 64))
        if mutation == "duration":
            frozen["sources"][0]["durationUs"] += 1
        if mutation == "status":
            run = replace(run, status=RunStatus.PENDING)
        runs["source-0"] = replace(runs["source-0"], run=run)
    if mutation == "missing":
        runs = {}
    if mutation == "extra":
        runs["extra"] = runs["source-0"]
    with pytest.raises(ValueError):
        bind_manifest(frozen, runs, "test")


def test_exclusive_bundle_keeps_original_bytes_and_rejects_tampering(tmp_path):
    raw, assets = plan_fixture(tmp_path)
    input_path = tmp_path / "plan.json"
    data = (json.dumps(raw, indent=2) + "\n").encode()
    input_path.write_bytes(data)
    output = tmp_path / "frozen"
    frozen = freeze(raw, assets)
    write_freeze(input_path, data, frozen, output)
    assert (output / "plan-input.json").read_bytes() == data
    assert read_freeze(output)[0] == frozen
    before = snapshot(output)
    with pytest.raises(FileExistsError):
        write_freeze(input_path, data, frozen, output)
    assert snapshot(output) == before
    (output / "freeze.json").write_bytes(
        canonical_json({**frozen, "frozenAt": "2027-01-01T00:00:00Z"})
    )
    with pytest.raises(ValueError, match="已改变"):
        read_freeze(output)


@pytest.mark.parametrize("changed", ["input", "source"])
def test_freeze_checks_change_during_probe_before_creating_output(tmp_path, changed):
    raw, assets = plan_fixture(tmp_path)
    input_path = tmp_path / "plan.json"
    data = canonical_json(raw)
    input_path.write_bytes(data)
    frozen = freeze(raw, assets)
    if changed == "input":
        input_path.write_bytes(data + b" ")
    else:
        assets["source-0"].source_path.write_bytes(b"changed source")
    output = tmp_path / "frozen"
    with pytest.raises(ValueError):
        write_freeze(input_path, data, frozen, output)
    assert not output.exists()


def test_public_cli_probes_only_and_binds_without_search_or_project_writes(
    tmp_path, monkeypatch, capsys
):
    bundle = bundle_fixture(tmp_path)
    raw, assets = plan_fixture(tmp_path, bundle=bundle)
    raw["sources"][0]["path"] = str(bundle.asset.source_path)
    assets["source-0"] = bundle.asset
    input_path = tmp_path / "plan.json"
    input_path.write_bytes(canonical_json(raw))
    output = tmp_path / "frozen"
    for name in (
        "_pinned_asr_settings",
        "LocalAsrProvider",
        "vision_for_run",
        "BudgetLedger",
        "HttpxVisionTransport",
    ):
        monkeypatch.setattr(
            cli, name, lambda *a, **k: pytest.fail("preparation invoked model or budget")
        )
    monkeypatch.setattr(cli, "execute_search", lambda *a, **k: pytest.fail("binding searched"))
    monkeypatch.setattr(cli, "search_timeline", lambda *a, **k: pytest.fail("binding searched"))

    class ProbeOnly:
        def __init__(self, repository):
            pass

        async def probe(self, path, context):
            return bundle.asset

    monkeypatch.setattr(cli, "FfmpegMediaProcessor", ProbeOnly)
    assert cli.main(["freeze-benchmark", "--input", str(input_path), "--output", str(output)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["paidRequestsSent"] == 0 and receipt["qualityGate"] is None

    async def complete():
        store = await SqliteTimelineStore.open(tmp_path / "project")
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            await store.persist_timeline("run-1", "vision", (event_fixture(bundle),), (), HASH)
            await store.complete_run("run-1")
        finally:
            await store.close()

    asyncio.run(complete())
    project = tmp_path / "project"
    before = snapshot(project)
    mapping = tmp_path / "runs.json"
    mapping.write_text('{"source-0":"run-1"}')
    bound = tmp_path / "bound"
    assert (
        cli.main(
            [
                "bind-benchmark",
                "--freeze",
                str(output),
                "--project",
                str(project),
                "--runs",
                str(mapping),
                "--output",
                str(bound),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert snapshot(project) == before
    manifest = loads_manifest((bound / "benchmark.json").read_text())
    assert manifest.media[0].sha256 == bundle.asset.sha256 and not manifest.human_labels.confirmed
    assert manifest.queries[0].candidate_labels == ()
    forbidden_output = project / "unwanted"
    assert (
        cli.main(
            [
                "bind-benchmark",
                "--freeze",
                str(output),
                "--project",
                str(project),
                "--runs",
                str(mapping),
                "--output",
                str(forbidden_output),
            ]
        )
        == 2
    )
    assert not forbidden_output.exists() and snapshot(project) == before


def bound_fixture(tmp_path):
    raw, assets = plan_fixture(tmp_path, confirmed=True)
    original = tmp_path / "plan.json"
    data = canonical_json(raw)
    original.write_bytes(data)
    directory = tmp_path / "frozen"
    frozen = freeze(raw, assets)
    write_freeze(original, data, frozen, directory)
    _, sha = read_freeze(directory)
    manifest = bind_manifest(frozen, timelines(assets), "test")
    bound = tmp_path / "bound"
    write_binding(
        directory=directory,
        freeze_sha256=sha,
        output=bound,
        project=tmp_path / "project",
        manifest=manifest,
        provenance={"schemaVersion": "benchmark-binding-v1", "freezeSha256": sha},
    )
    return bound, manifest


def test_frozen_binding_allows_only_actual_candidate_judgments_and_review(tmp_path):
    bound, manifest = bound_fixture(tmp_path)
    manifest["humanLabels"]["reviewed"] = True
    manifest["queries"][0]["candidateLabels"] = [
        {
            "eventId": "candidate-1",
            "humanEventId": "human-0-0",
            "startUs": 0,
            "endUs": 500,
            "grade": 2,
            "reason": "Synthetic judgment only.",
        }
    ]
    validate_bound_manifest(bound, canonical_json(manifest))


@pytest.mark.parametrize(
    "change",
    [
        "query",
        "range",
        "group",
        "source",
        "independence",
        "confirmation",
        "version",
        "missing",
        "duplicate",
    ],
)
def test_changed_frozen_basis_is_refused_before_benchmark_search(tmp_path, change):
    bound, manifest = bound_fixture(tmp_path)
    if change == "query":
        manifest["queries"][0]["text"] = "different mechanic"
    if change == "range":
        manifest["queries"][0]["referenceEvents"][0]["usableRanges"][0]["endUs"] = 400
    if change == "group":
        manifest["queries"][0]["referenceEvents"][0]["independenceGroup"] = "different-event"
    if change == "source":
        manifest["media"][0]["sha256"] = "f" * 64
    if change == "independence":
        manifest["humanLabels"]["independentTestSet"] = True
    if change == "confirmation":
        manifest["humanLabels"]["confirmed"] = False
    if change == "version":
        manifest["labelVersion"] = "changed-version"
    if change == "missing":
        manifest["queries"] = []
    if change == "duplicate":
        manifest["queries"].append(manifest["queries"][0])
    with pytest.raises(ValueError):
        validate_bound_manifest(bound, canonical_json(manifest))


def test_public_benchmark_binding_check_precedes_store_and_embedding(tmp_path, monkeypatch, capsys):
    bound, manifest = bound_fixture(tmp_path)
    manifest["queries"][0]["text"] = "changed"
    input_path = tmp_path / "judged.json"
    input_path.write_bytes(canonical_json(manifest))
    project = tmp_path / "project"
    (project / "timeline.sqlite3").write_bytes(b"existing project placeholder")

    async def forbidden(*args, **kwargs):
        pytest.fail("invalid frozen input opened store")

    monkeypatch.setattr(cli.SqliteTimelineStore, "open", forbidden)
    code = cli.main(
        [
            "benchmark",
            "--input",
            str(input_path),
            "--project",
            str(project),
            "--output",
            str(tmp_path / "report.json"),
            "--binding",
            str(bound),
        ]
    )
    assert code == 2 and json.loads(capsys.readouterr().err)["code"] == "input.benchmark"
    assert not (tmp_path / "report.json").exists()


def test_plan_example_is_unconfirmed_and_has_no_candidate_labels():
    path = Path(__file__).resolve().parents[1] / "templates/phase0-benchmark-plan.example.json"
    plan = loads_plan(path.read_text(encoding="utf-8"))
    assert not plan.manifest.human_labels.confirmed
    assert all(not query.candidate_labels for query in plan.manifest.queries)
