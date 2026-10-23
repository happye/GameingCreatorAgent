"""Static declarations are local imports on registered frames; synthetic fixtures only."""

import asyncio
import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest
from test_detail_action_eligibility import eligible_request
from test_temporal_frame_contract import action_event, schema_detail
from test_temporal_frame_contract import analyze as analyze_vision

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import (
    CostStatus,
    InvocationMetadata,
    ProviderUsage,
)
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observations import (
    StaticCollectionArtifact,
    build_static_collection_artifact,
)
from gamingcreator.application.storage import (
    InvocationStatus,
    RunConfiguration,
    RunStatus,
    StoredRun,
    StoredTimeline,
)
from gamingcreator.cli.main import main
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.static_observations import (
    MAX_STATIC_PACKAGE_BYTES,
    STATIC_OBSERVATION_SCHEMA_VERSION,
    STATIC_QUERY_SCHEMA_VERSION,
    StaticObservationError,
    UnsupportedStaticSchema,
    canonical_package_json,
    observation_id,
    package_sha256,
)
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.deepseek_vision import (
    PROMPT_VERSION,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    PROMPT_VERSION_V5,
    PROMPT_VERSION_V6,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_codec import (
    loads_static_package,
    loads_static_query,
)
from gamingcreator.infrastructure.static_observation_store import (
    SqliteStaticObservationStore,
)

PIPELINE_HASH = "b" * 64
CONFIG = RunConfiguration(
    AnalysisConfig("fixture", "fixture-model", 20, 100),
    Decimal("1.0"),
    "fixture-pipeline-v1",
    PIPELINE_HASH,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(root: Path, run_id: str = "run-1", *, images: int = 2) -> MediaPreprocessingResult:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.fixture"
    source.write_bytes(b"synthetic source bytes; not a real recording")
    streams = (MediaStream(0, "video", Fraction(1, 1000), 1000, 2000),)
    asset = MediaAsset(
        "media-1",
        source.resolve(),
        sha(source),
        streams,
        Fraction(1),
        2_000_000,
        "fixture-probe-v1",
    )
    directory = root / "project" / "runs" / run_id / "media"
    directory.mkdir(parents=True, exist_ok=True)
    visual: list[VisualEvidence] = []
    for index in range(images):
        path = directory / f"frame-{index}.png"
        path.write_bytes(f"synthetic registered frame {index}".encode())
        visual.append(
            VisualEvidence(
                f"{run_id}:{asset.media_id}:image:{index:06d}",
                path.resolve(),
                sha(path),
                1100 + index * 400,
                Fraction(1, 1000),
                SourceInstant(100_000 + index * 400_000, asset.duration_us),
            )
        )
    bundle = MediaPreprocessingResult(
        asset,
        tuple(visual),
        None,
        directory / "media-manifest.json",
        "fixture-v1",
        "fixture-processor",
    )
    write_manifest(bundle, SamplingParameters())
    return bundle


async def _create_run(
    project: Path,
    bundle: MediaPreprocessingResult,
    run_id: str,
    *,
    complete: bool,
    coverage_gap: bool,
    invocation: bool,
) -> None:
    store = await SqliteTimelineStore.open(project)
    try:
        await store.create_run(run_id, bundle.asset, CONFIG)
        await store.begin_stage(run_id, "media", bundle.asset.sha256)
        await store.persist_media_bundle(run_id, bundle)
        await store.begin_stage(run_id, "vision", PIPELINE_HASH)
        if invocation:
            metadata = InvocationMetadata(
                "fixture",
                "fixture-model",
                None,
                None,
                "fixture-prompt",
                "fixture-schema",
                1,
                ProviderUsage(
                    original_cost=Decimal("0.25"),
                    currency="CNY",
                    cost_cny=Decimal("0.25"),
                    cost_status=CostStatus.ESTIMATED,
                ),
            )
            planned = replace(metadata, usage=ProviderUsage(), elapsed_ms=None)
            await store.begin_invocation("attempt-1", run_id, "vision", "window-1", planned)
            await store.finish_invocation("attempt-1", InvocationStatus.COMPLETED, metadata)
        if coverage_gap:
            await store.stop_run(run_id, RunStatus.FAILED, "analysis.coverage_gap")
        elif complete:
            await store.persist_timeline(run_id, "vision", (), (), PIPELINE_HASH)
            await store.complete_run(run_id)
    finally:
        await store.close()


def create_project(
    root: Path,
    run_id: str = "run-1",
    *,
    images: int = 2,
    complete: bool = True,
    coverage_gap: bool = False,
    invocation: bool = False,
) -> tuple[Path, MediaPreprocessingResult]:
    root.mkdir(parents=True, exist_ok=True)
    bundle = build_bundle(root, run_id, images=images)
    project = root / "project"
    asyncio.run(
        _create_run(
            project,
            bundle,
            run_id,
            complete=complete,
            coverage_gap=coverage_gap,
            invocation=invocation,
        )
    )
    return project, bundle


async def _run_identity(project: Path, run_id: str) -> StoredRun:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await store.load_run(run_id)
    finally:
        await store.close()


def condition(kind: str, value: str, part_group: str) -> dict[str, str]:
    return {"kind": kind, "value": value, "partGroup": part_group}


def default_conditions() -> list[dict[str, str]]:
    return [
        condition("hair_color", "black", "head"),
        condition("clothing_color", "red", "torso"),
        condition("clothing_shape", "coat", "torso"),
        condition("held_shape", "long_rod", "hand"),
        condition("held_class", "weapon", "hand"),
    ]


def default_observations(bundle: MediaPreprocessingResult) -> list[dict[str, object]]:
    return [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": [
                {
                    "actorId": "actor-a",
                    "attributes": [
                        {
                            "partGroup": "head",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "black",
                            "status": "observed",
                        },
                        {
                            "partGroup": "torso",
                            "partId": "torso",
                            "kind": "clothing_color",
                            "value": "red",
                            "status": "observed",
                        },
                        {
                            "partGroup": "torso",
                            "partId": "torso",
                            "kind": "clothing_shape",
                            "value": "coat",
                            "status": "observed",
                        },
                        {
                            "partGroup": "hand",
                            "partId": "hand",
                            "kind": "held_shape",
                            "value": "long_rod",
                            "status": "observed",
                        },
                        {
                            "partGroup": "hand",
                            "partId": "hand",
                            "kind": "held_class",
                            "value": "weapon",
                            "status": "observed",
                        },
                    ],
                }
            ],
        }
    ]


def standalone_package(
    bundle: MediaPreprocessingResult,
    *,
    observations: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schemaVersion": STATIC_OBSERVATION_SCHEMA_VERSION,
        "runId": "run-1",
        "collectionId": "look-1",
        "mediaId": bundle.asset.media_id,
        "sourceSha256": bundle.asset.sha256,
        "configHash": "d" * 64,
        "pipelineVersion": "fixture-pipeline-v1",
        "pipelineHash": PIPELINE_HASH,
        "provenance": {
            "sourceNote": "Synthetic local declaration for offline tests.",
            "sourcePayloadSha256": "c" * 64,
            "sourcePayloadVersion": "fixture-source-v1",
        },
        "observations": observations if observations is not None else default_observations(bundle),
    }
    document.update(overrides)
    return document


def package_document(
    project: Path,
    bundle: MediaPreprocessingResult,
    run_id: str = "run-1",
    collection_id: str = "look-1",
    observations: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict[str, object]:
    run = asyncio.run(_run_identity(project, run_id))
    document: dict[str, object] = standalone_package(
        bundle,
        observations=observations,
        runId=run_id,
        collectionId=collection_id,
    )
    document["sourceSha256"] = run.asset.sha256
    document["configHash"] = run.config_hash
    document["pipelineVersion"] = run.configuration.pipeline_version
    document["pipelineHash"] = run.configuration.pipeline_hash
    document.update(overrides)
    return document


def query_document(
    collection_id: str = "look-1",
    conditions: list[dict[str, str]] | None = None,
    run_id: str = "run-1",
) -> dict[str, object]:
    return {
        "schemaVersion": STATIC_QUERY_SCHEMA_VERSION,
        "runId": run_id,
        "collectionId": collection_id,
        "actorAll": conditions if conditions is not None else default_conditions(),
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _invoke_main(
    capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, dict[str, object] | None, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    document = json.loads(captured.out) if captured.out.strip() else None
    return code, document, captured.err


def import_static(
    project: Path,
    package_path: Path,
    capsys: pytest.CaptureFixture[str],
    run_id: str = "run-1",
    collection_id: str = "look-1",
) -> tuple[int, dict[str, object] | None, str]:
    return _invoke_main(
        capsys,
        "import-static-observations",
        "--project",
        str(project),
        "--run",
        run_id,
        "--collection",
        collection_id,
        "--input",
        str(package_path),
    )


def search_static(
    project: Path,
    query_path: Path,
    capsys: pytest.CaptureFixture[str],
    run_id: str = "run-1",
    collection_id: str = "look-1",
) -> tuple[int, dict[str, object] | None, str]:
    return _invoke_main(
        capsys,
        "search-static-observations",
        "--project",
        str(project),
        "--run",
        run_id,
        "--collection",
        collection_id,
        "--input",
        str(query_path),
    )


def error_code(stderr: str) -> str:
    return cast(str, json.loads(stderr)["code"])


def collection_artifact(project: Path, package_path: Path) -> StaticCollectionArtifact:
    async def load_timeline() -> StoredTimeline:
        reader = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await load_searchable_timeline(reader, "run-1")
        finally:
            await reader.close()

    return build_static_collection_artifact(
        loads_static_package(package_path.read_bytes()),
        asyncio.run(load_timeline()),
    )


def test_codec_is_strict_about_versions_bounds_duplicates_and_forbidden_fields(
    tmp_path: Path,
) -> None:
    bundle = build_bundle(tmp_path, images=1)
    package = standalone_package(bundle)
    parsed = loads_static_package(json.dumps(package).encode())
    assert len(parsed.observations) == 1
    assert len(parsed.observations[0].actors[0].attributes) == 5
    assert (
        json.loads(canonical_package_json(parsed))["observations"][0]["actors"][0]["actorId"]
        == "actor-a"
    )
    without_pipeline_hash = json.loads(json.dumps(package))
    without_pipeline_hash.pop("pipelineHash")
    assert loads_static_package(json.dumps(without_pipeline_hash).encode()).pipeline_hash is None
    reordered = json.loads(json.dumps(package))
    reordered["observations"][0]["actors"][0]["attributes"].reverse()
    assert package_sha256(loads_static_package(json.dumps(reordered).encode())) == package_sha256(
        parsed
    )

    def reject(document: dict[str, object]) -> None:
        with pytest.raises(StaticObservationError):
            loads_static_package(json.dumps(document).encode())

    action = json.loads(json.dumps(package))
    action["observations"][0]["actors"][0]["attributes"][0]["kind"] = "action"
    reject(action)

    environment = json.loads(json.dumps(package))
    environment["observations"][0]["actors"][0]["attributes"][0]["kind"] = "environment"
    reject(environment)

    path_field = json.loads(json.dumps(package))
    path_field["observations"][0]["path"] = "outside.png"
    reject(path_field)

    time_field = json.loads(json.dumps(package))
    time_field["observations"][0]["sourceUs"] = 100_000
    reject(time_field)

    with pytest.raises(StaticObservationError):
        loads_static_package(b'{"schemaVersion":"a","schemaVersion":"b"}')
    with pytest.raises(StaticObservationError):
        loads_static_package(b" " * (MAX_STATIC_PACKAGE_BYTES + 1))
    with pytest.raises(UnsupportedStaticSchema):
        loads_static_package(
            json.dumps({**package, "schemaVersion": "static-observation-import-v2"}).encode()
        )
    with pytest.raises(StaticObservationError):
        loads_static_package(json.dumps({**package, "observations": []}).encode())

    actors = json.loads(json.dumps(package))
    actors["observations"][0]["actors"] = [
        {"actorId": f"actor-{index}", "attributes": []} for index in range(9)
    ]
    reject(actors)

    attributes = json.loads(json.dumps(package))
    attributes["observations"][0]["actors"][0]["attributes"] = [
        {
            "partGroup": "head",
            "partId": "head",
            "kind": "hair_color",
            "value": "black",
            "status": "observed",
        }
        for _ in range(17)
    ]
    reject(attributes)

    observations = json.loads(json.dumps(package))
    observations["observations"] = observations["observations"] * 129
    reject(observations)

    query = query_document()
    parsed_query = loads_static_query(json.dumps(query).encode())
    assert len(parsed_query.constraint.actor_all) == 5
    for forbidden in (
        [condition("action", "run", "body")],
        [condition("effect", "light_ring", "body")],
        [condition("environment", "water", "scene")],
    ):
        with pytest.raises(StaticObservationError):
            loads_static_query(json.dumps(query_document(conditions=forbidden)).encode())
    duplicate = default_conditions()
    duplicate.append(duplicate[0])
    with pytest.raises(ValueError):
        loads_static_query(json.dumps(query_document(conditions=duplicate)).encode())
    with pytest.raises(StaticObservationError):
        loads_static_query(
            json.dumps(
                {**query, "environmentAll": [condition("environment", "water", "scene")]}
            ).encode()
        )
    with pytest.raises(UnsupportedStaticSchema):
        loads_static_query(
            json.dumps({**query, "schemaVersion": "static-observation-query-v2"}).encode()
        )


def test_real_completed_empty_event_run_imports_and_searches_static_single_frame(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    package_path = tmp_path / "package.json"
    package_document_value = package_document(project, bundle)
    write_json(package_path, package_document_value)
    timeline_hash = sha(project / "timeline.sqlite3")

    code, imported, stderr = import_static(project, package_path, capsys)
    assert (code, stderr) == (0, "")
    assert imported is not None
    assert imported["status"] == "created"
    package = loads_static_package(package_path.read_bytes())
    assert imported["collectionSha256"] == package_sha256(package)
    assert imported["observationCount"] == 1
    assert imported["actorCount"] == 1
    assert imported["localPaidRequestsSent"] == 0
    assert imported["sourceCostCny"] is None and imported["sourceCostStatus"] == "unknown"
    assert imported["visualVerified"] is None
    assert imported["humanLabels"] is None
    assert imported["qualityGate"] is None
    assert imported["f006Passed"] is imported["f009Passed"] is imported["f010Passed"] is False
    assert sha(project / "timeline.sqlite3") == timeline_hash
    assert (project / "static-observations.sqlite3").is_file()

    expected_id = observation_id(package, package.observations[0])
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    code, searched, stderr = search_static(project, query_path, capsys)
    assert (code, stderr) == (0, "")
    assert searched is not None
    assert searched["matchCount"] == 1
    assert searched["collectionSha256"] == imported["collectionSha256"]
    assert searched["provenance"] == package_document_value["provenance"]
    assert searched["sourcePath"] == str(bundle.asset.source_path)
    assert searched["sourceSha256"] == bundle.asset.sha256
    match = cast(list[dict[str, object]], searched["matches"])[0]
    assert match["kind"] == "static_appearance"
    assert match["observationId"] == expected_id
    assert match["actorId"] == "actor-a"
    assert match["evidenceId"] == bundle.images[0].evidence_id
    assert match["sourceTimeUs"] == 100_000
    assert match["sourceRange"] == {
        "startUs": 100_000,
        "endUs": 100_001,
        "durationUs": 2_000_000,
    }
    assert match["imageSha256"] == bundle.images[0].sha256
    assert match["artifactPath"] == str(bundle.images[0].path.resolve())
    assert match["sourcePath"] == str(bundle.asset.source_path)
    supports = cast(list[dict[str, object]], match["supportedAttributes"])
    assert {
        (item["kind"], item["value"], item["partGroup"], item["partId"]) for item in supports
    } == {
        ("hair_color", "black", "head", "head"),
        ("clothing_color", "red", "torso", "torso"),
        ("clothing_shape", "coat", "torso", "torso"),
        ("held_shape", "long_rod", "hand", "hand"),
        ("held_class", "weapon", "hand", "hand"),
    }
    assert all(item["evidenceId"] == bundle.images[0].evidence_id for item in supports)

    legacy_path = tmp_path / "legacy-query.json"
    write_json(
        legacy_path,
        {
            "schemaVersion": "actor-detail-query-schema-v1",
            "version": "actor-detail-query-v1",
            "vocabularyVersion": "actor-detail-vocabulary-v1",
            "actorAll": default_conditions(),
            "environmentAll": [],
        },
    )
    code, legacy, stderr = search_static(project, legacy_path, capsys)
    assert (code, stderr) == (0, "") and legacy is not None
    assert legacy["matchCount"] == 1
    scope_free_path = tmp_path / "scope-free-query.json"
    write_json(
        scope_free_path,
        {
            "schemaVersion": STATIC_QUERY_SCHEMA_VERSION,
            "actorAll": default_conditions(),
        },
    )
    code, scope_free, stderr = search_static(project, scope_free_path, capsys)
    assert (code, stderr) == (0, "") and scope_free is not None
    assert scope_free["matchCount"] == 1
    write_json(
        legacy_path,
        {
            "schemaVersion": "actor-detail-query-schema-v1",
            "version": "actor-detail-query-v1",
            "vocabularyVersion": "actor-detail-vocabulary-v1",
            "actorAll": [condition("action", "run", "body")],
            "environmentAll": [],
        },
    )
    code, _, stderr = search_static(project, legacy_path, capsys)
    assert code == 2 and error_code(stderr) == "input.static_observation"

    missing = default_conditions()
    missing[0] = condition("hair_color", "purple", "head")
    write_json(query_path, query_document(conditions=missing))
    code, searched, stderr = search_static(project, query_path, capsys)
    assert (code, stderr) == (0, "")
    assert searched is not None and searched["matchCount"] == 0

    write_json(query_path, query_document(conditions=[condition("action", "run", "body")]))
    code, _, stderr = search_static(project, query_path, capsys)
    assert code == 2 and error_code(stderr) == "input.static_observation"

    action_package = json.loads(json.dumps(package_document_value))
    action_package["observations"][0]["actors"][0]["attributes"][0]["kind"] = "action"
    action_path = tmp_path / "action-package.json"
    write_json(action_path, action_package)
    code, _, stderr = import_static(project, action_path, capsys, collection_id="bad-action")
    assert code == 2 and error_code(stderr) == "input.static_observation"

    async def reload() -> object:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await store.load_completed_timeline("run-1")
        finally:
            await store.close()

    timeline = asyncio.run(reload())
    assert timeline.events == ()


def test_package_without_optional_pipeline_hash_roundtrips_through_the_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    document = package_document(project, bundle)
    document.pop("pipelineHash")
    package_path = tmp_path / "package-without-pipeline-hash.json"
    write_json(package_path, document)
    code, imported, stderr = import_static(project, package_path, capsys)
    assert (code, stderr) == (0, "") and imported is not None
    assert imported["status"] == "created"
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    code, searched, stderr = search_static(project, query_path, capsys)
    assert (code, stderr) == (0, "") and searched is not None
    assert searched["matchCount"] == 1


def test_old_v6_single_frame_action_boundary_stays_rejected(tmp_path: Path) -> None:
    request = eligible_request(tmp_path, frames=9)
    request = replace(
        request,
        evidence=tuple(
            replace(item, source_time=SourceInstant(31_500_000 + index * 500_000, 54_743_220))
            for index, item in enumerate(request.evidence)
        ),
    )
    appearance = dict(
        action_event(),
        startFrameId="f0",
        endFrameId="f0",
        evidenceIds=["f0"],
        observableFacts=["第一幅画面中，一个穿盔甲的巨型角色站在平台上。"],
    )
    result, _, _, _ = analyze_vision(request, [appearance])
    assert schema_detail(result, "event_frame_boundaries") == {
        "eventIndex": 0,
        "startUs": 31_500_000,
        "endUs": 31_500_001,
    }


def _import_collection(
    tmp_path: Path,
    project: Path,
    bundle: MediaPreprocessingResult,
    capsys: pytest.CaptureFixture[str],
    collection_id: str,
    observations: list[dict[str, object]],
) -> None:
    path = tmp_path / f"package-{collection_id}.json"
    write_json(
        path,
        package_document(project, bundle, collection_id=collection_id, observations=observations),
    )
    code, document, stderr = import_static(project, path, capsys, collection_id=collection_id)
    assert (code, stderr) == (0, ""), (code, stderr)
    assert document is not None and document["status"] == "created"


def _search_collection(
    tmp_path: Path,
    project: Path,
    capsys: pytest.CaptureFixture[str],
    collection_id: str,
    conditions: list[dict[str, str]],
) -> dict[str, object]:
    fingerprint = hashlib.sha256(
        json.dumps(conditions, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:12]
    path = tmp_path / f"query-{collection_id}-{fingerprint}.json"
    write_json(path, query_document(collection_id=collection_id, conditions=conditions))
    code, document, stderr = search_static(project, path, capsys, collection_id=collection_id)
    assert (code, stderr) == (0, ""), (code, stderr)
    assert document is not None
    return document


def test_matching_never_pools_actors_frames_or_part_groups(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    split = [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": [
                {
                    "actorId": "actor-a",
                    "attributes": [
                        {
                            "partGroup": "head",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "black",
                            "status": "observed",
                        }
                    ],
                },
                {
                    "actorId": "actor-b",
                    "attributes": [
                        {
                            "partGroup": "torso",
                            "partId": "torso",
                            "kind": "clothing_color",
                            "value": "red",
                            "status": "observed",
                        }
                    ],
                },
            ],
        }
    ]
    _import_collection(tmp_path, project, bundle, capsys, "split-actors", split)
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "split-actors",
        [condition("hair_color", "black", "head"), condition("clothing_color", "red", "torso")],
    )
    assert report["matchCount"] == 0

    mismatch = [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": [
                {
                    "actorId": "actor-a",
                    "attributes": [
                        {
                            "partGroup": "hand",
                            "partId": "hand-left",
                            "kind": "held_shape",
                            "value": "long_rod",
                            "status": "observed",
                        },
                        {
                            "partGroup": "hand",
                            "partId": "hand-right",
                            "kind": "held_class",
                            "value": "weapon",
                            "status": "observed",
                        },
                    ],
                }
            ],
        }
    ]
    _import_collection(tmp_path, project, bundle, capsys, "part-mismatch", mismatch)
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "part-mismatch",
        [condition("held_shape", "long_rod", "hand"), condition("held_class", "weapon", "hand")],
    )
    assert report["matchCount"] == 0

    matched = json.loads(json.dumps(mismatch))
    matched[0]["actors"][0]["attributes"][0]["partId"] = "hand"
    matched[0]["actors"][0]["attributes"][1]["partId"] = "hand"
    _import_collection(tmp_path, project, bundle, capsys, "part-match", matched)
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "part-match",
        [condition("held_shape", "long_rod", "hand"), condition("held_class", "weapon", "hand")],
    )
    assert report["matchCount"] == 1

    cross_frame = [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": [
                {
                    "actorId": "actor-shared",
                    "attributes": [
                        {
                            "partGroup": "head",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "black",
                            "status": "observed",
                        }
                    ],
                }
            ],
        },
        {
            "localObservationId": "obs-2",
            "evidenceId": bundle.images[1].evidence_id,
            "actors": [
                {
                    "actorId": "actor-shared",
                    "attributes": [
                        {
                            "partGroup": "torso",
                            "partId": "torso",
                            "kind": "clothing_color",
                            "value": "red",
                            "status": "observed",
                        }
                    ],
                }
            ],
        },
    ]
    _import_collection(tmp_path, project, bundle, capsys, "cross-frame", cross_frame)
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "cross-frame",
        [condition("hair_color", "black", "head"), condition("clothing_color", "red", "torso")],
    )
    assert report["matchCount"] == 0


def test_query_part_group_is_local_and_group_renaming_is_invariant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    observations = [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": [
                {
                    "actorId": "actor-a",
                    "attributes": [
                        {
                            "partGroup": "head",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "black",
                            "status": "observed",
                        },
                        {
                            "partGroup": "torso",
                            "partId": "torso",
                            "kind": "clothing_color",
                            "value": "red",
                            "status": "observed",
                        },
                        {
                            "partGroup": "torso",
                            "partId": "torso",
                            "kind": "clothing_shape",
                            "value": "coat",
                            "status": "observed",
                        },
                        {
                            "partGroup": "hand",
                            "partId": "hand",
                            "kind": "held_shape",
                            "value": "long_rod",
                            "status": "observed",
                        },
                        {
                            "partGroup": "hand",
                            "partId": "hand",
                            "kind": "held_class",
                            "value": "weapon",
                            "status": "observed",
                        },
                    ],
                }
            ],
        }
    ]
    _import_collection(tmp_path, project, bundle, capsys, "group-local", observations)
    canonical = [
        condition("hair_color", "black", "head"),
        condition("clothing_color", "red", "torso"),
        condition("clothing_shape", "coat", "torso"),
        condition("held_shape", "long_rod", "hand"),
        condition("held_class", "weapon", "hand"),
    ]
    renamed = [
        condition("hair_color", "black", "hair_group"),
        condition("clothing_color", "red", "body_group"),
        condition("clothing_shape", "coat", "body_group"),
        condition("held_shape", "long_rod", "held_group"),
        condition("held_class", "weapon", "held_group"),
    ]
    canonical_report = _search_collection(tmp_path, project, capsys, "group-local", canonical)
    renamed_report = _search_collection(tmp_path, project, capsys, "group-local", renamed)
    assert canonical_report["matchCount"] == 1
    assert renamed_report["matchCount"] == 1

    def signature(report: dict[str, object]) -> list[tuple[str, str, str]]:
        matches = cast(list[dict[str, object]], report["matches"])
        supports = cast(list[dict[str, object]], matches[0]["supportedAttributes"])
        return sorted(
            (cast(str, item["kind"]), cast(str, item["value"]), cast(str, item["partId"]))
            for item in supports
        )

    assert signature(canonical_report) == signature(renamed_report)


def test_same_real_part_conflict_is_checked_across_all_source_groups(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    observations = [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": [
                {
                    "actorId": "actor-a",
                    "attributes": [
                        {
                            "partGroup": "source_a",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "black",
                            "status": "observed",
                        },
                        {
                            "partGroup": "source_b",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "white",
                            "status": "observed",
                        },
                    ],
                }
            ],
        }
    ]
    _import_collection(tmp_path, project, bundle, capsys, "source-group-conflict", observations)
    black = _search_collection(
        tmp_path,
        project,
        capsys,
        "source-group-conflict",
        [condition("hair_color", "black", "query_head")],
    )
    assert black["matchCount"] == 0
    black_and_white = _search_collection(
        tmp_path,
        project,
        capsys,
        "source-group-conflict",
        [
            condition("hair_color", "black", "query_one"),
            condition("hair_color", "white", "query_two"),
        ],
    )
    assert black_and_white["matchCount"] == 0


def test_uncertain_unknown_missing_and_conflict_never_fully_support(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1)

    def observation(attributes: list[dict[str, str]]) -> list[dict[str, object]]:
        return [
            {
                "localObservationId": "obs-1",
                "evidenceId": bundle.images[0].evidence_id,
                "actors": [{"actorId": "actor-a", "attributes": attributes}],
            }
        ]

    _import_collection(
        tmp_path,
        project,
        bundle,
        capsys,
        "uncertain",
        observation(
            [
                {
                    "partGroup": "head",
                    "partId": "head",
                    "kind": "hair_color",
                    "value": "black",
                    "status": "observed",
                },
                {
                    "partGroup": "head",
                    "partId": "head-2",
                    "kind": "hair_color",
                    "value": "black",
                    "status": "uncertain",
                },
            ]
        ),
    )
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "uncertain",
        [condition("hair_color", "black", "head")],
    )
    assert report["matchCount"] == 0

    _import_collection(
        tmp_path,
        project,
        bundle,
        capsys,
        "conflict",
        observation(
            [
                {
                    "partGroup": "head",
                    "partId": "head",
                    "kind": "hair_color",
                    "value": "black",
                    "status": "observed",
                },
                {
                    "partGroup": "head",
                    "partId": "head",
                    "kind": "hair_color",
                    "value": "white",
                    "status": "observed",
                },
            ]
        ),
    )
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "conflict",
        [condition("hair_color", "black", "head")],
    )
    assert report["matchCount"] == 0

    _import_collection(
        tmp_path,
        project,
        bundle,
        capsys,
        "uncertain-and",
        observation(
            [
                {
                    "partGroup": "torso",
                    "partId": "torso",
                    "kind": "clothing_color",
                    "value": "red",
                    "status": "observed",
                },
                {
                    "partGroup": "head",
                    "partId": "head",
                    "kind": "hair_color",
                    "value": "black",
                    "status": "uncertain",
                },
            ]
        ),
    )
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "uncertain-and",
        [condition("clothing_color", "red", "torso"), condition("hair_color", "black", "head")],
    )
    assert report["matchCount"] == 0

    _import_collection(
        tmp_path,
        project,
        bundle,
        capsys,
        "missing",
        observation(
            [
                {
                    "partGroup": "head",
                    "partId": "head",
                    "kind": "hair_color",
                    "value": "black",
                    "status": "observed",
                }
            ]
        ),
    )
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "missing",
        [condition("hair_color", "black", "head"), condition("clothing_color", "red", "torso")],
    )
    assert report["matchCount"] == 0
    report = _search_collection(
        tmp_path,
        project,
        capsys,
        "missing",
        [condition("hair_color", "purple", "head")],
    )
    assert report["matchCount"] == 0


def test_completed_coverage_identity_evidence_and_file_gates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "noncompleted"
    root.mkdir()
    project, bundle = create_project(root, complete=False)
    package_path = root / "package.json"
    write_json(package_path, package_document(project, bundle))
    code, _, stderr = import_static(project, package_path, capsys)
    assert code == 2 and error_code(stderr) == "storage.run_incomplete"

    gap_root = tmp_path / "coverage-gap"
    gap_root.mkdir()
    gap_project, gap_bundle = create_project(gap_root, coverage_gap=True)
    gap_path = gap_root / "package.json"
    write_json(gap_path, package_document(gap_project, gap_bundle))
    code, _, stderr = import_static(gap_project, gap_path, capsys)
    assert code == 2 and error_code(stderr) == "retrieval.coverage_gap"

    identity_root = tmp_path / "identity"
    identity_root.mkdir()
    identity_project, identity_bundle = create_project(identity_root)
    for field, value in (
        ("sourceSha256", "a" * 64),
        ("configHash", "e" * 64),
        ("pipelineVersion", "other-pipeline"),
        ("pipelineHash", "f" * 64),
        ("mediaId", "media-other"),
    ):
        path = identity_root / f"{field}.json"
        write_json(
            path,
            package_document(identity_project, identity_bundle, **{field: value}),
        )
        code, _, stderr = import_static(identity_project, path, capsys)
        assert code == 5 and error_code(stderr) == "static.identity"

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    evidence_project, evidence_bundle = create_project(evidence_root)
    unknown = default_observations(evidence_bundle)
    unknown[0]["evidenceId"] = "run-1:media-1:image:000099"
    path = evidence_root / "unknown.json"
    write_json(path, package_document(evidence_project, evidence_bundle, observations=unknown))
    code, _, stderr = import_static(evidence_project, path, capsys)
    assert code == 5 and error_code(stderr) == "static.identity"

    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing_project, missing_bundle = create_project(missing_root)
    missing_bundle.images[0].path.unlink()
    path = missing_root / "package.json"
    write_json(path, package_document(missing_project, missing_bundle))
    code, _, stderr = import_static(missing_project, path, capsys)
    assert code == 5 and error_code(stderr) == "storage.integrity"


def test_search_rechecks_registered_evidence_clock_hash_and_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    assert import_static(project, package_path, capsys)[0] == 0
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    assert search_static(project, query_path, capsys)[0] == 0

    database = project / "static-observations.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE static_observations SET source_time_us = source_time_us + 1")
        connection.commit()
    code, _, stderr = search_static(project, query_path, capsys)
    assert code == 5 and error_code(stderr) == "static.integrity"

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE static_observations SET source_time_us = source_time_us - 1")
        connection.execute("UPDATE static_observations SET image_sha256 = ?", ("f" * 64,))
        connection.commit()
    code, _, stderr = search_static(project, query_path, capsys)
    assert code == 5 and error_code(stderr) == "static.integrity"

    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "UPDATE static_observations SET image_sha256 = ?", (bundle.images[0].sha256,)
        )
        connection.execute(
            "UPDATE static_observations SET artifact_path = artifact_path || '.missing'"
        )
        connection.commit()
    code, _, stderr = search_static(project, query_path, capsys)
    assert code == 5 and error_code(stderr) == "static.integrity"

    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "UPDATE static_observations SET artifact_path = ?",
            (str(bundle.images[0].path.resolve()),),
        )
        connection.commit()
    assert search_static(project, query_path, capsys)[0] == 0

    bundle.asset.source_path.write_bytes(b"changed synthetic source")
    code, _, stderr = search_static(project, query_path, capsys)
    assert code == 5 and error_code(stderr) == "storage.integrity"


def test_search_requires_the_exact_collection_without_cross_collection_fallback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    assert import_static(project, package_path, capsys)[0] == 0
    missing = tmp_path / "missing-collection.json"
    write_json(missing, query_document(collection_id="look-9"))
    code, document, stderr = search_static(project, missing, capsys, collection_id="look-9")
    assert code == 5 and error_code(stderr) == "static.collection_missing"
    assert document is None


def test_store_unknown_schema_corrupt_payload_and_projection_fail_explicitly(
    tmp_path: Path,
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    artifact = collection_artifact(project, package_path)
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        assert store.publish(artifact) == "created"
    finally:
        store.close()

    database = project / "static-observations.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        payload = connection.execute("SELECT canonical_payload FROM static_collections").fetchone()[
            0
        ]
        payload_value = json.loads(payload)
        payload_value["schemaVersion"] = "static-observation-import-v2"
        unknown_payload = json.dumps(
            payload_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        connection.execute(
            "UPDATE static_collections SET canonical_payload=?, package_sha256=?",
            (unknown_payload, hashlib.sha256(unknown_payload.encode()).hexdigest()),
        )
        connection.commit()

    with pytest.raises(AppError) as error:
        store = SqliteStaticObservationStore.open(project, read_only=True)
        try:
            store.load_collection("run-1", "look-1")
        finally:
            store.close()
    assert error.value.code == "static.schema_unsupported"


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("payload", "static.integrity"),
        ("package_hash", "static.integrity"),
        ("observation_json", "static.integrity"),
        ("delete_row", "static.integrity"),
        ("provenance", "static.integrity"),
    ],
)
def test_store_corruption_is_not_an_empty_result(
    tmp_path: Path, damage: str, expected: str
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    artifact = collection_artifact(project, package_path)
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        assert store.publish(artifact) == "created"
    finally:
        store.close()

    database = project / "static-observations.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        if damage == "payload":
            connection.execute("UPDATE static_collections SET canonical_payload='{}'")
        elif damage == "package_hash":
            connection.execute("UPDATE static_collections SET package_sha256=?", ("f" * 64,))
        elif damage == "observation_json":
            connection.execute("UPDATE static_observations SET observation_json='{}'")
        elif damage == "delete_row":
            connection.execute("DELETE FROM static_observations")
        else:
            connection.execute("UPDATE static_collections SET provenance_json='{}'")
        connection.commit()

    with pytest.raises(AppError) as error:
        store = SqliteStaticObservationStore.open(project, read_only=True)
        try:
            store.load_collection("run-1", "look-1")
        finally:
            store.close()
    assert error.value.code == expected


def test_unknown_store_schema_fails_on_open(tmp_path: Path) -> None:
    project, bundle = create_project(tmp_path, images=1)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    artifact = collection_artifact(project, package_path)
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        assert store.publish(artifact) == "created"
    finally:
        store.close()
    with closing(sqlite3.connect(project / "static-observations.sqlite3")) as connection:
        connection.execute("PRAGMA user_version=99")
        connection.commit()
    with pytest.raises(AppError) as error:
        SqliteStaticObservationStore.open(project, read_only=True)
    assert error.value.code == "static.store_schema"


def test_idempotency_conflict_new_collection_and_full_transaction_rollback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    code, first, stderr = import_static(project, package_path, capsys)
    assert (code, stderr) == (0, "") and first is not None
    assert first["status"] == "created"
    code, second, stderr = import_static(project, package_path, capsys)
    assert (code, stderr) == (0, "") and second is not None
    assert second["status"] == "unchanged"

    changed = json.loads(json.dumps(package_document(project, bundle)))
    changed["observations"][0]["actors"][0]["attributes"][0]["value"] = "white"
    changed_path = tmp_path / "changed.json"
    write_json(changed_path, changed)
    code, _, stderr = import_static(project, changed_path, capsys)
    assert code == 5 and error_code(stderr) == "static.collection_conflict"

    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    assert search_static(project, query_path, capsys)[0] == 0

    look_two = json.loads(json.dumps(changed))
    look_two["collectionId"] = "look-2"
    look_two_path = tmp_path / "changed-look-2.json"
    write_json(look_two_path, look_two)
    code, created, stderr = import_static(project, look_two_path, capsys, collection_id="look-2")
    assert (code, stderr) == (0, "") and created is not None
    assert created["status"] == "created"
    white_conditions = default_conditions()
    white_conditions[0] = condition("hair_color", "white", "head")
    white_path = tmp_path / "white-query.json"
    write_json(white_path, query_document(collection_id="look-2", conditions=white_conditions))
    code, report, stderr = search_static(project, white_path, capsys, collection_id="look-2")
    assert (code, stderr) == (0, "") and report is not None
    assert report["matchCount"] == 1

    observations = [
        {
            "localObservationId": "obs-1",
            "evidenceId": bundle.images[0].evidence_id,
            "actors": default_observations(bundle)[0]["actors"],
        },
        {
            "localObservationId": "obs-2",
            "evidenceId": bundle.images[1].evidence_id,
            "actors": [
                {
                    "actorId": "actor-b",
                    "attributes": [
                        {
                            "partGroup": "head",
                            "partId": "head",
                            "kind": "hair_color",
                            "value": "black",
                            "status": "observed",
                        }
                    ],
                }
            ],
        },
    ]
    rollback_path = tmp_path / "rollback-package.json"
    write_json(
        rollback_path,
        package_document(project, bundle, collection_id="rollback", observations=observations),
    )
    artifact = collection_artifact(project, rollback_path)
    bad_artifact = replace(
        artifact,
        records=(artifact.records[0], artifact.records[0]),
    )
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        with pytest.raises(AppError) as error:
            store.publish(bad_artifact)
        assert error.value.code in {"static.constraint", "static.integrity"}
    finally:
        store.close()
    with closing(sqlite3.connect(project / "static-observations.sqlite3")) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM static_collections WHERE collection_id='rollback'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM static_observations WHERE collection_id='rollback'"
            ).fetchone()[0]
            == 0
        )
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        assert store.publish(artifact) == "created"
    finally:
        store.close()


def test_concurrent_same_package_publishes_once(tmp_path: Path) -> None:
    project, bundle = create_project(tmp_path, images=1)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    artifact = collection_artifact(project, package_path)

    def publish(artifact: StaticCollectionArtifact) -> str:
        store = SqliteStaticObservationStore.open(project, read_only=False)
        try:
            return store.publish(artifact)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, (artifact, artifact)))
    assert sorted(results) == ["created", "unchanged"]
    with closing(sqlite3.connect(project / "static-observations.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM static_collections").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM static_observations").fetchone()[0] == 1


def test_old_timeline_fees_prompt_and_default_search_outputs_stay_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1, invocation=True)
    assert (
        main(["search", "任意", "--project", str(project), "--run", "run-1", "--mode", "lexical"])
        == 0
    )
    capsys.readouterr()
    timeline_hash = sha(project / "timeline.sqlite3")
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as connection:
        before = connection.execute(
            "SELECT invocation_id,status,original_cost,cost_cny,cost_status "
            "FROM provider_invocations ORDER BY invocation_id"
        ).fetchall()

    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    assert import_static(project, package_path, capsys)[0] == 0
    assert search_static(project, query_path, capsys)[0] == 0
    assert sha(project / "timeline.sqlite3") == timeline_hash
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as connection:
        after = connection.execute(
            "SELECT invocation_id,status,original_cost,cost_cny,cost_status "
            "FROM provider_invocations ORDER BY invocation_id"
        ).fetchall()
    assert after == before

    expected = {
        PROMPT_VERSION: "c3a6d3f286b5e8b582a91929afcfde038d39ff605d017619919e1a583c507d26",
        PROMPT_VERSION_V2: "f9adb61a5be1dd03ca603c9515c5f6ffea3ae731b1f55a61332a23dd37383236",
        PROMPT_VERSION_V3: "27762b0b9d390c64d53ec4be815bd6e8ead4d249ec9864bb87735223b3ad1c4d",
        PROMPT_VERSION_V4: "9ea350e10eb028f1f5e2dc7d355ebd1d080ad8ae8397eb709705a25773323f48",
        PROMPT_VERSION_V5: "c64c644e9889fcfd91cc0e9a26d8bf1b9546ce73c548e6ac056a5067498ff98a",
        PROMPT_VERSION_V6: "a60d114d9dd8bf82c5d2ea62c30c4cfe2b4316b08de34ade3cba883d6de9ea00",
    }
    assert {version: vision_prompt_fingerprint(version) for version in expected} == expected

    async def reload() -> object:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await store.load_completed_timeline("run-1")
        finally:
            await store.close()

    timeline = asyncio.run(reload())
    assert timeline.events == ()
    assert timeline.transcripts == ()


def test_store_path_rejects_symbolic_links(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"not a database")
    link = project / "static-observations.sqlite3"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available in this environment")
    with pytest.raises(AppError) as error:
        SqliteStaticObservationStore.open(project, read_only=True)
    assert error.value.code == "static.path"


def test_store_path_rejects_hard_links(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"not a database")
    link = project / "static-observations.sqlite3"
    try:
        os.link(outside, link)
    except OSError:
        pytest.skip("hard links are not available in this environment")
    with pytest.raises(AppError) as error:
        SqliteStaticObservationStore.open(project, read_only=True)
    assert error.value.code == "static.path"


def test_store_path_rejects_delete_journal_hard_link_before_import(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path, images=1)
    first_path = tmp_path / "first-package.json"
    write_json(first_path, package_document(project, bundle))
    assert import_static(project, first_path, capsys)[0] == 0
    database = project / "static-observations.sqlite3"
    database_before = database.read_bytes()

    victim = tmp_path / "journal-victim.bin"
    victim.write_bytes(b"\x00" + b"synthetic retained journal bytes")
    victim_before = victim.read_bytes()
    journal = database.with_name(database.name + "-journal")
    try:
        os.link(victim, journal)
    except OSError:
        pytest.skip("hard links are not available in this environment")

    second_path = tmp_path / "second-package.json"
    write_json(second_path, package_document(project, bundle, collection_id="look-2"))
    code, _, stderr = import_static(project, second_path, capsys, collection_id="look-2")
    assert code == 5 and error_code(stderr) == "static.path"
    with pytest.raises(AppError) as error:
        SqliteStaticObservationStore.open(project, read_only=True)
    assert error.value.code == "static.path"
    assert victim.read_bytes() == victim_before
    assert database.read_bytes() == database_before

    journal.unlink()
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    code, searched, stderr = search_static(project, query_path, capsys)
    assert (code, stderr) == (0, "") and searched is not None
    assert searched["matchCount"] == 1
