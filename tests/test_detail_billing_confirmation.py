"""Synthetic human declarations preserve API evidence and conservative send gates."""

import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from test_detail_budget_sidecar import EVENT, OTHER, RUN
from test_detail_cost_history import finish, paths, plan, snapshot

from gamingcreator.application.detail_billing_confirmation import MATERIAL_SCHEMA_VERSION
from gamingcreator.application.detail_refinement import request_hash
from gamingcreator.application.detail_refinement_budget import reserve_attempt
from gamingcreator.application.providers import (
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import detail_billing_confirmation as billing
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history


def failed(project, request, number, reservation="2"):
    sidecar.finish_attempt(
        project,
        request,
        number,
        budget_id="budget-a",
        reservation=Decimal(reservation),
        result=ProviderResult(
            ProviderStatus.FAILED,
            None,
            InvocationMetadata(
                request.identity.provider,
                request.identity.requested_model,
                None,
                None,
                request.identity.prompt_version,
                request.identity.schema_version,
                1,
                ProviderUsage(),
                execution_details="HTTP 400 synthetic fixture",
            ),
            ProviderFailure("provider.http", False),
        ),
    )


def material(project, request, number=1):
    directory, planned, result = paths(project, request, number)
    return {
        "schemaVersion": MATERIAL_SCHEMA_VERSION,
        "projectPath": str(project.resolve()),
        "runId": request.run_id,
        "budgetId": "budget-a",
        "requestHash": request_hash(request),
        "attemptNo": number,
        "requestSha256": hashlib.sha256((directory / "request.json").read_bytes()).hexdigest(),
        "plannedSha256": hashlib.sha256(planned.read_bytes()).hexdigest(),
        "resultSha256": hashlib.sha256(result.read_bytes()).hexdigest(),
        "confirmedCostCny": "0",
        "statement": "Synthetic reviewer checked no charge.",
        "source": "synthetic billing fixture",
        "confirmedAtUtc": "2026-10-11T01:02:03+00:00",
    }


def save_material(tmp_path, body, name="human.json"):
    path = tmp_path / name
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


def import_material(project, body, material_path):
    return billing.import_billing_confirmation(
        project,
        run_id=body["runId"],
        budget_id=body["budgetId"],
        request_hash=body["requestHash"],
        attempt_no=body["attemptNo"],
        material_path=material_path,
    )


def fixture(tmp_path):
    project = tmp_path / "project"
    request, number = plan(project)
    failed(project, request, number)
    body = material(project, request, number)
    return project, request, body, save_material(tmp_path, body)


def test_two_http400_release_exact_sum_keep_other_costs_and_send_gate(tmp_path, monkeypatch):
    project = tmp_path / "project"
    for event in (EVENT, OTHER):
        request, number = plan(project, event, reservation="2.032768")
        failed(project, request, number, "2.032768")
    other_request, other_number = plan(project, run="run-2")
    failed(project, other_request, other_number)
    known_request, known_number = plan(project, OTHER, run="run-3")
    finish(project, known_request, known_number, cost="0.015")
    original = snapshot(project)
    before = refinement_cost_history(project, RUN)
    for index, event in enumerate((EVENT, OTHER)):
        # The saved frozen request is deterministic; no inference or external call.
        from test_detail_budget_sidecar import timeline

        from gamingcreator.application.detail_refinement import prepare_refinement

        request = prepare_refinement(timeline(), event).request
        body = material(project, request)
        record = import_material(
            project, body, save_material(tmp_path, body, f"human-{index}.json")
        )
        assert (
            record["materialSha256"] == hashlib.sha256(record["materialJson"].encode()).hexdigest()
        )
    for name, value in original.items():
        assert snapshot(project)[name] == value
    read_before = snapshot(project)
    for name in ("_atomic", "_append_charge", "_publish", "_recover_refinement"):
        monkeypatch.setattr(sidecar, name, lambda *args: pytest.fail("Reader wrote evidence"))
    monkeypatch.setattr(
        httpx.Client, "send", lambda *args, **kwargs: pytest.fail("Reader sent HTTP")
    )
    monkeypatch.setattr(
        httpx.AsyncClient, "send", lambda *args, **kwargs: pytest.fail("Reader sent HTTP")
    )
    monkeypatch.setattr(
        sidecar.BudgetWriterLock, "acquire", lambda *args: pytest.fail("Reader locked")
    )
    after = refinement_cost_history(project, RUN, ceiling_cny=Decimal("1"))
    assert after["summary"] == before["summary"]
    assert after["sharedCommitment"] == before["sharedCommitment"]
    assert after["sharedCommitment"]["unknownCostCount"] == 3
    assert after["sharedHumanBillingSummary"] == {
        "confirmedNoChargeCount": 2,
        "releasedReservationCny": "4.065536",
        "reconciledCommitmentCny": "2.015000",
        "ceilingCny": "1",
        "remainingCny": "-1.015000",
    }
    assert all(row["metadata"]["usage"]["costCny"] is None for row in after["attempts"])
    assert snapshot(project) == read_before
    with pytest.raises(AppError):
        reserve_attempt(Decimal("2.1"), sidecar._charges(project), 1, Decimal("0.01"))


def test_idempotent_same_material_conflict_and_attempt_specificity(tmp_path):
    project, request, body, path = fixture(tmp_path)
    first = import_material(project, body, path)
    before = snapshot(project)
    assert import_material(project, body, path) == first
    assert snapshot(project) == before
    request, number = plan(project, retry=True)
    failed(project, request, number)
    report = refinement_cost_history(project, RUN)
    assert report["sharedHumanBillingSummary"]["releasedReservationCny"] == "2"
    assert [row["humanBillingConfirmation"] is None for row in report["attempts"]] == [False, True]
    changed = dict(body, statement="different reviewer statement")
    with pytest.raises(AppError):
        import_material(project, changed, save_material(tmp_path, changed))
    assert (
        refinement_cost_history(project, RUN)["sharedHumanBillingSummary"]["confirmedNoChargeCount"]
        == 1
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("projectPath", "another-project"),
        ("runId", "wrong-run"),
        ("budgetId", "wrong-budget"),
        ("requestHash", "0" * 64),
        ("attemptNo", 2),
        ("attemptNo", True),
        ("confirmedCostCny", "1"),
        ("confirmedCostCny", "NaN"),
        ("confirmedCostCny", "Infinity"),
        ("confirmedCostCny", "-0"),
        ("confirmedCostCny", 0),
        ("requestSha256", "0" * 64),
        ("plannedSha256", "0" * 64),
        ("resultSha256", "0" * 64),
        ("confirmedAtUtc", "2026-10-11T00:00:00"),
        ("statement", ""),
        ("source", "x" * 4097),
    ],
)
def test_wrong_identity_amount_or_evidence_rejected(tmp_path, field, value):
    project, _, body, _ = fixture(tmp_path)
    body[field] = value
    path = save_material(tmp_path, body)
    before = snapshot(project)
    with pytest.raises(AppError):
        import_material(project, body, path)
    assert snapshot(project) == before
    assert (
        refinement_cost_history(project, RUN)["sharedHumanBillingSummary"]["releasedReservationCny"]
        == "0"
    )


@pytest.mark.parametrize("damage", ["planned", "settled", "pending", "orphan", "no_ledger"])
def test_ineligible_attempt_refuses_confirmation(tmp_path, damage, monkeypatch):
    project, request, body, path = fixture(tmp_path)
    _, planned, result = paths(project, request)
    if damage == "planned":
        result.unlink()
    elif damage == "orphan":
        planned.unlink()
    elif damage == "no_ledger":
        (project / "detail-refinement-budgets/budget-a/ledger.jsonl").unlink()
    else:
        # Rebuild clean fixture to persist known provider usage with/without settlement.
        project = tmp_path / "known-project"
        request, number = plan(project)
        if damage == "pending":
            monkeypatch.setattr(
                sidecar, "_settle_record", lambda *args: (_ for _ in ()).throw(OSError())
            )
            with pytest.raises(OSError):
                finish(project, request, number)
        else:
            finish(project, request, number)
        body = material(project, request)
        path = save_material(tmp_path, body)
    before = snapshot(project)
    with pytest.raises(AppError):
        import_material(project, body, path)
    assert snapshot(project) == before


@pytest.mark.parametrize("damage", ["duplicate", "nonfinite", "oversize"])
def test_strict_material_json(tmp_path, damage):
    project, _, body, path = fixture(tmp_path)
    if damage == "duplicate":
        path.write_text(json.dumps(body)[:-1] + ',"attemptNo":1}')
    elif damage == "nonfinite":
        path.write_text(json.dumps(dict(body, attemptNo=float("nan"))))
    else:
        path.write_bytes(b" " * (sidecar._MAX_JSON_BYTES + 1))
    before = snapshot(project)
    with pytest.raises(AppError):
        import_material(project, body, path)
    assert snapshot(project) == before


@pytest.mark.parametrize("damage", ["record", "original", "orphan", "duplicate_key", "oversize"])
def test_damaged_published_records_never_release_or_repair(tmp_path, damage):
    project, request, body, path = fixture(tmp_path)
    import_material(project, body, path)
    record_path = next(project.rglob("billing-confirmations/*.json"))
    if damage == "original":
        result = paths(project, request)[2]
        result.write_bytes(result.read_bytes() + b"\n")
    elif damage == "orphan":
        (project / "detail-refinement-budgets/budget-a/ledger.jsonl").unlink()
    elif damage == "duplicate_key":
        record_path.write_text(record_path.read_text()[:-1] + ',"reservationCny":"2"}')
    elif damage == "oversize":
        record_path.write_bytes(b" " * (sidecar._MAX_JSON_BYTES + 1))
    else:
        record_path.write_text("{}")
    before = snapshot(project)
    with pytest.raises(AppError):
        refinement_cost_history(project, RUN)
    assert snapshot(project) == before


def test_interrupted_atomic_publish_is_not_counted_then_can_resume(tmp_path, monkeypatch):
    project, _, body, path = fixture(tmp_path)
    original_replace = Path.replace

    def interrupt(self, target):
        if "billing-confirmations" in str(target):
            raise OSError("synthetic interruption before publication")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", interrupt)
    with pytest.raises(AppError):
        import_material(project, body, path)
    assert list(project.rglob("billing-confirmations/*.json.tmp"))
    assert (
        refinement_cost_history(project, RUN)["sharedHumanBillingSummary"]["releasedReservationCny"]
        == "0"
    )
    monkeypatch.setattr(Path, "replace", original_replace)
    import_material(project, body, path)
    assert (
        refinement_cost_history(project, RUN)["sharedHumanBillingSummary"]["releasedReservationCny"]
        == "2"
    )


def test_second_process_import_read_and_lock_busy(tmp_path):
    project, _, body, path = fixture(tmp_path)
    code = """
import json, sys
from pathlib import Path
from gamingcreator.infrastructure.detail_billing_confirmation import import_billing_confirmation
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history
from gamingcreator.domain.errors import AppError
b=json.loads(Path(sys.argv[2]).read_text())
try:
    import_billing_confirmation(Path(sys.argv[1]),run_id=b['runId'],budget_id=b['budgetId'],request_hash=b['requestHash'],attempt_no=b['attemptNo'],material_path=Path(sys.argv[2]))
except AppError as e:
    print(e.code); sys.exit(4)
print(json.dumps(refinement_cost_history(Path(sys.argv[1]), b['runId'])['sharedHumanBillingSummary']))
"""
    with sidecar.BudgetWriterLock(project):
        busy = subprocess.run(
            [sys.executable, "-B", "-c", code, str(project), str(path)],
            capture_output=True,
            text=True,
        )
    assert busy.returncode == 4 and "storage.writer_busy" in busy.stdout
    assert (
        refinement_cost_history(project, RUN)["sharedHumanBillingSummary"]["releasedReservationCny"]
        == "0"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(project), str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["releasedReservationCny"] == "2"
    before = snapshot(project)
    again = subprocess.run(
        [sys.executable, "-B", "-c", code, str(project), str(path)], capture_output=True, text=True
    )
    assert again.returncode == 0 and snapshot(project) == before


def test_material_link_rejected(tmp_path):
    project, _, body, path = fixture(tmp_path)
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("Windows symlink permission unavailable")
    with pytest.raises(AppError):
        import_material(project, body, link)


def test_missing_history_has_no_writes_and_no_invented_ceiling(tmp_path):
    project = tmp_path / "missing"
    report = refinement_cost_history(project, RUN)
    assert report["sharedHumanBillingSummary"] == {
        "confirmedNoChargeCount": 0,
        "releasedReservationCny": "0",
        "reconciledCommitmentCny": "0",
    }
    assert not project.exists()


def test_cross_project_and_explicit_argument_mismatch_rejected_before_lock(tmp_path):
    project, _, body, path = fixture(tmp_path)
    wrong_project = tmp_path / "another-project"
    with pytest.raises(AppError):
        import_material(wrong_project, body, path)
    assert not wrong_project.exists()
    before = snapshot(project)
    with pytest.raises(AppError):
        billing.import_billing_confirmation(
            project,
            run_id="wrong-run",
            budget_id=body["budgetId"],
            request_hash=body["requestHash"],
            attempt_no=body["attemptNo"],
            material_path=path,
        )
    assert snapshot(project) == before


def test_original_evidence_rechecked_inside_budget_lock(tmp_path, monkeypatch):
    project, request, body, path = fixture(tmp_path)
    acquire = sidecar.BudgetWriterLock.acquire

    def drift_on_acquire(self):
        acquire(self)
        result = paths(project, request)[2]
        result.write_bytes(result.read_bytes() + b"\n")

    monkeypatch.setattr(sidecar.BudgetWriterLock, "acquire", drift_on_acquire)
    with pytest.raises(AppError):
        import_material(project, body, path)
    assert not list(project.rglob("billing-confirmations/*.json"))
    assert (
        refinement_cost_history(project, RUN)["sharedHumanBillingSummary"]["releasedReservationCny"]
        == "0"
    )


@pytest.mark.parametrize(
    "ceiling", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1"), Decimal("1e-99999"), "2", True]
)
def test_invalid_explicit_ceiling_refuses_without_writes(tmp_path, ceiling):
    project, _, _, _ = fixture(tmp_path)
    before = snapshot(project)
    with pytest.raises(AppError):
        refinement_cost_history(project, RUN, ceiling_cny=ceiling)
    assert snapshot(project) == before


def test_concurrent_process_imports_publish_only_one_confirmation(tmp_path):
    project, _, body, path = fixture(tmp_path)
    ready_paths = [tmp_path / f"ready-{index}" for index in range(2)]
    start = tmp_path / "start"
    code = """
import json, sys, time
from pathlib import Path
from gamingcreator.infrastructure.detail_billing_confirmation import import_billing_confirmation
from gamingcreator.domain.errors import AppError
b=json.loads(Path(sys.argv[2]).read_text())
Path(sys.argv[3]).touch()
deadline=time.monotonic()+10
while not Path(sys.argv[4]).exists():
    if time.monotonic()>deadline: sys.exit(5)
    time.sleep(.01)
try:
    r=import_billing_confirmation(Path(sys.argv[1]),run_id=b['runId'],budget_id=b['budgetId'],request_hash=b['requestHash'],attempt_no=b['attemptNo'],material_path=Path(sys.argv[2]))
    print(r['materialSha256'])
except AppError as e:
    print(e.code); sys.exit(4)
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", code, str(project), str(path), str(ready), str(start)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for ready in ready_paths
    ]
    import time

    try:
        deadline = time.monotonic() + 10
        while not all(ready.exists() for ready in ready_paths):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        start.touch()
        results = [(process, process.communicate(timeout=15)) for process in processes]
        assert any(process.returncode == 0 for process, _ in results)
        for process, (stdout, stderr) in results:
            assert process.returncode in (0, 4), stderr
            if process.returncode == 4:
                assert stdout.strip() == "storage.writer_busy"
        assert len(list(project.rglob("billing-confirmations/*.json"))) == 1
        report = refinement_cost_history(project, RUN)
        assert report["sharedHumanBillingSummary"]["confirmedNoChargeCount"] == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction boundary")
@pytest.mark.parametrize("linked_part", ["project", "material", "records"])
def test_junction_paths_refused_and_external_files_preserved(tmp_path, linked_part):
    project, _, body, path = fixture(tmp_path)
    if linked_part == "project":
        linked = tmp_path / "linked-project"
        target = project
    elif linked_part == "material":
        target = tmp_path / "outside"
        target.mkdir()
        path = save_material(target, body)
        linked = tmp_path / "linked-material"
    else:
        target = tmp_path / "outside"
        target.mkdir()
        (target / "protected.txt").write_text("preserve me")
        linked = project / "detail-refinement-budgets/budget-a/billing-confirmations"
    junction = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(linked), str(target)], capture_output=True
    )
    if junction.returncode:
        pytest.skip("Windows junction unavailable")
    before = snapshot(target)
    with pytest.raises(AppError):
        if linked_part == "project":
            import_material(linked, body, path)
        elif linked_part == "material":
            import_material(project, body, linked / path.name)
        else:
            import_material(project, body, path)
    assert snapshot(target) == before
