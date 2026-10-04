import asyncio
import hashlib
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.retrieval import search_timeline
from gamingcreator.application.storage import RunConfiguration, RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import (
    Embedding,
    EmbeddingSpace,
    EvidenceReference,
    SemanticEvent,
    TranscriptSegment,
)
from gamingcreator.domain.time import SourceInstant, SourceRange

SPACE = EmbeddingSpace("fixture", "controlled-semantic-fixture", "fixed-test-only", 2, "l2")
META = InvocationMetadata(
    "fixture", "fixture", "fixture", "v1", "test", "embedding-v1", 1, ProviderUsage()
)


def timeline(events=None, transcripts=()):
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
        for index in range(10)
    )
    evidence += (
        EvidenceReference(
            "run:audio",
            "media",
            "audio",
            SourceRange(0, asset.duration_us, asset.duration_us),
            Path("audio.wav"),
            "a" * 64,
            "fixture",
        ),
    )
    if events is None:
        events = (
            event("jump", 0, 1, "角色跳跃到平台", "jump"),
            event("build", 3, 4, "player assembles a shelter", "construction"),
        )
    return StoredTimeline(run, (), evidence, transcripts, events, ())


def event(identifier, start, end, facts, tag):
    return SemanticEvent(
        identifier,
        "media",
        "run",
        SourceRange(start * 1_000_000, end * 1_000_000, 10_000_000),
        (facts,),
        (tag,),
        (f"run:image:{start}",),
        "visual",
        None,
    )


class SynonymFixture:
    """Explicit semantic fixture: does not claim to be a real embedding model."""

    async def embed(self, request, context):
        result = []
        for index, text in enumerate(request.texts):
            build = any(
                term in text
                for term in ("build a home", "assembles a shelter", "construction", "建造房屋")
            )
            vector = (1.0, 0.0) if build else (0.0, 1.0)
            result.append(
                Embedding(
                    f"{request.run_id}:{index}",
                    SPACE,
                    vector,
                    hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        return ProviderResult(ProviderStatus.COMPLETED, tuple(result), META)


def search(data, query, **kwargs):
    return asyncio.run(search_timeline(data, query, **kwargs))


def test_chinese_bigrams_and_english_word_baseline():
    assert (
        search(timeline(), "帮我找角色跳跃的视频片段", mode="lexical").candidates[0].event_id
        == "jump"
    )
    assert (
        search(timeline(), "show construction clip", mode="lexical").candidates[0].event_id
        == "build"
    )


def test_semantic_synonym_comparison_has_evidence_and_identity():
    assert search(timeline(), "build a home", mode="lexical").candidates == ()
    result = search(
        timeline(), "build a home", mode="semantic", embedding_provider=SynonymFixture()
    )
    candidate = result.candidates[0]
    assert candidate.event_id == "build"
    assert candidate.source_range == SourceRange(3_000_000, 4_000_000, 10_000_000)
    assert candidate.evidence_ids == ("run:image:3",)
    assert candidate.score_kind == "cosine"
    assert "not probability" in candidate.why
    assert result.embedding_metadata == META
    assert {item.subject_id for item in result.event_embeddings} == {"jump", "build"}
    build_embedding = next(item for item in result.event_embeddings if item.subject_id == "build")
    assert (
        build_embedding.text_hash
        == hashlib.sha256(b"passage: player assembles a shelter\nconstruction").hexdigest()
    )


def test_database_embedding_exports_exclude_query_and_transcript_subjects():
    segment = TranscriptSegment(
        "media", SourceRange(7_000_000, 8_000_000, 10_000_000), "打开角色背包"
    )
    result = search(
        timeline(transcripts=(segment,)), "construction", embedding_provider=SynonymFixture()
    )
    assert len(result.event_embeddings) == 2
    assert {item.subject_id for item in result.event_embeddings} == {"jump", "build"}


def test_hybrid_retains_lexical_and_semantic_signals_without_padding():
    result = search(timeline(), "construction", embedding_provider=SynonymFixture())
    assert len(result.candidates) == 1
    assert result.candidates[0].score_kind == "rrf-bm25-cosine"
    assert "BM25=" in result.candidates[0].why and "cosine=" in result.candidates[0].why


@pytest.mark.parametrize("query", ["", "  ", "!!!", "show me the clip"])
def test_empty_or_only_fillers_returns_no_candidates(query):
    assert search(timeline(), query).candidates == ()


def test_negative_lexical_query_returns_empty():
    assert search(timeline(), "spaceship laser trading", mode="lexical").candidates == ()


def test_negative_semantic_query_below_cutoff_does_not_pad_results():
    class Orthogonal(SynonymFixture):
        async def embed(self, request, context):
            result = await super().embed(request, context)
            output = tuple(
                replace(item, vector=(1.0, 0.0) if index == 0 else (0.0, 1.0))
                for index, item in enumerate(result.output)
            )
            return replace(result, output=output)

    assert (
        search(
            timeline(), "spaceship laser trading", mode="semantic", embedding_provider=Orthogonal()
        ).candidates
        == ()
    )


def test_ambiguous_high_cosines_abstain_in_hybrid_and_remain_visible_in_baseline():
    class Ambiguous(SynonymFixture):
        async def embed(self, request, context):
            result = await super().embed(request, context)
            output = [replace(result.output[0], vector=(1.0, 0.0))]
            for index, item in enumerate(result.output[1:]):
                value = 0.85 - index * 0.01
                output.append(replace(item, vector=(value, (1 - value * value) ** 0.5)))
            return replace(result, output=tuple(output))

    hybrid = search(timeline(), "spaceship laser", embedding_provider=Ambiguous())
    assert hybrid.candidates == ()
    assert hybrid.abstention_reason == "semantic_ambiguity_without_lexical_anchor"
    baseline = search(
        timeline(), "spaceship laser", mode="semantic", embedding_provider=Ambiguous()
    )
    assert len(baseline.candidates) == 2


def test_generic_player_word_is_not_a_relevance_anchor():
    assert search(timeline(), "player spaceship laser", mode="lexical").candidates == ()


def test_independent_same_description_does_not_trigger_ambiguous_tie_abstention():
    events = tuple(
        event(
            f"build-{index}", index * 2, index * 2 + 1, "player assembles a shelter", "construction"
        )
        for index in range(5)
    )
    result = search(timeline(events), "build a home", embedding_provider=SynonymFixture())
    assert len(result.candidates) == 5
    assert result.abstention_reason is None


def test_hybrid_semantic_tail_window_keeps_best_ties_and_retains_lexical_hits():
    class Tail(SynonymFixture):
        async def embed(self, request, context):
            result = await super().embed(request, context)
            output = [replace(result.output[0], vector=(1.0, 0.0))]
            for index, item in enumerate(result.output[1:]):
                value = 0.95 if index == 0 else 0.82
                output.append(replace(item, vector=(value, (1 - value * value) ** 0.5)))
            return replace(result, output=tuple(output))

    unanchored = search(timeline(), "spaceship laser", embedding_provider=Tail())
    assert [item.event_id for item in unanchored.candidates] == ["jump"]
    anchored = search(timeline(), "construction", embedding_provider=Tail())
    assert {item.event_id for item in anchored.candidates} == {"jump", "build"}
    assert (
        len(
            search(
                timeline(), "spaceship laser", mode="semantic", embedding_provider=Tail()
            ).candidates
        )
        == 2
    )


def test_empty_timeline_needs_no_embedding_model():
    assert search(timeline(()), "跳跃").candidates == ()


def test_missing_semantic_model_is_explicit():
    with pytest.raises(AppError) as error:
        search(timeline(), "跳跃")
    assert error.value.code == "retrieval.embedding_missing"


def test_stable_tie_order_ignores_input_order():
    first, second = event("z", 0, 1, "jump", "jump"), event("a", 4, 5, "jump", "jump")
    left = search(timeline((first, second)), "jump", mode="lexical")
    right = search(timeline((second, first)), "jump", mode="lexical")
    assert left.candidates == right.candidates
    assert [item.event_id for item in left.candidates] == ["z", "a"]


def test_overlapping_same_action_deduplicates_but_separate_actions_survive():
    events = (
        event("a", 0, 2, "角色跳跃到平台", "jump"),
        event("b", 1, 3, "角色跳跃到平台", "jump"),
        event("c", 5, 6, "角色跳跃到平台", "jump"),
    )
    candidates = search(timeline(events), "角色跳跃", mode="lexical").candidates
    assert len(candidates) == 2
    assert {item.event_id for item in candidates} == {"a", "c"}


def test_overlapping_distinct_mechanics_are_not_duplicates():
    events = (
        event("a", 0, 2, "player build shelter", "build"),
        event("b", 1, 3, "player chop tree", "chop"),
    )
    assert len(search(timeline(events), "build chop", mode="lexical").candidates) == 2


def test_transcript_candidate_has_audio_evidence_and_no_fabricated_event():
    segment = TranscriptSegment(
        "media", SourceRange(7_000_000, 8_000_000, 10_000_000), "打开角色背包"
    )
    result = search(timeline(transcripts=(segment,)), "角色背包", mode="lexical")
    assert result.candidates[0].event_id is None
    assert result.candidates[0].evidence_ids == ("run:audio",)


def test_transcript_is_folded_into_overlapping_visual_event():
    segment = TranscriptSegment("media", SourceRange(0, 1_000_000, 10_000_000), "按键释放连击技能")
    result = search(timeline(transcripts=(segment,)), "连击技能", mode="lexical")
    assert len(result.candidates) == 1 and result.candidates[0].event_id == "jump"


@pytest.mark.parametrize("status", [RunStatus.RUNNING, RunStatus.FAILED, RunStatus.INTERRUPTED])
def test_unfinished_run_refused(status):
    data = timeline()
    with pytest.raises(AppError, match="已完成"):
        search(replace(data, run=replace(data.run, status=status)), "jump", mode="lexical")


@pytest.mark.parametrize("change", ["run", "media", "evidence", "time"])
def test_cross_run_media_or_evidence_refused(change):
    data = timeline()
    invalid = data.events[0]
    if change == "run":
        invalid = replace(invalid, run_id="other")
    elif change == "media":
        invalid = replace(invalid, media_id="other")
    elif change == "evidence":
        invalid = replace(invalid, evidence_ids=("other:image:0",))
    else:
        invalid = replace(invalid, source_range=SourceRange(8_000_000, 9_000_000, 10_000_000))
    with pytest.raises(AppError) as error:
        search(replace(data, events=(invalid,)), "jump", mode="lexical")
    assert error.value.code == "retrieval.timeline_invalid"


@pytest.mark.parametrize("kind", ["space", "hash", "subject", "count", "zero"])
def test_bad_embedding_association_is_refused(kind):
    class Broken(SynonymFixture):
        async def embed(self, request, context):
            result = await super().embed(request, context)
            vectors = list(result.output)
            if kind == "space":
                vectors[-1] = replace(vectors[-1], space=replace(SPACE, revision_scope="different"))
            elif kind == "hash":
                vectors[-1] = replace(vectors[-1], text_hash="wrong")
            elif kind == "subject":
                vectors[-1] = replace(vectors[-1], subject_id="other:1")
            elif kind == "count":
                vectors.pop()
            else:
                vectors[-1] = replace(vectors[-1], vector=(0.0, 0.0))
            return replace(result, output=tuple(vectors))

    with pytest.raises(AppError) as error:
        search(timeline(), "construction", embedding_provider=Broken())
    assert error.value.code == "retrieval.embedding_invalid"


def test_context_cancellation_propagates_before_model_call():
    context = CancellationContext("run", 1)
    context.cancelled.set()
    with pytest.raises(asyncio.CancelledError):
        search(timeline(), "construction", mode="lexical", context=context)


def test_provider_cancelling_context_cannot_return_success():
    class Cancelling(SynonymFixture):
        async def embed(self, request, context):
            result = await super().embed(request, context)
            context.cancelled.set()
            return result

    with pytest.raises(asyncio.CancelledError):
        search(
            timeline(),
            "construction",
            context=CancellationContext("run", 1),
            embedding_provider=Cancelling(),
        )


@pytest.mark.parametrize(
    "options",
    [
        {"top_k": 0},
        {"top_k": True},
        {"mode": "other"},
        {"min_similarity": float("nan")},
        {"min_similarity": True},
    ],
)
def test_invalid_configuration_refused(options):
    with pytest.raises(AppError):
        search(timeline(), "construction", **options)
