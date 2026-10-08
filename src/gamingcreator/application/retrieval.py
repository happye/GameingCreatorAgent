"""Deterministic evidence-backed lexical and local semantic clip retrieval."""

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from typing import Literal

from gamingcreator.application.observation_text import display_facts
from gamingcreator.application.providers import (
    CancellationContext,
    EmbeddingProvider,
    EmbeddingRequest,
    InvocationMetadata,
    ProviderStatus,
)
from gamingcreator.application.storage import RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import Embedding, EvidenceReference
from gamingcreator.domain.time import SourceInstant, SourceRange

RetrievalMode = Literal["lexical", "semantic", "hybrid"]
RETRIEVAL_VERSION = "bm25-e5-rrf-v7"
PROJECT_RETRIEVAL_VERSION = RETRIEVAL_VERSION + "-project-v1"
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
# A small explicit-language guard, not a language model. Apply this only to
# positive action queries; passage identities follow the observation projection.
_ACTION_TERMS = {
    "jump": ("跳跃", "跳起", "起跳", "jump", "jumps", "jumping", "jumped"),
    "shoot": ("射击", "开枪", "shoot", "shoots", "shooting"),
    "attack": ("攻击", "attack", "attacks", "attacking", "attacked"),
    "fight": ("战斗", "打斗", "fight", "fights", "fighting", "combat"),
    "interact": (
        "交互",
        "互动",
        "interact",
        "interacts",
        "interacting",
        "interaction",
        "interactions",
    ),
    "move": ("移动", "move", "moves", "moving", "movement"),
}
_ACTION_BY_TERM = {term: action for action, terms in _ACTION_TERMS.items() for term in terms}
_ACTION_PATTERN = (
    "(?:"
    + "|".join(
        rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])" if term.isascii() else re.escape(term)
        for term in sorted(_ACTION_BY_TERM, key=len, reverse=True)
    )
    + ")"
)
_ACTION_MENTION = re.compile(_ACTION_PATTERN)
_CHINESE_ACTION_ITEM = _ACTION_PATTERN + r"(?:动作|行为|迹象)?"
_EXPLICIT_DENIAL = re.compile(
    r"(?:未观察到|未见|没有|无)(?:(?:明确|明显|可见|实际|任何)的?)*"
    r"(?:(?:玩家角色|玩家|角色)(?:正在|进行)?)?"
    + _CHINESE_ACTION_ITEM
    + r"(?:\s*(?:、|，|,|和|或|与|以及|及)\s*"
    + _CHINESE_ACTION_ITEM
    + r")*"
    + r"|\b(?:no(?:\s+evidence\s+of)?|without|(?:do|does|did)\s+not|"
    r"(?:do|does|did)n't|not)\s+"
    r"(?:(?:clear|visible|obvious|actual|any|clearly|visibly)\s+)*"
    + _ACTION_PATTERN
    + r"(?:(?:,\s*(?:(?:or|and)\s+)?|\s+(?:or|and)\s+)"
    + _ACTION_PATTERN
    + r")*"
)
_UNCERTAIN_DENIAL_PREFIX = re.compile(
    r"(?:可能|或许|也许|似乎|不确定(?:是否)?|无法确认(?:是否)?|不能确认(?:是否)?|"
    r"无法确定(?:是否)?|不能确定(?:是否)?|不知道(?:是否)?|"
    r"并非|并不是|不是|不一定|未必|\b(?:maybe|possibly|perhaps|not|never|"
    r"unclear whether|unclear if|cannot confirm|may be|might be))(?:并|也|仍|还)?\s*$|"
    r"(?:是否|有)\s*$"
)
_NEGATIVE_QUERY_INTENT = re.compile(
    r"没有|未见|未观察到|无|不|避免|禁止|排除|不要|"
    r"\b(?:no|not|without|avoid|exclude|excluding|except|never)\b|\b(?:do|does|did)n't\b"
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
class CandidateSource:
    candidate_id: str
    event_id: str | None
    media_id: str
    source_range: SourceRange
    evidence_ids: tuple[str, ...]
    observable_facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateText:
    candidate_id: str
    facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticFacet:
    facet_id: str
    candidate_id: str
    facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalSupplement:
    snapshot_sha256: str
    candidates: tuple[CandidateText, ...]
    projection_version: str = "saved-detail-text-v1"
    semantic_facets: tuple[SemanticFacet, ...] = ()


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
    semantic_detail_matches: tuple[tuple[str, str], ...] = ()
    lexical_detail_matches: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectCandidateClip:
    run_id: str
    clip: CandidateClip


@dataclass(frozen=True, slots=True)
class ProjectSearchResult:
    scope_id: str
    query: str
    mode: RetrievalMode
    sources: tuple[StoredRun, ...]
    candidates: tuple[ProjectCandidateClip, ...]
    embedding_metadata: InvocationMetadata | None
    min_similarity: float
    min_semantic_margin: float
    abstention_reason: str | None
    retrieval_version: str = PROJECT_RETRIEVAL_VERSION
    semantic_detail_matches: tuple[tuple[str, str], ...] = ()
    lexical_detail_matches: tuple[tuple[str, str], ...] = ()


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
    run_id: str
    source_identifier: str
    supplemental_facts: tuple[str, ...] = ()

    @property
    def candidate_id(self) -> str:
        digest = hashlib.sha256(f"{self.run_id}:{self.source_identifier}".encode()).hexdigest()
        return "clip-" + digest[:24]


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
        text = "\n".join(
            (*display_facts(event.observable_facts), *event.mechanic_tags, *transcripts)
        ).strip()
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
                    run.run_id,
                    f"event:{event.event_id}",
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
                run.run_id,
                identity,
            )
        )
    return tuple(sorted(documents, key=lambda item: (item.source_range.start_us, item.identifier)))


def candidate_sources(timeline: StoredTimeline) -> tuple[CandidateSource, ...]:
    """Project original candidate identities without scores, embeddings or another search."""
    return tuple(
        CandidateSource(
            item.candidate_id,
            item.event_id,
            item.media_id,
            item.source_range,
            item.evidence_ids,
            item.facts,
        )
        for item in _documents(timeline)
    )


def _lexical_query(query: str) -> str:
    folded = unicodedata.normalize("NFKC", query).casefold().replace("’", "'")
    extras: list[str] = []
    for word, term in _CROSS_LINGUAL_TERMS:
        if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", folded):
            extras.append(term)
    # Reuse only the known Chinese action aliases. Expanding English words such
    # as "jump" would also match game titles like JUMP ASSEMBLE. Negative-intent
    # queries retain their previous behavior, without new absence semantics.
    if not _NEGATIVE_QUERY_INTENT.search(folded):
        for match in _ACTION_MENTION.finditer(folded):
            extras.extend(
                term for term in _ACTION_TERMS[_ACTION_BY_TERM[match.group()]] if not term.isascii()
            )
    if not extras:
        return query
    return query + "\n" + " ".join(dict.fromkeys(extras))


def _denied_action_documents(documents: tuple[_Document, ...], query: str) -> frozenset[str]:
    """Reject only recognized query actions mentioned exclusively in explicit denials.

    Unknown wording stays eligible. Any unnegated occurrence, including a separate
    affirmative clause, defeats exclusion. Absence queries retain existing ranking;
    this guard does not implement negative-query semantics.
    """
    folded_query = unicodedata.normalize("NFKC", query).casefold().replace("’", "'")
    if _NEGATIVE_QUERY_INTENT.search(folded_query):
        return frozenset()
    actions = {_ACTION_BY_TERM[match.group()] for match in _ACTION_MENTION.finditer(folded_query)}
    if not actions:
        return frozenset()
    denied = set()
    for document in documents:
        text = unicodedata.normalize("NFKC", document.text).casefold().replace("’", "'")
        spans = tuple(
            match.span()
            for match in _EXPLICIT_DENIAL.finditer(text)
            if not _UNCERTAIN_DENIAL_PREFIX.search(text[max(0, match.start() - 32) : match.start()])
        )
        negative_actions, other_actions = set(), set()
        for match in _ACTION_MENTION.finditer(text):
            action = _ACTION_BY_TERM[match.group()]
            if action not in actions:
                continue
            if any(start <= match.start() and match.end() <= end for start, end in spans):
                negative_actions.add(action)
            else:
                other_actions.add(action)
        if negative_actions and not other_actions:
            denied.add(document.identifier)
    return frozenset(denied)


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
    if left.media_id != right.media_id:
        return False
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
        set(_tokens(" ".join(display_facts(left.facts)))),
        set(_tokens(" ".join(display_facts(right.facts)))),
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
    return await _search_documents(
        timeline.run.run_id,
        (timeline,),
        query,
        top_k=top_k,
        mode=mode,
        embedding_provider=embedding_provider,
        context=context,
        min_similarity=min_similarity,
        min_semantic_margin=min_semantic_margin,
    )


async def search_timelines(
    timelines: tuple[StoredTimeline, ...],
    query: str,
    *,
    top_k: int = 10,
    mode: RetrievalMode = "hybrid",
    embedding_provider: EmbeddingProvider | None = None,
    context: CancellationContext | None = None,
    min_similarity: float = 0.80,
    min_semantic_margin: float = 0.02,
    supplement: RetrievalSupplement | None = None,
) -> ProjectSearchResult:
    """Rank one joint corpus, retaining each original task/candidate identity."""
    if not 1 <= len(timelines) <= 100:
        raise _fail("retrieval.scope", "请选择1–100个已完成任务。")
    timelines = tuple(sorted(timelines, key=lambda item: item.run.run_id))
    sources = tuple(item.run for item in timelines)
    if (
        len({run.run_id for run in sources}) != len(sources)
        or len({run.asset.media_id for run in sources}) != len(sources)
        or len({run.asset.sha256 for run in sources}) != len(sources)
    ):
        raise _fail("retrieval.scope", "任务不能重复，同一原录像请只选择一个分析版本。")
    identity = json.dumps(
        [
            (
                run.run_id,
                run.config_hash,
                run.configuration.pipeline_hash,
                run.asset.media_id,
                run.asset.sha256,
                run.asset.duration_us,
            )
            for run in sources
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if supplement is not None:
        if (
            not re.fullmatch(r"[a-f0-9]{64}", supplement.snapshot_sha256)
            or supplement.projection_version
            not in {"saved-detail-text-v1", "saved-detail-text-v2", "saved-detail-text-v3"}
            or supplement.projection_version == "saved-detail-text-v1"
            and supplement.semantic_facets
        ):
            raise _fail("retrieval.supplement", "已有细节的语料快照无效。")
        identity += "\n" + supplement.projection_version + ":" + supplement.snapshot_sha256
    scope_id = "project-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    result = await _search_documents(
        scope_id,
        timelines,
        query,
        namespace=True,
        top_k=top_k,
        mode=mode,
        embedding_provider=embedding_provider,
        context=context,
        min_similarity=min_similarity,
        min_semantic_margin=min_semantic_margin,
        supplement=supplement,
    )
    owners = {
        document.candidate_id: document.run_id
        for timeline in timelines
        for document in _documents(timeline)
    }
    return ProjectSearchResult(
        scope_id,
        result.query,
        result.mode,
        sources,
        tuple(ProjectCandidateClip(owners[item.candidate_id], item) for item in result.candidates),
        result.embedding_metadata,
        result.min_similarity,
        result.min_semantic_margin,
        result.abstention_reason,
        PROJECT_RETRIEVAL_VERSION
        + (
            "-saved-details-" + supplement.projection_version.rsplit("-", 1)[1]
            if supplement
            else ""
        ),
        result.semantic_detail_matches,
        result.lexical_detail_matches,
    )


async def _search_documents(
    run_id: str,
    timelines: tuple[StoredTimeline, ...],
    query: str,
    *,
    namespace: bool = False,
    top_k: int = 10,
    mode: RetrievalMode = "hybrid",
    embedding_provider: EmbeddingProvider | None = None,
    context: CancellationContext | None = None,
    min_similarity: float = 0.80,
    min_semantic_margin: float = 0.02,
    supplement: RetrievalSupplement | None = None,
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
    documents = tuple(
        replace(document, identifier=f"{document.run_id}:{document.identifier}")
        if namespace
        else document
        for timeline in timelines
        for document in _documents(timeline)
    )
    facets: tuple[SemanticFacet, ...] = supplement.semantic_facets if supplement else ()
    grouped = supplement is not None and supplement.projection_version == "saved-detail-text-v3"
    if supplement is not None:
        extra = {row.candidate_id: row.facts for row in supplement.candidates}
        visual = {row.candidate_id for row in documents if row.event_id is not None}
        if (
            len(extra) != len(supplement.candidates)
            or not set(extra) <= visual
            or any(
                type(facts) is not tuple
                or not 1 <= len(facts) <= 256
                or any(type(fact) is not str or not fact or len(fact) > 4096 for fact in facts)
                for facts in extra.values()
            )
        ):
            raise _fail("retrieval.supplement", "细节文字与原视觉候选不一致。")
        if (
            len(facets) > 20_000
            or len({row.facet_id for row in facets}) != len(facets)
            or any(
                type(row.facet_id) is not str
                or not re.fullmatch(r"facet-[a-f0-9]{24}", row.facet_id)
                or row.candidate_id not in extra
                or type(row.facts) is not tuple
                or not row.facts
                or any(
                    type(fact) is not str or fact not in extra[row.candidate_id]
                    for fact in row.facts
                )
                or len("\n".join(row.facts)) > 8192 - len("passage: ")
                for row in facets
            )
        ):
            raise _fail("retrieval.supplement", "人物细节组与原候选不一致或超过20,000组。")
        documents = tuple(
            replace(
                row,
                text=row.text if grouped else row.text + "\n" + "\n".join(extra[row.candidate_id]),
                supplemental_facts=extra[row.candidate_id],
            )
            if row.candidate_id in extra
            else row
            for row in documents
        )
    query = query.strip()
    if context is not None:
        if context.run_id != run_id:
            raise _fail("retrieval.configuration", "检索上下文关联无效。")
        context.check_cancelled()
    if not documents or not _tokens(query):
        return SearchResult(
            run_id,
            query,
            mode,
            (),
            min_similarity=min_similarity,
            min_semantic_margin=min_semantic_margin,
        )
    denied_actions = _denied_action_documents(documents, query)
    lexical_winners: dict[str, str] = {}
    lexical_documents = documents
    facet_documents: tuple[_Document, ...] = ()
    if grouped and mode != "semantic":
        by_candidate = {row.candidate_id: row for row in documents}
        facet_documents = tuple(
            replace(
                by_candidate[facet.candidate_id],
                identifier=facet.facet_id,
                text="\n".join(facet.facts),
            )
            for facet in facets
        )
        lexical_documents += facet_documents
    lexical = (
        {
            identifier: score
            for identifier, score in _lexical_scores(lexical_documents, query).items()
            if identifier not in denied_actions
        }
        if mode != "semantic"
        else {}
    )
    if facet_documents:
        identifiers = {row.candidate_id: row.identifier for row in documents}
        for lexical_facet in facet_documents:
            score = lexical.pop(lexical_facet.identifier, None)
            identifier = identifiers[lexical_facet.candidate_id]
            if (
                score is not None
                and identifier not in denied_actions
                and score > lexical.get(identifier, -1.0)
            ):
                lexical[identifier] = score
                lexical_winners[identifier] = lexical_facet.identifier
    semantic = {}
    facet_winners: dict[str, str] = {}
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
        texts = (
            f"query: {query}",
            *(f"passage: {item.text}" for item in documents),
            *("passage: " + "\n".join(item.facts) for item in facets),
        )
        result = await embedding_provider.embed(
            EmbeddingRequest(run_id, texts, "embedding-v1"),
            context or CancellationContext(run_id, 120),
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
            or embedding.subject_id != f"{run_id}:{index}"
            for index, (embedding, text) in enumerate(zip(embeddings, texts, strict=True))
        ):
            raise _fail("retrieval.embedding_invalid", "模型返回的向量空间、数量或文本关联不一致。")
        metadata = result.metadata
        document_embeddings = embeddings[1 : 1 + len(documents)]
        event_embeddings = tuple(
            replace(embedding, subject_id=document.event_id)
            for document, embedding in zip(documents, document_embeddings, strict=True)
            if document.event_id is not None
        )
        similarities = {
            document.identifier: _cosine(embeddings[0], embedding)
            for document, embedding in zip(documents, document_embeddings, strict=True)
        }
        identifiers = {row.candidate_id: row.identifier for row in documents}
        for facet, embedding in zip(facets, embeddings[1 + len(documents) :], strict=True):
            identifier = identifiers[facet.candidate_id]
            similarity = _cosine(embeddings[0], embedding)
            if similarity > similarities[identifier]:
                similarities[identifier] = similarity
                facet_winners[identifier] = facet.facet_id
        for document in documents:
            similarity = similarities[document.identifier]
            if similarity >= min_similarity and document.identifier not in denied_actions:
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
            for document in documents:
                if document.identifier in denied_actions:
                    continue
                description = (
                    unicodedata.normalize(
                        "NFKC", "\n".join(document.facts + document.supplemental_facts)
                    )
                    .casefold()
                    .strip()
                )
                groups[description] = max(
                    groups.get(description, -1.0), similarities[document.identifier]
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
        signals = []
        if document.identifier in lexical:
            signals.append(f"BM25={lexical[document.identifier]:.4f}")
            if document.identifier in lexical_winners:
                signals.append(f"lexicalDetailFacet={lexical_winners[document.identifier]}")
        if document.identifier in semantic:
            signals.append(f"cosine={semantic[document.identifier]:.4f}")
            if document.identifier in facet_winners:
                signals.append(f"detailFacet={facet_winners[document.identifier]}")
        candidates.append(
            CandidateClip(
                document.candidate_id,
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
        run_id,
        query,
        mode,
        tuple(candidates),
        metadata,
        min_similarity=min_similarity,
        min_semantic_margin=min_semantic_margin,
        abstention_reason=abstention_reason,
        event_embeddings=event_embeddings,
        semantic_detail_matches=tuple(
            (row.candidate_id, facet_winners[row.identifier])
            for row in selected
            if row.identifier in semantic and row.identifier in facet_winners
        ),
        lexical_detail_matches=tuple(
            (row.candidate_id, lexical_winners[row.identifier])
            for row in selected
            if row.identifier in lexical_winners
        ),
    )
