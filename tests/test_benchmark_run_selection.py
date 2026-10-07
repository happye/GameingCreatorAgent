"""Explicit frozen-source choices; fixtures never establish retrieval quality."""

import asyncio
import copy
import hashlib
import json
from dataclasses import replace
from urllib.parse import urlencode

import pytest
from test_benchmark_preparation import freeze, plan_fixture
from test_benchmark_workflow import submit
from test_inspection_http import get, stored_project, workspace
from test_sqlite_store import CONFIG, HASH, bundle_fixture, event_fixture

from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.application.benchmark_run_selection import binding_choices
from gamingcreator.application.storage import RunStatus, StoredRun
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.benchmark_preparation_files import write_freeze
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.benchmark_workflow import BenchmarkWorkflows


def test_choices_keep_versions_identity_declarations_and_query_partition(tmp_path):
    raw, assets = plan_fixture(tmp_path, 3)
    raw["sources"][0].update(recordingGroup=None, modelResultsViewed=True, partition="development")
    raw["sources"][1]["partition"] = "development"
    raw["queries"] = [raw["queries"][0], raw["queries"][2]]
    frozen = freeze(raw, assets)
    config = replace(
        CONFIG, analysis=replace(CONFIG.analysis, vision_prompt_version="phase0-vision-v6")
    )
    current = StoredRun("b-new", assets["source-0"], config, "a" * 64, RunStatus.COMPLETED, None)
    old = replace(current, run_id="a-old", configuration=CONFIG)
    pending = replace(current, run_id="c-pending", status=RunStatus.PENDING)
    wrong_duration = replace(
        current,
        run_id="d-duration",
        asset=replace(
            current.asset,
            duration_us=3_000_000,
            streams=(replace(current.asset.streams[0], duration_ts=3000),),
        ),
    )
    foreign = replace(current, run_id="e-other-source", asset=assets["source-2"])
    before = copy.deepcopy(frozen)
    choices = binding_choices(
        frozen, [foreign, pending, current, old, wrong_duration], "development"
    )
    assert frozen == before and len(choices) == 1
    row = choices[0]
    assert row["sourceId"] == "source-0" and row["recordingGroup"] is None
    assert row["modelResultsViewed"] is True
    assert row["sourceSha256"] == current.asset.sha256
    candidates = row["candidates"]
    assert [item["runId"] for item in candidates] == ["a-old", "b-new", "c-pending", "d-duration"]
    assert [item["selectable"] for item in candidates] == [True, True, False, False]
    assert candidates[1]["analysisLabel"] == "主体细节与动作 V6"
    assert candidates[2]["reason"] and candidates[3]["reason"]
    assert binding_choices(frozen, [foreign], "test")[0]["sourceId"] == "source-2"


@pytest.mark.parametrize("partition", ["", "production", "development"])
def test_no_automatic_partition_or_query_fallback(tmp_path, partition):
    raw, assets = plan_fixture(tmp_path)
    with pytest.raises(ValueError):
        binding_choices(freeze(raw, assets), [], partition)


def test_duplicate_physical_source_cannot_be_two_selectable_sources(tmp_path):
    raw, assets = plan_fixture(tmp_path, 2)
    raw["sources"][1]["path"] = raw["sources"][0]["path"]
    assets["source-1"] = assets["source-0"]
    run = StoredRun("same-run", assets["source-0"], CONFIG, HASH, RunStatus.COMPLETED, None)
    choices = binding_choices(freeze(raw, assets), [run], "test")
    assert all(row["duplicateSource"] for row in choices)
    assert all(not row["candidates"][0]["selectable"] for row in choices)


@pytest.fixture
def selection_workflow(tmp_path, monkeypatch):
    project, bundle = stored_project(tmp_path)
    second = bundle_fixture(project.parent, "run-2")

    async def another_version():
        store = await SqliteTimelineStore.open(project)
        try:
            config = replace(CONFIG, analysis=replace(CONFIG.analysis, model="second-fixture"))
            await store.create_run("run-2", second.asset, config)
            await store.begin_stage("run-2", "media", HASH)
            await store.persist_media_bundle("run-2", second)
            await store.begin_stage("run-2", "vision", HASH)
            await store.persist_timeline(
                "run-2", "vision", (event_fixture(second, "run-2", "event-2"),), (), HASH
            )
            await store.complete_run("run-2")
            await store.create_run("run-pending", bundle.asset, CONFIG)
        finally:
            await store.close()

    asyncio.run(another_version())
    plans = tmp_path / "plan-fixture"
    plans.mkdir()
    raw, _ = plan_fixture(plans)
    raw["sources"][0]["path"] = str(bundle.asset.source_path)
    frozen = freeze(raw, {"source-0": bundle.asset})
    manager = BenchmarkWorkflows(tmp_path)
    identifier = manager.create({"name": "程序选择夹具，无人工验收"})["id"]
    original = manager._execute

    def prepared(identifier, row, fields, rows):
        action = row["action"]
        if action in {"references", "references-import"}:
            publish_review_bundle(
                manager._output(identifier, row), {"benchmark-plan.json": canonical_json(raw)}, []
            )
            return 0, None
        if action == "freeze":
            source = manager._output(identifier, rows["references-import"]) / "benchmark-plan.json"
            write_freeze(source, source.read_bytes(), frozen, manager._output(identifier, row))
            return 0, None
        return original(identifier, row, fields, rows)

    monkeypatch.setattr(manager, "_execute", prepared)
    for action, fields in [
        ("references", {"inputText": json.dumps(raw)}),
        ("references-import", {"inputText": "{}"}),
        ("freeze", {}),
    ]:
        value = submit(manager, identifier, action, fields)
        assert value["attempts"][-1]["status"] == "finished", value
    yield manager, identifier, project, bundle
    manager.close()


def options(manager, identifier, project):
    return asyncio.run(manager.binding_options(identifier, str(project), "test"))


def test_metadata_reads_do_not_verify_media_or_write_and_bind_still_rejects_damage(
    selection_workflow, monkeypatch
):
    manager, identifier, project, bundle = selection_workflow
    database = (project / "timeline.sqlite3").read_bytes()
    bundle.images[0].path.write_bytes(b"damaged evidence")
    original = SqliteTimelineStore.load_completed_timeline

    async def forbidden(*args, **kwargs):
        raise AssertionError("Picker must not read completed media/timeline")

    monkeypatch.setattr(SqliteTimelineStore, "load_completed_timeline", forbidden)
    value = options(manager, identifier, project)
    assert value["mediaIntegrityVerified"] is False and value["qualityGate"] is None
    assert value["previousSelection"] == {} and value["paidRequestsSent"] == 0
    assert sum(item["selectable"] for item in value["sources"][0]["candidates"]) == 2
    assert (project / "timeline.sqlite3").read_bytes() == database
    monkeypatch.setattr(SqliteTimelineStore, "load_completed_timeline", original)
    result = submit(
        manager,
        identifier,
        "bind",
        {
            "project": str(project),
            "partition": "test",
            "inputText": '{"source-0":"run-1"}',
            "freezeSha256": value["freezeSha256"],
        },
    )
    assert result["attempts"][-1]["status"] == "failed"
    assert result["qualityGate"] is None


def test_stale_freeze_rejected_without_attempt_legacy_bind_and_reload_keep_explicit_selection(
    selection_workflow,
):
    manager, identifier, project, _ = selection_workflow
    value = options(manager, identifier, project)
    before = manager.get(identifier)
    fields = {
        "project": str(project),
        "partition": "test",
        "inputText": '{"source-0":"run-2"}',
        "freezeSha256": "0" * 64,
    }
    with pytest.raises(AppError, match="旧冻结"):
        manager.submit({"workflow": identifier, "action": "bind", "fields": fields})
    assert manager.get(identifier) == before
    fields.pop("freezeSha256")  # Existing manual mappings remain compatible.
    result = submit(manager, identifier, "bind", fields)
    assert result["attempts"][-1]["status"] == "finished", result
    reader = BenchmarkWorkflows(manager.repository)
    try:
        restored = options(reader, identifier, project)
        assert restored["freezeSha256"] == value["freezeSha256"]
        assert restored["previousSelection"] == {"source-0": "run-2"}
    finally:
        reader.close()


def test_http_choices_exact_identity_and_no_paid_or_quality_claim(selection_workflow):
    manager, identifier, project, _ = selection_workflow
    query = {"workflow": identifier, "project": str(project), "partition": "test"}
    with workspace(manager.repository) as base:
        path = "/api/benchmark-bind-options?" + urlencode(query)
        code, _, body = get(base, path)
        assert code == 200
        payload = json.loads(body)
        assert payload["schemaVersion"] == "benchmark-bind-options-v1"
        assert payload["previousSelection"] == {} and payload["mediaIntegrityVerified"] is False
        assert len(payload["sources"][0]["candidates"]) == 3
        assert get(base, path + "&extra=value")[0] == 400
        assert get(base, path, headers={"Origin": "https://outside.invalid"})[0] == 403
        assert (
            get(
                base,
                "/api/benchmark-bind-options?" + urlencode({**query, "partition": "development"}),
            )[0]
            == 400
        )
        assert (
            get(
                base, "/api/benchmark-bind-options?" + urlencode({**query, "project": "../outside"})
            )[0]
            == 400
        )
        assert (
            payload["freezeSha256"]
            == hashlib.sha256(
                manager.file(identifier, payload["freezeAttempt"], "freeze.json")
            ).hexdigest()
        )
