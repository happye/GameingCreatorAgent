"""Exact local comparison contracts; fixtures do not prove visual recognition improved."""

import asyncio
import hashlib
import importlib.util
import json
import socket
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from test_detail_budget_sidecar import EVENT, OTHER
from test_detail_parts import registered_timeline
from test_detail_provider import prepared_fixture, visible_detail
from test_detail_temporal_provider import temporal_model

from gamingcreator.application.detail_query import match_report
from gamingcreator.application.detail_refinement import (
    canonical_request_json,
    prepare_refinement,
    request_hash,
)
from gamingcreator.application.detail_refinement_budget import (
    RESULT_SCHEMA_VERSION,
    canonical_detail_json,
    payload_hash,
)
from gamingcreator.domain.actor_details import AttributeConstraint, AttributeKind, QueryConstraint
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    parse_detail,
    provider_refinement_identity,
)
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    PROMPT,
    parse_temporal_detail,
    provider_temporal_identity,
    temporal_refinement_settings,
)

SPEC = importlib.util.spec_from_file_location(
    "detail_pilot_comparison_script",
    Path(__file__).parents[1] / "scripts/prepare-detail-pilot-comparison.py",
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = script
SPEC.loader.exec_module(script)


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def publish(project, request, detail):
    digest = sidecar.freeze_request(project, request)
    write_json(
        sidecar.sidecar_directory(project, request.run_id, digest) / "result.json",
        {
            "schemaVersion": RESULT_SCHEMA_VERSION,
            "requestHash": digest,
            "payloadHash": payload_hash(detail),
            "payloadJson": canonical_detail_json(detail),
            "actualModel": "fixture-only",
            "modelRevision": None,
        },
    )


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    request, paths = prepared_fixture(images)
    stored = registered_timeline(request, paths)
    first = next(event for event in stored.events if event.event_id == EVENT)
    stored = replace(stored, events=(first, replace(first, event_id=OTHER)))
    project = tmp_path / "project"
    project.mkdir()
    (project / "timeline.sqlite3").write_bytes(b"read-only fixture; actual SQL checked by dry-run")
    proposal, report, reviews, requests = [], [], [], []
    for case_id, event_id in zip(
        ("actor-separation", "held-item-shape"), (EVENT, OTHER), strict=True
    ):
        old = prepare_refinement(stored, event_id, identity=provider_refinement_identity())
        new = prepare_refinement(
            stored,
            event_id,
            identity=provider_temporal_identity(),
            settings=temporal_refinement_settings(),
        )
        assert old.request is not None and new.request is not None
        detail = parse_detail(json.dumps(visible_detail(old.request)), old.request)
        publish(project, old.request, detail)
        requests.append(new.request)
        frames = []
        for frame in new.request.evidence:
            data = paths[frame.evidence_id].read_bytes()
            width, height = script._dimensions(data)
            frames.append(
                {
                    "evidenceId": frame.evidence_id,
                    "sourceUs": frame.source_time.time_us,
                    "durationUs": frame.source_time.duration_us,
                    "sha256": frame.image_sha256,
                    "width": width,
                    "height": height,
                    "bytes": len(data),
                    "path": str(paths[frame.evidence_id].resolve()),
                }
            )
        proposal.append(
            {
                "caseId": case_id,
                "runId": stored.run.run_id,
                "eventId": event_id,
                "candidateId": new.request.candidate_id,
                "eventFingerprint": new.request.event_fingerprint,
                "legacyRequestHash": old.request_hash,
                "requestHash": new.request_hash,
                "canonicalRequest": json.loads(canonical_request_json(new.request)),
                "basePromptVersion": new.request.base_prompt_version,
                "basePromptHash": new.request.base_prompt_hash,
                "reviewPurpose": "仅用于合同验证。",
                "inputFrames": frames,
            }
        )
        constraint = QueryConstraint(
            (AttributeConstraint(AttributeKind.HAIR_COLOR, "white", "hair"),)
        )
        report.append(
            {
                "caseId": case_id,
                "runId": stored.run.run_id,
                "eventId": event_id,
                "requestHash": old.request_hash,
                "attempt": {
                    "status": "completed",
                    "requestHash": old.request_hash,
                    "payloadHash": payload_hash(detail),
                    "payloadJson": canonical_detail_json(detail),
                },
                "match": match_report(
                    old.request,
                    detail,
                    constraint,
                    run_id=stored.run.run_id,
                    event_id=event_id,
                    request_digest=old.request_hash,
                ),
            }
        )
        reviews.append(
            {
                "caseId": case_id,
                "runId": stored.run.run_id,
                "eventId": event_id,
                "requestHash": old.request_hash,
                "refinementPayloadHash": payload_hash(detail),
                "scope": "actor-description",
                "targetActorIds": ["shot-1/actor-1"],
                "verdict": "accepted" if case_id == "actor-separation" else "rejected",
                "source": "direct-project-user-feedback",
                "statement": "用户仅确认/标错旧版描述。",
            }
        )
    proposal_path, report_path, feedback_path = [
        tmp_path / name for name in ("proposal.json", "report.json", "feedback.json")
    ]
    identity = provider_temporal_identity()
    proposal_sha = write_json(
        proposal_path,
        {
            "schemaVersion": "actor-detail-temporal-pilot-proposal-v1",
            "project": str(project),
            "provider": identity.provider,
            "requestedModel": identity.requested_model,
            "promptVersion": identity.prompt_version,
            "promptHash": identity.prompt_hash,
            "schema": identity.schema_version,
            "systemPrompt": PROMPT,
            "destination": "https://api.deepseek.com/chat/completions",
            "cases": proposal,
        },
    )
    report_sha = write_json(
        report_path, {"schemaVersion": "actor-detail-pilot-report-v1", "cases": report}
    )
    write_json(
        feedback_path,
        {
            "schemaVersion": "detail-pilot-human-feedback-v1",
            "recordedOn": "2026-10-06",
            "pilotReportSha256": report_sha,
            "cases": reviews,
            "unmentionedEntries": "unreviewed",
            "phase0QualityGate": None,
            "newProviderCalls": 0,
        },
    )
    calls = []

    class Store:
        async def load_completed_timeline(self, run_id):
            calls.append(("completed", run_id))
            return stored

        async def close(self):
            calls.append(("closed",))

        @staticmethod
        async def open(path, *, read_only=False):
            assert path == project.resolve() and read_only
            calls.append(("read-only",))
            return Store()

    monkeypatch.setattr(script, "SqliteTimelineStore", Store)
    return {
        "args": [project, proposal_path, proposal_sha, report_path, feedback_path],
        "requests": requests,
        "calls": calls,
        "tmp": tmp_path,
        "paths": paths,
    }


def prepare(fixture):
    return asyncio.run(script.prepare_comparison(*fixture["args"]))


def rebind_proposal(fixture, mutation):
    path = fixture["args"][1]
    value = json.loads(path.read_text())
    mutation(value)
    fixture["args"][2] = write_json(path, value)


def test_missing_v4_keeps_exact_old_feedback_and_new_independent_dimensions_null(
    fixture, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Comparison attempted a paid call, lock, recovery or settlement")

    for name in (
        "BudgetWriterLock",
        "RefinementWriterLock",
        "begin_attempt",
        "finish_attempt",
        "send_refinement",
        "_recover_refinement",
    ):
        monkeypatch.setattr(sidecar, name, forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = script._snapshot(fixture["args"][0])
    result = prepare(fixture)
    assert result["paidRequestsSent"] == 0 and result["qualityGate"] is None
    assert script._snapshot(fixture["args"][0]) == before
    for case, template in zip(
        result["cases"], script.review_template(result)["cases"], strict=True
    ):
        assert len(case["frames"]) == 3
        assert case["legacy"]["descriptions"][0]["feedback"]
        assert case["temporal"]["state"] == "no_saved_result"
        assert case["temporal"]["scene"] is None and case["temporal"]["humanReview"] is None
        assert case["temporal"]["match"]["result"]["status"] == "unverified"
        for key in (
            "temporalPayloadHash",
            "objectMistakenForActor",
            "shotBoundariesAreReal",
            "positiveDescriptionsRetained",
            "queriedClipUsable",
            "reviewedTemporalEntityIds",
        ):
            assert template[key] is None
        assert "targetActorIds" not in template
    assert fixture["calls"][0] == ("read-only",) and fixture["calls"][-1] == ("closed",)


def test_exact_saved_v4_scene_is_read_and_matched_without_borrowing_old_judgment(fixture):
    request = fixture["requests"][0]
    detail = parse_temporal_detail(json.dumps(temporal_model(request)), request)
    publish(fixture["args"][0], request, detail)
    result = prepare(fixture)
    case = result["cases"][0]
    assert case["temporal"]["state"] == "saved_result"
    assert len(case["temporal"]["scene"]["entities"]) == 2
    assert case["temporal"]["payloadHash"] == payload_hash(detail)
    assert case["temporal"]["humanReview"] is None
    assert case["temporal"]["match"]["constraintJson"] == case["legacy"]["match"]["constraintJson"]
    page = script.render_html(result)
    assert "抵近镜头的物品" in page and "逐帧可见/遮挡" in page and "谁持有什么物品" in page


@pytest.mark.parametrize(
    "change",
    ["duplicate", "run", "request", "canonical", "frame", "time", "frame-hash", "extra-frame"],
)
def test_rebound_proposal_still_cannot_substitute_candidate_request_or_frames(fixture, change):
    def mutate(value):
        row = value["cases"][0]
        if change == "duplicate":
            value["cases"][1]["caseId"] = row["caseId"]
        elif change == "run":
            row["runId"] = "foreign-run"
        elif change == "request":
            row["requestHash"] = "a" * 64
        elif change == "canonical":
            row["canonicalRequest"]["settings"]["maxOutputTokens"] = 4095
        elif change == "extra-frame":
            row["inputFrames"].append(deepcopy(row["inputFrames"][0]))
        else:
            field = {"frame": "evidenceId", "time": "sourceUs", "frame-hash": "sha256"}[change]
            row["inputFrames"][0][field] = "foreign" if field != "sourceUs" else 28_000_001

    rebind_proposal(fixture, mutate)
    with pytest.raises(ValueError):
        prepare(fixture)


def test_frozen_sha_changed_image_and_tampered_saved_result_are_refused(fixture):
    path = fixture["args"][1]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="proposal SHA"):
        prepare(fixture)
    fixture["args"][2] = hashlib.sha256(path.read_bytes()).hexdigest()
    image = next(iter(fixture["paths"].values()))
    image.write_bytes(image.read_bytes() + b"changed")
    with pytest.raises((ValueError, script._SchemaError)):
        prepare(fixture)


def test_wrong_published_v4_hash_cannot_be_shown_as_missing_or_success(fixture):
    request = fixture["requests"][0]
    detail = parse_temporal_detail(json.dumps(temporal_model(request)), request)
    publish(fixture["args"][0], request, detail)
    directory = sidecar.sidecar_directory(
        fixture["args"][0],
        request.run_id,
        request_hash(request),
    )
    path = directory / "result.json"
    value = json.loads(path.read_text())
    value["payloadHash"] = "a" * 64
    write_json(path, value)
    with pytest.raises(AppError):
        prepare(fixture)


def test_feedback_requires_original_report_bytes_and_exact_legacy_payload(fixture):
    report = fixture["args"][3]
    report.write_bytes(report.read_bytes() + b" ")
    with pytest.raises(ValueError, match="report SHA"):
        prepare(fixture)


@pytest.mark.parametrize("change", ["status", "reason", "report-label", "case-gate", "match-label"])
def test_rebound_report_sha_cannot_forge_program_results_or_human_acceptance(fixture, change):
    report_path, feedback_path = fixture["args"][3:]
    report = json.loads(report_path.read_text())
    if change in ("status", "reason"):
        report["cases"][0]["match"]["result"][change] = (
            "unverified" if change == "status" else "伪造理由"
        )
    elif change == "report-label":
        report["humanLabels"] = {"usable": True}
    elif change == "case-gate":
        report["cases"][0]["qualityGate"] = True
    else:
        report["cases"][0]["match"]["humanLabels"] = {"usable": True}
    feedback = json.loads(feedback_path.read_text())
    feedback["pilotReportSha256"] = write_json(report_path, report)
    write_json(feedback_path, feedback)
    with pytest.raises(ValueError):
        prepare(fixture)


def test_html_escapes_every_untrusted_text_and_has_no_external_or_script_resources(fixture):
    result = prepare(fixture)
    attack = '<script>alert(1)</script><img src="https://evil.invalid" onerror="x()">'
    result["cases"][0]["reviewPurpose"] = attack
    result["cases"][0]["legacy"]["descriptions"][0]["description"] = attack
    result["cases"][0]["legacy"]["descriptions"][0]["feedback"][0]["statement"] = attack
    page = script.render_html(result)
    assert attack not in page and "&lt;script&gt;" in page
    assert "<script" not in page and 'src="https:' not in page
    assert page.count('src="data:image/jpeg;base64,') == 6
    assert "script-src 'none'" in page and "connect-src 'none'" in page
    assert "未执行/暂无结果" in page


def test_outputs_are_new_downloadable_files_and_never_overwrite_sources_or_reviews(fixture):
    result = prepare(fixture)
    output = fixture["tmp"] / "fresh-review"
    hashes = script.write_comparison(result, output)
    assert len(hashes) == 3 and set(path.name for path in output.iterdir()) == set(
        script.OUTPUT_FILES
    )
    assert (
        json.loads((output / "human-review-template.json").read_text())["phase0QualityGate"] is None
    )
    with pytest.raises(FileExistsError):
        script.write_comparison(result, output)
    for rejected in (fixture["args"][0] / "review", fixture["tmp"], Path("relative-review")):
        with pytest.raises(ValueError):
            script.write_comparison(result, rejected)


def test_source_changes_during_preparation_and_absent_database_are_refused(fixture, monkeypatch):
    original = script._snapshot
    count = 0

    def unstable(project):
        nonlocal count
        count += 1
        return dict(original(project), changed=str(count))

    monkeypatch.setattr(script, "_snapshot", unstable)
    with pytest.raises(ValueError, match="sources|source database"):
        prepare(fixture)
    (fixture["args"][0] / "timeline.sqlite3").unlink()
    with pytest.raises(FileNotFoundError):
        prepare(fixture)
