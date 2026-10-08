"""Optional observed-attribute ranking text preserves sources and refuses stale detail corpora."""

import asyncio
import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from test_detail_inspection import refuse_sends
from test_detail_parts import visible_parts
from test_detail_query import manifest, publish_v2_fixture, snapshot
from test_detail_temporal_provider import temporal_model
from test_inspection_http import get, workspace
from test_project_detail_query import create_detail_pool
from test_retrieval import META, SPACE

from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash
from gamingcreator.application.detail_retrieval import build_saved_detail_corpus
from gamingcreator.application.providers import ProviderResult, ProviderStatus
from gamingcreator.application.retrieval import CandidateText, RetrievalSupplement, search_timelines
from gamingcreator.application.search_detail_query import search_snapshot_sha256
from gamingcreator.cli import main as cli
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.models import Embedding
from gamingcreator.infrastructure.deepseek_detail_parts import parse_parts_detail
from gamingcreator.infrastructure.deepseek_detail_temporal import parse_temporal_detail
from gamingcreator.infrastructure.detail_query_sidecar import (
    read_saved_detail_corpus,
    refinement_identity_for_profile,
    refinement_settings_for_profile,
)
from gamingcreator.infrastructure.project_search_files import (
    read_project_search,
    write_project_search,
)


class WhiteHairEmbedding:
    """Deterministic transport fixture, not evidence of real E5 quality."""

    def __init__(self):
        self.texts = []

    async def embed(self, request, context):
        self.texts = request.texts
        embeddings = tuple(
            Embedding(
                f"{request.run_id}:{index}",
                SPACE,
                (1.0, 0.0) if "white hair" in text else (0.0, 1.0),
                hashlib.sha256(text.encode()).hexdigest(),
            )
            for index, text in enumerate(request.texts)
        )
        return ProviderResult(ProviderStatus.COMPLETED, embeddings, META)


def corpus_for(timeline, detail):
    identity = refinement_identity_for_profile("v2")
    settings = refinement_settings_for_profile("v2")
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=identity, settings=settings
    ).request
    return build_saved_detail_corpus(
        (timeline,),
        lambda source, event: (request, detail),
        profile="v2",
        identity=identity,
        settings=settings,
    )


@pytest.fixture
def detail_pool(tmp_path, monkeypatch):
    project, timeline, _ = create_detail_pool(tmp_path)
    target, detail = publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    return project, timeline, target, detail


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_all_modes_discover_attributes_absent_from_base_text_without_changing_facts(
    detail_pool, mode
):
    project, timeline, _, _ = detail_pool
    before = snapshot(project)
    index = read_saved_detail_corpus(project, (timeline,), "v2")
    original = asyncio.run(
        search_timelines(
            (timeline,), "white hair", mode=mode, embedding_provider=WhiteHairEmbedding()
        )
    )
    assert not original.candidates
    provider = WhiteHairEmbedding()
    augmented = asyncio.run(
        search_timelines(
            (timeline,),
            "white hair",
            mode=mode,
            embedding_provider=provider,
            supplement=index.supplement,
        )
    )
    assert len(augmented.candidates) == 1
    clip = augmented.candidates[0].clip
    assert clip.observable_facts == timeline.events[0].observable_facts
    assert clip.evidence_ids == tuple(sorted(timeline.events[0].evidence_ids))
    assert clip.source_range == timeline.events[0].source_range
    assert "saved-details-v3" in augmented.retrieval_version
    assert augmented.scope_id != original.scope_id
    assert index.manifest["indexedEvents"] == 1
    assert all(
        row["kind"] == "hair_color" for row in index.evidence[clip.candidate_id]["attributes"]
    )
    assert not any("staff" in text for row in index.supplement.candidates for text in row.facts)
    if mode != "lexical":
        assert "white hair" not in provider.texts[1]
        assert any("white hair" in text for text in provider.texts[1 + len(timeline.events) :])
    assert snapshot(project) == before


def test_uncertain_and_free_actor_description_are_not_positive_ranking_text(detail_pool):
    project, timeline, _, _ = detail_pool
    index = read_saved_detail_corpus(project, (timeline,), "v2")
    for query in ("staff", "法杖", "onerror", "detailInjected"):
        result = asyncio.run(
            search_timelines((timeline,), query, mode="lexical", supplement=index.supplement)
        )
        assert not result.candidates


def test_overlapping_exclusive_observed_values_are_excluded_within_one_part(detail_pool):
    _, timeline, _, detail = detail_pool
    shot = detail.shots[0]
    actor = shot.actors[0]
    hair = actor.attributes[0]
    conflicting = replace(actor, attributes=(*actor.attributes, replace(hair, value="black")))
    index = corpus_for(timeline, replace(detail, shots=(replace(shot, actors=(conflicting,)),)))
    assert index.manifest["publishedRefinements"] == 1 and index.manifest["indexedEvents"] == 0
    assert not index.supplement.candidates


@pytest.mark.parametrize(
    "field,value",
    [
        ("configuration_hash", "f" * 64),
        ("media_sha256", "f" * 64),
        ("detail_identity_hash", "f" * 64),
    ],
)
def test_wrong_source_or_profile_refinement_never_enters_corpus(detail_pool, field, value):
    _, timeline, _, detail = detail_pool
    with pytest.raises(AppError) as caught:
        corpus_for(timeline, replace(detail, **{field: value}))
    assert caught.value.code == "retrieval.detail_source"


def test_missing_exact_profile_retains_base_corpus_and_creates_nothing(detail_pool):
    project, timeline, _, _ = detail_pool
    before = snapshot(project)
    index = read_saved_detail_corpus(project, (timeline,), "v4")
    assert not index.supplement.candidates and index.manifest["publishedRefinements"] == 0
    base = asyncio.run(search_timelines((timeline,), "白色", mode="lexical"))
    extra = asyncio.run(
        search_timelines((timeline,), "白色", mode="lexical", supplement=index.supplement)
    )
    assert extra.candidates == base.candidates
    assert snapshot(project) == before


@pytest.mark.parametrize("profile", ["v1", "v3", "v4"])
def test_each_exact_profile_uses_its_validated_observed_projection(detail_pool, profile):
    _, timeline, _, detail = detail_pool
    identity = refinement_identity_for_profile(profile)
    settings = refinement_settings_for_profile(profile)
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=identity, settings=settings
    ).request
    if profile == "v1":
        detail = replace(detail, detail_identity_hash=identity.prompt_hash)
    elif profile == "v3":
        detail = parse_parts_detail(json.dumps(visible_parts(request)), request)
    else:
        detail = parse_temporal_detail(json.dumps(temporal_model(request)), request)
    corpus = build_saved_detail_corpus(
        (timeline,),
        lambda source, event: (request, detail),
        profile=profile,
        identity=identity,
        settings=settings,
    )
    assert (
        corpus.manifest["profile"] == profile
        and corpus.manifest["promptHash"] == identity.prompt_hash
    )
    assert corpus.manifest["indexedEvents"] == 1
    evidence = corpus.evidence[detail.candidate_id]["attributes"]
    assert all(row["status"] == "observed" for row in evidence)
    if profile == "v4":
        assert {row["actorId"] for row in evidence} == {"actor-1"}
        assert {row["kind"] for row in evidence} == {"hair_color", "held_shape"}


@pytest.mark.parametrize("uncertain", ["owner", "classification"])
def test_temporal_uncertain_ownership_or_object_classification_never_supplies_positive_held_text(
    detail_pool, uncertain
):
    _, timeline, _, _ = detail_pool
    identity = refinement_identity_for_profile("v4")
    settings = refinement_settings_for_profile("v4")
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=identity, settings=settings
    ).request
    model = temporal_model(request)
    if uncertain == "owner":
        model["owners"][0]["status"] = "uncertain"
    else:
        model["entities"][1]["classification"]["status"] = "uncertain"
    detail = parse_temporal_detail(json.dumps(model), request)
    corpus = build_saved_detail_corpus(
        (timeline,),
        lambda source, event: (request, detail),
        profile="v4",
        identity=identity,
        settings=settings,
    )
    assert {row["kind"] for row in corpus.evidence[detail.candidate_id]["attributes"]} == {
        "hair_color"
    }


def test_unknown_candidate_supplement_refuses_before_embedding(detail_pool):
    _, timeline, _, _ = detail_pool
    extra = RetrievalSupplement("a" * 64, (CandidateText("other", ("white hair",)),))
    with pytest.raises(AppError) as caught:
        asyncio.run(search_timelines((timeline,), "white hair", mode="semantic", supplement=extra))
    assert caught.value.code == "retrieval.supplement"


def test_oversized_event_scope_refuses_before_reading_any_sidecar(detail_pool):
    _, timeline, _, _ = detail_pool
    oversized = replace(timeline, events=timeline.events * 20001)

    def forbidden(*args):
        raise AssertionError("Do not start partial corpus reads beyond the limit")

    with pytest.raises(AppError) as caught:
        build_saved_detail_corpus(
            (oversized,),
            forbidden,
            profile="v2",
            identity=refinement_identity_for_profile("v2"),
            settings=refinement_settings_for_profile("v2"),
        )
    assert caught.value.code == "retrieval.detail_source"


def search(project, tmp_path, **kwargs):
    return asyncio.run(
        cli.execute_project_search(
            project, ["run-1", "run-2"], "white hair", tmp_path, mode="lexical", **kwargs
        )
    )


def test_saved_ranking_and_matching_keep_exact_index_snapshot_with_only_two_new_files(
    detail_pool, tmp_path
):
    project, timeline, _, _ = detail_pool
    before = snapshot(project)
    saved = search(project, tmp_path, detail_profile="v2")
    assert len(saved["candidates"]) == 1
    assert saved == read_project_search(project, saved["searchId"])
    assert saved["detailRetrieval"]["profile"] == "v2"
    assert saved["candidates"][0]["observableFacts"] == list(timeline.events[0].observable_facts)
    after_search = snapshot(project)
    assert set(after_search) - set(before) == {
        str(saved_file.relative_to(project))
        for saved_file in (project / "project-searches" / saved["searchId"]).iterdir()
    }
    assert len(set(after_search) - set(before)) == 2
    assert all(after_search[path] == value for path, value in before.items())
    matched = asyncio.run(
        cli.execute_search_detail_match(
            project,
            saved["searchId"],
            search_snapshot_sha256(saved),
            json.dumps(manifest()),
            profile="v2",
        )
    )
    assert matched["search"] == saved and matched["counts"]["full"] == 1
    assert matched["humanLabels"] is None and matched["qualityGate"] is None
    assert snapshot(project) == after_search


def test_changed_valid_detail_corpus_refuses_annotation_of_old_ranking(detail_pool, tmp_path):
    project, _, target, detail = detail_pool
    saved = search(project, tmp_path, detail_profile="v2")
    shot = detail.shots[0]
    actor = shot.actors[0]
    changed = replace(
        detail,
        shots=(
            replace(
                shot,
                actors=(
                    replace(
                        actor,
                        attributes=(
                            replace(actor.attributes[0], value="black"),
                            *actor.attributes[1:],
                        ),
                    ),
                ),
            ),
        ),
    )
    payload = json.loads((target / "result.json").read_bytes())
    payload.update(payloadHash=payload_hash(changed), payloadJson=canonical_detail_json(changed))
    (target / "result.json").write_text(json.dumps(payload))
    before = snapshot(project)
    with pytest.raises(AppError) as caught:
        asyncio.run(
            cli.execute_search_detail_match(
                project,
                saved["searchId"],
                search_snapshot_sha256(saved),
                json.dumps(manifest()),
                profile="v4",
            )
        )
    assert caught.value.code == "retrieval.detail_snapshot"
    assert snapshot(project) == before


def test_tampered_index_attributes_even_with_valid_search_receipt_are_refused(
    detail_pool, tmp_path
):
    project, _, _, _ = detail_pool
    saved = search(project, tmp_path, detail_profile="v2")
    saved = json.loads(json.dumps(saved))
    saved["searchId"] = uuid4().hex
    saved["candidates"][0]["detailSearchEvidence"]["attributes"][0]["value"] = "black"
    write_project_search(project, saved)
    with pytest.raises(AppError) as caught:
        asyncio.run(
            cli.execute_search_detail_match(
                project,
                saved["searchId"],
                search_snapshot_sha256(saved),
                json.dumps(manifest()),
                profile="v2",
            )
        )
    assert caught.value.code == "retrieval.detail_snapshot"


@pytest.mark.parametrize("profile", ["v2", "latest", None, True])
def test_http_optional_profile_is_explicit_and_preserves_legacy_request(
    detail_pool, tmp_path, profile
):
    project, _, _, _ = detail_pool
    payload = {
        "project": str(project),
        "runs": ["run-1", "run-2"],
        "query": "white hair",
        "mode": "lexical",
        "top": 10,
        "detailProfile": profile,
    }
    with workspace(tmp_path) as base:
        status, _, data = get(
            base,
            "/api/search-project",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        if profile == "v2":
            assert status == 200 and len(json.loads(data)["candidates"]) == 1
        else:
            assert status == 400
        del payload["detailProfile"]
        status, _, data = get(
            base,
            "/api/search-project",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert status == 200 and not json.loads(data)["candidates"]
        assert "detailRetrieval" not in json.loads(data)
