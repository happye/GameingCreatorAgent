"""Persist real transcript candidates and never upgrade unverified billing evidence."""

import asyncio
import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.providers import (
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.storage import InvocationStatus
from gamingcreator.cli.main import execute_benchmark, execute_search
from gamingcreator.domain.models import Embedding, EmbeddingSpace, SemanticEvent, TranscriptSegment
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.local_embeddings import LocalEmbeddingProvider
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def audio_project(root: Path, *, unverified_cost: bool = False):
    bundle = bundle_fixture(root, audio=True)
    project = root / "project"
    store = await SqliteTimelineStore.open(project)
    try:
        await store.create_run("run-1", bundle.asset, CONFIG)
        await store.begin_stage("run-1", "media", bundle.asset.sha256)
        await store.persist_media_bundle("run-1", bundle)
        await store.begin_stage("run-1", "vision", bundle.asset.sha256)
        if unverified_cost:
            opening = InvocationMetadata(
                "deepseek", "deepseek-flash", None, None, "fixture", "fixture", 1, ProviderUsage()
            )
            await store.begin_invocation("attempt-1", "run-1", "vision", "logical-1", opening)
            await store.finish_invocation(
                "attempt-1",
                InvocationStatus.COMPLETED,
                replace(
                    opening,
                    usage=ProviderUsage(
                        original_cost=Decimal(1), currency="CNY", cost_cny=Decimal(1)
                    ),
                ),
            )
        segment = TranscriptSegment(
            bundle.asset.media_id,
            SourceRange(100_000, 500_000, bundle.asset.duration_us),
            "玩家正在开启设置菜单",
        )
        await store.persist_timeline(
            "run-1", "vision", (), (segment,), hashlib.sha256(b"audio").hexdigest()
        )
        await store.complete_run("run-1")
    finally:
        await store.close()
    return bundle, project


def test_audio_search_has_nullable_event_and_round_trips_storage(tmp_path):
    async def scenario():
        _, project = await audio_project(tmp_path)
        result = await execute_search(project, "run-1", "开启设置菜单", tmp_path, mode="lexical")
        assert len(result["candidates"]) == 1
        candidate = result["candidates"][0]
        assert candidate["eventId"] is None
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            reloaded = await store.load_retrieval(result["retrievalId"])
            assert reloaded["hits"][0]["event_id"] is None
            assert reloaded["hits"][0]["candidate_id"] == candidate["candidateId"]
            assert reloaded["hits"][0]["evidence_ids"] == tuple(candidate["evidenceIds"])
            assert not (await store.load_completed_timeline("run-1")).events
        finally:
            await store.close()

    asyncio.run(scenario())


def test_shipped_hybrid_search_finds_english_attack_and_abstains_on_repair(tmp_path, monkeypatch):
    fixture_space = EmbeddingSpace(
        "fixture", "controlled-semantic-fixture", "fixed-test-only", 2, "l2"
    )

    class Ambiguous:
        space = fixture_space

        async def embed(self, request, context):
            output = []
            for index, text in enumerate(request.texts):
                value = 1.0 if index == 0 else 0.85 - (index - 1) * 0.01
                output.append(
                    Embedding(
                        f"{request.run_id}:{index}",
                        fixture_space,
                        (value, (1 - value * value) ** 0.5),
                        hashlib.sha256(text.encode()).hexdigest(),
                    )
                )
            return ProviderResult(
                ProviderStatus.COMPLETED,
                tuple(output),
                InvocationMetadata(
                    "fixture",
                    "fixture",
                    "fixture",
                    "v1",
                    "test",
                    "embedding-v1",
                    1,
                    ProviderUsage(),
                ),
            )

    monkeypatch.setattr(
        LocalEmbeddingProvider,
        "from_manifest",
        staticmethod(lambda repository: Ambiguous()),
    )

    async def scenario():
        bundle = bundle_fixture(tmp_path)
        project = tmp_path / "project"
        attack = SemanticEvent(
            "strike",
            bundle.asset.media_id,
            "run-1",
            SourceRange(0, 800_000, bundle.asset.duration_us),
            ("角色发出攻击并造成伤害",),
            ("攻击",),
            (bundle.images[0].evidence_id,),
            "visual",
            None,
        )
        menu = SemanticEvent(
            "menu",
            bundle.asset.media_id,
            "run-1",
            SourceRange(100_000, 1_500_000, bundle.asset.duration_us),
            ("画面打开游戏设置菜单",),
            ("菜单",),
            (bundle.images[0].evidence_id,),
            "visual",
            None,
        )
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-1", bundle.asset, CONFIG)
            await store.begin_stage("run-1", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-1", bundle)
            await store.begin_stage("run-1", "vision", bundle.asset.sha256)
            await store.persist_timeline(
                "run-1",
                "vision",
                (attack, menu),
                (),
                hashlib.sha256(b"events").hexdigest(),
            )
            await store.complete_run("run-1")
        finally:
            await store.close()
        english = await execute_search(
            project,
            "run-1",
            "Find clips of fighters attacking each other in the arena",
            tmp_path,
        )
        repair = await execute_search(project, "run-1", "汽车修理工拆卸发动机维修车辆", tmp_path)
        assert any(
            item["eventId"] == "strike" and item["evidenceIds"] and item["observableFacts"]
            for item in english["candidates"]
        )
        assert repair["candidates"] == []
        assert repair["abstentionReason"] == "semantic_ambiguity_without_lexical_anchor"

    asyncio.run(scenario())


def test_benchmark_cannot_promote_an_unverified_nonempty_cost(tmp_path):
    async def scenario():
        bundle, project = await audio_project(tmp_path, unverified_cost=True)
        manifest = {
            "schemaVersion": 1,
            "datasetId": "development-fixture",
            "labelVersion": None,
            "humanLabels": {
                "confirmed": False,
                "annotators": [],
                "reviewed": False,
                "frozenAt": None,
                "independentTestSet": False,
            },
            "media": [
                {
                    "mediaId": bundle.asset.media_id,
                    "runId": "run-1",
                    "sha256": bundle.asset.sha256,
                    "durationUs": bundle.asset.duration_us,
                }
            ],
            "queries": [
                {
                    "id": "unlabelled",
                    "text": "开启设置菜单",
                    "kind": "main",
                    "mediaId": bundle.asset.media_id,
                    "runId": "run-1",
                    "referenceEvents": [],
                    "candidateLabels": [],
                }
            ],
        }
        input_path, output_path = tmp_path / "labels.json", tmp_path / "report.json"
        input_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = await execute_benchmark(project, input_path, output_path, tmp_path, mode="lexical")
        assert report["qualityGate"] is None and report["mediaVerified"] is True
        assert report["cost"]["status"] == "unverified"
        assert report["cost"]["coldCny"] is None
        assert report["cost"]["coldCostGateUnder5CnyPerHour"] is None
        assert output_path.is_file()

    asyncio.run(scenario())
