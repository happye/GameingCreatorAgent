"""Persisted text-only reasoning preparation and single-use API confirmations."""

import asyncio
import json
import re
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.creation_proposals import (
    CreationProposal,
    EditingSnapshot,
    canonical,
    clip_rows,
    create_snapshot,
    revision_for_application,
    validate_proposal,
)
from gamingcreator.application.creation_reasoning import ReasoningRequest, reasoning_request
from gamingcreator.application.creation_replacements import candidate_manifest_sha
from gamingcreator.application.plan_proposals import (
    PlanSnapshot,
    compile_plan_proposal,
    validate_plan_proposal,
)
from gamingcreator.application.plan_reasoning import plan_reasoning_request
from gamingcreator.application.pricing import PriceSnapshot
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderStatus,
)
from gamingcreator.application.storage import InvocationStatus
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.creation_reasoning_provider import (
    MODEL,
    DeepSeekCreationReasoningProvider,
    trusted_price_snapshot,
)
from gamingcreator.infrastructure.http_transport import VisionTransport
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.revision_jobs import load_chain, prepare_revision

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs

PREPARED_SCHEMA = "creation-reasoning-prepared-v1"
RESULT_SCHEMA = "creation-reasoning-result-v1"


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _digest(value: Any) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def _write(directory: Path, name: str, document: dict[str, Any]) -> None:
    write_creation(directory, {name: document}, ())


def _read(directory: Path, name: str, schema: str) -> dict[str, Any]:
    receipt = json.loads(read_bounded(directory / "receipt.json"))
    raw = read_bounded(directory / name)
    if receipt.get("schemaVersion") != "creation-receipt-v1" or receipt.get("files") != {
        name: sha256(raw).hexdigest()
    }:
        raise ValueError("Reasoning record hash mismatch.")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("schemaVersion") != schema:
        raise ValueError("Unsupported reasoning record schema.")
    return document


class _Recorder:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None:
        _write(
            self.directory / "provider-start",
            "invocation.json",
            {
                "schemaVersion": "creation-reasoning-invocation-v1",
                "invocationId": invocation_id,
                "runId": run_id,
                "stageId": stage_id,
                "logicalRequestId": logical_request_id,
                "metadata": _jsonable(asdict(metadata)),
            },
        )

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None:
        _write(
            self.directory / "provider-finish",
            "invocation.json",
            {
                "schemaVersion": "creation-reasoning-invocation-v1",
                "invocationId": invocation_id,
                "status": status.value,
                "metadata": _jsonable(asdict(metadata)),
                "errorCode": error_code,
            },
        )


class CreationReasoningService:
    def __init__(
        self,
        jobs: "CreationJobs",
        *,
        price_snapshot: PriceSnapshot,
        transport: VisionTransport | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        self.jobs = jobs
        self.price = trusted_price_snapshot(price_snapshot)
        self.transport = transport
        self.timeout_seconds = CancellationContext("validation", timeout_seconds).timeout_seconds
        self.root = jobs.safe(jobs.root / "reasoning")
        self.root.mkdir(exist_ok=True)

    def _directory(self, prepared_hash: str) -> Path:
        if not isinstance(prepared_hash, str) or not re.fullmatch("[a-f0-9]{64}", prepared_hash):
            raise ValueError("Invalid prepared hash.")
        return self.jobs.safe(self.root / prepared_hash)

    def _snapshot(self, job_id: str, plan_id: str) -> tuple[EditingSnapshot, str]:
        chain = load_chain(self.jobs, job_id, plan_id)
        return (
            create_snapshot(job_id, chain.plan_id, chain.digest, chain.root_sha, chain.edl),
            chain.project_id,
        )

    def prepare(self, job_id: str, plan_id: str, instruction: str) -> dict[str, Any]:
        snapshot, project_id = self._snapshot(job_id, plan_id)
        return self._prepare(snapshot, project_id, job_id, plan_id, instruction)

    def prepare_plan(self, job_id: str) -> dict[str, Any]:
        from gamingcreator.ui.plan_reasoning_jobs import original_snapshot

        snapshot, original = original_snapshot(self.jobs, job_id)
        result = self._prepare(snapshot, original["projectId"], job_id, "", "", "plan")
        result["originalRequest"] = {
            key: original[key]
            for key in ("brief", "fps", "runIds", "eventIds", "clipRanges")
            if key in original
        }
        return result

    def _prepare(
        self,
        snapshot: EditingSnapshot | PlanSnapshot,
        project_id: str,
        job_id: str,
        plan_id: str,
        instruction: str,
        purpose: str = "edit",
    ) -> dict[str, Any]:
        request = (
            plan_reasoning_request(snapshot)
            if isinstance(snapshot, PlanSnapshot)
            else reasoning_request(snapshot, instruction)
        )
        quote = self.price.reservation_cny(self.price.context_limit_tokens, 2048)
        if quote <= 0 or MODEL.casefold() not in {s.casefold() for s in self.price.model_aliases}:
            raise ValueError("Unknown or invalid pilot cost upper bound.")
        record = {
            "schemaVersion": PREPARED_SCHEMA,
            "purpose": purpose,
            "intentId": uuid4().hex,
            "jobId": job_id,
            "planId": plan_id,
            "projectId": project_id,
            "snapshotFingerprint": snapshot.fingerprint,
            "instruction": instruction,
            "request": asdict(request),
            "requestHash": _digest(asdict(request)),
            "requestedModel": MODEL,
            "maxOutputTokens": 2048,
            "maxCostCny": str(quote),
            "priceVersion": self.price.version,
            "priceHash": _digest(_jsonable(asdict(self.price))),
        }
        prepared_hash = _digest(record)
        directory = self._directory(prepared_hash)
        _write(directory, "prepared.json", record)
        return {
            "purpose": purpose,
            "preparedHash": prepared_hash,
            "snapshotFingerprint": snapshot.fingerprint,
            "requestedModel": MODEL,
            "maxOutputTokens": 2048,
            "maxCostCny": str(quote),
            "priceVersion": self.price.version,
            "promptVersion": request.prompt_version,
            "schemaVersion": request.schema_version,
            "requestHash": record["requestHash"],
            "payloadPreview": {"system": request.system, "user": request.user},
            "payloadSummary": {
                "textOnly": True,
                "inputFrames": 0,
                "clipCount": len(snapshot.clips)
                if isinstance(snapshot, PlanSnapshot)
                else len(snapshot.payload["parent_edl"]["segments"]),
            },
        }

    def _prepared(self, prepared_hash: str) -> dict[str, Any]:
        record = _read(self._directory(prepared_hash), "prepared.json", PREPARED_SCHEMA)
        if _digest(record) != prepared_hash:
            raise ValueError("Prepared parameters changed.")
        return record

    def _current(self, record: dict[str, Any]) -> EditingSnapshot | PlanSnapshot:
        if record.get("purpose", "edit") == "plan":
            return self._current_plan(record)
        snapshot, project_id = self._snapshot(record["jobId"], record["planId"])
        if (
            project_id != record["projectId"]
            or snapshot.fingerprint != record["snapshotFingerprint"]
        ):
            raise ValueError("Saved parent changed; prepare again.")
        if (
            _digest(asdict(reasoning_request(snapshot, record["instruction"])))
            != record["requestHash"]
        ):
            raise ValueError("Prepared request changed.")
        return snapshot

    def _current_plan(self, record: dict[str, Any]) -> PlanSnapshot:
        from gamingcreator.ui.plan_reasoning_jobs import original_snapshot

        snapshot, original = original_snapshot(self.jobs, record["jobId"])
        if (
            original["projectId"] != record["projectId"]
            or snapshot.fingerprint != record["snapshotFingerprint"]
            or _digest(asdict(plan_reasoning_request(snapshot))) != record["requestHash"]
        ):
            raise ValueError("Saved planning inputs changed; prepare again.")
        return snapshot

    def adopt_plan(self, prepared_hash: str) -> dict[str, Any]:
        from gamingcreator.ui.plan_reasoning_jobs import adopt

        return adopt(self, prepared_hash)

    def read_result(self, prepared_hash: str) -> dict[str, Any]:
        self._prepared(prepared_hash)
        result = _read(
            self.jobs.safe(self._directory(prepared_hash) / "attempt/result"),
            "result.json",
            RESULT_SCHEMA,
        )
        if result.get("preparedHash") != prepared_hash:
            raise ValueError("Result belongs to another preparation.")
        return result

    async def execute(
        self,
        prepared_hash: str,
        expected_snapshot_fingerprint: str,
        confirmed_max_cny: Decimal,
    ) -> dict[str, Any]:
        directory = self._directory(prepared_hash)
        record = self._prepared(prepared_hash)
        if (
            expected_snapshot_fingerprint != record["snapshotFingerprint"]
            or not isinstance(confirmed_max_cny, Decimal)
            or not confirmed_max_cny.is_finite()
            or confirmed_max_cny < Decimal(record["maxCostCny"])
        ):
            raise ValueError(
                "Explicit matching snapshot and sufficient amount confirmation required."
            )
        lock = ProjectWriterLock(directory)
        lock.acquire()
        try:
            attempt = self.jobs.safe(directory / "attempt")
            if attempt.exists():
                if self.jobs.safe(attempt / "result").exists():
                    result = self.read_result(prepared_hash)
                    if result["status"] == "completed":
                        return result
                raise ValueError("Attempt already consumed; prepare and confirm a new intent.")
            snapshot = await asyncio.to_thread(self._current, record)
            if record["priceHash"] != _digest(_jsonable(asdict(self.price))):
                raise ValueError("Price snapshot changed; prepare again.")
            confirmation = {
                "schemaVersion": "creation-reasoning-confirmation-v1",
                "preparedHash": prepared_hash,
                "expectedSnapshotFingerprint": expected_snapshot_fingerprint,
                "confirmedMaxCny": str(confirmed_max_cny),
                "confirmationSource": "execute-api-parameters",
            }
            _write(attempt / "planned", "confirmation.json", confirmation)
            return await self._run(record, prepared_hash, snapshot, attempt, confirmed_max_cny)
        finally:
            lock.close()

    async def _run(
        self,
        record: dict[str, Any],
        prepared_hash: str,
        snapshot: EditingSnapshot | PlanSnapshot,
        attempt: Path,
        confirmed_max_cny: Decimal,
    ) -> dict[str, Any]:
        request = ReasoningRequest(**record["request"])

        async def gate(candidate: ReasoningRequest) -> bool:
            confirmed = _read(
                attempt / "planned", "confirmation.json", "creation-reasoning-confirmation-v1"
            )
            return (
                confirmed["preparedHash"] == prepared_hash
                and confirmed["expectedSnapshotFingerprint"] == snapshot.fingerprint
                and Decimal(confirmed["confirmedMaxCny"]) >= Decimal(record["maxCostCny"])
                and _digest(asdict(candidate)) == record["requestHash"]
            )

        ledger = BudgetLedger(confirmed_max_cny, 1, 1)
        provider = DeepSeekCreationReasoningProvider(
            approval=gate,
            ledger=ledger,
            recorder=_Recorder(attempt),
            reservation_cny=Decimal(record["maxCostCny"]),
            price_snapshot=self.price,
            transport=self.transport,
            max_output_tokens=2048,
        )
        result: dict[str, Any] = {
            "schemaVersion": RESULT_SCHEMA,
            "purpose": record.get("purpose", "edit"),
            "preparedHash": prepared_hash,
            "status": "failed",
            "proposal": None,
            "metadata": None,
        }
        try:
            response = await provider.complete(
                request, CancellationContext(prepared_hash, self.timeout_seconds)
            )
            result.update(
                status=response.status.value,
                metadata=_jsonable(asdict(response.metadata)),
                errorCode=None if response.error is None else response.error.code,
            )
            if response.status == ProviderStatus.COMPLETED:
                result.update(_validated_output(snapshot, response.output))
        except asyncio.CancelledError:
            result.update(status="cancelled", errorCode="reasoning.cancelled")
        except Exception:
            result.update(status="failed", errorCode="reasoning.failed")
        result["billing"] = {
            "reservedCny": str(ledger.reserved_cny),
            "knownCostCny": None if ledger.unresolved_attempts else str(ledger.known_cost_cny),
            "unresolvedAttempts": ledger.unresolved_attempts,
        }
        _write(self.jobs.safe(attempt / "result"), "result.json", result)
        return result

    def revision_for_application(self, prepared_hash: str) -> dict[str, Any]:
        record = self._prepared(prepared_hash)
        if record.get("purpose", "edit") != "edit":
            raise ValueError("Plan results cannot edit a timeline.")
        result = self.read_result(prepared_hash)
        if result["status"] != "completed" or result["proposal"] is None:
            raise ValueError("No successful edit proposal is available.")
        saved = dict(result["proposal"])
        saved.pop("response")
        saved["changes"] = tuple(saved["changes"])
        proposal = CreationProposal(**saved)
        current = self._current(record)
        assert isinstance(current, EditingSnapshot)
        chain = load_chain(self.jobs, record["jobId"], record["planId"])
        verified = create_snapshot(
            record["jobId"], chain.plan_id, chain.digest, chain.root_sha, chain.edl
        )
        if verified.fingerprint != current.fingerprint:
            raise ValueError("Saved parent changed before application.")
        revised = revision_for_application(proposal, current, candidate_manifest=chain.manifest)
        if chain.edl.get("schemaVersion") == "edit-decision-revision-v4":
            if chain.manifest is None:
                raise ValueError("A v4 parent requires its verified candidate manifest.")
            revised, _ = prepare_revision(
                self.jobs,
                {
                    "clips": proposal.response["clips"],
                    "replacements": [],
                    "candidateManifestSha256": candidate_manifest_sha(chain.manifest),
                },
                chain,
            )
        return revised

    def proposal_for_editor(
        self,
        prepared_hash: str,
        job_id: str,
        plan_id: str,
        expected_parent_receipt_sha256: str,
    ) -> dict[str, Any]:
        record = self._prepared(prepared_hash)
        if record["jobId"] != job_id or record["planId"] != plan_id:
            raise ValueError("Prepared job or plan does not match the editor.")
        if record.get("purpose", "edit") != "edit":
            raise ValueError("Plan results cannot edit a timeline.")
        current = self._current(record)
        assert isinstance(current, EditingSnapshot)
        if current.payload["parentReceiptSha256"] != expected_parent_receipt_sha256:
            raise ValueError("Saved parent changed; prepare again.")
        revised = self.revision_for_application(prepared_hash)
        snapshot = create_snapshot(
            job_id,
            plan_id,
            expected_parent_receipt_sha256,
            current.payload["rootReceiptSha256"],
            revised,
        )
        return {
            "clips": clip_rows(snapshot),
            "preparedHash": prepared_hash,
            "jobId": job_id,
            "planId": plan_id,
            "expectedParentReceiptSha256": expected_parent_receipt_sha256,
        }


def _validated_output(snapshot: EditingSnapshot | PlanSnapshot, output: Any) -> dict[str, Any]:
    if isinstance(snapshot, PlanSnapshot):
        proposal = validate_plan_proposal(snapshot, output)
        preview = []
        if proposal.response["kind"] == "plan_proposal":
            report = compile_plan_proposal(snapshot, proposal)
            preview = [
                {
                    **plan,
                    "segments": [
                        {key: value for key, value in segment.items() if key != "sourcePath"}
                        for segment in plan["segments"]
                    ],
                }
                for plan in report["plans"]
            ]
        return {
            "purpose": "plan",
            "proposal": {**asdict(proposal), "response": proposal.response},
            "planPreview": {"fps": snapshot.fps, "plans": preview},
        }
    edit = validate_proposal(snapshot, output)
    return {"purpose": "edit", "proposal": _jsonable({**asdict(edit), "response": edit.response})}
