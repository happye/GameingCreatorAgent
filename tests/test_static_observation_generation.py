"""Offline static generation: frozen proposal, strict typed output, publish and query."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from fake_vision_transport import FakeVisionTransport
from test_static_observations import (
    condition,
    create_project,
    default_conditions,
    package_document,
    query_document,
    sha,
    write_json,
)

import gamingcreator.cli.static_observation_generation as cli_generation
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004, pricing_period
from gamingcreator.application.providers import ProviderUsage
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observation_generation import (
    STATIC_GENERATION_AUTHORIZATION_SCHEMA_VERSION,
    STATIC_GENERATION_DECLARATION,
    STATIC_GENERATION_PROMPT_VERSION,
    STATIC_GENERATION_SCHEMA_VERSION,
    StaticGenerationParameters,
    authorization_file_bytes,
    generation_reservation_cny,
    loads_static_generation_authorization,
    loads_static_generation_proposal,
    proposal_file_bytes,
    proposal_sha256,
)
from gamingcreator.cli.main import main
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.static_observations import StaticObservationPackage
from gamingcreator.infrastructure.http_transport import HttpResponse, TransportError
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_attempts import (
    LEDGER_INITIALIZED_MARKER,
    LEDGER_SQLITE_NAME,
    SqliteStaticGenerationLedger,
)
from gamingcreator.infrastructure.static_observation_store import (
    SqliteStaticObservationStore,
)

COLLECTION = "look-1"
ACTORS_CONTENT = json.dumps(
    {
        "actors": [
            {
                "actorIndex": 1,
                "parts": [
                    {
                        "partGroup": "hair",
                        "partIndex": 1,
                        "attributes": {"hair_color": "black"},
                    },
                    {
                        "partGroup": "clothing",
                        "partIndex": 1,
                        "attributes": {"clothing_color": "red", "clothing_shape": "coat"},
                    },
                    {
                        "partGroup": "held",
                        "partIndex": 1,
                        "attributes": {"held_shape": "long_rod", "held_class": "weapon"},
                    },
                ],
            }
        ]
    }
)
MULTI_PART_CONTENT = json.dumps(
    {
        "actors": [
            {
                "actorIndex": 1,
                "parts": [
                    {
                        "partGroup": "hair",
                        "partIndex": 1,
                        "attributes": {"hair_color": "black"},
                    },
                    {
                        "partGroup": "clothing",
                        "partIndex": 1,
                        "attributes": {
                            "clothing_color": "brown",
                            "clothing_shape": "shorts",
                        },
                    },
                    {
                        "partGroup": "clothing",
                        "partIndex": 2,
                        "attributes": {
                            "clothing_color": "white",
                            "clothing_shape": "coat",
                        },
                    },
                    {
                        "partGroup": "held",
                        "partIndex": 1,
                        "attributes": {
                            "held_shape": "long_rod",
                            "held_class": "staff",
                        },
                    },
                    {
                        "partGroup": "held",
                        "partIndex": 2,
                        "attributes": {
                            "held_shape": "curved_object",
                            "held_class": "weapon",
                        },
                    },
                ],
            }
        ]
    }
)


def _usage() -> dict[str, int]:
    return {
        "prompt_tokens": 120,
        "completion_tokens": 20,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 120,
        "total_tokens": 140,
    }


def static_reply(
    content: str,
    *,
    response_id: str = "chatcmpl-static-offline-1",
    model: str = "deepseek-flash",
    usage: bool = True,
    usage_values: dict[str, int] | None = None,
) -> HttpResponse:
    body: dict[str, object] = {
        "id": response_id,
        "model": model,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }
    if usage:
        body["usage"] = usage_values if usage_values is not None else _usage()
    return HttpResponse(200, json.dumps(body).encode("utf-8"))


def expected_charge() -> str:
    from datetime import UTC, datetime
    from decimal import Decimal

    period, _ = pricing_period(datetime.now(UTC))
    usage = DEEPSEEK_FLASH_20261004.estimate_usage(
        ProviderUsage(120, 20, 0), "deepseek-flash", "deepseek-flash", period=period
    )
    cost = usage.cost_cny
    assert isinstance(cost, Decimal)
    return str(cost)


def invocation(transport: FakeVisionTransport, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_generation, "build_vision_transport", lambda: transport)


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def authorization_document(
    proposal_path: Path,
    *,
    authorization_id: str = "auth-static-1",
    max_cost_cny: str = "0.5",
    **overrides: object,
) -> dict[str, object]:
    proposal = loads_static_generation_proposal(proposal_path.read_bytes())
    parameters = {
        "maxOutputTokens": proposal.parameters.max_output_tokens,
        "maxInputTokenCeiling": proposal.parameters.max_input_token_ceiling,
        "maxImageBytes": proposal.parameters.max_image_bytes,
        "imageDetail": proposal.parameters.image_detail,
        "timeoutSeconds": proposal.parameters.timeout_seconds,
        "maxRequests": 1,
        "maxInputFrames": 1,
    }
    document: dict[str, object] = {
        "schemaVersion": STATIC_GENERATION_AUTHORIZATION_SCHEMA_VERSION,
        "authorizationId": authorization_id,
        "proposalHash": proposal.proposal_sha256,
        "projectRoot": proposal.project_root,
        "databasePath": proposal.database_path,
        "ledgerRoot": proposal.ledger_root,
        "provider": proposal.identity.provider,
        "model": proposal.identity.model,
        "promptVersion": proposal.identity.prompt_version,
        "promptHash": proposal.identity.prompt_hash,
        "generationSchemaVersion": proposal.identity.schema_version,
        "vocabularyVersion": proposal.identity.vocabulary_version,
        "parameters": parameters,
        "currency": "CNY",
        "maxCostCny": max_cost_cny,
        "maxRequests": 1,
        "maxInputFrames": 1,
        "humanAuthorizationRef": "synthetic test authorization; no real provider call",
        "allowModel": True,
        "declaration": STATIC_GENERATION_DECLARATION,
    }
    document.update(overrides)
    document["authorizationSha256"] = hashlib.sha256(
        _canonical(document).encode("utf-8")
    ).hexdigest()
    return document


def write_authorization(
    path: Path,
    proposal_path: Path,
    *,
    authorization_id: str = "auth-static-1",
    raw: bool = False,
    **overrides: object,
) -> Path:
    document = authorization_document(proposal_path, authorization_id=authorization_id, **overrides)
    if raw:
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path
    authorization = loads_static_generation_authorization(
        json.dumps(document, ensure_ascii=False).encode("utf-8")
    )
    path.write_bytes(authorization_file_bytes(authorization))
    return path


def invoke(
    capsys: pytest.CaptureFixture[str], *arguments: str
) -> tuple[int, dict[str, object] | None, str]:
    code = main(list(arguments))
    captured = capsys.readouterr()
    document = json.loads(captured.out) if captured.out.strip() else None
    return code, document, captured.err


def error_code(stderr: str) -> str:
    return str(json.loads(stderr)["code"])


def prepare(
    capsys: pytest.CaptureFixture[str],
    project: Path,
    output: Path,
    evidence_id: str,
    collection: str = COLLECTION,
) -> dict[str, object]:
    code, document, stderr = invoke(
        capsys,
        "prepare-static-observation-generation",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        collection,
        "--evidence",
        evidence_id,
        "--output",
        str(output),
    )
    assert code == 0, stderr
    assert document is not None
    return document


def dispatch(
    capsys: pytest.CaptureFixture[str], project: Path, proposal: Path, authorization: Path
) -> tuple[int, dict[str, object] | None, str]:
    return invoke(
        capsys,
        "dispatch-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    )


def resume(
    capsys: pytest.CaptureFixture[str], project: Path, proposal: Path, authorization: Path
) -> tuple[int, dict[str, object] | None, str]:
    return invoke(
        capsys,
        "resume-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    )


def attempt_files(project: Path) -> tuple[Path, ...]:
    directory = project / ".static-observation-generation" / "ledger" / "attempts"
    return () if not directory.is_dir() else tuple(sorted(directory.glob("*.json")))


def load_collection(project: Path, collection: str = COLLECTION) -> StaticObservationPackage:
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        return store.load_collection("run-1", collection).package
    finally:
        store.close()


def timeline(project: Path) -> object:
    async def load() -> object:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await load_searchable_timeline(store, "run-1")
        finally:
            await store.close()

    return asyncio.run(load())


def test_prepare_is_offline_frozen_and_never_creates_authorization(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    output = tmp_path / "proposal.json"

    def forbidden() -> object:
        raise AssertionError("prepare must not build a network transport")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli_generation, "build_vision_transport", forbidden)
        first = prepare(capsys, project, output, bundle.images[0].evidence_id)
        second = prepare(capsys, project, output, bundle.images[0].evidence_id)

    assert first["status"] == "prepared"
    assert second["status"] == "unchanged"
    assert first["proposalHash"] == second["proposalHash"]
    assert first["providerRequestsSent"] == 0
    assert first["modelInvocations"] == 0
    assert first["authorizationCreated"] is False
    assert first["authorizationRequired"] is True
    assert first["reservationCny"] == str(generation_reservation_cny(StaticGenerationParameters()))
    proposal = loads_static_generation_proposal(output.read_bytes())
    assert proposal.evidence_id == bundle.images[0].evidence_id
    assert proposal.image_sha256 == bundle.images[0].sha256
    assert proposal.source_time_us == 100_000
    assert proposal.run_id == "run-1"
    assert proposal.collection_id == COLLECTION
    assert proposal.identity.prompt_hash
    assert proposal.profile == "static-frame-profile-v2"
    assert proposal.identity.prompt_version == STATIC_GENERATION_PROMPT_VERSION
    assert proposal.identity.schema_version == STATIC_GENERATION_SCHEMA_VERSION
    assert first["parameters"]["maxRequests"] == 1
    assert proposal.price_version == first["priceVersion"]
    assert not (project / ".static-observation-generation").exists()
    assert sorted(path.name for path in tmp_path.glob("*.json")) == ["proposal.json"]

    code, _, stderr = invoke(
        capsys,
        "prepare-static-observation-generation",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        "look-2",
        "--evidence",
        bundle.images[0].evidence_id,
        "--output",
        str(output),
    )
    assert code == 2, stderr
    assert error_code(stderr) == "input.static_generation"


def test_dispatch_publishes_typed_frame_and_repeat_resume_send_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    timeline_hash = sha(project / "timeline.sqlite3")
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)

    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    assert report["status"] == "published"
    assert report["providerRequestsSent"] == 1
    assert report["publishStatus"] == "created"
    assert report["attemptStatus"] == "recorded"
    assert report["generationStatus"] == "observed"
    assert report["actorCount"] == 1
    assert report["chargeStatus"] == "known"
    assert report["chargeCny"] == expected_charge()
    assert report["overAuthorizationLimit"] is False
    assert report["visualVerified"] is None
    assert report["humanLabels"] is None
    assert report["qualityGate"] is None
    assert report["f006Passed"] is False
    assert report["f009Passed"] is False
    assert report["f010Passed"] is False
    assert report["automaticRetry"] is False
    assert len(transport.payloads) == 1
    payload = transport.payloads[0]
    assert payload["model"] == "deepseek-flash"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["stream"] is False
    assert payload["temperature"] == 0
    assert len(payload["messages"]) == 2  # type: ignore[arg-type]
    frame = bundle.images[0]
    package = load_collection(project)
    observation = package.observations[0]
    assert observation.evidence_id == frame.evidence_id
    assert observation.local_observation_id == "gen-" + report["proposalHash"][:40]
    assert [actor.actor_id for actor in observation.actors] == ["actor-1"]
    assert {attribute.kind.value for attribute in observation.actors[0].attributes} == {
        "hair_color",
        "clothing_color",
        "clothing_shape",
        "held_shape",
        "held_class",
    }
    assert package.run_id == "run-1"
    assert package.collection_id == COLLECTION
    assert package.provenance.source_payload_sha256 == report["responseSha256"]
    assert "自动静态草案" in package.provenance.source_note
    assert sha(project / "timeline.sqlite3") == timeline_hash
    assert len(attempt_files(project)) == 1

    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    code, search, stderr = invoke(
        capsys,
        "search-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        COLLECTION,
        "--input",
        str(query_path),
    )
    assert code == 0, stderr
    assert search is not None
    assert search["collectionSha256"] == report["collectionSha256"]
    assert search["matchCount"] == 1
    match = search["matches"][0]
    assert match["evidenceId"] == frame.evidence_id
    assert match["imageSha256"] == frame.sha256
    assert match["sourceTimeUs"] == 100_000
    assert match["supportedAttributes"][0]["partId"] in {
        "hair-1",
        "clothing-1",
        "held-1",
    }
    assert search["visualVerified"] is None

    with pytest.MonkeyPatch.context() as patch:
        again = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: again)
        code, repeated, stderr = dispatch(capsys, project, proposal_path, authorization_path)
        assert code == 0, stderr
        assert repeated is not None
        assert repeated["status"] == "published"
        assert repeated["providerRequestsSent"] == 0
        assert repeated["publishStatus"] == "unchanged"
        assert again.payloads == []
        code, recovered, stderr = resume(capsys, project, proposal_path, authorization_path)
        assert code == 0, stderr
        assert recovered is not None
        assert recovered["providerRequestsSent"] == 0
        assert recovered["status"] == "published"
        assert again.payloads == []

    assert len(attempt_files(project)) == 1
    assert sha(project / "timeline.sqlite3") == timeline_hash


def test_explicit_local_parts_do_not_merge_garments_or_held_objects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(MULTI_PART_CONTENT)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    assert report["status"] == "published"

    observation = load_collection(project).observations[0]
    by_part: dict[str, dict[str, str]] = {}
    for attribute in observation.actors[0].attributes:
        by_part.setdefault(attribute.part_id, {})[attribute.kind.value] = attribute.value
    assert by_part["clothing-1"] == {
        "clothing_color": "brown",
        "clothing_shape": "shorts",
    }
    assert by_part["clothing-2"] == {
        "clothing_color": "white",
        "clothing_shape": "coat",
    }
    assert by_part["held-1"] == {"held_shape": "long_rod", "held_class": "staff"}
    assert by_part["held-2"] == {
        "held_shape": "curved_object",
        "held_class": "weapon",
    }

    cases = [
        (
            [
                condition("clothing_color", "brown", "torso"),
                condition("clothing_shape", "coat", "torso"),
            ],
            0,
            None,
        ),
        (
            [
                condition("clothing_color", "white", "torso"),
                condition("clothing_shape", "coat", "torso"),
            ],
            1,
            "clothing-2",
        ),
        (
            [
                condition("clothing_color", "brown", "torso"),
                condition("clothing_shape", "shorts", "torso"),
            ],
            1,
            "clothing-1",
        ),
        (
            [
                condition("held_shape", "long_rod", "hand"),
                condition("held_class", "weapon", "hand"),
            ],
            0,
            None,
        ),
        (
            [
                condition("held_shape", "long_rod", "hand"),
                condition("held_class", "staff", "hand"),
            ],
            1,
            "held-1",
        ),
        (
            [
                condition("held_shape", "curved_object", "hand"),
                condition("held_class", "weapon", "hand"),
            ],
            1,
            "held-2",
        ),
    ]
    for index, (conditions, expected, expected_part) in enumerate(cases):
        query_path = tmp_path / f"query-{index}.json"
        write_json(query_path, query_document(conditions=conditions))
        code, search, stderr = invoke(
            capsys,
            "search-static-observations",
            "--project",
            str(project),
            "--run",
            "run-1",
            "--collection",
            COLLECTION,
            "--input",
            str(query_path),
        )
        assert code == 0, (index, stderr)
        assert search is not None
        assert search["matchCount"] == expected, (index, search["matches"])
        if expected_part is not None:
            assert {
                support["partId"] for support in search["matches"][0]["supportedAttributes"]
            } == {expected_part}


def test_old_flat_attribute_protocol_is_not_silently_reinterpreted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    flat = json.dumps(
        {
            "actors": [
                {
                    "actorIndex": 1,
                    "attributes": {
                        "hair_color": "black",
                        "clothing_color": "red",
                        "clothing_shape": "coat",
                        "held_shape": "long_rod",
                        "held_class": "weapon",
                    },
                }
            ]
        }
    )
    transport = FakeVisionTransport([static_reply(flat)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 4, stderr
    assert report is not None
    assert report["status"] == "failed"
    assert "provider.schema" in report["diagnostics"]
    assert not (project / "static-observations.sqlite3").exists()


def test_empty_actors_is_no_observations_with_one_registered_frame(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply('{"actors":[]}')])
    invocation(transport, monkeypatch)

    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    assert report["status"] == "no_observations"
    assert report["generationStatus"] == "no_observations"
    assert report["actorCount"] == 0
    assert report["observationCount"] == 1
    package = load_collection(project)
    assert len(package.observations) == 1
    assert package.observations[0].evidence_id == bundle.images[0].evidence_id
    assert package.observations[0].actors == ()
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    code, search, stderr = invoke(
        capsys,
        "search-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        COLLECTION,
        "--input",
        str(query_path),
    )
    assert code == 0, stderr
    assert search is not None
    assert search["matchCount"] == 0


def forbidden_contents() -> list[pytest.param]:
    actors = json.loads(ACTORS_CONTENT)["actors"]
    valid_parts = actors[0]["parts"]

    def actor(parts: object) -> dict[str, object]:
        return {"actors": [{"actorIndex": 1, "parts": parts}]}

    def part(
        group: str = "clothing", index: int = 1, attributes: object = None
    ) -> dict[str, object]:
        return {
            "partGroup": group,
            "partIndex": index,
            "attributes": {"clothing_color": "red"} if attributes is None else attributes,
        }

    cases = [
        ("root_extra", json.dumps({"actors": [], "runId": "run-1"})),
        ("actor_extra", json.dumps({"actors": [{**actors[0], "evidenceId": "x"}]})),
        (
            "old_flat_protocol",
            json.dumps(
                {
                    "actors": [
                        {
                            "actorIndex": 1,
                            "attributes": {"hair_color": "black"},
                        }
                    ]
                }
            ),
        ),
        ("action", json.dumps(actor([part("hair", 1, {"action": "run"})]))),
        ("environment", json.dumps(actor([part("clothing", 1, {"environment": "water"})]))),
        (
            "cross_group_kind",
            json.dumps(actor([part("held", 1, {"clothing_color": "red"})])),
        ),
        (
            "type",
            json.dumps({"actors": [{"actorIndex": "1", "parts": valid_parts}]}),
        ),
        (
            "part_index_type",
            json.dumps(actor([part("clothing", "1", {"clothing_color": "red"})])),
        ),
        (
            "nested",
            json.dumps(actor([part("hair", 1, {"hair_color": {"v": "black"}})])),
        ),
        (
            "duplicate_actor",
            json.dumps(
                {
                    "actors": [
                        {"actorIndex": 1, "parts": [part("hair", 1, {"hair_color": "black"})]},
                        {"actorIndex": 1, "parts": [part("hair", 1, {"hair_color": "black"})]},
                    ]
                }
            ),
        ),
        (
            "duplicate_part",
            json.dumps(
                actor(
                    [
                        part("clothing", 1, {"clothing_color": "red"}),
                        part("clothing", 1, {"clothing_shape": "coat"}),
                    ]
                )
            ),
        ),
        (
            "second_hair_part",
            json.dumps(
                actor(
                    [
                        part("hair", 1, {"hair_color": "black"}),
                        part("hair", 1, {"hair_color": "white"}),
                    ]
                )
            ),
        ),
        ("part_index_zero", json.dumps(actor([part("clothing", 0, {})]))),
        (
            "hair_part_index_two",
            json.dumps(actor([part("hair", 2, {"hair_color": "black"})])),
        ),
        (
            "fourth_clothing_part",
            json.dumps(actor([part("clothing", 4, {"clothing_color": "red"})])),
        ),
        ("empty_parts", json.dumps(actor([]))),
        ("empty_part_attributes", json.dumps(actor([part("hair", 1, {})]))),
        (
            "too_many_parts",
            json.dumps(
                actor(
                    [
                        part("hair", 1, {"hair_color": "black"}),
                        part("clothing", 1, {"clothing_color": "red"}),
                        part("clothing", 2, {"clothing_color": "blue"}),
                        part("clothing", 3, {"clothing_color": "white"}),
                        part("held", 1, {"held_shape": "long_rod"}),
                        part("held", 2, {"held_shape": "curved_object"}),
                        part("held", 3, {"held_shape": "flat_object"}),
                        part("clothing", 1, {"clothing_shape": "coat"}),
                    ]
                )
            ),
        ),
        (
            "too_many_actors",
            json.dumps(
                {
                    "actors": [
                        {
                            "actorIndex": index,
                            "parts": [part("hair", 1, {"hair_color": "black"})],
                        }
                        for index in range(1, 10)
                    ]
                }
            ),
        ),
        (
            "bad_value",
            json.dumps(actor([part("hair", 1, {"hair_color": "rainbow"})])),
        ),
        (
            "duplicate_key",
            '{"actors":[{"actorIndex":1,"parts":[{"partGroup":"hair","partIndex":1,'
            '"partIndex":2,"attributes":{"hair_color":"black"}}]}]}',
        ),
        ("foreign_frame_time", json.dumps({"actors": [], "sourceTimeUs": 100_000})),
        ("oversized", json.dumps({"actors": [], "padding": "x" * 70_000})),
        ("not_json", "not json"),
        ("array", "[]"),
    ]
    return [pytest.param(content, id=name) for name, content in cases]


@pytest.mark.parametrize("content", forbidden_contents())
def test_forbidden_or_malformed_output_never_publishes_and_never_retries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    content: str,
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(content)])
    invocation(transport, monkeypatch)

    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 4, stderr
    assert report is not None
    assert report["status"] == "failed"
    assert report["providerRequestsSent"] == 1
    assert report["publishStatus"] is None
    assert report["chargeStatus"] == "known"
    assert report["chargeCny"] == expected_charge()
    assert "provider.schema" in report["diagnostics"]
    assert report["visualVerified"] is None
    assert not (project / "static-observations.sqlite3").exists()

    with pytest.MonkeyPatch.context() as patch:
        check = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: check)
        code, repeated, stderr = dispatch(capsys, project, proposal_path, authorization_path)
        assert code == 4, stderr
        assert repeated is not None
        assert repeated["providerRequestsSent"] == 0
        assert check.payloads == []
        code, recovered, stderr = resume(capsys, project, proposal_path, authorization_path)
        assert code == 4, stderr
        assert recovered is not None
        assert recovered["providerRequestsSent"] == 0
        assert check.payloads == []
    assert len(attempt_files(project)) == 1


def test_unknown_reservation_stays_but_new_authorization_has_independent_quota(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([HttpResponse(500, b'{"error":"offline failure"}')])
    invocation(transport, monkeypatch)

    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 4, stderr
    assert report is not None
    assert report["status"] == "failed"
    assert report["chargeStatus"] == "unknown"
    assert report["chargeCny"] is None
    assert report["reservationCny"] == "0.416"
    assert not (project / "static-observations.sqlite3").exists()

    second_proposal = tmp_path / "proposal-look-2.json"
    prepare(
        capsys,
        project,
        second_proposal,
        bundle.images[0].evidence_id,
        collection="look-2",
    )
    second_authorization = write_authorization(
        tmp_path / "authorization-look-2.json",
        second_proposal,
        authorization_id="auth-static-2",
    )
    with pytest.MonkeyPatch.context() as patch:
        independent = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
        patch.setattr(cli_generation, "build_vision_transport", lambda: independent)
        code, second_report, stderr = dispatch(
            capsys, project, second_proposal, second_authorization
        )
        assert code == 0, stderr
        assert second_report is not None
        assert second_report["status"] == "published"
        assert second_report["providerRequestsSent"] == 1
        assert second_report["authorizationId"] == "auth-static-2"
        assert second_report["chargeStatus"] == "known"
        assert len(independent.payloads) == 1
    assert load_collection(project, "look-2").collection_id == "look-2"
    attempt_documents = [
        json.loads(path.read_text(encoding="utf-8")) for path in attempt_files(project)
    ]
    assert len(attempt_documents) == 2
    assert {item["authorizationId"] for item in attempt_documents} == {
        "auth-static-1",
        "auth-static-2",
    }
    original_attempt = next(
        item for item in attempt_documents if item["authorizationId"] == "auth-static-1"
    )
    assert original_attempt["result"]["status"] == "failed"
    assert original_attempt["result"]["metadata"]["usage"]["costCny"] is None

    # The original authorization still cannot sign a different proposal.
    with pytest.MonkeyPatch.context() as patch:
        blocked = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: blocked)
        code, _, stderr = dispatch(capsys, project, second_proposal, authorization_path)
        assert code == 7
        assert error_code(stderr) == "static_generation.authorization_mismatch"
        assert blocked.payloads == []

    code, recovered, stderr = resume(capsys, project, proposal_path, authorization_path)
    assert code == 4, stderr
    assert recovered is not None
    assert recovered["status"] == "failed"
    assert recovered["providerRequestsSent"] == 0
    assert recovered["reservationCny"] == "0.416"
    assert len(list((project / "runs").glob("**/*.png"))) == 2


@pytest.mark.parametrize(
    ("overrides"),
    [
        {"proposalHash": "0" * 64},
        {"projectRoot": "C:\\elsewhere"},
        {"ledgerRoot": "C:\\elsewhere\\ledger"},
        {"maxCostCny": "0.1"},
        {"allowModel": False},
        {"maxRequests": 2},
        {"currency": "USD"},
        {"humanAuthorizationRef": "   "},
        {"declaration": "trust me"},
        {
            "parameters": {
                "maxOutputTokens": 2_500,
                "maxInputTokenCeiling": 200_000,
                "maxImageBytes": 4_194_304,
                "imageDetail": "high",
                "timeoutSeconds": 60,
                "maxRequests": 1,
                "maxInputFrames": 1,
            }
        },
        {"promptHash": "d" * 64},
        {"model": "deepseek-other"},
    ],
)
def test_authorization_gates_refuse_before_any_send(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(
        tmp_path / "authorization.json", proposal_path, raw=True, **dict(overrides)
    )
    transport = FakeVisionTransport([])
    invocation(transport, monkeypatch)

    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code != 0
    assert report is None
    assert stderr
    assert transport.payloads == []
    assert attempt_files(project) == ()


def test_tampered_authorization_hash_and_tampered_proposal_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    document = json.loads(authorization_path.read_text(encoding="utf-8"))
    document["maxCostCny"] = "0.25"
    authorization_path.write_text(json.dumps(document), encoding="utf-8")
    transport = FakeVisionTransport([])
    invocation(transport, monkeypatch)
    code, _, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 7
    assert error_code(stderr) == "static_generation.authorization_hash"
    assert transport.payloads == []

    proposal_document = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal_document["collectionId"] = "look-9"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(proposal_document), encoding="utf-8")
    code, _, stderr = dispatch(capsys, project, tampered, authorization_path)
    assert code == 2
    assert transport.payloads == []


def test_source_clock_and_version_drift_are_refused_before_send(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    original = loads_static_generation_proposal(proposal_path.read_bytes())

    def frozen(mutated: object, path: Path) -> Path:
        draft = replace(mutated, proposal_sha256="0" * 64)
        final = replace(draft, proposal_sha256=proposal_sha256(draft))
        path.write_bytes(proposal_file_bytes(final))
        return path

    cases = [
        replace(original, source_time_us=original.source_time_us + 1),
        replace(original, image_sha256="e" * 64),
        replace(original, config_hash="e" * 64),
        replace(original, pipeline_hash="e" * 64),
        replace(original, duration_us=original.duration_us + 1),
        replace(original, reservation_cny=original.reservation_cny + Decimal("0.001")),
    ]
    for index, case in enumerate(cases):
        drifted = frozen(case, tmp_path / f"drifted-{index}.json")
        authorization = write_authorization(
            tmp_path / f"authorization-{index}.json",
            drifted,
            authorization_id=f"auth-drift-{index}",
        )
        transport = FakeVisionTransport([])
        invocation(transport, monkeypatch)
        code, report, stderr = dispatch(capsys, project, drifted, authorization)
        assert code == 2, (index, stderr)
        assert report is None
        assert transport.payloads == []
    assert attempt_files(project) == ()


def test_changed_registered_image_bytes_are_refused_before_send(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    bundle.images[0].path.write_bytes(b"changed synthetic frame bytes")
    transport = FakeVisionTransport([])
    invocation(transport, monkeypatch)
    code, _, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code in (2, 5), stderr
    assert transport.payloads == []
    assert attempt_files(project) == ()


def test_existing_collection_is_never_overwritten_and_attempt_is_not_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    package_path = tmp_path / "existing-package.json"
    write_json(package_path, package_document(project, bundle))
    code, imported, stderr = invoke(
        capsys,
        "import-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        COLLECTION,
        "--input",
        str(package_path),
    )
    assert code == 0, stderr
    assert imported is not None
    existing_sha = imported["collectionSha256"]
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)

    code, _, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 5
    assert error_code(stderr) == "static.collection_conflict"
    assert len(transport.payloads) == 1
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        assert store.load_collection("run-1", COLLECTION).package_sha256 == existing_sha
    finally:
        store.close()

    with pytest.MonkeyPatch.context() as patch:
        blocked = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: blocked)
        code, _, stderr = resume(capsys, project, proposal_path, authorization_path)
        assert code == 5
        assert blocked.payloads == []
    assert len(attempt_files(project)) == 1


def test_same_proposal_with_different_authorization_is_rejected_without_send(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_a = write_authorization(
        tmp_path / "authorization-a.json", proposal_path, authorization_id="auth-static-a"
    )
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_a)
    assert code == 0, stderr
    assert report is not None
    collection_sha = report["collectionSha256"]
    attempt_file = attempt_files(project)[0]
    attempt_before = attempt_file.read_bytes()
    attempt_document = json.loads(attempt_before)
    assert attempt_document["authorizationId"] == "auth-static-a"

    authorization_b = write_authorization(
        tmp_path / "authorization-b.json", proposal_path, authorization_id="auth-static-b"
    )
    with pytest.MonkeyPatch.context() as patch:
        blocked = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: blocked)
        code, _, stderr = dispatch(capsys, project, proposal_path, authorization_b)
        assert code == 7
        assert error_code(stderr) == "static_generation.authorization_conflict"
        assert blocked.payloads == []
        code, _, stderr = resume(capsys, project, proposal_path, authorization_b)
        assert code == 7
        assert error_code(stderr) == "static_generation.authorization_conflict"
        assert blocked.payloads == []
    assert attempt_file.read_bytes() == attempt_before
    assert len(attempt_files(project)) == 1
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        assert store.load_collection("run-1", COLLECTION).package_sha256 == collection_sha
    finally:
        store.close()


@pytest.mark.parametrize("damage", ["truncate", "delete"])
def test_damaged_ledger_database_blocks_new_authorization_without_send(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)
    code, _, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert len(attempt_files(project)) == 1
    attempt_before = attempt_files(project)[0].read_bytes()
    ledger_directory = project / ".static-observation-generation" / "ledger"
    assert (ledger_directory / LEDGER_INITIALIZED_MARKER).is_file()
    ledger_database = ledger_directory / LEDGER_SQLITE_NAME

    second_proposal = tmp_path / "proposal-look-2.json"
    prepare(
        capsys,
        project,
        second_proposal,
        bundle.images[0].evidence_id,
        collection="look-2",
    )
    reused_authorization = write_authorization(
        tmp_path / "reused-authorization.json",
        second_proposal,
        authorization_id="auth-static-1",
        max_cost_cny="0.6",
    )
    if damage == "truncate":
        ledger_database.write_bytes(b"")
    else:
        ledger_database.unlink()
    with pytest.MonkeyPatch.context() as patch:
        blocked = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: blocked)
        code, report, stderr = dispatch(capsys, project, second_proposal, reused_authorization)
        assert code == 5, stderr
        assert report is None
        assert error_code(stderr) in {
            "static_generation.ledger_corrupt",
            "static_generation.ledger_inconsistent",
        }
        assert blocked.payloads == []
    assert attempt_files(project)[0].read_bytes() == attempt_before
    assert (ledger_directory / LEDGER_INITIALIZED_MARKER).is_file()
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        with pytest.raises(AppError) as missing:
            store.load_collection("run-1", "look-2")
        assert missing.value.code == "static.collection_missing"
    finally:
        store.close()


def test_same_authorization_id_with_different_content_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None

    changed = write_authorization(
        tmp_path / "authorization.json", proposal_path, max_cost_cny="0.6"
    )
    with pytest.MonkeyPatch.context() as patch:
        blocked = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: blocked)
        code, _, stderr = dispatch(capsys, project, proposal_path, changed)
        assert code == 7
        assert error_code(stderr) == "static_generation.authorization_conflict"
        assert blocked.payloads == []


def test_copied_proposal_and_output_location_do_not_reset_the_fixed_ledger(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)
    code, first, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert first is not None

    copied_proposal = tmp_path / "copied-proposal.json"
    copied_proposal.write_bytes(proposal_path.read_bytes())
    copied_authorization = tmp_path / "copied-authorization.json"
    copied_authorization.write_bytes(authorization_path.read_bytes())
    checkpoint = first["collectionSha256"]
    assert checkpoint is not None
    with pytest.MonkeyPatch.context() as patch:
        blocked = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: blocked)
        code, repeated, stderr = dispatch(capsys, project, copied_proposal, copied_authorization)
        assert code == 0, stderr
        assert repeated is not None
        assert repeated["providerRequestsSent"] == 0
        assert repeated["publishStatus"] == "unchanged"
        assert repeated["collectionSha256"] == checkpoint
        assert blocked.payloads == []
    assert len(attempt_files(project)) == 1
    code, recovered, stderr = resume(capsys, project, copied_proposal, copied_authorization)
    assert code == 0, stderr
    assert recovered is not None
    assert recovered["providerRequestsSent"] == 0
    assert recovered["status"] == "published"


def test_transport_error_keeps_unknown_reservation_without_publish(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([TransportError("provider.timeout", True)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 4, stderr
    assert report is not None
    assert report["status"] == "failed"
    assert report["chargeStatus"] == "unknown"
    assert report["httpStatus"] is None
    assert report["responseBytes"] == 0
    assert report["reservationCny"] == "0.416"
    assert not (project / "static-observations.sqlite3").exists()
    with pytest.MonkeyPatch.context() as patch:
        check = FakeVisionTransport([])
        patch.setattr(cli_generation, "build_vision_transport", lambda: check)
        code, recovered, stderr = resume(capsys, project, proposal_path, authorization_path)
        assert code == 4, stderr
        assert recovered is not None
        assert check.payloads == []
        assert recovered["status"] == "failed"


def test_dispatch_forwards_the_exact_single_registered_frame_and_condition_lookup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document(conditions=default_conditions()[:2]))
    code, search, stderr = invoke(
        capsys,
        "search-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        COLLECTION,
        "--input",
        str(query_path),
    )
    assert code == 0, stderr
    assert search is not None
    assert search["matchCount"] == 1
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM semantic_events").fetchone()[0] == 0


def test_planned_attempt_is_durable_before_the_single_http_send(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    proposal = loads_static_generation_proposal(proposal_path.read_bytes())
    observed: dict[str, object] = {}

    def before_post(payload: dict[str, object], timeout_seconds: float) -> None:
        del payload, timeout_seconds
        ledger = SqliteStaticGenerationLedger(project)
        try:
            state = ledger.load_attempt(proposal.proposal_sha256)
            assert state is not None
            assert state.result is None
            assert state.charge_status == "unknown"
            observed["reservation"] = str(state.reservation_cny)
            observed["revision"] = state.revision
        finally:
            ledger.close()
        attempt_file = next(
            (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
        )
        document = json.loads(attempt_file.read_text(encoding="utf-8"))
        assert document["status"] == "planned"
        assert document["result"] is None
        assert document["reservationCny"] == "0.416"
        assert document["inputFrames"] == 1

    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)], before_post=before_post)
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    assert report["providerRequestsSent"] == 1
    assert observed == {"reservation": "0.416", "revision": 1}
    assert len(transport.payloads) == 1


def test_missing_usage_keeps_unknown_reservation_but_publishes_typed_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT, usage=False)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    assert report["status"] == "published"
    assert report["chargeStatus"] == "unknown"
    assert report["chargeCny"] is None
    assert report["reservationCny"] == "0.416"
    assert report["overAuthorizationLimit"] is False
    assert load_collection(project).observations[0].actors


def test_actual_estimated_cost_above_authorization_is_recorded_not_clipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 100_000,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 1_000_000,
        "total_tokens": 1_100_000,
    }
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT, usage_values=usage)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    assert report["status"] == "published"
    assert report["chargeStatus"] == "known"
    charge = Decimal(str(report["chargeCny"]))
    assert charge > Decimal("0.5")
    assert report["overAuthorizationLimit"] is True
    assert report["reservationCny"] == "0.416"
    assert load_collection(project).observations[0].actors


def test_raw_model_and_http_shapes_are_never_persisted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    raw_content = '{"actors": []}'
    transport = FakeVisionTransport([static_reply(raw_content)])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code == 0, stderr
    assert report is not None
    attempt_file = next(
        (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
    )
    persisted = attempt_file.read_text(encoding="utf-8")
    assert raw_content not in persisted
    assert '"choices"' not in persisted
    assert report["responseSha256"] in persisted
    assert report["responseBytes"] > 0
    result_document = json.loads(persisted)["result"]
    assert result_document["metadata"]["provider"] == "deepseek"
    assert result_document["metadata"]["requestedModel"] == "deepseek-flash"
    assert result_document["metadata"]["actualModel"] == "deepseek-flash"
    assert result_document["metadata"]["promptVersion"] == STATIC_GENERATION_PROMPT_VERSION
    assert result_document["metadata"]["schemaVersion"] == STATIC_GENERATION_SCHEMA_VERSION
    assert result_document["metadata"]["attempt"] == 1


def test_copied_authorization_cannot_authorize_another_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    project_one, bundle_one = create_project(first_root)
    project_two, bundle_two = create_project(second_root)
    proposal_one = first_root / "proposal.json"
    prepare(capsys, project_one, proposal_one, bundle_one.images[0].evidence_id)
    authorization_one = write_authorization(first_root / "authorization.json", proposal_one)
    proposal_two = second_root / "proposal.json"
    prepare(capsys, project_two, proposal_two, bundle_two.images[0].evidence_id)
    copied = second_root / "copied-authorization.json"
    copied.write_bytes(authorization_one.read_bytes())
    transport = FakeVisionTransport([])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project_two, proposal_two, copied)
    assert code == 7
    assert report is None
    assert error_code(stderr) in {
        "static_generation.authorization_mismatch",
        "static_generation.authorization_scope",
    }
    assert transport.payloads == []
    assert attempt_files(project_two) == ()
    assert not (project_two / "static-observations.sqlite3").exists()


@pytest.mark.parametrize(
    ("mutation", "parameters"),
    [
        (
            "UPDATE analysis_runs SET status='running' WHERE run_id=?",
            ("run-1",),
        ),
        (
            "UPDATE evidence SET start_us=start_us+1 WHERE evidence_id=?",
            ("__EVIDENCE__",),
        ),
        (
            "UPDATE media_assets SET content_hash=? WHERE media_id=?",
            ("f" * 64, "media-1"),
        ),
    ],
    ids=["completed_eligibility", "registered_clock", "media_source_hash"],
)
def test_current_database_drift_is_refused_before_send(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    parameters: tuple[str, ...],
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    values = tuple(
        bundle.images[0].evidence_id if value == "__EVIDENCE__" else value for value in parameters
    )
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as connection:
        connection.execute(mutation, values)
        connection.commit()
    transport = FakeVisionTransport([])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, proposal_path, authorization_path)
    assert code in (2, 5), (code, stderr)
    assert report is None
    assert transport.payloads == []
    assert attempt_files(project) == ()
    assert not (project / "static-observations.sqlite3").exists()


def test_old_frozen_protocol_identity_cannot_be_reinterpreted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project, bundle = create_project(tmp_path)
    proposal_path = tmp_path / "proposal.json"
    prepare(capsys, project, proposal_path, bundle.images[0].evidence_id)
    authorization_path = write_authorization(tmp_path / "authorization.json", proposal_path)
    document = json.loads(proposal_path.read_text(encoding="utf-8"))
    document["profile"] = "static-frame-profile-v1"
    document["promptVersion"] = "static-frame-observation-prompt-v1"
    document["generationSchemaVersion"] = "static-observation-generation-schema-v1"
    document["promptHash"] = "a" * 64
    old_protocol = tmp_path / "old-protocol-proposal.json"
    old_protocol.write_text(json.dumps(document), encoding="utf-8")
    transport = FakeVisionTransport([])
    invocation(transport, monkeypatch)
    code, report, stderr = dispatch(capsys, project, old_protocol, authorization_path)
    assert code == 2, stderr
    assert report is None
    assert transport.payloads == []
    assert attempt_files(project) == ()
    assert not (project / "static-observations.sqlite3").exists()
