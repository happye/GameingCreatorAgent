"""Proposal prep freezes registered requests without sending, reserving or rewriting sources."""

import asyncio
import importlib.util
import json
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from storage_process_helper import RUN_ID, prepare
from test_detail_budget_sidecar import EVENT, OTHER, timeline
from test_detail_parts import registered_timeline
from test_detail_provider import prepared_fixture

from gamingcreator.application.detail_refinement import canonical_request_json, prepare_refinement
from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

SPEC = importlib.util.spec_from_file_location(
    "detail_temporal_proposal_script",
    Path(__file__).parents[1] / "scripts/prepare-detail-temporal-pilot.py",
)
assert SPEC is not None and SPEC.loader is not None
proposal_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proposal_script
SPEC.loader.exec_module(proposal_script)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    request, paths = prepared_fixture(images)
    stored = registered_timeline(request, paths)
    first = next(item for item in stored.events if item.event_id == EVENT)
    second = replace(first, event_id=OTHER, observable_facts=("另一个候选的冻结事实。",))
    stored = replace(stored, events=(first, second))
    project = tmp_path / "project"
    project.mkdir()
    (project / "timeline.sqlite3").write_bytes(b"snapshot-only database fixture")
    budget = project / "detail-refinement-budgets/legacy"
    budget.mkdir(parents=True)
    (budget / "ledger.jsonl").write_text("unchanged ledger fixture", encoding="utf-8")
    details = project / "runs/run-1/detail-refinements/frozen"
    details.mkdir(parents=True)
    (details / "result.json").write_text("unchanged sidecar fixture", encoding="utf-8")
    specifications = []
    rows = []
    for case_id, event_id in (("actor-separation", EVENT), ("held-item-shape", OTHER)):
        old = prepare_refinement(stored, event_id, identity=provider_refinement_identity())
        assert old.request is not None
        specifications.append(
            proposal_script.CaseSpec(
                case_id, stored.run.run_id, event_id, old.request_hash, "开发fixture。"
            )
        )
        rows.append(
            {
                "caseId": case_id,
                "runId": stored.run.run_id,
                "eventId": event_id,
                "requestHash": old.request_hash,
                "canonicalRequest": json.loads(canonical_request_json(old.request)),
            }
        )
    monkeypatch.setattr(proposal_script, "CASE_SPECS", tuple(specifications))
    baseline = tmp_path / "legacy-proposal.json"
    baseline.write_text(
        json.dumps(
            {
                "schemaVersion": "actor-detail-pilot-proposal-v1",
                "priorUnknownReservationCny": "4.065536",
                "cases": rows,
            }
        ),
        encoding="utf-8",
    )
    shared = {
        "knownEstimatedCostCny": "0.01850612",
        "unknownCostCount": 0,
        "unknownReservedCny": "0",
        "commitmentCny": "0.01850612",
        "attemptCount": 2,
    }
    history = {
        "sharedCommitment": shared,
        "attempts": [
            {"requestHash": item.old_request_hash, "status": "completed"} for item in specifications
        ],
    }
    monkeypatch.setattr(proposal_script, "refinement_cost_history", lambda *args: history)
    calls = []

    class ReadOnlyStore:
        async def load_completed_timeline(self, run_id):
            calls.append(("load_completed_timeline", run_id))
            return stored

        async def close(self):
            calls.append(("closed",))

    async def open_read_only(path, *, read_only=False):
        assert path == project.resolve() and read_only
        calls.append(("read_only",))
        return ReadOnlyStore()

    monkeypatch.setattr(
        proposal_script,
        "SqliteTimelineStore",
        type("Store", (), {"open": staticmethod(open_read_only)}),
    )
    return project, baseline, stored, paths, history, calls


def read_proposal(prepared):
    project, baseline, *_ = prepared
    return asyncio.run(proposal_script.prepare_proposal(project, baseline))


def test_exact_original_frames_and_read_only_sources_are_frozen_without_any_calls(
    prepared, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No sending, locks, reservations or settlement during preparation")

    for name in (
        "BudgetWriterLock",
        "RefinementWriterLock",
        "begin_attempt",
        "finish_attempt",
        "send_refinement",
    ):
        monkeypatch.setattr(sidecar, name, forbidden)
    monkeypatch.setattr(proposal_script.DeepSeekDetailTemporalProvider, "refine", forbidden)
    monkeypatch.setattr(proposal_script.NoSendTransport, "post", forbidden)
    result = read_proposal(prepared)
    project, baseline, stored, *_ = prepared
    assert result["paidRequestsSent"] == 0 and result["realV4RecognitionVerified"] is False
    assert result["protectedFilesBefore"] == result["protectedFilesAfter"]
    assert result["protectedFilesBefore"] == proposal_script.protected_snapshot(project)
    assert result["authorization"] == {
        "legacyAuthorizedAttempts": 2,
        "legacyAttemptsConsumed": 2,
        "newBudgetAndRequestCountPermissionRequired": True,
        "newDestinationPermissionRequired": True,
        "executionAuthorized": False,
    }
    assert result["destination"] == "https://api.deepseek.com/chat/completions"
    assert result["maximumNewHttpAttempts"] == 2 and not result["automaticRetry"]
    assert len(result["cases"]) == 2
    original = json.loads(baseline.read_text())["cases"]
    for case, old in zip(result["cases"], original, strict=True):
        assert len(case["inputFrames"]) == 3 and case["maxHttpAttempts"] == 1
        assert case["canonicalRequest"]["evidence"] == old["canonicalRequest"]["evidence"]
        assert case["canonicalRequest"]["settings"]["maxOutputTokens"] == 4096
        assert case["canonicalRequest"]["schemaVersion"] == "actor-detail-refinement-schema-v2"
        assert case["requestHash"] != old["requestHash"]
        assert case["inputFrames"][0]["width"] == 512
        assert all(
            item["evidenceId"] in stored.events[0].evidence_ids for item in case["inputFrames"]
        )
        assert case["sequenceTextBlocks"][0]["frameCount"] == 3
    assert prepared[-1] == [
        ("read_only",),
        ("load_completed_timeline", stored.run.run_id),
        ("load_completed_timeline", stored.run.run_id),
        ("closed",),
    ]


def test_peak_reservation_is_separate_from_current_shared_cost_and_old_unknown(prepared):
    cost = read_proposal(prepared)["costPlan"]
    assert cost["period"] == "peak" and cost["inputTokenCeilingPerAttempt"] == 1_000_000
    assert cost["maxOutputTokensPerAttempt"] == 4096
    assert Decimal(cost["reservationCnyPerAttempt"]) == Decimal("2.032768")
    assert Decimal(cost["newMaximumReservationCny"]) == Decimal("4.065536")
    assert Decimal(cost["minimumSourceProjectSharedRefinementCeilingCny"]) == Decimal("4.08404212")
    assert cost["priorTaskUnknownReservationCny"] == "4.065536"
    assert cost["priorTaskUnknownReservationPreserved"] and not cost["reservationIsInvoice"]


def test_source_project_unknown_commitment_cannot_disappear_in_new_budget_plan(prepared):
    history = prepared[4]
    history["sharedCommitment"].update(
        unknownCostCount=1, unknownReservedCny="2", commitmentCny="2.01850612"
    )
    cost = read_proposal(prepared)["costPlan"]
    assert Decimal(cost["minimumSourceProjectSharedRefinementCeilingCny"]) == Decimal("6.08404212")
    assert cost["sourceProjectExistingRefinementCommitment"]["unknownReservedCny"] == "2"
    assert cost["priorTaskUnknownReservationCny"] == "4.065536"


@pytest.mark.parametrize(
    "damage",
    [
        "missing_image",
        "changed_image",
        "candidate_facts",
        "extra_candidate_frame",
        "incomplete_run",
        "cross_candidate",
        "canonical_tamper",
        "source_database_missing",
        "legacy_attempt_missing",
    ],
)
def test_source_changes_missing_inputs_and_foreign_candidates_block_freezing(
    prepared, monkeypatch, damage
):
    project, baseline, stored, paths, history, _ = prepared
    if damage == "missing_image":
        next(iter(paths.values())).unlink()
    elif damage == "changed_image":
        next(iter(paths.values())).write_bytes(b"changed")
    elif damage == "source_database_missing":
        (project / "timeline.sqlite3").unlink()
    elif damage == "legacy_attempt_missing":
        history["attempts"] = []
    elif damage in {"cross_candidate", "canonical_tamper"}:
        value = json.loads(baseline.read_text())
        if damage == "cross_candidate":
            value["cases"][0]["eventId"] = value["cases"][1]["eventId"]
        else:
            value["cases"][0]["canonicalRequest"]["evidence"][0]["sha256"] = "a" * 64
        baseline.write_text(json.dumps(value), encoding="utf-8")
    else:
        if damage == "candidate_facts":
            stored = replace(
                stored,
                events=(
                    replace(stored.events[0], observable_facts=("changed",)),
                    *stored.events[1:],
                ),
            )
        elif damage == "extra_candidate_frame":
            stored = replace(
                stored,
                events=(
                    replace(
                        stored.events[0],
                        evidence_ids=(
                            *stored.events[0].evidence_ids,
                            timeline().evidence[-1].evidence_id,
                        ),
                    ),
                    *stored.events[1:],
                ),
            )
        else:
            stored = replace(stored, run=replace(stored.run, status=RunStatus.FAILED))

        class Store:
            async def load_completed_timeline(self, run_id):
                return stored

            async def close(self):
                pass

        async def open_store(*args, **kwargs):
            return Store()

        monkeypatch.setattr(
            proposal_script,
            "SqliteTimelineStore",
            type("Fake", (), {"open": staticmethod(open_store)}),
        )
    with pytest.raises((OSError, ValueError, AppError)):
        read_proposal(prepared)


@pytest.mark.parametrize("file_type", ["database", "sidecar", "ledger"])
def test_concurrent_source_mutation_is_detected_before_any_proposal_output(
    prepared, monkeypatch, file_type
):
    project, _, stored, *_ = prepared
    path = {
        "database": project / "timeline.sqlite3",
        "sidecar": project / "runs/run-1/detail-refinements/frozen/result.json",
        "ledger": project / "detail-refinement-budgets/legacy/ledger.jsonl",
    }[file_type]

    class Store:
        async def load_completed_timeline(self, run_id):
            path.write_bytes(b"concurrent writer changed the file")
            return stored

        async def close(self):
            pass

    async def open_store(*args, **kwargs):
        return Store()

    monkeypatch.setattr(
        proposal_script, "SqliteTimelineStore", type("Fake", (), {"open": staticmethod(open_store)})
    )
    with pytest.raises(ValueError, match="changed during preparation"):
        read_proposal(prepared)


def test_freeze_is_exclusive_and_refuses_output_inside_the_source_project(prepared, tmp_path):
    proposal = read_proposal(prepared)
    output = tmp_path / "review/proposal.json"
    digest = proposal_script.freeze_proposal(proposal, output)
    before = output.read_bytes()
    assert proposal_script._sha(before) == digest
    with pytest.raises(FileExistsError):
        proposal_script.freeze_proposal(proposal, output)
    assert output.read_bytes() == before
    with pytest.raises(ValueError):
        proposal_script.freeze_proposal(proposal, Path("relative.json"))
    with pytest.raises(ValueError):
        proposal_script.freeze_proposal(proposal, prepared[0] / "proposal.json")


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_real_completed_timeline_loader_rejects_missing_or_changed_source_media(
    prepared, tmp_path, monkeypatch, damage
):
    project = tmp_path / "real-storage"
    asyncio.run(prepare(project, completed=True))
    source = project / "fixture-source.mp4"
    if damage == "missing":
        source.unlink()
    else:
        source.write_bytes(b"changed source video")
    specs = tuple(replace(item, run_id=RUN_ID) for item in proposal_script.CASE_SPECS)
    monkeypatch.setattr(proposal_script, "CASE_SPECS", specs)
    value = json.loads(prepared[1].read_text())
    for row in value["cases"]:
        row["runId"] = RUN_ID
    prepared[1].write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(proposal_script, "SqliteTimelineStore", SqliteTimelineStore)
    with pytest.raises(AppError):
        asyncio.run(proposal_script.prepare_proposal(project, prepared[1]))
