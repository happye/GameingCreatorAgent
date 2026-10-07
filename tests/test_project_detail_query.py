"""Whole-scope matching and exact saved details; synthetic data is not human acceptance."""

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest
from test_detail_inspection import refuse_sends, seed_project
from test_detail_query import constraint, manifest, publish_v2_fixture, snapshot
from test_inspection_http import get, workspace
from test_project_retrieval import recording
from test_sqlite_store import HASH, bundle_fixture, event_fixture

from gamingcreator.application.detail_query import match_report
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.project_detail_query import match_project_details
from gamingcreator.cli import main as cli
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


class StoredPool:
    def __init__(self, *timelines):
        self.timelines = {row.run.run_id: row for row in timelines}
        self.reads = []

    async def load_completed_timeline(self, identifier):
        self.reads.append(identifier)
        return self.timelines[identifier]


def report(timeline, event_id, query, status="unverified"):
    value = match_report(
        None, None, query, run_id=timeline.run.run_id, event_id=event_id, request_digest=None
    )
    value["refinementProfile"] = "v2"
    value["result"]["status"] = status
    return value


def test_full_filter_checks_events_beyond_first_page_and_keeps_sources_separate():
    first, other = recording("left"), recording("right")
    first = replace(
        first, events=tuple(replace(first.events[0], event_id=f"event-{i:02}") for i in range(26))
    )
    store = StoredPool(first, other)
    calls = []

    def saved(timeline, event_id, query):
        calls.append((timeline.run.run_id, event_id))
        return report(timeline, event_id, query, "full" if event_id == "event-25" else "partial")

    value = asyncio.run(
        match_project_details(
            store, ["right", "left"], constraint(), "v2", saved, status="full", limit=1
        )
    )
    assert len(calls) == 27 and value["counts"] == {
        "full": 1,
        "partial": 26,
        "no_match": 0,
        "unverified": 0,
    }
    assert value["totalEvents"] == 27 and value["totalSelected"] == 1 and value["hasNext"] is False
    assert value["results"][0]["eventId"] == "event-25" and value["results"][0]["runId"] == "left"
    assert value["humanLabels"] is value["qualityGate"] is None
    assert value["ordinarySearches"] == value["paidRequestsSent"] == 0


def test_pagination_snapshot_covers_all_results_and_input_order_is_stable():
    store = StoredPool(recording("left"), recording("right"))
    first = asyncio.run(
        match_project_details(store, ["right", "left"], constraint(), "v2", report, limit=1)
    )
    same = asyncio.run(
        match_project_details(store, ["left", "right"], constraint(), "v2", report, limit=1)
    )
    assert first == same and first["hasNext"]
    second = asyncio.run(
        match_project_details(
            store,
            ["left", "right"],
            constraint(),
            "v2",
            report,
            limit=1,
            offset=1,
            expected_snapshot=first["snapshotId"],
        )
    )
    assert second["snapshotId"] == first["snapshotId"] and second["results"][0]["runId"] == "right"
    with pytest.raises(AppError, match="发生变化"):
        asyncio.run(
            match_project_details(
                store,
                ["left", "right"],
                constraint(),
                "v2",
                lambda *args: report(*args, status="partial"),
                expected_snapshot=first["snapshotId"],
            )
        )


@pytest.mark.parametrize(
    "override",
    [
        {"run_ids": []},
        {"run_ids": [str(i) for i in range(101)]},
        {"run_ids": ["left", "left"]},
        {"profile": "future"},
        {"limit": True},
        {"limit": 51},
        {"offset": -1},
        {"status": "useful"},
        {"expected_snapshot": "invalid"},
    ],
)
def test_invalid_inputs_refuse_before_store_or_matcher(override):
    store = StoredPool(recording("left"))
    arguments = dict(
        store=store, run_ids=["left"], constraint=constraint(), profile="v2", matcher=report
    )
    arguments.update(override)
    with pytest.raises(AppError):
        asyncio.run(match_project_details(**arguments))
    assert store.reads == []


def test_same_physical_recording_versions_refuse_before_matching():
    first = recording("left")
    second = recording("right", asset=first.run.asset)
    store = StoredPool(first, second)

    def forbidden(*args):
        raise AssertionError("Do not match duplicate source versions")

    with pytest.raises(AppError, match="同一原录像"):
        asyncio.run(match_project_details(store, ["left", "right"], constraint(), "v2", forbidden))


def create_detail_pool(tmp_path, second_event_count=1):
    project, bundle, first = seed_project(tmp_path)
    publish_v2_fixture(project, first)
    second = bundle_fixture(project.parent, "run-2")
    source = project.parent / "第二段.fixture"
    source.write_bytes(b"another synthetic recording")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    asset = replace(second.asset, source_path=source.resolve(), sha256=digest, media_id=digest)
    image = replace(second.images[0], evidence_id=f"run-2:{digest}:image:000000")
    second = replace(second, asset=asset, images=(image,))
    write_manifest(second, SamplingParameters())
    event = event_fixture(second, "run-2", f"run-2:{digest}:event:" + "cd" * 12)

    async def create():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-2", asset, first.run.configuration)
            await store.begin_stage("run-2", "media", HASH)
            await store.persist_media_bundle("run-2", second)
            await store.begin_stage("run-2", "vision", HASH)
            events = tuple(
                replace(event, event_id=f"run-2:{digest}:event:{index:024x}")
                for index in range(second_event_count)
            )
            await store.persist_timeline("run-2", "vision", events, (), HASH)
            await store.complete_run("run-2")
            await store.create_run("run-pending", asset, first.run.configuration)
        finally:
            await store.close()

    asyncio.run(create())
    return project, first, second


@pytest.fixture
def detail_pool(tmp_path):
    return create_detail_pool(tmp_path)


def body(project, **overrides):
    return {
        "project": str(project),
        "runs": ["run-1", "run-2"],
        "profile": "v2",
        "constraint": manifest(),
        "limit": 1,
        "offset": 0,
        "status": "all",
        "snapshot": None,
        **overrides,
    }


def post(base, document, **headers):
    return get(
        base,
        "/api/match-project-details",
        method="POST",
        data=json.dumps(document).encode(),
        headers={"Content-Type": "application/json", **headers},
    )


def test_actual_http_saved_full_missing_unverified_filter_and_read_only(
    detail_pool, tmp_path, monkeypatch
):
    project, _, _ = detail_pool
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        code, _, raw = post(base, body(project))
        assert code == 200
        first = json.loads(raw)
        assert first["counts"] == {"full": 1, "partial": 0, "no_match": 0, "unverified": 1}
        assert first["results"][0]["runId"] == "run-1" and first["hasNext"]
        code, _, raw = post(base, body(project, offset=1, snapshot=first["snapshotId"]))
        assert code == 200 and json.loads(raw)["results"][0]["runId"] == "run-2"
        code, _, raw = post(base, body(project, status="full", snapshot=first["snapshotId"]))
        assert code == 200 and json.loads(raw)["totalSelected"] == 1
        code, _, raw = post(base, body(project, profile="v4"))
        assert code == 200 and json.loads(raw)["counts"]["unverified"] == 2
        assert get(base, "/api/health")[0] == 200
    assert snapshot(project) == before


@pytest.mark.parametrize(
    "change",
    [
        {"runs": ["run-1", "run-pending"]},
        {"runs": ["run-1", "run-1"]},
        {"profile": "future"},
        {"constraint": {"query": "白发红衣"}},
        {"limit": True},
        {"offset": -1},
        {"save": True},
        {"snapshot": "0" * 64},
    ],
)
def test_bad_http_scope_or_parameters_refuse_and_keep_existing_files(detail_pool, tmp_path, change):
    project, _, _ = detail_pool
    before = snapshot(project)
    with workspace(tmp_path) as base:
        code, _, _ = post(base, body(project, **change))
        assert code in {400, 409}
        assert post(base, body(project), Origin="https://outside.invalid")[0] == 403
    assert snapshot(project) == before


def test_cli_reports_all_scope_without_search_or_match_files(
    detail_pool, tmp_path, capsys, monkeypatch
):
    project, _, _ = detail_pool
    refuse_sends(monkeypatch)
    query = tmp_path / "conditions.json"
    query.write_text(json.dumps(manifest()), encoding="utf-8")
    before = snapshot(project)
    assert (
        cli.main(
            [
                "match-project-details",
                "--project",
                str(project),
                "--run",
                "run-2",
                "--run",
                "run-1",
                "--input",
                str(query),
                "--profile",
                "v2",
                "--status",
                "full",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["totalEvents"] == 2 and result["totalSelected"] == 1
    assert snapshot(project) == before
