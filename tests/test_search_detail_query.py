"""Saved-ranking detail annotations retain provenance, rank and unknown audio states."""

import asyncio
import copy
import json
from dataclasses import replace

import pytest
from test_detail_inspection import refuse_sends
from test_detail_query import constraint, manifest, snapshot
from test_inspection_http import get, workspace
from test_project_detail_query import StoredPool, create_detail_pool, report
from test_project_retrieval import completed_pool, recording

from gamingcreator.application.retrieval import SearchResult, search_timelines
from gamingcreator.application.search_detail_query import (
    match_search_details,
    search_snapshot_sha256,
)
from gamingcreator.cli import main as cli
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.project_search_files import read_project_search


def document(*timelines):
    result = asyncio.run(search_timelines(timelines, "shelter", mode="lexical"))
    sources = [
        {
            "runId": run.run_id,
            "mediaId": run.asset.media_id,
            "sourceName": run.asset.source_path.name,
            "sourceSha256": run.asset.sha256,
            "durationUs": run.asset.duration_us,
            "configHash": run.config_hash,
            "pipelineHash": run.configuration.pipeline_hash,
            "pipelineVersion": run.configuration.pipeline_version,
        }
        for run in result.sources
    ]
    rows = []
    for position, candidate in enumerate(result.candidates, 1):
        source = next(row for row in sources if row["runId"] == candidate.run_id)
        row = cli._search_document(
            SearchResult(candidate.run_id, result.query, result.mode, (candidate.clip,)), 73
        )["candidates"][0]
        rows.append(
            row
            | {
                "rank": position,
                "runId": candidate.run_id,
                "sourceName": source["sourceName"],
                "sourceSha256": source["sourceSha256"],
            }
        )
    return {
        "schemaVersion": "project-search-v1",
        "searchId": "a" * 32,
        "scopeId": result.scope_id,
        "query": result.query,
        "mode": result.mode,
        "topK": 10,
        "elapsedMs": 73,
        "sources": sources,
        "candidates": rows,
    }


def test_original_order_scores_and_fields_remain_in_separate_read_only_annotation():
    left, right = recording("left"), recording("right")
    saved = document(left, right)
    original = copy.deepcopy(saved)
    calls = []

    def matcher(timeline, event, query):
        calls.append((timeline.run.run_id, event))
        return report(
            timeline, event, query, "full" if timeline.run.run_id == "left" else "partial"
        )

    value = asyncio.run(
        match_search_details(
            StoredPool(left, right),
            saved,
            search_snapshot_sha256(saved),
            constraint(),
            "v2",
            matcher,
        )
    )
    assert value["search"] == saved == original and value["search"]["elapsedMs"] == 73
    assert [row["rank"] for row in value["matches"]] == [1, 2]
    assert [row["candidateId"] for row in value["matches"]] == [
        row["candidateId"] for row in saved["candidates"]
    ]
    assert len(calls) == 2 and value["counts"] == {
        "full": 1,
        "partial": 1,
        "no_match": 0,
        "unverified": 0,
    }
    assert value["humanLabels"] is value["qualityGate"] is None
    assert value["ordinarySearches"] == value["paidRequestsSent"] == 0


def test_changed_saved_content_refuses_before_loading_or_matching():
    source = recording("left")
    saved = document(source)
    digest = search_snapshot_sha256(saved)
    saved["candidates"][0]["score"] += 1
    store = StoredPool(source)
    with pytest.raises(AppError, match="排名已变化"):
        asyncio.run(match_search_details(store, saved, digest, constraint(), "v2", report))
    assert not store.reads


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("sources", "mediaId", "other"),
        ("sources", "configHash", "f" * 64),
        ("sources", "sourceSha256", "f" * 64),
        ("sources", "durationUs", True),
        ("candidates", "rank", True),
        ("candidates", "candidateId", "other"),
        ("candidates", "eventId", "other"),
        ("candidates", "runId", "right"),
        ("candidates", "startUs", 9),
        ("candidates", "endUs", 9),
        ("candidates", "evidenceIds", []),
        ("candidates", "observableFacts", ["invented"]),
        ("candidates", "sourceSha256", "f" * 64),
        ("candidates", "score", True),
    ],
)
def test_wrong_saved_source_or_candidate_refuses_before_matching(section, field, value):
    source = recording("left")
    saved = document(source)
    saved[section][0][field] = value

    def forbidden(*args):
        raise AssertionError("Do not match invalid origins")

    with pytest.raises(AppError) as failure:
        asyncio.run(
            match_search_details(
                StoredPool(source),
                saved,
                search_snapshot_sha256(saved),
                constraint(),
                "v2",
                forbidden,
            )
        )
    assert failure.value.code == "retrieval.search_source"


def test_duplicate_physical_sources_refuse_before_source_projection():
    left = recording("left")
    right = recording("right")
    saved = document(left, right)
    duplicate = replace(right, run=replace(right.run, asset=left.run.asset))
    with pytest.raises(AppError, match="同一原录像"):
        asyncio.run(
            match_search_details(
                StoredPool(left, duplicate),
                saved,
                search_snapshot_sha256(saved),
                constraint(),
                "v2",
                report,
            )
        )


@pytest.fixture
def saved_search(tmp_path, monkeypatch):
    project, first, _ = create_detail_pool(tmp_path)
    refuse_sends(monkeypatch)
    result = asyncio.run(
        cli.execute_project_search(
            project, ["run-1", "run-2"], "fixture-mechanic 白色", tmp_path, mode="lexical"
        )
    )
    assert len(result["candidates"]) == 2
    return project, first, result


def body(project, saved, **overrides):
    return {
        "project": str(project),
        "searchId": saved["searchId"],
        "searchSha256": search_snapshot_sha256(saved),
        "profile": "v2",
        "constraint": manifest(),
        **overrides,
    }


def post(base, payload, **headers):
    return get(
        base,
        "/api/match-search-details",
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
    )


def test_actual_http_matches_exact_saved_details_without_research_or_new_files(
    saved_search, tmp_path
):
    project, first, saved = saved_search
    before = snapshot(project)
    with workspace(tmp_path) as base:
        code, _, data = post(base, body(project, saved))
        assert code == 200
        result = json.loads(data)
        assert result["search"] == saved == read_project_search(project, saved["searchId"])
        assert result["counts"] == {"full": 1, "partial": 0, "no_match": 0, "unverified": 1}
        known = next(row for row in result["matches"] if row["eventId"] == first.events[0].event_id)
        assert known["status"] == "full" and known["match"]["refinementProfile"] == "v2"
        code, _, data = post(base, body(project, saved, profile="v4"))
        assert code == 200 and json.loads(data)["counts"]["unverified"] == 2
    assert snapshot(project) == before


@pytest.mark.parametrize(
    "change",
    [
        {"searchSha256": "0" * 64},
        {"searchId": "../other"},
        {"profile": "latest"},
        {"searchSha256": True},
        {"constraint": {"naturalLanguage": "white hair"}},
        {"candidates": []},
    ],
)
def test_bad_http_identity_or_extra_client_candidates_refuse(saved_search, tmp_path, change):
    project, _, saved = saved_search
    before = snapshot(project)
    with workspace(tmp_path) as base:
        assert post(base, body(project, saved, **change))[0] in {400, 409}
        assert post(base, body(project, saved), Origin="https://outside.invalid")[0] == 403
    assert snapshot(project) == before


def test_actual_transcript_candidate_is_unknown_without_calling_visual_matcher(
    tmp_path, monkeypatch
):
    directory = tmp_path / "artifacts"
    directory.mkdir()
    project, _ = asyncio.run(completed_pool(directory))
    refuse_sends(monkeypatch)
    saved = asyncio.run(
        cli.execute_project_search(
            project, ["run-0", "run-1", "run-2"], "建造", tmp_path, mode="lexical"
        )
    )
    before = snapshot(project)
    value = asyncio.run(
        cli.execute_search_detail_match(
            project,
            saved["searchId"],
            search_snapshot_sha256(saved),
            json.dumps(manifest()),
            profile="v2",
        )
    )
    audio = next(row for row in value["matches"] if row["runId"] == "run-2")
    assert audio["eventId"] is None and audio["match"] is None
    assert audio["status"] == "unverified" and audio["availability"] == "transcript_only"
    assert value["search"] == saved and snapshot(project) == before


def test_public_cli_preserves_saved_rank_and_does_not_save_a_match(saved_search, tmp_path, capsys):
    project, _, saved = saved_search
    path = tmp_path / "conditions.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    before = snapshot(project)
    assert (
        cli.main(
            [
                "match-search-details",
                "--project",
                str(project),
                "--search",
                saved["searchId"],
                "--search-sha256",
                search_snapshot_sha256(saved),
                "--input",
                str(path),
                "--profile",
                "v2",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["search"] == saved and result["qualityGate"] is None
    assert snapshot(project) == before
