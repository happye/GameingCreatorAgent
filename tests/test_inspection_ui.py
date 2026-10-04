import asyncio
import hashlib

from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.providers import (
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.models import Embedding, EmbeddingSpace, SemanticEvent
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.service import inspect_run

SPACE = EmbeddingSpace("fixture", "controlled-semantic-fixture", "fixed-test-only", 2, "l2")
DIGEST = "b" * 64


def _event(bundle, run_id, event_id, start, end, facts, tag):
    return SemanticEvent(
        event_id,
        bundle.asset.media_id,
        run_id,
        SourceRange(start, end, bundle.asset.duration_us),
        (facts,),
        (tag,),
        (bundle.images[0].evidence_id,),
        "visual",
        None,
    )


async def _media(store, bundle, run_id):
    await store.create_run(run_id, bundle.asset, CONFIG)
    await store.begin_stage(run_id, "media", bundle.asset.sha256)
    await store.persist_media_bundle(run_id, bundle)


class _Ambiguous:
    space = SPACE

    async def embed(self, request, context):
        output = []
        for index, text in enumerate(request.texts):
            value = 1.0 if index == 0 else 0.85 - (index - 1) * 0.01
            output.append(
                Embedding(
                    f"{request.run_id}:{index}",
                    SPACE,
                    (value, (1 - value * value) ** 0.5),
                    hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        return ProviderResult(
            ProviderStatus.COMPLETED,
            tuple(output),
            InvocationMetadata(
                "fixture", "fixture", "fixture", "v1", "test", "embedding-v1", 1, ProviderUsage()
            ),
        )


def test_surface_read_aligns_rank_time_and_a_later_store_event(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "gamingcreator.cli.main.LocalEmbeddingProvider.from_manifest",
        lambda repository: _Ambiguous(),
    )

    async def scenario():
        search_root = tmp_path / "search"
        search_root.mkdir()
        search_bundle = bundle_fixture(search_root, "run-search")
        search_project = search_root / "project"
        early = _event(
            search_bundle,
            "run-search",
            "early",
            0,
            150_000,
            "画面左侧先出现大量环境描述",
            "环境",
        )
        late = _event(search_bundle, "run-search", "late", 100_000, 900_000, "角色攻击", "攻击")
        store = await SqliteTimelineStore.open(search_project)
        try:
            await _media(store, search_bundle, "run-search")
            await store.begin_stage("run-search", "vision", DIGEST)
            await store.persist_timeline(
                "run-search", "vision", (early, late), (), hashlib.sha256(b"both").hexdigest()
            )
            await store.complete_run("run-search")
        finally:
            await store.close()

        english = await inspect_run(
            search_project,
            "run-search",
            "Find clips of fighters attacking each other in the arena",
            tmp_path,
        )
        repair = await inspect_run(
            search_project,
            "run-search",
            "汽车修理工拆卸发动机维修车辆",
            tmp_path,
        )
        stored = {event.event_id: event for event in (early, late)}
        assert any(row["evidenceIds"] and row["observableFacts"] for row in english["candidates"])
        assert repair["candidates"] == []
        assert repair["abstentionReason"] == "semantic_ambiguity_without_lexical_anchor"
        for row in english["candidates"]:
            event = stored[row["eventId"]]
            assert row["startUs"] == event.source_range.start_us
            assert row["endUs"] == event.source_range.end_us
            assert tuple(row["evidenceIds"]) == event.evidence_ids
        starts = [row["startUs"] for row in english["timeline"]]
        assert starts == sorted(starts)
        rank_key = [
            (-row["score"], row["startUs"], row["eventId"]) for row in english["candidates"]
        ]
        assert rank_key == sorted(rank_key)
        assert [row["startUs"] for row in english["candidates"]] != starts[
            : len(english["candidates"])
        ]

        open_root = tmp_path / "open"
        open_root.mkdir()
        open_bundle = bundle_fixture(open_root, "run-open")
        open_project = open_root / "project"
        first = _event(open_bundle, "run-open", "first", 0, 150_000, "第一段已完成窗口", "窗口")
        second = _event(
            open_bundle, "run-open", "second", 100_000, 900_000, "第二段新写入窗口", "窗口"
        )
        writer = await SqliteTimelineStore.open(open_project)
        try:
            await _media(writer, open_bundle, "run-open")
            await writer.begin_stage("run-open", "vision-000000", DIGEST)
            await writer.persist_timeline(
                "run-open",
                "vision-000000",
                (first,),
                (),
                hashlib.sha256(b"first").hexdigest(),
            )
            seen = await inspect_run(open_project, "run-open", "", tmp_path)
            assert [row["eventId"] for row in seen["timeline"]] == ["first"]
            await writer.begin_stage("run-open", "vision-000001", DIGEST)
            await writer.persist_timeline(
                "run-open",
                "vision-000001",
                (second,),
                (),
                hashlib.sha256(b"second").hexdigest(),
            )
            again = await inspect_run(open_project, "run-open", "", tmp_path)
        finally:
            await writer.close()
        assert [
            (row["eventId"], row["observableFacts"], row["evidenceIds"])
            for row in again["timeline"]
        ] == [
            ("first", ["第一段已完成窗口"], [open_bundle.images[0].evidence_id]),
            ("second", ["第二段新写入窗口"], [open_bundle.images[0].evidence_id]),
        ]
        assert not (open_project / "runs" / "run-open" / "semantic_timeline.json").exists()
        print(
            "ENGLISH_HIT",
            [
                (row["startUs"], row["endUs"], row["observableFacts"], row["evidenceIds"])
                for row in english["candidates"]
            ],
        )
        print("CAR_REPAIR_CANDIDATES", repair["candidates"])
        print("SOURCE_TIME", [row["startUs"] for row in english["timeline"]])
        print(
            "RANK_ORDER",
            [(row["score"], row["startUs"], row["eventId"]) for row in english["candidates"]],
        )
        print(
            "SECOND_READ",
            [
                (row["eventId"], row["startUs"], row["observableFacts"], row["evidenceIds"])
                for row in again["timeline"]
            ],
        )

    asyncio.run(scenario())
