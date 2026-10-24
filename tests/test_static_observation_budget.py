"""Static generation budget: pure policy, fixed project ledger, and conservative recovery."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_static_observation_generation import authorization_document

from gamingcreator.application.providers import (
    CostStatus,
    InvocationMetadata,
    ProviderUsage,
)
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observation_budget import (
    StaticAttemptResult,
    StaticAttemptState,
    attempt_charge,
    budget_usage,
    consistency_verdict,
    ensure_plan_allowed,
)
from gamingcreator.application.static_observation_generation import (
    STATIC_GENERATION_PROMPT_VERSION,
    STATIC_GENERATION_SCHEMA_VERSION,
    StaticGenerationAuthorization,
    StaticGenerationProposal,
    authorization_sha256,
    build_static_generation_proposal,
    loads_static_generation_authorization,
    loads_static_generation_proposal,
    proposal_file_bytes,
)
from gamingcreator.domain.actor_details import AttributeKind, AttributeStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.static_observations import StaticActor, StaticAttribute
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_attempts import (
    LEDGER_SQLITE_NAME,
    SqliteStaticGenerationLedger,
)


def project_and_proposal(
    tmp_path: Path, *, collection: str = "look-1"
) -> tuple[Path, Path, StaticGenerationProposal]:
    from test_static_observations import create_project

    project, bundle = create_project(tmp_path)
    proposal = proposal_for(project, bundle.images[0].evidence_id, collection=collection)
    path = tmp_path / f"proposal-{collection}.json"
    path.write_bytes(proposal_file_bytes(proposal))
    return project, path, proposal


def proposal_for(
    project: Path, evidence_id: str, *, collection: str = "look-1"
) -> StaticGenerationProposal:
    async def load() -> object:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await load_searchable_timeline(store, "run-1")
        finally:
            await store.close()

    timeline = asyncio.run(load())
    return build_static_generation_proposal(
        project,
        timeline,  # type: ignore[arg-type]
        run_id="run-1",
        collection_id=collection,
        evidence_id=evidence_id,
    )


def authorization_for(
    proposal_path: Path, *, authorization_id: str = "auth-ledger-1", **overrides: object
) -> StaticGenerationAuthorization:
    document = authorization_document(proposal_path, authorization_id=authorization_id, **overrides)
    return loads_static_generation_authorization(
        json.dumps(document, ensure_ascii=False).encode("utf-8")
    )


def changed_authorization(
    authorization: StaticGenerationAuthorization, **changes: object
) -> StaticGenerationAuthorization:
    draft = replace(authorization, authorization_sha256="0" * 64, **changes)
    return replace(draft, authorization_sha256=authorization_sha256(draft))


def metadata(*, cost: Decimal | None = None) -> InvocationMetadata:
    usage = (
        ProviderUsage()
        if cost is None
        else ProviderUsage(
            original_cost=cost,
            currency="CNY",
            cost_cny=cost,
            cost_status=CostStatus.ESTIMATED,
        )
    )
    return InvocationMetadata(
        "deepseek",
        "deepseek-flash",
        "deepseek-flash",
        None,
        STATIC_GENERATION_PROMPT_VERSION,
        STATIC_GENERATION_SCHEMA_VERSION,
        1,
        usage,
    )


def observed_result(cost: Decimal | None = Decimal("0.01")) -> StaticAttemptResult:
    actor = StaticActor(
        "actor-1",
        (
            StaticAttribute(
                "hair", "hair", AttributeKind.HAIR_COLOR, "black", AttributeStatus.OBSERVED
            ),
        ),
    )
    return StaticAttemptResult(
        "observed",
        (actor,),
        metadata(cost=cost),
        "a" * 64,
        512,
        128,
        200,
        (),
        "2026-10-24T05:00:01+00:00",
    )


def unknown_failure_result() -> StaticAttemptResult:
    return StaticAttemptResult(
        "failed",
        (),
        metadata(cost=None),
        None,
        0,
        None,
        None,
        ("provider.timeout",),
        "2026-10-24T05:00:01+00:00",
    )


def attempt_state(
    *,
    revision: int,
    result: StaticAttemptResult | None,
    charge: Decimal | None,
    charge_status: str,
) -> StaticAttemptState:
    return StaticAttemptState(
        "attempt-" + "f" * 32,
        "a" * 64,
        "auth-ledger-1",
        "b" * 64,
        "a" * 64,
        "run-1",
        "look-1",
        Decimal("0.416"),
        "CNY",
        "2026-10-24T05:00:00+00:00",
        revision,
        1,
        False,
        result,
        charge,
        charge_status,  # type: ignore[arg-type]
    )


def test_consistency_verdict_is_explicit_and_conservative() -> None:
    assert (
        consistency_verdict(
            row_present=False,
            file_present=False,
            row_revision=0,
            file_revision=0,
            row_sha256="",
            file_sha256="",
        )
        == "consistent"
    )
    assert (
        consistency_verdict(
            row_present=False,
            file_present=True,
            row_revision=0,
            file_revision=1,
            row_sha256="",
            file_sha256="c" * 64,
        )
        == "reconstruct_row"
    )
    assert (
        consistency_verdict(
            row_present=True,
            file_present=True,
            row_revision=1,
            file_revision=2,
            row_sha256="c" * 64,
            file_sha256="d" * 64,
        )
        == "settle_from_file"
    )
    assert (
        consistency_verdict(
            row_present=True,
            file_present=True,
            row_revision=2,
            file_revision=2,
            row_sha256="c" * 64,
            file_sha256="c" * 64,
        )
        == "consistent"
    )
    with pytest.raises(AppError):
        consistency_verdict(
            row_present=True,
            file_present=False,
            row_revision=1,
            file_revision=0,
            row_sha256="c" * 64,
            file_sha256="",
        )
    for row_revision, file_revision, row_sha, file_sha in (
        (2, 1, "d" * 64, "c" * 64),
        (1, 1, "c" * 64, "d" * 64),
        (2, 2, "c" * 64, "d" * 64),
        (2, 1, "c" * 64, "c" * 64),
    ):
        assert (
            consistency_verdict(
                row_present=True,
                file_present=True,
                row_revision=row_revision,
                file_revision=file_revision,
                row_sha256=row_sha,
                file_sha256=file_sha,
            )
            == "fail_closed"
        )


def test_unknown_attempt_keeps_request_frame_and_money() -> None:
    planned = attempt_state(revision=1, result=None, charge=None, charge_status="unknown")
    usage = budget_usage((planned,))
    assert usage.requests == 1
    assert usage.input_frames == 1
    assert usage.known_cost_cny == 0
    assert usage.reserved_cny == Decimal("0.416")
    assert usage.committed_cny == Decimal("0.416")
    with pytest.raises(AppError) as refused:
        ensure_plan_allowed(
            (planned,),
            reservation_cny=Decimal("0.416"),
            currency="CNY",
            max_cost_cny=Decimal("0.5"),
            max_requests=1,
            max_input_frames=1,
        )
    assert refused.value.code == "static_generation.budget_exhausted"
    ensure_plan_allowed(
        (),
        reservation_cny=Decimal("0.416"),
        currency="CNY",
        max_cost_cny=Decimal("0.5"),
        max_requests=1,
        max_input_frames=1,
    )
    with pytest.raises(AppError):
        ensure_plan_allowed(
            (),
            reservation_cny=Decimal("0.6"),
            currency="CNY",
            max_cost_cny=Decimal("0.5"),
            max_requests=1,
            max_input_frames=1,
        )
    with pytest.raises(AppError):
        ensure_plan_allowed(
            (),
            reservation_cny=Decimal("0.1"),
            currency="USD",
            max_cost_cny=Decimal("0.5"),
            max_requests=1,
            max_input_frames=1,
        )


def test_known_charge_is_recorded_once_and_never_clipped() -> None:
    result = observed_result(cost=Decimal("0.9"))
    assert attempt_charge(result) == (Decimal("0.9"), "known")
    assert attempt_charge(unknown_failure_result()) == (None, "unknown")
    settled = attempt_state(revision=2, result=result, charge=Decimal("0.9"), charge_status="known")
    usage = budget_usage((settled,))
    assert usage.known_cost_cny == Decimal("0.9")
    assert usage.reserved_cny == 0
    assert usage.committed_cny == Decimal("0.9")


def plan_attempt(
    project: Path,
    proposal_path: Path,
    *,
    authorization: StaticGenerationAuthorization | None = None,
    planned_at: str = "2026-10-24T05:00:00+00:00",
) -> tuple[SqliteStaticGenerationLedger, StaticAttemptState]:
    proposal = loads_static_generation_proposal(proposal_path.read_bytes())
    auth = authorization if authorization is not None else authorization_for(proposal_path)
    ledger = SqliteStaticGenerationLedger(project)
    ledger.bind_authorization(auth)
    state, created = ledger.plan_attempt(proposal, auth, planned_at=planned_at)
    assert created is True
    return ledger, state


def ledger_path(project: Path) -> Path:
    return project / ".static-observation-generation" / "ledger" / LEDGER_SQLITE_NAME


def test_plan_persists_planned_before_any_send_and_is_at_most_once(tmp_path: Path) -> None:
    project, proposal_path, _ = project_and_proposal(tmp_path)
    ledger, state = plan_attempt(project, proposal_path)
    try:
        assert state.result is None
        assert state.published is False
        assert state.reservation_cny == Decimal("0.416")
        assert state.charge_status == "unknown"
        assert (ledger.root / "ledger-initialized").is_file()
        attempt_file = next(
            (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
        )
        document = json.loads(attempt_file.read_text(encoding="utf-8"))
        assert document["status"] == "planned"
        assert document["revision"] == 1
        assert document["reservationCny"] == "0.416"
        assert document["inputFrames"] == 1
        auth = authorization_for(proposal_path)
        again, created = ledger.plan_attempt(
            loads_static_generation_proposal(proposal_path.read_bytes()),
            auth,
            planned_at="2026-10-24T05:10:00+00:00",
        )
        assert created is False
        assert again.attempt_id == state.attempt_id
        assert (
            len(
                tuple(
                    (project / ".static-observation-generation" / "ledger" / "attempts").glob(
                        "*.json"
                    )
                )
            )
            == 1
        )
    finally:
        ledger.close()


def test_same_authorization_cannot_switch_collection_but_a_new_one_can_send(
    tmp_path: Path,
) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, state = plan_attempt(project, proposal_path)
    try:
        other = proposal_for(project, proposal.evidence_id, collection="look-2")
        original_auth = authorization_for(proposal_path)
        with pytest.raises(AppError) as refused:
            ledger.plan_attempt(other, original_auth, planned_at="2026-10-24T05:00:00+00:00")
        assert refused.value.code == "static_generation.authorization_scope"

        other_auth = changed_authorization(
            original_auth,
            authorization_id="auth-ledger-2",
            proposal_sha256=other.proposal_sha256,
        )
        ledger.bind_authorization(other_auth)
        planned_other, created = ledger.plan_attempt(
            other, other_auth, planned_at="2026-10-24T05:00:00+00:00"
        )
        assert created is True
        assert planned_other.authorization_id == "auth-ledger-2"
        assert planned_other.charge_status == "unknown"
        assert planned_other.reservation_cny == Decimal("0.416")
        assert planned_other.result is None

        second = SqliteStaticGenerationLedger(project)
        try:
            first_state = second.load_attempt(proposal.proposal_sha256)
            assert first_state is not None
            assert first_state.authorization_id == state.authorization_id
            assert first_state.reservation_cny == Decimal("0.416")
            second_state = second.load_attempt(other.proposal_sha256)
            assert second_state is not None
            assert second_state.authorization_id == "auth-ledger-2"
            assert second_state.reservation_cny == Decimal("0.416")
        finally:
            second.close()
        assert (
            len(
                tuple(
                    (project / ".static-observation-generation" / "ledger" / "attempts").glob(
                        "*.json"
                    )
                )
            )
            == 2
        )
        # The new authorization is itself single-request: it cannot switch again.
        third = proposal_for(project, proposal.evidence_id, collection="look-3")
        third_auth = changed_authorization(other_auth, proposal_sha256=third.proposal_sha256)
        with pytest.raises(AppError) as reused:
            ledger.plan_attempt(third, third_auth, planned_at="2026-10-24T05:00:00+00:00")
        assert reused.value.code == "static_generation.authorization_conflict"
        assert len(tuple((ledger.root / "attempts").glob("*.json"))) == 2
    finally:
        ledger.close()


def test_known_result_settles_once_and_identical_replay_is_idempotent(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    try:
        result = observed_result()
        settled = ledger.record_result(request_key=proposal.proposal_sha256, result=result)  # type: ignore[attr-defined]
        assert settled.charge_status == "known"
        assert settled.charge_cny == Decimal("0.01")
        assert settled.result == result
        replay = ledger.record_result(
            request_key=proposal.proposal_sha256,
            result=result,  # type: ignore[attr-defined]
        )
        assert replay == settled
        with pytest.raises(AppError):
            ledger.record_result(
                request_key=proposal.proposal_sha256,  # type: ignore[attr-defined]
                result=observed_result(cost=Decimal("0.02")),
            )
    finally:
        ledger.close()


def test_unknown_result_keeps_its_authorization_quota_separate(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    try:
        settled = ledger.record_result(
            request_key=proposal.proposal_sha256,
            result=unknown_failure_result(),
        )
        assert settled.charge_status == "unknown"
        assert settled.charge_cny is None
        usage = budget_usage((settled,))
        assert usage.reserved_cny == Decimal("0.416")
        other = proposal_for(project, proposal.evidence_id, collection="look-2")
        original_auth = authorization_for(proposal_path)
        with pytest.raises(AppError) as switched:
            ledger.plan_attempt(other, original_auth, planned_at="2026-10-24T06:00:00+00:00")
        assert switched.value.code == "static_generation.authorization_scope"
        other_auth = changed_authorization(
            original_auth,
            authorization_id="auth-ledger-2",
            proposal_sha256=other.proposal_sha256,
        )
        ledger.bind_authorization(other_auth)
        second, created = ledger.plan_attempt(
            other, other_auth, planned_at="2026-10-24T06:00:00+00:00"
        )
        assert created is True
        assert second.authorization_id == "auth-ledger-2"
        old = ledger.load_attempt(proposal.proposal_sha256)
        assert old is not None
        assert old.charge_status == "unknown"
        assert budget_usage((old,)).reserved_cny == Decimal("0.416")
    finally:
        ledger.close()


def test_existing_empty_ledger_database_fails_closed_without_losing_history(
    tmp_path: Path,
) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, state = plan_attempt(project, proposal_path)
    ledger.close()
    attempt_file = next(
        (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
    )
    original_attempt = attempt_file.read_bytes()
    ledger_path(project).write_bytes(b"")
    with pytest.raises(AppError) as refused:
        SqliteStaticGenerationLedger(project)
    assert refused.value.code == "static_generation.ledger_corrupt"
    assert attempt_file.read_bytes() == original_attempt
    assert state.proposal_sha256 == proposal.proposal_sha256


def test_missing_ledger_database_with_attempt_history_fails_closed(tmp_path: Path) -> None:
    project, proposal_path, _ = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    ledger.close()
    attempt_file = next(
        (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
    )
    original_attempt = attempt_file.read_bytes()
    ledger_path(project).unlink()
    (project / ".static-observation-generation" / "ledger" / "ledger-initialized").unlink()
    with pytest.raises(AppError) as refused:
        SqliteStaticGenerationLedger(project)
    assert refused.value.code == "static_generation.ledger_inconsistent"
    assert attempt_file.read_bytes() == original_attempt
    assert not ledger_path(project).exists()


def test_missing_marker_after_initialization_fails_closed(tmp_path: Path) -> None:
    project, proposal_path, _ = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    ledger.close()
    marker = project / ".static-observation-generation" / "ledger" / "ledger-initialized"
    marker.unlink()
    with pytest.raises(AppError) as refused:
        SqliteStaticGenerationLedger(project)
    assert refused.value.code == "static_generation.ledger_inconsistent"


def test_existing_attempt_rejects_a_different_authorization(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, state = plan_attempt(project, proposal_path)
    try:
        other_auth = changed_authorization(
            authorization_for(proposal_path), authorization_id="auth-ledger-other"
        )
        ledger.bind_authorization(other_auth)
        with pytest.raises(AppError) as refused:
            ledger.plan_attempt(
                loads_static_generation_proposal(proposal_path.read_bytes()),
                other_auth,
                planned_at="2026-10-24T05:30:00+00:00",
            )
        assert refused.value.code == "static_generation.authorization_conflict"
        assert state.authorization_id == "auth-ledger-1"
        assert len(tuple((ledger.root / "attempts").glob("*.json"))) == 1
        assert proposal.proposal_sha256
    finally:
        ledger.close()


def test_recorded_file_ahead_of_planned_row_is_settled_from_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    try:

        def crash(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated crash after result file write")

        monkeypatch.setattr(ledger, "_settle_recorded_row", crash)
        result = observed_result()
        with pytest.raises(RuntimeError):
            ledger.record_result(request_key=proposal.proposal_sha256, result=result)  # type: ignore[attr-defined]
    finally:
        ledger.close()

    recovered = SqliteStaticGenerationLedger(project)
    try:
        state = recovered.load_attempt(proposal.proposal_sha256)  # type: ignore[attr-defined]
        assert state is not None
        assert state.result == observed_result()
        assert state.charge_status == "known"
        assert state.charge_cny == Decimal("0.01")
        assert state.revision == 2
    finally:
        recovered.close()


def test_planned_file_without_row_is_reconstructed_conservatively(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, state = plan_attempt(project, proposal_path)
    ledger.close()
    with closing(sqlite3.connect(ledger_path(project))) as connection:
        connection.execute(
            "DELETE FROM generation_attempts WHERE request_key=?",
            (proposal.proposal_sha256,),
        )
        connection.commit()
    recovered = SqliteStaticGenerationLedger(project)
    try:
        rebuilt = recovered.load_attempt(proposal.proposal_sha256)  # type: ignore[attr-defined]
        assert rebuilt is not None
        assert rebuilt.attempt_id == state.attempt_id
        assert rebuilt.result is None
        assert rebuilt.charge_status == "unknown"
        assert rebuilt.reservation_cny == Decimal("0.416")
        usage = budget_usage((rebuilt,))
        assert usage.reserved_cny == Decimal("0.416")
    finally:
        recovered.close()


def test_row_without_attempt_file_fails_closed(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    ledger.close()
    for path in (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json"):
        path.unlink()
    recovered = SqliteStaticGenerationLedger(project)
    try:
        with pytest.raises(AppError) as refused:
            recovered.load_attempt(proposal.proposal_sha256)
        assert refused.value.code == "static_generation.ledger_inconsistent"
    finally:
        recovered.close()


def test_tampered_attempt_file_fails_closed(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    ledger.close()
    attempt_file = next(
        (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
    )
    document = json.loads(attempt_file.read_text(encoding="utf-8"))
    document["plannedAt"] = "2026-10-24T05:00:02+00:00"
    attempt_file.write_text(json.dumps(document), encoding="utf-8")
    recovered = SqliteStaticGenerationLedger(project)
    try:
        with pytest.raises(AppError) as refused:
            recovered.load_attempt(proposal.proposal_sha256)  # type: ignore[attr-defined]
        assert refused.value.code == "static_generation.ledger_inconsistent"
    finally:
        recovered.close()


def test_corrupt_ledger_database_fails_closed(tmp_path: Path) -> None:
    project, proposal_path, _ = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    ledger.close()
    ledger_path(project).write_bytes(b"not a sqlite database")
    with pytest.raises(AppError) as refused:
        SqliteStaticGenerationLedger(project)
    assert refused.value.code == "static_generation.ledger_corrupt"


def test_same_authorization_id_with_different_content_is_rejected(tmp_path: Path) -> None:
    project, proposal_path, _ = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    try:
        original = authorization_for(proposal_path)
        changed = changed_authorization(original, max_cost_cny=Decimal("0.6"))
        assert changed.authorization_id == original.authorization_id
        with pytest.raises(AppError) as refused:
            ledger.bind_authorization(changed)
        assert refused.value.code == "static_generation.authorization_conflict"
    finally:
        ledger.close()


def test_publication_marking_requires_a_recorded_success(tmp_path: Path) -> None:
    project, proposal_path, proposal = project_and_proposal(tmp_path)
    ledger, _ = plan_attempt(project, proposal_path)
    try:
        with pytest.raises(AppError):
            ledger.mark_published(proposal.proposal_sha256)  # type: ignore[attr-defined]
        ledger.record_result(
            request_key=proposal.proposal_sha256,  # type: ignore[attr-defined]
            result=unknown_failure_result(),
        )
        with pytest.raises(AppError):
            ledger.mark_published(proposal.proposal_sha256)  # type: ignore[attr-defined]
    finally:
        ledger.close()
