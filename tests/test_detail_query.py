"""Explicit manifest matching through real read-only SQLite and CLI boundaries."""

import json
from dataclasses import replace
from urllib.parse import urlencode

import pytest
from test_detail_inspection import publish_fixture, refuse_sends, seed_project
from test_inspection_http import get, workspace

from gamingcreator.application.detail_query import loads_constraint
from gamingcreator.application.detail_refinement import prepare_refinement
from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash
from gamingcreator.cli.main import main
from gamingcreator.domain.actor_details import canonical_constraint_json, constraint_hash
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.detail_query_sidecar import match_refinement
from gamingcreator.infrastructure.detail_refinement_sidecar import freeze_request, sidecar_directory


def manifest(*conditions):
    return {
        "schemaVersion": "actor-detail-query-schema-v1",
        "version": "actor-detail-query-v1",
        "vocabularyVersion": "actor-detail-vocabulary-v1",
        "actorAll": [
            {"kind": kind, "value": value, "partGroup": group}
            for kind, value, group in conditions or [("hair_color", "white", "hair")]
        ],
        "environmentAll": [],
    }


def constraint(*conditions):
    return loads_constraint(json.dumps(manifest(*conditions)))


def cli_args(project, timeline, input_path, profile="v1", save=False):
    args = [
        "match-details",
        "--project",
        str(project),
        "--run",
        timeline.run.run_id,
        "--event",
        timeline.events[0].event_id,
        "--input",
        str(input_path),
        "--profile",
        profile,
    ]
    return args + (["--save-match"] if save else [])


def snapshot(project):
    return {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file() and not path.name.endswith(("-shm", "-wal"))
    }


def test_explicit_synonyms_normalize_to_one_constraint_identity():
    chinese = constraint(("hair_color", "白发", "hair"))
    english = constraint()
    assert constraint_hash(chinese) == constraint_hash(english)
    assert loads_constraint(canonical_constraint_json(chinese)) == chinese


@pytest.mark.parametrize(
    "damage",
    [
        "unknown",
        "duplicate",
        "negation",
        "or",
        "version",
        "empty",
        "duplicate_condition",
        "too_many",
        "wrong_scope",
        "type",
        "oversize",
    ],
)
def test_manifest_rejects_ambiguous_or_unbounded_inputs(damage):
    value = manifest()
    if damage == "unknown":
        value["actorAll"][0]["value"] = "rainbow"
    elif damage == "negation":
        value["actorAll"][0]["not"] = True
    elif damage == "or":
        value["actorAny"] = value["actorAll"]
    elif damage == "version":
        value["version"] = "future"
    elif damage == "empty":
        value["actorAll"] = []
    elif damage == "duplicate_condition":
        value["actorAll"].append(dict(value["actorAll"][0]))
    elif damage == "too_many":
        value["actorAll"] *= 17
    elif damage == "wrong_scope":
        value["actorAll"][0].update(kind="environment", value="water")
    elif damage == "type":
        value["actorAll"][0]["partGroup"] = True
    text = json.dumps(value)
    if damage == "duplicate":
        text = text[:-1] + ',"version":"actor-detail-query-v1"}'
    elif damage == "oversize":
        text += " " * 1_048_576
    with pytest.raises(ValueError):
        loads_constraint(text)


def test_cli_missing_details_is_unverified_without_any_sidecar_write(tmp_path, monkeypatch, capsys):
    project, _, timeline = seed_project(tmp_path)
    refuse_sends(monkeypatch)
    query_path = tmp_path / "query.json"
    query_path.write_text(json.dumps(manifest()))
    before = snapshot(project)
    assert main(cli_args(project, timeline, query_path, profile="v2", save=True)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["status"] == "unverified" and result["refinementPayloadHash"] is None
    assert result["humanLabels"] is None and result["qualityGate"] is None
    assert snapshot(project) == before
    assert not (project / "runs/run-1/detail-refinements").exists()


@pytest.mark.parametrize("compound", [False, True])
def test_cli_reports_full_or_partial_with_frame_part_and_uncertainty(
    tmp_path, monkeypatch, capsys, compound
):
    project, _, timeline = seed_project(tmp_path)
    directory, _, detail = publish_fixture(project, timeline)
    refuse_sends(monkeypatch)
    conditions = [("hair_color", "white", "hair")]
    if compound:
        conditions.append(("held_class", "staff", "held"))
    query_path = tmp_path / "query.json"
    query_path.write_text(json.dumps(manifest(*conditions)))
    before = snapshot(project)
    assert main(cli_args(project, timeline, query_path)) == 0
    document = json.loads(capsys.readouterr().out)
    result = document["result"]
    assert result["status"] == ("partial" if compound else "full")
    actor = result["matches"][0]
    assert actor["actorId"] == "left" and actor["shotId"] == "shot-1"
    assert actor["satisfied"][0]["partId"] == "hair"
    assert actor["satisfied"][0]["evidenceIds"] == [detail.evidence[0].evidence_id]
    assert document["sourceRange"]["startUs"] == timeline.events[0].source_range.start_us
    assert len(actor["uncertain"]) == (1 if compound else 0)
    assert document["refinementPayloadHash"] == payload_hash(detail)
    assert snapshot(project) == before and not (directory / "matches").exists()


def test_saved_match_is_immutable_idempotent_and_does_not_change_refinement_or_sqlite(
    tmp_path, monkeypatch
):
    project, _, timeline = seed_project(tmp_path)
    directory, _, _ = publish_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    query = constraint()
    first = match_refinement(
        project, timeline, timeline.events[0].event_id, query, profile="v1", save=True
    )
    matches = list((directory / "matches").glob("*.json"))
    assert len(matches) == 1
    written = matches[0].stat().st_mtime_ns
    assert first == json.loads(matches[0].read_text())
    assert first == match_refinement(
        project, timeline, timeline.events[0].event_id, query, profile="v1", save=True
    )
    assert matches[0].stat().st_mtime_ns == written
    for relative, content in before.items():
        assert (project / relative).read_bytes() == content
    assert not list((project / "detail-refinement-budgets").glob("*/ledger.jsonl"))
    tampered = dict(first, qualityGate=True)
    matches[0].write_text(json.dumps(tampered))
    with pytest.raises(AppError) as caught:
        match_refinement(
            project, timeline, timeline.events[0].event_id, query, profile="v1", save=True
        )
    assert caught.value.code == "refinement.immutable"


def publish_v2_fixture(project, timeline):
    _v1_directory, document, detail = publish_fixture(project, timeline)
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=provider_refinement_identity()
    ).request
    digest = freeze_request(project, request)
    detail = replace(detail, detail_identity_hash=request.identity.prompt_hash)
    target = sidecar_directory(project, request.run_id, digest)
    document.update(
        requestHash=digest,
        payloadJson=canonical_detail_json(detail),
        payloadHash=payload_hash(detail),
    )
    (target / "result.json").write_text(json.dumps(document))
    return target, detail


def test_profile_selection_reads_exact_v2_over_http_without_rewriting_anything(
    tmp_path, monkeypatch
):
    project, _, timeline = seed_project(tmp_path)
    target, detail = publish_v2_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = snapshot(project)
    with workspace(tmp_path) as base:
        options = {
            "project": project.relative_to(tmp_path).as_posix(),
            "run": "run-1",
            "detailProfile": "v2",
        }
        status, _, body = get(base, "/api/inspect?" + urlencode(options))
        assert status == 200
        document = json.loads(body)
        assert document["detailRefinementProfile"]["profile"] == "v2"
        saved = document["timeline"][0]["detailRefinement"]
        assert (
            saved["availability"] == "reused"
            and saved["detail"]["detailIdentityHash"] == detail.detail_identity_hash
        )
        status, _, body = get(
            base, "/api/inspect?" + urlencode(dict(options, detailProfile="future"))
        )
        assert status == 400 and json.loads(body)["code"] == "input.detail_profile"
    assert snapshot(project) == before
    assert target.is_dir()


def test_wrong_profile_returns_unverified_instead_of_using_another_saved_version(
    tmp_path, monkeypatch
):
    project, _, timeline = seed_project(tmp_path)
    publish_fixture(project, timeline)
    refuse_sends(monkeypatch)
    result = match_refinement(
        project, timeline, timeline.events[0].event_id, constraint(), profile="v2", save=True
    )
    assert result["result"]["status"] == "unverified"
    request = prepare_refinement(
        timeline, timeline.events[0].event_id, identity=provider_refinement_identity()
    )
    assert not sidecar_directory(project, "run-1", request.request_hash).exists()


def test_cli_rejects_bad_query_before_opening_or_writing_project(tmp_path, capsys):
    project, _, timeline = seed_project(tmp_path)
    path = tmp_path / "bad.json"
    path.write_text('{"freeQuery":"白头发拿武器"}')
    before = snapshot(project)
    assert main(cli_args(project, timeline, path)) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and json.loads(captured.err)["code"] == "input.detail_query"
    assert snapshot(project) == before
