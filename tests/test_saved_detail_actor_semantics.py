"""Subject-focused semantic scores retain one source candidate and legacy corpus snapshots."""

import asyncio
import hashlib
import json
import math
from dataclasses import replace

import pytest
from test_detail_query import manifest, snapshot
from test_retrieval import META, SPACE
from test_saved_detail_retrieval import detail_pool  # noqa: F401 - shared isolated fixture

from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.application.detail_retrieval import (
    LEGACY_VERSION,
    VERSION,
    build_saved_detail_corpus,
)
from gamingcreator.application.providers import ProviderResult, ProviderStatus
from gamingcreator.application.retrieval import search_timelines
from gamingcreator.application.search_detail_query import search_snapshot_sha256
from gamingcreator.cli import main as cli
from gamingcreator.domain.actor_details import AttributeKind
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.models import Embedding
from gamingcreator.infrastructure.detail_query_sidecar import (
    read_saved_detail_corpus,
    refinement_identity_for_profile,
    refinement_settings_for_profile,
)
from gamingcreator.infrastructure.project_search_files import (
    read_project_search,
    write_project_search,
)


class FocusedEmbedding:
    """Only the focused passage crosses threshold; whole-event text remains weak."""

    def __init__(self, facts):
        self.focused = {"passage: " + "\n".join(row) for row in facts}
        self.texts = ()

    async def embed(self, request, context):
        self.texts = request.texts
        vectors = []
        for index, text in enumerate(request.texts):
            score = 1.0 if index == 0 else 0.95 if text in self.focused else 0.70
            vectors.append(
                Embedding(
                    f"{request.run_id}:{index}",
                    SPACE,
                    (score, math.sqrt(1 - score * score)),
                    hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        return ProviderResult(ProviderStatus.COMPLETED, tuple(vectors), META)


def test_corpus_separates_actors_and_environment_and_keeps_exact_attribute_provenance(request):
    _, timeline, _, detail = request.getfixturevalue("detail_pool")
    shot = detail.shots[0]
    actor = shot.actors[0]
    hair = next(row for row in actor.attributes if row.kind == AttributeKind.HAIR_COLOR)
    red = replace(actor, actor_id="other-actor", attributes=(replace(hair, value="red"),))
    environment = replace(
        hair, kind=AttributeKind.ENVIRONMENT, value="outdoors", part_id="environment"
    )
    detail = replace(
        detail, shots=(replace(shot, actors=(actor, red), environment=(environment,)),)
    )
    identity = refinement_identity_for_profile("v2")
    settings = refinement_settings_for_profile("v2")
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=identity, settings=settings
    ).request
    corpus = build_saved_detail_corpus(
        (timeline,),
        lambda *_: (request, detail),
        profile="v2",
        identity=identity,
        settings=settings,
    )
    assert corpus.manifest["version"] == VERSION
    assert corpus.manifest["semanticFacetCount"] == 3
    record = corpus.evidence[detail.candidate_id]
    facets = corpus.manifest["semanticFacets"]
    assert {row["actorId"] for row in facets} == {None, actor.actor_id, "other-actor"}
    for facet in facets:
        attrs = [record["attributes"][index] for index in facet["attributeIndexes"]]
        assert all(
            row["shotId"] == facet["shotId"] and row["actorId"] == facet["actorId"] for row in attrs
        )
        assert all(row["status"] == "observed" and row["evidenceIds"] for row in attrs)
        assert facet["facts"] == list(dict.fromkeys(row["text"] for row in attrs))
    assert not any(
        "staff" in text for row in corpus.supplement.semantic_facets for text in row.facts
    )


@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
@pytest.mark.parametrize("copies", [1, 5])
def test_focused_scores_cross_threshold_without_duplicate_candidates_or_extra_rrf_votes(
    request, mode, copies
):
    project, timeline, _, _ = request.getfixturevalue("detail_pool")
    before = snapshot(project)
    corpus = read_saved_detail_corpus(project, (timeline,), "v2")
    first = corpus.supplement.semantic_facets[0]
    facets = tuple(replace(first, facet_id=f"facet-{index:024x}") for index in range(copies))
    supplement = replace(corpus.supplement, semantic_facets=facets)
    provider = FocusedEmbedding([first.facts])
    result = asyncio.run(
        search_timelines(
            (timeline,), "white hair", mode=mode, embedding_provider=provider, supplement=supplement
        )
    )
    assert len(result.candidates) == 1
    candidate = result.candidates[0].clip
    assert candidate.score == pytest.approx(0.95 if mode == "semantic" else 2 / 61)
    assert candidate.observable_facts == timeline.events[0].observable_facts
    assert candidate.evidence_ids == tuple(sorted(timeline.events[0].evidence_ids))
    assert candidate.source_range == timeline.events[0].source_range
    assert result.semantic_detail_matches == ((candidate.candidate_id, facets[0].facet_id),)
    assert len(provider.texts) == 1 + len(timeline.events) + copies
    assert snapshot(project) == before


@pytest.mark.parametrize(
    "invalid", ["foreign", "duplicate", "invented", "empty", "long", "too_many", "legacy"]
)
def test_invalid_facet_scope_or_text_refuses_before_embedding(request, invalid):
    project, timeline, _, _ = request.getfixturevalue("detail_pool")
    before = snapshot(project)
    corpus = read_saved_detail_corpus(project, (timeline,), "v2")
    facet = corpus.supplement.semantic_facets[0]
    rows = (facet,)
    version = VERSION
    if invalid == "foreign":
        rows = (replace(facet, candidate_id="another-candidate"),)
    elif invalid == "duplicate":
        rows = (facet, facet)
    elif invalid == "invented":
        rows = (replace(facet, facts=("invented observed staff",)),)
    elif invalid == "empty":
        rows = (replace(facet, facts=()),)
    elif invalid == "long":
        rows = (replace(facet, facts=facet.facts * 1000),)
    elif invalid == "too_many":
        rows = tuple(replace(facet, facet_id=f"facet-{index:024x}") for index in range(20_001))
    else:
        version = LEGACY_VERSION
    supplement = replace(corpus.supplement, projection_version=version, semantic_facets=rows)
    provider = FocusedEmbedding([facet.facts])
    with pytest.raises(AppError) as caught:
        asyncio.run(
            search_timelines(
                (timeline,),
                "white hair",
                mode="semantic",
                embedding_provider=provider,
                supplement=supplement,
            )
        )
    assert caught.value.code == "retrieval.supplement"
    assert not provider.texts and snapshot(project) == before


def test_legacy_saved_search_still_revalidates_original_manifest_without_borrowing_new_projection(
    request, monkeypatch, tmp_path
):
    project, timeline, _, _ = request.getfixturevalue("detail_pool")
    reader = cli.read_saved_detail_corpus
    monkeypatch.setattr(
        cli,
        "read_saved_detail_corpus",
        lambda project, timelines, profile: reader(
            project, timelines, profile, version=LEGACY_VERSION
        ),
    )
    run_ids = (timeline.run.run_id,)
    old = asyncio.run(
        cli.execute_project_search(
            project, run_ids, "white hair", tmp_path, mode="lexical", detail_profile="v2"
        )
    )
    assert old["detailRetrieval"]["version"] == LEGACY_VERSION
    assert "semanticFacets" not in old["detailRetrieval"]
    monkeypatch.setattr(cli, "read_saved_detail_corpus", reader)
    old_match = asyncio.run(
        cli.execute_search_detail_match(
            project,
            old["searchId"],
            search_snapshot_sha256(old),
            json.dumps(manifest()),
            profile="v2",
        )
    )
    assert old_match["search"] == old
    new = asyncio.run(
        cli.execute_project_search(
            project, run_ids, "white hair", tmp_path, mode="lexical", detail_profile="v2"
        )
    )
    assert new["detailRetrieval"]["version"] == VERSION
    assert new["detailRetrieval"]["snapshotSha256"] != old["detailRetrieval"]["snapshotSha256"]
    assert read_project_search(project, old["searchId"]) == old


@pytest.mark.parametrize(
    "field,value",
    [
        ("semanticDetailFacetId", "facet-" + "f" * 24),
        ("semanticDetailFacetId", []),
        ("semanticDetailFacetId", False),
        ("version", []),
        ("version", "latest"),
    ],
)
def test_cli_records_winning_group_and_refuses_foreign_group_provenance(
    request, monkeypatch, tmp_path, field, value
):
    project, timeline, _, _ = request.getfixturevalue("detail_pool")
    corpus = read_saved_detail_corpus(project, (timeline,), "v2")
    monkeypatch.setattr(
        cli.LocalEmbeddingProvider,
        "from_manifest",
        lambda _: FocusedEmbedding([row.facts for row in corpus.supplement.semantic_facets]),
    )
    result = asyncio.run(
        cli.execute_project_search(
            project,
            (timeline.run.run_id,),
            "white hair",
            tmp_path,
            mode="semantic",
            detail_profile="v2",
        )
    )
    row = result["candidates"][0]
    assert row["semanticDetailFacetId"] == corpus.supplement.semantic_facets[0].facet_id
    assert result["retrievalVersion"].endswith("-saved-details-v2")
    if field == "version":
        result["detailRetrieval"]["version"] = value
    else:
        row[field] = value
    result["searchId"] = "c" * 32
    write_project_search(project, result)
    with pytest.raises(AppError) as caught:
        asyncio.run(
            cli.execute_search_detail_match(
                project,
                result["searchId"],
                search_snapshot_sha256(result),
                json.dumps(manifest()),
                profile="v2",
            )
        )
    assert caught.value.code == "retrieval.detail_snapshot"
