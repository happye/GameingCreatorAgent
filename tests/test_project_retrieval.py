"""Joint corpus ranking preserves independent sources and original candidate identities."""

import asyncio
import hashlib
import json
import math
import os
import subprocess
import sys
from dataclasses import replace

import pytest
from test_retrieval import SynonymFixture, event, timeline
from test_sqlite_store import CONFIG, bundle_fixture, event_fixture

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import (
    CancellationContext,
)
from gamingcreator.application.retrieval import (
    PROJECT_RETRIEVAL_VERSION,
    search_timeline,
    search_timelines,
)
from gamingcreator.application.storage import RunStatus
from gamingcreator.cli import main as cli
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import TranscriptSegment
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.project_search_files import (
    read_project_search,
    write_project_search,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def recording(identifier, *, facts="player assembles a shelter", asset=None):
    original = timeline(events=(event("same-event-id", 0, 1, facts, "construction"),))
    asset = asset or replace(
        original.run.asset,
        media_id=identifier,
        sha256=hashlib.sha256(identifier.encode()).hexdigest(),
    )
    return replace(
        original,
        run=replace(original.run, run_id=identifier, asset=asset),
        evidence=tuple(
            replace(
                item,
                evidence_id=item.evidence_id.replace("run:", identifier + ":"),
                media_id=asset.media_id,
            )
            for item in original.evidence
        ),
        events=tuple(
            replace(
                item,
                run_id=identifier,
                media_id=asset.media_id,
                evidence_ids=tuple(
                    value.replace("run:", identifier + ":") for value in item.evidence_ids
                ),
            )
            for item in original.events
        ),
    )


class CapturingEmbedding(SynonymFixture):
    def __init__(self):
        self.requests = []

    async def embed(self, request, context):
        self.requests.append(request)
        return await super().embed(request, context)


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_same_time_same_description_in_different_recordings_both_survive(mode):
    left, right = recording("left"), recording("right")
    provider = CapturingEmbedding()
    result = asyncio.run(
        search_timelines((right, left), "construction", mode=mode, embedding_provider=provider)
    )
    assert len(result.candidates) == 2
    assert {item.run_id for item in result.candidates} == {"left", "right"}
    assert len({item.clip.candidate_id for item in result.candidates}) == 2
    for source in (left, right):
        old = asyncio.run(
            search_timeline(
                source, "construction", mode=mode, embedding_provider=CapturingEmbedding()
            )
        ).candidates[0]
        new = next(item.clip for item in result.candidates if item.run_id == source.run.run_id)
        assert new.candidate_id == old.candidate_id
        assert new.source_range == old.source_range and new.evidence_ids == old.evidence_ids
        assert new.observable_facts == old.observable_facts
    if mode != "lexical":
        assert len(provider.requests) == 1 and len(provider.requests[0].texts) == 3
        assert provider.requests[0].run_id == result.scope_id
    assert result.retrieval_version == PROJECT_RETRIEVAL_VERSION


def test_joint_bm25_changes_corpus_scores_and_input_order_does_not_change_result():
    left, right = recording("left"), recording("right", facts="construction beside river")
    standalone = asyncio.run(search_timeline(left, "construction", mode="lexical"))
    forward = asyncio.run(search_timelines((left, right), "construction", mode="lexical"))
    reverse = asyncio.run(search_timelines((right, left), "construction", mode="lexical"))
    assert forward == reverse
    assert (
        next(item.clip.score for item in forward.candidates if item.run_id == "left")
        != standalone.candidates[0].score
    )
    limited = asyncio.run(search_timelines((left, right), "construction", mode="lexical", top_k=1))
    assert limited.candidates == forward.candidates[:1]


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_single_source_pool_has_exact_original_candidates(mode):
    source = recording("one")
    original = asyncio.run(
        search_timeline(source, "construction", mode=mode, embedding_provider=SynonymFixture())
    )
    result = asyncio.run(
        search_timelines((source,), "construction", mode=mode, embedding_provider=SynonymFixture())
    )
    assert tuple(item.clip for item in result.candidates) == original.candidates
    assert result.min_similarity == original.min_similarity
    assert result.abstention_reason == original.abstention_reason


def test_same_audio_interval_from_two_sources_retains_nullable_event_and_original_ids():
    sources = []
    for identifier in ("left", "right"):
        source = recording(identifier)
        source = replace(
            source,
            events=(),
            transcripts=(
                TranscriptSegment(
                    source.run.asset.media_id,
                    SourceRange(7_000_000, 8_000_000, 10_000_000),
                    "开启角色背包",
                ),
            ),
        )
        sources.append(source)
    result = asyncio.run(search_timelines(tuple(sources), "开启背包", mode="lexical"))
    assert len(result.candidates) == 2
    assert all(item.clip.event_id is None for item in result.candidates)
    assert all(item.clip.evidence_ids == (item.run_id + ":audio",) for item in result.candidates)


@pytest.mark.parametrize(
    "kind", ["empty", "many", "run_duplicate", "source_duplicate", "incomplete", "bad_evidence"]
)
def test_invalid_scope_refuses_before_embedding(kind):
    first, second = recording("first"), recording("second")
    values = (first, second)
    if kind == "empty":
        values = ()
    elif kind == "many":
        values = (first,) * 101
    elif kind == "run_duplicate":
        values = (first, first)
    elif kind == "source_duplicate":
        values = (first, recording("other-version", asset=first.run.asset))
    elif kind == "incomplete":
        values = (first, replace(second, run=replace(second.run, status=RunStatus.PENDING)))
    else:
        values = (first, replace(second, evidence=()))
    provider = CapturingEmbedding()
    with pytest.raises(AppError):
        asyncio.run(search_timelines(values, "construction", embedding_provider=provider))
    assert provider.requests == []


@pytest.mark.parametrize("query", ["", "  ", "!!!", "show me the clip", "spaceship laser trading"])
def test_empty_or_negative_lexical_search_does_not_pad(query):
    assert (
        asyncio.run(
            search_timelines((recording("first"), recording("second")), query, mode="lexical")
        ).candidates
        == ()
    )


def test_explicit_denial_and_global_semantic_cutoff_apply_to_all_sources():
    yes = recording("yes", facts="角色建造房屋并跳跃到平台")
    no = recording("no", facts="角色建造房屋，没有跳跃动作")
    yes = replace(yes, events=tuple(replace(e, mechanic_tags=()) for e in yes.events))
    no = replace(no, events=tuple(replace(e, mechanic_tags=()) for e in no.events))
    result = asyncio.run(search_timelines((yes, no), "跳跃", mode="lexical"))
    assert [item.run_id for item in result.candidates] == ["yes"]
    assert asyncio.run(
        search_timelines(
            (yes, no), "build a home", mode="semantic", embedding_provider=SynonymFixture()
        )
    ).candidates


def test_wrong_scope_context_and_embedding_failure_never_return_partial_rankings():
    sources = (recording("left"), recording("right"))
    with pytest.raises(AppError):
        asyncio.run(
            search_timelines(sources, "construction", context=CancellationContext("wrong", 1))
        )

    class Failing(CapturingEmbedding):
        async def embed(self, request, context):
            raise AppError("embedding.failed", "fixture failure", ExitCode.PROVIDER)

    with pytest.raises(AppError):
        asyncio.run(search_timelines(sources, "construction", embedding_provider=Failing()))


def test_hybrid_semantic_margin_is_global_not_a_union_of_per_source_results():
    sources = (recording("left"), recording("right", facts="construction beside river"))

    class Contrasting(CapturingEmbedding):
        async def embed(self, request, context):
            result = await super().embed(request, context)
            vectors = []
            for text in request.texts:
                cosine = 1.0 if text.startswith("query:") else 0.91 if "river" in text else 0.96
                vectors.append((cosine, math.sqrt(1 - cosine * cosine)))
            return replace(
                result,
                output=tuple(
                    replace(item, vector=vector)
                    for item, vector in zip(result.output, vectors, strict=True)
                ),
            )

    originals = [
        asyncio.run(search_timeline(source, "unworded intent", embedding_provider=Contrasting()))
        for source in sources
    ]
    assert all(len(result.candidates) == 1 for result in originals)
    semantic = asyncio.run(
        search_timelines(
            sources, "unworded intent", mode="semantic", embedding_provider=Contrasting()
        )
    )
    assert len(semantic.candidates) == 2
    hybrid = asyncio.run(
        search_timelines(sources, "unworded intent", embedding_provider=Contrasting())
    )
    assert [item.run_id for item in hybrid.candidates] == ["left"]


def test_cancelled_joint_query_returns_no_candidates_and_does_not_enter_embedding():
    sources = (recording("left"), recording("right"))
    scope = asyncio.run(search_timelines(sources, "construction", mode="lexical")).scope_id
    context = CancellationContext(scope, 1)
    context.cancelled.set()
    provider = CapturingEmbedding()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            search_timelines(sources, "construction", context=context, embedding_provider=provider)
        )
    assert provider.requests == []


async def completed_pool(root):
    project = root / "project"
    store = await SqliteTimelineStore.open(project)
    bundles = []
    try:
        for index in range(3):
            identifier = f"run-{index}"
            bundle = bundle_fixture(root, identifier, audio=index == 2)
            source = root / f"source-{index}.fixture"
            bundle.asset.source_path.replace(source)
            source.write_bytes(f"unique-source-{index}".encode())
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            bundle = replace(
                bundle,
                asset=replace(
                    bundle.asset, source_path=source.resolve(), media_id=digest, sha256=digest
                ),
            )
            write_manifest(bundle, SamplingParameters())
            await store.create_run(identifier, bundle.asset, CONFIG)
            await store.begin_stage(identifier, "media", bundle.asset.sha256)
            await store.persist_media_bundle(identifier, bundle)
            await store.begin_stage(identifier, "vision", bundle.asset.sha256)
            interval = SourceRange(100_000, 800_000, bundle.asset.duration_us)
            events = (
                (
                    replace(
                        event_fixture(bundle, identifier, f"event-{index}"),
                        observable_facts=("角色建造房屋",),
                        uncertainty=f"原不确定性 {index}",
                    ),
                )
                if index < 2
                else ()
            )
            segments = (
                (TranscriptSegment(bundle.asset.media_id, interval, "角色建造房屋"),)
                if index == 2
                else ()
            )
            await store.persist_timeline(identifier, "vision", events, segments, digest)
            await store.complete_run(identifier)
            bundles.append(bundle)
        return project, bundles
    finally:
        await store.close()


def snapshot(project):
    return {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in project.rglob("*")
        if p.is_file() and not p.name.endswith((".lock", "-wal", "-shm"))
    }


def forbidden(*args, **kwargs):
    pytest.fail("Project retrieval entered paid analysis or mutated a single-run retrieval.")


def test_cli_joint_record_preserves_three_origins_and_second_process_reads_fixed_ranks(
    tmp_path, monkeypatch
):
    async def scenario():
        project, _ = await completed_pool(tmp_path)
        before = snapshot(project)
        for name in ("LocalAsrProvider", "HttpxVisionTransport", "vision_for_run", "BudgetLedger"):
            monkeypatch.setattr(cli, name, forbidden)
        monkeypatch.setattr(SqliteTimelineStore, "persist_search", forbidden)
        monkeypatch.setattr(cli.LocalEmbeddingProvider, "from_manifest", forbidden)
        result = await cli.execute_project_search(
            project, ["run-2", "run-0", "run-1"], "建造房屋", tmp_path, mode="lexical"
        )
        assert len(result["sources"]) == len(result["candidates"]) == 3
        assert [item["rank"] for item in result["candidates"]] == [1, 2, 3]
        assert {item["runId"] for item in result["candidates"]} == {"run-0", "run-1", "run-2"}
        for item in result["candidates"]:
            assert item["uncertainty"] == (
                None if item["runId"] == "run-2" else "原不确定性 " + item["runId"][-1]
            )
            assert item["eventId"] == (
                None if item["runId"] == "run-2" else "event-" + item["runId"][-1]
            )
        assert read_project_search(project, result["searchId"]) == result
        assert all(snapshot(project)[path] == digest for path, digest in before.items())
        assert (
            result["modelAnalysisCalls"] == result["newReservations"] == 0
            and result["qualityGate"] is None
        )
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import json,sys;from pathlib import Path;from gamingcreator.infrastructure.project_search_files import read_project_search;print(json.dumps(read_project_search(Path(sys.argv[1]),sys.argv[2]),ensure_ascii=False))",
                str(project),
                result["searchId"],
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=os.environ | {"PYTHONUTF8": "1"},
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        assert child.returncode == 0 and json.loads(child.stdout) == result

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["pending", "source_bytes", "frame_bytes", "unknown_run"])
def test_unverified_source_refuses_before_model_or_output(tmp_path, monkeypatch, change):
    async def scenario():
        project, bundles = await completed_pool(tmp_path)
        ids = ["run-0", "run-1", "run-2"]
        if change == "pending":
            store = await SqliteTimelineStore.open(project)
            try:
                await store.create_run("pending", bundles[0].asset, CONFIG)
            finally:
                await store.close()
            ids.append("pending")
        elif change == "source_bytes":
            bundles[1].asset.source_path.write_bytes(b"changed source")
        elif change == "frame_bytes":
            bundles[1].images[0].path.write_bytes(b"changed frame")
        else:
            ids.append("missing")
        before = snapshot(project)
        monkeypatch.setattr(cli.LocalEmbeddingProvider, "from_manifest", forbidden)
        with pytest.raises(AppError):
            await cli.execute_project_search(project, ids, "建造房屋", tmp_path)
        assert snapshot(project) == before and not (project / "project-searches").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "override",
    [
        {"run_ids": []},
        {"run_ids": ["run", "run"]},
        {"run_ids": ["run"] * 101},
        {"query": " "},
        {"query": "x" * 4097},
        {"top_k": 101},
        {"top_k": True},
        {"min_similarity": float("nan")},
    ],
)
def test_invalid_cli_parameters_refuse_without_creating_project(tmp_path, override):
    values = {"run_ids": ["run"], "query": "building"} | override
    with pytest.raises(AppError):
        asyncio.run(cli.execute_project_search(tmp_path / "missing", repository=tmp_path, **values))
    assert not (tmp_path / "missing").exists()


def test_cli_parser_accepts_repeated_run_and_never_creates_absent_project(tmp_path, capsys):
    assert (
        cli.main(
            [
                "search-project",
                "building",
                "--project",
                str(tmp_path / "missing"),
                "--run",
                "a",
                "--run",
                "b",
                "--mode",
                "lexical",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["code"] == "input.project"


@pytest.mark.parametrize("damage", ["changed_result", "missing_receipt", "existing_record"])
def test_saved_record_is_exclusive_and_refuses_missing_or_changed_receipt(tmp_path, damage):
    async def scenario():
        project, _ = await completed_pool(tmp_path)
        result = await cli.execute_project_search(
            project, ["run-0", "run-1"], "建造房屋", tmp_path, mode="lexical"
        )
        directory = project / "project-searches" / result["searchId"]
        if damage == "changed_result":
            path = directory / "result.json"
            data = json.loads(path.read_bytes())
            data["query"] = "changed"
            path.write_text(json.dumps(data), encoding="utf-8")
        elif damage == "missing_receipt":
            (directory / "receipt.json").unlink()
        else:
            before = snapshot(project)
            with pytest.raises(AppError):
                write_project_search(project, result)
            assert snapshot(project) == before
            return
        with pytest.raises(AppError):
            read_project_search(project, result["searchId"])

    asyncio.run(scenario())
