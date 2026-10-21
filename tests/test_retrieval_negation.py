"""Explicit action-denial behavior; fixtures do not establish model quality."""

import asyncio
import hashlib
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.providers import (
    CancellationContext,
    EmbeddingRequest,
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.retrieval import RetrievalMode, SearchResult, search_timeline
from gamingcreator.application.storage import RunConfiguration, RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import (
    Embedding,
    EmbeddingSpace,
    EvidenceReference,
    SemanticEvent,
    TranscriptSegment,
)
from gamingcreator.domain.time import SourceInstant, SourceRange

SPACE = EmbeddingSpace("fixture", "negation-fixture", "fixed-test-only", 2, "l2")
META = InvocationMetadata(
    "fixture", "fixture", "fixture", "v1", "test", "embedding-v1", 1, ProviderUsage()
)


def timeline(*facts: str) -> StoredTimeline:
    asset = MediaAsset(
        "media",
        Path("source.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1_000_000), 0, 10_000_000),),
        Fraction(0),
        10_000_000,
        "fixture",
    )
    config = RunConfiguration(
        AnalysisConfig("fixture", "fixture", 10, 10), Decimal("1"), "fixture", "a" * 64
    )
    run = StoredRun("run", asset, config, "a" * 64, RunStatus.COMPLETED, None)
    evidence = tuple(
        EvidenceReference(
            f"run:image:{index}",
            "media",
            "image",
            SourceInstant(index * 1_000_000 + 100_000, asset.duration_us),
            Path(f"{index}.jpg"),
            "a" * 64,
            "fixture",
        )
        for index in range(len(facts))
    )
    events = tuple(
        SemanticEvent(
            f"event-{index}",
            "media",
            "run",
            SourceRange(index * 1_000_000, (index + 1) * 1_000_000, asset.duration_us),
            (fact,),
            (),
            (f"run:image:{index}",),
            "visual",
            None,
        )
        for index, fact in enumerate(facts)
    )
    return StoredTimeline(run, (), evidence, (), events, ())


class EqualSimilarity:
    """Deliberately adversarial semantic fixture: every description scores 1.0."""

    async def embed(
        self, request: EmbeddingRequest, context: CancellationContext
    ) -> ProviderResult[tuple[Embedding, ...]]:
        return ProviderResult(
            ProviderStatus.COMPLETED,
            tuple(
                Embedding(
                    f"{request.run_id}:{index}",
                    SPACE,
                    (1.0, 0.0),
                    hashlib.sha256(text.encode("utf-8")).hexdigest(),
                )
                for index, text in enumerate(request.texts)
            ),
            META,
        )


def search(data: StoredTimeline, query: str, mode: RetrievalMode) -> SearchResult:
    return asyncio.run(
        search_timeline(data, query, mode=mode, embedding_provider=EqualSimilarity())
    )


@pytest.mark.parametrize("mode", ["lexical", "hybrid", "semantic"])
@pytest.mark.parametrize(
    ("query", "denial", "positive"),
    [
        (
            "寻找跳跃玩法的片段",
            "角色聚集在中央，但无明确攻击、跳跃或交互动作。",
            "角色跳跃并落地。",
        ),
        (
            "jumping",
            "No clear attacks, jumps or interactions are visible.",
            "The character is jumping onto a ledge.",
        ),
        ("shooting", "There is no shooting or jumping.", "The player is shooting at a target."),
        ("attacking", "The character does not attack.", "The character is attacking an enemy."),
        ("jump", "The character doesn't jump.", "The character can jump onto a platform."),
        ("jump", "The character does not visibly jump.", "The character starts to jump."),
    ],
)
def test_denied_action_cannot_supply_positive_hit(
    mode: RetrievalMode, query: str, denial: str, positive: str
) -> None:
    result = search(timeline(denial, positive), query, mode)
    assert [item.event_id for item in result.candidates] == ["event-1"]
    assert result.retrieval_version == "bm25-e5-rrf-v7"


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    ("query", "fact"),
    [
        ("跳跃", "未见射击，随后角色跳跃落地。"),
        ("跳跃", "没有跳跃或攻击，随后角色起跳并落地。"),
        ("jumps", "No jumps are visible at first, then the character jumps onto a ledge."),
        ("jumping", "The character is not shooting but is jumping."),
        ("jump attacks", "No jumps are visible, but the character attacks."),
    ],
)
def test_affirmative_clause_survives_other_denials(
    mode: RetrievalMode, query: str, fact: str
) -> None:
    assert [item.event_id for item in search(timeline(fact), query, mode).candidates] == ["event-0"]


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    ("query", "fact"),
    [
        ("跳跃", "可能没有跳跃，动作被特效遮挡。"),
        ("跳跃", "可能并没有跳跃，动作被特效遮挡。"),
        ("跳跃", "无法确认是否没有跳跃。"),
        ("跳跃", "无法确定有没有跳跃。"),
        ("跳跃", "并非没有跳跃。"),
        ("跳跃", "未必没有跳跃。"),
        ("跳跃", "无法确认是否发生跳跃。"),
        ("jumps", "There may be no jumps; the view is obstructed."),
        ("jumps", "It is not without jumps."),
    ],
)
def test_uncertain_or_double_negative_language_is_not_excluded(
    mode: RetrievalMode, query: str, fact: str
) -> None:
    assert search(timeline(fact), query, mode).candidates


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    ("query", "fact"),
    [
        ("没有跳跃的片段", "场景没有跳跃动作。"),
        ("未见跳跃", "无明确跳跃动作。"),
        ("without jumping", "There is no jumping."),
        ("no jump", "The character does not jump."),
        ("exclude jumping", "The character is not jumping."),
    ],
)
def test_absence_intent_does_not_apply_positive_action_guard(
    mode: RetrievalMode, query: str, fact: str
) -> None:
    # This preserves previous ranking, rather than claiming absence-query understanding.
    assert search(timeline(fact), query, mode).candidates


@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
@pytest.mark.parametrize(
    ("query", "fact"),
    [
        ("场地中央", "角色聚集在场地中央，无明确攻击、跳跃或交互动作。"),
        ("arena", "Characters gather in the arena without jumping."),
        ("a shot of the arena", "The arena is visible with no shooting."),
    ],
)
def test_non_action_query_keeps_same_event(mode: RetrievalMode, query: str, fact: str) -> None:
    assert search(timeline(fact), query, mode).candidates


def test_semantic_passage_identity_keeps_denied_facts_and_all_event_exports() -> None:
    facts = ("无明确跳跃动作。", "角色跳跃到平台。", "角色打开背包。")
    result = search(timeline(*facts), "跳跃", "hybrid")
    assert "event-0" not in {item.event_id for item in result.candidates}
    assert {item.subject_id for item in result.event_embeddings} == {
        "event-0",
        "event-1",
        "event-2",
    }
    assert {item.text_hash for item in result.event_embeddings} == {
        hashlib.sha256(f"passage: {fact}".encode()).hexdigest() for fact in facts
    }
    assert result.min_similarity == 0.80
    assert result.min_semantic_margin == 0.02


def test_unknown_generic_description_is_not_blanket_filtered_for_action_query() -> None:
    result = search(timeline("角色跳跃到平台。", "角色打开背包。"), "跳跃", "hybrid")
    assert {item.event_id for item in result.candidates} == {"event-0", "event-1"}


@pytest.mark.parametrize("mode", ["lexical", "hybrid", "semantic"])
@pytest.mark.parametrize(
    "fact",
    ["无明确攻击、跳跃或交互动作。", "没有攻击和跳跃。", "未见跳跃。", "No evidence of jumping."],
)
def test_only_denied_evidence_returns_empty(mode: RetrievalMode, fact: str) -> None:
    query = "jumping" if fact.isascii() else "跳跃"
    assert search(timeline(fact), query, mode).candidates == ()


def timeline_with_tags(*rows: tuple[str, tuple[str, ...]]) -> StoredTimeline:
    """Each row is (observable_fact, mechanic_tags)."""
    facts = tuple(row[0] for row in rows)
    base = timeline(*facts)
    events = tuple(
        SemanticEvent(
            event.event_id,
            event.media_id,
            event.run_id,
            event.source_range,
            event.observable_facts,
            tags,
            event.evidence_ids,
            event.modality,
            event.uncertainty,
        )
        for event, (_fact, tags) in zip(base.events, rows, strict=True)
    )
    return StoredTimeline(base.run, base.checkpoints, base.evidence, base.transcripts, events, base.invocations)


def test_bare_mechanic_tags_cannot_defeat_explicit_fact_denial():
    """TD010: exclusive fact denial stays excluded even if mechanicTags echo the action."""
    result = asyncio.run(
        search_timeline(
            timeline_with_tags(
                ("没有跳跃，角色站在原地。", ("jump",)),
                ("角色完成一次跳跃。", ()),
            ),
            "角色跳跃",
            mode="hybrid",
            embedding_provider=EqualSimilarity(),
            top_k=5,
        )
    )
    assert isinstance(result, SearchResult)
    event_ids = [item.event_id for item in result.candidates]
    assert "event-0" not in event_ids
    assert "event-1" in event_ids



def timeline_db_shaped(
    rows: list[dict],
) -> StoredTimeline:
    """Build a Completed-timeline-shaped fixture (facts/tags/transcripts) without a live DB."""
    count = max(len(rows), 1)
    asset = MediaAsset(
        "media",
        Path("source.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1_000_000), 0, count * 1_000_000),),
        Fraction(0),
        count * 1_000_000,
        "fixture",
    )
    config = RunConfiguration(
        AnalysisConfig("fixture", "fixture", 10, 10), Decimal("1"), "fixture", "a" * 64
    )
    run = StoredRun("run", asset, config, "a" * 64, RunStatus.COMPLETED, None)
    evidence = tuple(
        EvidenceReference(
            f"run:image:{index}",
            "media",
            "image",
            SourceInstant(index * 1_000_000 + 100_000, asset.duration_us),
            Path(f"{index}.jpg"),
            "a" * 64,
            "fixture",
        )
        for index in range(len(rows))
    )
    events = []
    transcripts = []
    for index, row in enumerate(rows):
        facts = tuple(row.get("facts") or ())
        tags = tuple(row.get("tags") or ())
        # Empty-fact events still need a searchable document when tags exist.
        if not facts and not tags and not row.get("transcript"):
            facts = ("（空观察）",)
        events.append(
            SemanticEvent(
                f"event-{index}",
                "media",
                "run",
                SourceRange(index * 1_000_000, (index + 1) * 1_000_000, asset.duration_us),
                facts,
                tags,
                (f"run:image:{index}",),
                "visual",
                None,
            )
        )
        transcript = row.get("transcript")
        if transcript:
            transcripts.append(
                TranscriptSegment(
                    "media",
                    SourceRange(index * 1_000_000, (index + 1) * 1_000_000, asset.duration_us),
                    transcript,
                )
            )
    return StoredTimeline(
        run, (), evidence, tuple(transcripts), tuple(events), ()
    )


def test_tags_only_event_remains_searchable_without_fact_fallback():
    """TD010: empty facts + mechanicTags must not reintroduce tags into positive_text."""
    data = timeline_db_shaped([{"facts": [], "tags": ["jump"]}])
    # positive_text must stay empty so denial never scans tags; lexical still uses text.
    from gamingcreator.application.retrieval import _documents

    docs = _documents(data)
    assert len(docs) == 1
    assert docs[0].positive_text == ""
    assert "jump" in docs[0].text.casefold()
    result = search(data, "jump", "hybrid")
    assert [item.event_id for item in result.candidates] == ["event-0"]


def test_denied_action_does_not_block_other_action_tag_hit():
    """Denial of jump must not exclude the same clip from an attack query."""
    data = timeline_with_tags(
        ("没有跳跃，角色站在原地。", ("attack",)),
        ("角色发动一次攻击。", ()),
    )
    result = search(data, "攻击", "hybrid")
    ids = {item.event_id for item in result.candidates}
    assert "event-0" in ids
    assert "event-1" in ids


def test_transcript_affirmative_defeats_fact_denial_despite_echo_tag():
    """Mixed channel: transcript affirmation in positive_text keeps the clip."""
    data = timeline_db_shaped(
        [
            {
                "facts": ["没有跳跃。"],
                "tags": ["jump"],
                "transcript": "随后角色起跳并落地。",
            }
        ]
    )
    result = search(data, "跳跃", "hybrid")
    assert [item.event_id for item in result.candidates] == ["event-0"]


def test_fact_and_transcript_both_deny_keeps_exclusion_despite_tag():
    data = timeline_db_shaped(
        [
            {
                "facts": ["没有跳跃。"],
                "tags": ["jump"],
                "transcript": "画面未见跳跃动作。",
            },
            {"facts": ["角色跳跃到平台。"], "tags": []},
        ]
    )
    result = search(data, "跳跃", "hybrid")
    ids = [item.event_id for item in result.candidates]
    assert "event-0" not in ids
    assert "event-1" in ids


def test_td010_mixed_semantics_golden_shapes():
    """Offline DB-shaped对照: golden JSON drives include/exclude expectations."""
    import json

    payload = json.loads(
        Path("tests/fixtures/td010_mixed_semantics_shapes.json").read_text(encoding="utf-8-sig")
    )
    for case in payload["cases"]:
        data = timeline_db_shaped(case["events"])
        result = search(data, case["query"], "hybrid")
        got = {item.event_id for item in result.candidates}
        for index, event in enumerate(case["events"]):
            event_id = f"event-{index}"
            if event["expect"] == "excluded":
                assert event_id not in got, case["id"]
            else:
                assert event_id in got, case["id"]
