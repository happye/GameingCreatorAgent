"""Cross-actor supplemental terms cannot form one BM25 or semantic scoring document."""

import asyncio
import hashlib
import math
from dataclasses import replace

import pytest
from test_retrieval import META, SPACE, event, timeline

from gamingcreator.application.providers import ProviderResult, ProviderStatus
from gamingcreator.application.retrieval import (
    CandidateText,
    RetrievalSupplement,
    SemanticFacet,
    candidate_sources,
    search_timelines,
)
from gamingcreator.domain.models import Embedding


class CoherentEmbedding:
    """Transport fixture: both terms must be in this one passage; no real model claim."""

    def __init__(self):
        self.texts = ()

    async def embed(self, request, context):
        self.texts = request.texts
        vectors = []
        for index, text in enumerate(request.texts):
            score = (
                1.0 if index == 0 else 0.95 if "white hair" in text and "red coat" in text else 0.70
            )
            vectors.append(
                Embedding(
                    f"{request.run_id}:{index}",
                    SPACE,
                    (score, math.sqrt(1 - score * score)),
                    hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        return ProviderResult(ProviderStatus.COMPLETED, tuple(vectors), META)


def grouped_pool(*, original_support=False):
    source = timeline(
        events=(
            event("split", 0, 1, "two different actors", "scene"),
            event("coherent", 3, 4, "one actor standing", "scene"),
        )
        + (
            (event("base", 7, 8, "white hair red coat from original description", "scene"),)
            if original_support
            else ()
        )
    )
    ids = {row.event_id: row.candidate_id for row in candidate_sources(source)}
    facts = (
        CandidateText(ids["split"], ("white hair", "red coat")),
        CandidateText(ids["coherent"], ("white hair red coat",)),
    )
    facets = (
        SemanticFacet("facet-" + "1" * 24, ids["split"], ("white hair",)),
        SemanticFacet("facet-" + "2" * 24, ids["split"], ("red coat",)),
        SemanticFacet("facet-" + "3" * 24, ids["coherent"], ("white hair red coat",)),
    )
    return source, ids, RetrievalSupplement("a" * 64, facts, "saved-detail-text-v3", facets)


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_independent_groups_cannot_combine_cross_actor_terms_to_outscore_coherent_group(mode):
    source, ids, supplement = grouped_pool()
    provider = CoherentEmbedding()
    result = asyncio.run(
        search_timelines(
            (source,),
            "white hair red coat",
            mode=mode,
            embedding_provider=provider,
            supplement=supplement,
        )
    )
    assert result.candidates[0].clip.event_id == "coherent"
    assert len({row.clip.candidate_id for row in result.candidates}) == len(result.candidates)
    for row in result.candidates:
        original = next(event for event in source.events if event.event_id == row.clip.event_id)
        assert row.clip.observable_facts == original.observable_facts
        assert row.clip.source_range == original.source_range
        assert row.clip.evidence_ids == original.evidence_ids
    if mode == "semantic":
        assert len(result.candidates) == 1
        assert result.lexical_detail_matches == ()
    else:
        assert (
            dict(result.lexical_detail_matches)[ids["coherent"]]
            == supplement.semantic_facets[2].facet_id
        )
        assert all("lexicalDetailFacet=" in row.clip.why for row in result.candidates)
    if mode != "lexical":
        assert not any(
            "two different actors" in text and "white hair" in text for text in provider.texts
        )
        assert result.semantic_detail_matches == (
            (ids["coherent"], supplement.semantic_facets[2].facet_id),
        )


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_original_description_without_exact_detail_remains_eligible(mode):
    source, ids, supplement = grouped_pool(original_support=True)
    result = asyncio.run(
        search_timelines(
            (source,),
            "white hair red coat",
            mode=mode,
            embedding_provider=CoherentEmbedding(),
            supplement=supplement,
        )
    )
    assert "base" in {row.clip.event_id for row in result.candidates}
    assert ids["base"] not in dict(result.lexical_detail_matches)
    assert ids["base"] not in dict(result.semantic_detail_matches)


@pytest.mark.parametrize("copies", [1, 4])
@pytest.mark.parametrize("mode", ["lexical", "hybrid"])
def test_multiple_actor_groups_do_not_add_results_or_extra_rrf_votes(copies, mode):
    source, ids, supplement = grouped_pool()
    source = replace(source, events=(source.events[1],))
    first = supplement.semantic_facets[2]
    facets = tuple(replace(first, facet_id=f"facet-{index:024x}") for index in range(copies))
    supplement = replace(supplement, candidates=(supplement.candidates[1],), semantic_facets=facets)
    result = asyncio.run(
        search_timelines(
            (source,),
            "white hair red coat",
            mode=mode,
            embedding_provider=CoherentEmbedding(),
            supplement=supplement,
        )
    )
    assert len(result.candidates) == 1
    assert len(result.lexical_detail_matches) == 1
    if mode == "hybrid":
        assert result.candidates[0].clip.score == pytest.approx(2 / 61)
