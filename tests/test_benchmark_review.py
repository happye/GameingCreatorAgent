"""Synthetic review contracts and real local editing; no human acceptance claims."""

import asyncio
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_benchmark import document
from test_benchmark_preparation import freeze, plan_fixture
from test_detail_query import snapshot
from test_material_tasks import CONFIG
from test_sqlite_store import HASH, bundle_fixture, event_fixture, media_ready

from gamingcreator.application.benchmark import BenchmarkHit, parse_manifest, run_benchmark
from gamingcreator.application.benchmark_preparation import bind_manifest, canonical_json
from gamingcreator.application.benchmark_review import (
    build_review_context,
    judged_manifest,
    validate_review,
)
from gamingcreator.application.storage import RunStatus, StoredRun, StoredTimeline
from gamingcreator.cli import main as cli
from gamingcreator.infrastructure.benchmark_preparation_files import (
    read_freeze,
    write_binding,
    write_freeze,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.benchmark_review import render_benchmark_review

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_review_script", ROOT / "scripts/prepare-benchmark-review.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def review_fixture(tmp_path, count=11, *, failed=False):
    bundle = bundle_fixture(tmp_path)
    raw = document()
    raw["queries"][0]["candidateLabels"] = []
    raw["media"] = [
        {
            "mediaId": bundle.asset.media_id,
            "runId": "run-1",
            "sha256": bundle.asset.sha256,
            "durationUs": bundle.asset.duration_us,
        }
    ]
    raw["queries"][0].update({"mediaId": bundle.asset.media_id, "runId": "run-1"})
    run = StoredRun("run-1", bundle.asset, CONFIG, "f" * 64, RunStatus.COMPLETED, None)
    timeline = StoredTimeline(run, (), (), (), (), ())
    identifiers = ["event-0" if i < 2 else f"event-{i}" for i in range(count)]
    hits = tuple(
        BenchmarkHit(identifier, 100_000, 800_000, index + 1)
        for index, identifier in enumerate(identifiers)
    )
    metadata = {
        "runs": [
            {
                "runId": run.run_id,
                "pipelineVersion": run.configuration.pipeline_version,
                "configHash": run.config_hash,
            }
        ],
        "retrievalVersion": "synthetic-review-v1",
        "retrievalMode": "lexical",
    }

    async def search(query):
        if failed:
            raise ValueError("synthetic query failure")
        return hits

    async def verify(media):
        return None

    report = asyncio.run(
        run_benchmark(parse_manifest(raw), search, verify_media=verify, runner_metadata=metadata)
    )
    report["queries"][0]["retrievalId"] = None if failed else "retrieval-1"
    stored_hits = [
        {
            "rank": i + 1,
            "candidate_id": f"candidate-{i}",
            "event_id": identifier,
            "start_us": 100_000,
            "end_us": 800_000,
            "evidence_ids": [bundle.images[0].evidence_id],
        }
        for i, identifier in enumerate(identifiers)
    ]
    candidates = [
        {
            "rank": i + 1,
            "candidateId": hit["candidate_id"],
            "eventId": hit["event_id"],
            "mediaId": bundle.asset.media_id,
            "startUs": hit["start_us"],
            "endUs": hit["end_us"],
            "evidenceIds": hit["evidence_ids"],
            "observableFacts": ['</script><img src=x onerror="window.injected=true"> fixture'],
        }
        for i, hit in enumerate(stored_hits)
    ]
    retrieval = {
        "retrievalId": "retrieval-1",
        "runId": "run-1",
        "mediaId": bundle.asset.media_id,
        "query": raw["queries"][0]["text"],
        "retrievalVersion": "synthetic-review-v1",
        "parameters": {"mode": "lexical", "topK": 10},
        "hits": stored_hits,
        "result": {"candidates": candidates},
    }
    return raw, report, {"run-1": timeline}, {"retrieval-1": retrieval}, hits


def build(fixture):
    raw, report, sources, retrievals, _ = fixture
    return build_review_context(
        raw,
        report,
        report_sha256=hashlib.sha256(canonical_json(report)).hexdigest(),
        binding_sha256=hashlib.sha256(canonical_json(raw)).hexdigest(),
        timelines=sources,
        retrievals=retrievals,
    )


def test_audio_candidate_keeps_persisted_identity_without_visual_event(tmp_path):
    fixture = review_fixture(tmp_path, 1)
    raw, report, sources, retrievals, hits = fixture
    retrievals["retrieval-1"]["hits"][0]["event_id"] = None
    retrievals["retrieval-1"]["result"]["candidates"][0]["eventId"] = None
    report["queries"][0]["slots"][0]["eventId"] = "candidate-0"
    context, template = build((raw, report, sources, retrievals, hits))
    first = template["queries"][0]["slots"][0]
    assert first["eventId"] == "candidate-0" and first["candidateId"] == "candidate-0"
    record = recorded(template)
    judged = judged_manifest(context, record)
    assert judged["queries"][0]["candidateLabels"][0]["eventId"] == "candidate-0"


def recorded(template, *, grade=2):
    result = deepcopy(template)
    result.update({"recordedOn": "2026-10-07", "reviewer": "synthetic-fixture-only"})
    result["queries"][0]["slots"][0].update(
        {
            "grade": grade,
            "humanEventId": "human-0" if grade >= 2 else None,
            "reason": "Synthetic judgment, never real acceptance.",
        }
    )
    return result


@pytest.mark.parametrize("count", [0, 2, 11])
def test_ten_positions_keep_missing_duplicates_and_no_eleventh_refill(tmp_path, count):
    context, template = build(review_fixture(tmp_path, count))
    slots = template["queries"][0]["slots"]
    assert len(slots) == 10 and [slot["slot"] for slot in slots] == list(range(1, 11))
    assert all(slot["grade"] is None for slot in slots)
    if count >= 2:
        assert slots[1]["state"] == "known_duplicate"
    assert sum(slot["state"] == "missing" for slot in slots) == max(0, 10 - count)
    validate_review(canonical_json(template), template, context)
    assert judged_manifest(context, template)["queries"][0]["candidateLabels"] == []


def test_failed_query_is_explicit_and_cannot_be_judged(tmp_path):
    context, template = build(review_fixture(tmp_path, failed=True))
    assert context["queries"][0]["status"] == "failed"
    record = recorded(template, grade=0)
    with pytest.raises(ValueError):
        validate_review(canonical_json(record), template, context)


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "config",
        "query",
        "order",
        "range",
        "rank",
        "boolean_range",
        "count",
        "missing_id",
        "other_id",
        "version",
        "mode",
        "slots",
        "false_missing",
    ],
)
def test_report_cannot_replace_source_query_or_persisted_positions(tmp_path, change):
    fixture = review_fixture(tmp_path, 2)
    raw, report, sources, retrievals, _ = fixture
    row = report["queries"][0]
    if change == "source":
        report["media"][0]["sha256"] = "f" * 64
    if change == "config":
        report["runnerMetadata"]["runs"][0]["configHash"] = "e" * 64
    if change == "query":
        row["text"] = "different"
    if change == "order":
        row["slots"][0], row["slots"][1] = row["slots"][1], row["slots"][0]
    if change == "range":
        row["slots"][0]["endUs"] += 1
    if change == "rank":
        row["slots"][0]["reportedRank"] = 2
    if change == "boolean_range":
        row["slots"][0]["reportedRank"] = True
    if change == "count":
        row["totalReturned"] = 3
    if change == "missing_id":
        row.pop("retrievalId")
    if change == "other_id":
        row["retrievalId"] = "not-saved"
    if change == "version":
        report["runnerMetadata"]["retrievalVersion"] = "changed"
    if change == "mode":
        report["runnerMetadata"]["retrievalMode"] = "hybrid"
    if change == "slots":
        row["slots"].pop()
    if change == "false_missing":
        row["slots"][2]["status"] = "unjudged"
    with pytest.raises(ValueError):
        build(fixture)


@pytest.mark.parametrize(
    "change",
    [
        "basis",
        "slot",
        "range",
        "boolean_rank",
        "grade_bool",
        "grade_float",
        "grade_string",
        "grade_high",
        "reference",
        "reason",
        "metadata",
        "date",
        "duplicate",
        "missing",
    ],
)
def test_review_refuses_changed_basis_or_invalid_judgments(tmp_path, change):
    context, template = build(review_fixture(tmp_path, 2))
    record = recorded(template)
    slot = record["queries"][0]["slots"][0]
    if change == "basis":
        record["basisSha256"] = "0" * 64
    if change == "slot":
        slot["slot"] = 2
    if change == "range":
        slot["endUs"] += 1
    if change == "boolean_rank":
        slot["reportedRank"] = True
    if change == "grade_bool":
        slot["grade"] = True
    if change == "grade_float":
        slot["grade"] = 2.0
    if change == "grade_string":
        slot["grade"] = "2"
    if change == "grade_high":
        slot["grade"] = 4
    if change == "reference":
        slot["humanEventId"] = "not-frozen"
    if change == "reason":
        slot["reason"] = None
    if change == "metadata":
        record["reviewer"] = None
    if change == "date":
        record["recordedOn"] = "2026-02-30"
    if change == "duplicate":
        record["queries"][0]["slots"][1].update({"grade": 0, "reason": "duplicate"})
    if change == "missing":
        record["queries"][0]["slots"][2].update({"grade": 0, "reason": "missing"})
    with pytest.raises(ValueError):
        validate_review(canonical_json(record), template, context)


def test_partial_notes_do_not_become_grade_zero_and_duplicate_human_events_stay_duplicate(tmp_path):
    fixture = review_fixture(tmp_path, 3)
    context, template = build(fixture)
    record = recorded(template)
    record["queries"][0]["slots"][2].update({"reason": "needs later review"})
    assert len(judged_manifest(context, record)["queries"][0]["candidateLabels"]) == 1
    record["queries"][0]["slots"][2].update(
        {"grade": 2, "humanEventId": "human-0", "reason": "same real event"}
    )
    manifest = parse_manifest(judged_manifest(context, record))

    async def search(query):
        return fixture[-1]

    async def verify(media):
        return None

    report = asyncio.run(run_benchmark(manifest, search, verify_media=verify))
    assert report["queries"][0]["duplicateSlots"] == 2
    assert report["queries"][0]["usefulRateAt10"] == 0.1


def seed_script_project(tmp_path):
    bundle = bundle_fixture(tmp_path)
    raw, assets = plan_fixture(tmp_path, bundle=bundle)
    raw["sources"][0]["path"] = str(bundle.asset.source_path)
    raw["queries"][0]["text"] = "Observed fixture action"
    assets["source-0"] = bundle.asset
    original = tmp_path / "plan.json"
    data = canonical_json(raw)
    original.write_bytes(data)
    frozen = freeze(raw, assets)
    directory = tmp_path / "frozen"
    write_freeze(original, data, frozen, directory)
    _, sha = read_freeze(directory)
    project = tmp_path / "project"

    async def complete():
        store = await SqliteTimelineStore.open(project)
        try:
            await media_ready(store, bundle)
            await store.begin_stage("run-1", "vision", HASH)
            await store.persist_timeline("run-1", "vision", (event_fixture(bundle),), (), HASH)
            await store.complete_run("run-1")
            return await store.load_completed_timeline("run-1")
        finally:
            await store.close()

    timeline = asyncio.run(complete())
    manifest = bind_manifest(frozen, {"source-0": timeline}, "test")
    binding = tmp_path / "binding"
    write_binding(
        directory=directory,
        freeze_sha256=sha,
        output=binding,
        project=project,
        manifest=manifest,
        provenance={"schemaVersion": "benchmark-binding-v1", "freezeSha256": sha},
    )
    report = tmp_path / "report.json"
    result = asyncio.run(
        cli.execute_benchmark(
            project, binding / "benchmark.json", report, ROOT, mode="lexical", binding_path=binding
        )
    )
    assert result["queries"][0]["retrievalId"]
    return project, binding, report


def test_script_prepares_imports_and_rechecks_real_sqlite_receipt_without_search(
    tmp_path, monkeypatch, capsys
):
    project, binding, report = seed_script_project(tmp_path)
    before = snapshot(project)

    def forbidden(*args, **kwargs):
        pytest.fail("review invoked model, budget or search")

    for name in (
        "execute_search",
        "search_timeline",
        "LocalAsrProvider",
        "vision_for_run",
        "BudgetLedger",
        "HttpxVisionTransport",
    ):
        monkeypatch.setattr(cli, name, forbidden)
    args = ["--project", str(project), "--binding", str(binding), "--report", str(report)]
    output = tmp_path / "editor"
    assert script.main([*args, "--output", str(output)]) == 0
    capsys.readouterr()
    context = json.loads((output / "context.json").read_bytes())
    assert context["qualityGate"] is None
    template = json.loads((output / "record-template.json").read_bytes())
    record = recorded(template, grade=1)
    record_path = tmp_path / "record.json"
    record_path.write_bytes(canonical_json(record))
    saved = tmp_path / "saved"
    assert script.main([*args, "--record", str(record_path), "--output", str(saved)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["judgedPositions"] == 1 and receipt["qualityGate"] is None
    judged = json.loads((saved / "benchmark-judged.json").read_bytes())
    assert judged["queries"][0]["candidateLabels"][0]["grade"] == 1
    assert judged["humanLabels"]["confirmed"] is False
    assert snapshot(project) == before
    forbidden_output = project / "review-output"
    assert script.main([*args, "--output", str(forbidden_output)]) == 2
    assert not forbidden_output.exists() and snapshot(project) == before
    capsys.readouterr()
    record["queries"][0]["slots"][0]["endUs"] += 1
    record_path.write_bytes(canonical_json(record))
    assert (
        script.main([*args, "--record", str(record_path), "--output", str(tmp_path / "refused")])
        == 2
    )
    assert not (tmp_path / "refused").exists() and snapshot(project) == before


@pytest.mark.parametrize("width", [1366, 390])
def test_local_file_editor_round_trip_and_invalid_record_preserves_input(tmp_path, width):
    playwright = pytest.importorskip("playwright.sync_api")
    context, template = build(review_fixture(tmp_path, 2))
    path = tmp_path / "review.html"
    path.write_text(render_benchmark_review(context, template), encoding="utf-8")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900}, accept_downloads=True)
            requests, errors = [], []
            page.on(
                "request",
                lambda request: (
                    requests.append(request.url)
                    if not request.url.startswith(("file:", "data:", "blob:"))
                    else None
                ),
            )
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(path.as_uri())
            playwright.expect(page.locator(".slot")).to_have_count(10)
            assert page.locator("img").count() == 0
            assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
            grade = page.locator('[data-field="grade"]').first
            assert grade.input_value() == ""
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            downloaded = pending.value
            blank = json.loads(Path(downloaded.path()).read_bytes())
            assert blank == template
            page.locator("#recordedOn").fill("2026-10-07")
            page.locator("#reviewer").fill("synthetic-browser-only")
            grade.select_option("2")
            page.locator('[data-field="humanEventId"]').first.select_option("human-0")
            page.locator('[data-field="reason"]').first.fill("synthetic usable clip")
            with page.expect_download() as pending:
                page.locator("#download-record").click()
            downloaded = pending.value
            data = Path(downloaded.path()).read_bytes()
            valid = validate_review(data, template, context)
            assert valid["queries"][0]["slots"][0]["grade"] == 2
            page.locator('[data-field="reason"]').first.fill("keep current")
            invalid = deepcopy(valid)
            invalid["basisSha256"] = "0" * 64
            page.locator("#load-record").set_input_files(
                {
                    "name": "wrong.json",
                    "mimeType": "application/json",
                    "buffer": canonical_json(invalid),
                }
            )
            playwright.expect(page.locator("#status")).to_contain_text("无法载入")
            assert page.locator('[data-field="reason"]').first.input_value() == "keep current"
            page.locator("#load-record").set_input_files(
                {"name": "valid.json", "mimeType": "application/json", "buffer": data}
            )
            playwright.expect(page.locator("#status")).to_contain_text("已载入")
            assert (
                page.locator('[data-field="reason"]').first.input_value() == "synthetic usable clip"
            )
            page.evaluate("""() => {
                const original = File.prototype.text;
                File.prototype.text = function() {
                    if (this.name !== 'delayed.json') return original.call(this);
                    return new Promise(resolve => {
                        window.finishReviewLoad = () => original.call(this).then(resolve);
                    });
                };
            }""")
            page.locator("#load-record").set_input_files(
                {"name": "delayed.json", "mimeType": "application/json", "buffer": data}
            )
            page.locator('[data-field="reason"]').first.fill("new edit while loading")
            page.evaluate("() => window.finishReviewLoad()")
            playwright.expect(page.locator("#status")).to_contain_text("保留当前填写内容")
            assert (
                page.locator('[data-field="reason"]').first.input_value()
                == "new edit while loading"
            )
            assert not requests and not errors
        finally:
            browser.close()
