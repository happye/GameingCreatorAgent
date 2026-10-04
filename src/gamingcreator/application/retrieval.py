"""Deterministic evidence-backed lexical and local semantic clip retrieval."""

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from typing import Literal

from gamingcreator.application.providers import (
    CancellationContext,
    EmbeddingProvider,
    EmbeddingRequest,
    InvocationMetadata,
    ProviderStatus,
)
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import Embedding, EvidenceReference
from gamingcreator.domain.time import SourceInstant, SourceRange

RetrievalMode = Literal["lexical", "semantic", "hybrid"]
RETRIEVAL_VERSION = "bm25-e5-rrf-v3"
_STOP_WORDS = frozenset(
    "a an and are at avatar character characters clip find for from game gameplay in is me of on player please show the to video with".split()
)
_CHINESE_FILLER = (
    "帮我找到",
    "帮我找",
    "请找到",
    "请找",
    "的视频片段",
    "的片段",
    "视频中",
    "展示",
    "片段",
    "找出",
    "角色",
    "玩家",
    "游戏",
)
# English mechanic words share no characters with Chinese observable facts.
# Longer words come first so a shorter stem does not also match inside them.
_CROSS_LINGUAL_TERMS = (
    ("attacking", "攻击"),
    ("attacker", "攻击"),
    ("attacks", "攻击"),
    ("attack", "攻击"),
    ("fighters", "战斗"),
    ("fighter", "战斗"),
    ("fighting", "战斗"),
    ("fights", "战斗"),
    ("fight", "战斗"),
    ("combat", "战斗"),
)


@dataclass(frozen=True, slots=True)
class CandidateClip:
    candidate_id: str
    event_id: str | None
    media_id: str
    source_range: SourceRange
    score: float
    score_kind: str
    evidence_ids: tuple[str, ...]
    observable_facts: tuple[str, ...]
    why: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    run_id: str
    query: str
    mode: RetrievalMode
    candidates: tuple[CandidateClip, ...]
    embedding_metadata: InvocationMetadata | None = None
    retrieval_version: str = RETRIEVAL_VERSION
    min_similarity: float = 0.80
    min_semantic_margin: float = 0.02
    abstention_reason: str | None = None
    event_embeddings: tuple[Embedding, ...] = ()


@dataclass(frozen=True, slots=True)
class _Document:
    identifier: str
    event_id: str | None
    media_id: str
    source_range: SourceRange
    evidence_ids: tuple[str, ...]
    facts: tuple[str, ...]
    tags: tuple[str, ...]
    text: str


def _fail(code: str, message: str) -> AppError:
    return AppError(code, message, ExitCode.INPUT)


def _tokens(text: str) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", text).casefold()
    for filler in _CHINESE_FILLER:
        text = text.replace(filler, " ")
    tokens = []
    for word in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text):
        if word.isascii():
            if word not in _STOP_WORDS:
                tokens.append(word)
        elif len(word) == 1:
            tokens.append(word)
        else:
            tokens.extend(word[index : index + 2] for index in range(len(word) - 1))
    return tuple(tokens)


def _overlap(left: SourceRange, right: SourceRange) -> int:
    return max(0, min(left.end_us, right.end_us) - max(left.start_us, right.start_us))


def _evidence_overlaps(evidence: EvidenceReference, interval: SourceRange) -> bool:
    clock = evidence.source_time
    return (
        interval.start_us <= clock.time_us < interval.end_us
        if isinstance(clock, SourceInstant)
        else _overlap(clock, interval) > 0
    )


def _documents(timeline: StoredTimeline) -> tuple[_Document, ...]:
    run, asset = timeline.run, timeline.run.asset
    if run.status != RunStatus.COMPLETED:
        raise _fail("storage.run_incomplete", "只能检索已完成并校验的分析记录。")
    evidence = {item.evidence_id: item for item in timeline.evidence}
    if len(evidence) != len(timeline.evidence):
        raise _fail("retrieval.timeline_invalid", "时间轴证据标识重复。")
    for item in timeline.evidence:
        if (
            item.media_id != asset.media_id
            or item.source_time.duration_us != asset.duration_us
            or not item.evidence_id.startswith(f"{run.run_id}:")
        ):
            raise _fail("retrieval.timeline_invalid", "时间轴证据关联不一致。")
    for segment in timeline.transcripts:
        if (
            segment.media_id != asset.media_id
            or segment.source_range.duration_us != asset.duration_us
        ):
            raise _fail("retrieval.timeline_invalid", "转录与源媒体关联不一致。")
    documents = []
    seen = set()
    for event in timeline.events:
        if (
            event.run_id != run.run_id
            or event.media_id != asset.media_id
            or event.source_range.duration_us != asset.duration_us
            or event.event_id in seen
            or not event.evidence_ids
            or any(
                identifier not in evidence
                or not _evidence_overlaps(evidence[identifier], event.source_range)
                for identifier in event.evidence_ids
            )
        ):
            raise _fail("retrieval.timeline_invalid", "事件区间、标识或证据关联无效。")
        seen.add(event.event_id)
        transcripts = tuple(
            segment.text
            for segment in timeline.transcripts
            if _overlap(segment.source_range, event.source_range) > 0
        )
        text = "\n".join((*event.observable_facts, *event.mechanic_tags, *transcripts)).strip()
        if text:
            documents.append(
                _Document(
                    f"event:{event.event_id}",
                    event.event_id,
                    asset.media_id,
                    event.source_range,
                    tuple(sorted(set(event.evidence_ids))),
                    event.observable_facts,
                    event.mechanic_tags,
                    text,
                )
            )
    for segment in timeline.transcripts:
        if not segment.text.strip() or any(
            _overlap(segment.source_range, event.source_range)
            >= (segment.source_range.end_us - segment.source_range.start_us) / 2
            for event in timeline.events
        ):
            continue
        references = tuple(
            sorted(
                item.evidence_id
                for item in timeline.evidence
                if item.kind == "audio" and _evidence_overlaps(item, segment.source_range)
            )
        )
        if not references:
            continue
        text_hash = hashlib.sha256(segment.text.encode("utf-8")).hexdigest()
        identity = (
            f"transcript:{segment.source_range.start_us}:{segment.source_range.end_us}:{text_hash}"
        )
        documents.append(
            _Document(
                identity,
                None,
                asset.media_id,
                segment.source_range,
                references,
                (segment.text,),
                (),
                segment.text,
            )
        )
    return tuple(sorted(documents, key=lambda item: (item.source_range.start_us, item.identifier)))


def _lexical_query(query: str) -> str:
    folded = unicodedata.normalize("NFKC", query).casefold()
    extras: list[str] = []
    for word, term in _CROSS_LINGUAL_TERMS:
        if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", folded):
            extras.append(term)
    if not extras:
        return query
    return query + "\n" + " ".join(dict.fromkeys(extras))


def _lexical_scores(documents: tuple[_Document, ...], query: str) -> dict[str, float]:
    terms = frozenset(_tokens(_lexical_query(query)))
    counters = [Counter(_tokens(item.text)) for item in documents]
    average = sum(map(lambda counter: sum(counter.values()), counters)) / len(documents)
    if not terms or average == 0:
        return {}
    document_frequency = Counter(term for counter in counters for term in counter)
    scores = {}
    for document, counter in zip(documents, counters, strict=True):
        length = sum(counter.values())
        score = 0.0
        for term in terms:
            frequency = counter[term]
            if frequency:
                idf = math.log(
                    1
                    + (len(documents) - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                score += (
                    idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
                )
        if score > 0:
            scores[document.identifier] = score
    return scores


def _cosine(left: Embedding, right: Embedding) -> float:
    left_norm = math.hypot(*left.vector)
    right_norm = math.hypot(*right.vector)
    if (
        not left_norm
        or not right_norm
        or not math.isfinite(left_norm)
        or not math.isfinite(right_norm)
    ):
        raise _fail("retrieval.embedding_invalid", "检索向量不能为空。")
    return max(
        -1.0,
        min(
            1.0,
            math.fsum(
                (a / left_norm) * (b / right_norm)
                for a, b in zip(left.vector, right.vector, strict=True)
            ),
        ),
    )


def _duplicate(left: _Document, right: _Document) -> bool:
    intersection = _overlap(left.source_range, right.source_range)
    minimum = min(
        left.source_range.end_us - left.source_range.start_us,
        right.source_range.end_us - right.source_range.start_us,
    )
    if left.identifier == right.identifier:
        return True
    if not intersection or intersection / minimum < 0.5:
        return False
    left_terms, right_terms = (
        set(_tokens(" ".join(left.facts))),
        set(_tokens(" ".join(right.facts))),
    )
    union = left_terms | right_terms
    similarity = len(left_terms & right_terms) / len(union) if union else 0
    return (
        similarity >= 0.6
        or bool(set(left.evidence_ids) & set(right.evidence_ids))
        and similarity >= 0.35
    )


async def search_timeline(
    timeline: StoredTimeline,
    query: str,
    *,
    top_k: int = 10,
    mode: RetrievalMode = "hybrid",
    embedding_provider: EmbeddingProvider | None = None,
    context: CancellationContext | None = None,
    min_similarity: float = 0.80,
    min_semantic_margin: float = 0.02,
) -> SearchResult:
    """Rank validated source intervals; scores are ranking signals, never probabilities.

    The semantic cutoff is a tunable uncalibrated demo parameter, not a quality gate.
    Callers must obtain the timeline through load_completed_timeline to check file integrity.
    """
    if (
        type(top_k) is not int
        or not 1 <= top_k <= 100
        or mode not in ("lexical", "semantic", "hybrid")
    ):
        raise _fail("retrieval.configuration", "检索模式或结果数量无效。")
    if (
        type(min_similarity) not in (int, float)
        or not math.isfinite(min_similarity)
        or not -1 <= min_similarity <= 1
    ):
        raise _fail("retrieval.configuration", "语义检索阈值无效。")
    if (
        type(min_semantic_margin) not in (int, float)
        or not math.isfinite(min_semantic_margin)
        or not 0 <= min_semantic_margin <= 2
    ):
        raise _fail("retrieval.configuration", "语义检索分差阈值无效。")
    if not isinstance(query, str) or len(query) > 4096:
        raise _fail("retrieval.query", "查询须为不超过4096字符的文本。")
    documents = _documents(timeline)
    query = query.strip()
    if context is not None:
        if context.run_id != timeline.run.run_id:
            raise _fail("retrieval.configuration", "检索上下文关联无效。")
        context.check_cancelled()
    if not documents or not _tokens(query):
        return SearchResult(
            timeline.run.run_id,
            query,
            mode,
            (),
            min_similarity=min_similarity,
            min_semantic_margin=min_semantic_margin,
        )
    lexical = _lexical_scores(documents, query) if mode != "semantic" else {}
    semantic = {}
    metadata = None
    abstention_reason = None
    event_embeddings: tuple[Embedding, ...] = ()
    if mode != "lexical":
        if embedding_provider is None:
            raise AppError(
                "retrieval.embedding_missing",
                "语义检索需要已准备的本地模型；可显式使用lexical模式。",
                ExitCode.ENVIRONMENT,
            )
        texts = (f"query: {query}", *(f"passage: {item.text}" for item in documents))
        result = await embedding_provider.embed(
            EmbeddingRequest(timeline.run.run_id, texts, "embedding-v1"),
            context or CancellationContext(timeline.run.run_id, 120),
        )
        if context is not None:
            context.check_cancelled()
        if result.status != ProviderStatus.COMPLETED or result.output is None:
            raise AppError(
                result.error.code if result.error is not None else "retrieval.embedding_failed",
                "本地语义模型未完成检索向量计算。",
                ExitCode.CANCELLED
                if result.status == ProviderStatus.CANCELLED
                else ExitCode.PROVIDER,
            )
        embeddings = result.output
        if len(embeddings) != len(texts) or any(
            embedding.space != embeddings[0].space
            or embedding.text_hash != hashlib.sha256(text.encode("utf-8")).hexdigest()
            or embedding.subject_id != f"{timeline.run.run_id}:{index}"
            for index, (embedding, text) in enumerate(zip(embeddings, texts, strict=True))
        ):
            raise _fail("retrieval.embedding_invalid", "模型返回的向量空间、数量或文本关联不一致。")
        metadata = result.metadata
        event_embeddings = tuple(
            replace(embedding, subject_id=document.event_id)
            for document, embedding in zip(documents, embeddings[1:], strict=True)
            if document.event_id is not None
        )
        for document, embedding in zip(documents, embeddings[1:], strict=True):
            similarity = _cosine(embeddings[0], embedding)
            if similarity >= min_similarity:
                semantic[document.identifier] = similarity
        if mode == "hybrid" and semantic:
            # An uncalibrated candidate truncation window limits E5's high-cosine tail.
            # Repeated independent occurrences with equal scores remain eligible.
            best_similarity = max(semantic.values())
            semantic = {
                identifier: similarity
                for identifier, similarity in semantic.items()
                if similarity >= best_similarity - min_semantic_margin
            }
        if mode == "hybrid" and not lexical and semantic:
            # E5 absolute cosines are high even for unrelated text. Contrast distinct
            # descriptions, grouping repeated independent occurrences for this check.
            groups: dict[str, float] = {}
            for document, embedding in zip(documents, embeddings[1:], strict=True):
                description = (
                    unicodedata.normalize("NFKC", "\n".join(document.facts)).casefold().strip()
                )
                groups[description] = max(
                    groups.get(description, -1.0), _cosine(embeddings[0], embedding)
                )
            ordered = sorted(groups.values(), reverse=True)
            if (
                len(ordered) > 1
                and ordered[0] - ordered[1] < min_semantic_margin
                or len(ordered) == 1
                and ordered[0] < 0.90
            ):
                semantic = {}
                abstention_reason = "semantic_ambiguity_without_lexical_anchor"
    if mode == "lexical":
        scores, score_kind = lexical, "bm25"
    elif mode == "semantic":
        scores, score_kind = semantic, "cosine"
    else:
        scores = {}
        for component in (lexical, semantic):
            for rank, (identifier, _) in enumerate(
                sorted(component.items(), key=lambda pair: (-pair[1], pair[0])), 1
            ):
                scores[identifier] = scores.get(identifier, 0.0) + 1 / (60 + rank)
        score_kind = "rrf-bm25-cosine"
    selected: list[_Document] = []
    candidates = []
    for document in sorted(
        documents,
        key=lambda item: (
            -scores.get(item.identifier, -1),
            item.source_range.start_us,
            item.identifier,
        ),
    ):
        if document.identifier not in scores or any(
            _duplicate(document, item) for item in selected
        ):
            continue
        selected.append(document)
        identity = hashlib.sha256(
            f"{timeline.run.run_id}:{document.identifier}".encode()
        ).hexdigest()[:24]
        signals = []
        if document.identifier in lexical:
            signals.append(f"BM25={lexical[document.identifier]:.4f}")
        if document.identifier in semantic:
            signals.append(f"cosine={semantic[document.identifier]:.4f}")
        candidates.append(
            CandidateClip(
                f"clip-{identity}",
                document.event_id,
                document.media_id,
                document.source_range,
                scores[document.identifier],
                score_kind,
                document.evidence_ids,
                document.facts,
                "; ".join(signals) + "; ranking signal, not probability",
            )
        )
        if len(candidates) == top_k:
            break
    return SearchResult(
        timeline.run.run_id,
        query,
        mode,
        tuple(candidates),
        metadata,
        min_similarity=min_similarity,
        min_semantic_margin=min_semantic_margin,
        abstention_reason=abstention_reason,
        event_embeddings=event_embeddings,
    )
