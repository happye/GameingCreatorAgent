"""Freeze two v4 requests for review only; no provider calls, reservations or settlement."""

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

from gamingcreator.application.detail_refinement import canonical_request_json, prepare_refinement
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.storage import RunStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    PROMPT,
    DeepSeekDetailTemporalProvider,
    provider_temporal_identity,
    temporal_refinement_settings,
)
from gamingcreator.infrastructure.deepseek_vision import _jpeg_width, _json, _SchemaError
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history
from gamingcreator.infrastructure.http_transport import HttpResponse
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

DESTINATION = "https://api.deepseek.com/chat/completions"
PRIOR_UNKNOWN_CNY = Decimal("4.065536")
_MAX_JSON_BYTES = 1_048_576


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    run_id: str
    event_id: str
    old_request_hash: str
    review_purpose: str


_MEDIA = "172e1139b477352db5e5fe2f3be3afb5171935c2edd8a2d0278a434212fd00fd"
CASE_SPECS = (
    CaseSpec(
        "actor-separation",
        "96b5f01530ce43e2944828fb0520b9b4",
        f"96b5f01530ce43e2944828fb0520b9b4:{_MEDIA}:event:861706cd8d81c59fe3e89543",
        "dc31fcc36cfc4c0f1fc064ec30db399636723552806349e05e38b0add024fd13",
        "35–36秒三个角色描述的保留正例；用户只确认三个描述，不代表所有属性和检索质量通过。",
    ),
    CaseSpec(
        "held-item-shape",
        "f601fb9b3e734d5ea188fc15c790acbb",
        f"f601fb9b3e734d5ea188fc15c790acbb:{_MEDIA}:event:0b8be73b204cceb6f0e37c7d",
        "2d0b267fac0b8a390486678c57aea98b409b1018f7b8e4a3199fc74d0c48efce",
        "28–29秒物品靠近镜头并遮挡人物的失败反例；检验物品/角色误认和假切镜。",
    ),
)


class NoSendTransport:
    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        raise AssertionError("Proposal preparation must never send HTTP.")


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1_048_576):
            digest.update(block)
    return digest.hexdigest()


def protected_snapshot(project: Path) -> dict[str, str]:
    """Hash the database plus every existing refinement/budget file without taking locks."""
    if not (project / "timeline.sqlite3").is_file():
        raise FileNotFoundError("The source project database is missing.")
    paths = {project / "timeline.sqlite3"}
    for suffix in ("-wal", "-shm"):
        path = project / ("timeline.sqlite3" + suffix)
        if path.exists():
            paths.add(path)
    budget = project / "detail-refinement-budgets"
    if budget.exists():
        paths.update(path for path in budget.rglob("*") if path.is_file())
    runs = project / "runs"
    if runs.exists():
        for run in runs.iterdir():
            details = run / "detail-refinements"
            if details.exists():
                paths.update(path for path in details.rglob("*") if path.is_file())
    return {str(path.relative_to(project)): _file_sha(path) for path in sorted(paths)}


def _dimensions(data: bytes) -> tuple[int, int]:
    width = _jpeg_width(data)  # Validate the complete bounded JPEG structure first.
    position = 2
    while position + 4 <= len(data):
        while data[position] == 255:
            position += 1
        marker = data[position]
        position += 1
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        length = int.from_bytes(data[position : position + 2], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return width, int.from_bytes(data[position + 3 : position + 5], "big")
        position += length
    raise ValueError("No registered JPEG dimensions found.")


def _baseline(path: Path) -> tuple[dict[str, object], str]:
    data = path.read_bytes()
    if len(data) > _MAX_JSON_BYTES:
        raise ValueError("The legacy proposal is too large.")
    value = _json(data)
    rows = value.get("cases")
    if (
        value.get("schemaVersion") != "actor-detail-pilot-proposal-v1"
        or type(rows) is not list
        or len(rows) != len(CASE_SPECS)
        or value.get("priorUnknownReservationCny") != format(PRIOR_UNKNOWN_CNY, "f")
    ):
        raise ValueError("Unsupported frozen legacy proposal.")
    for row, spec in zip(rows, CASE_SPECS, strict=True):
        if type(row) is not dict or (
            row.get("caseId"),
            row.get("runId"),
            row.get("eventId"),
            row.get("requestHash"),
        ) != (spec.case_id, spec.run_id, spec.event_id, spec.old_request_hash):
            raise ValueError("Legacy proposal candidate identity changed.")
    return value, _sha(data)


async def prepare_proposal(project: Path, baseline_path: Path) -> dict[str, object]:
    project = project.resolve()
    baseline_path = baseline_path.resolve()
    baseline, baseline_sha = _baseline(baseline_path)
    before = protected_snapshot(project)
    store = await SqliteTimelineStore.open(project, read_only=True)
    cases = []
    price = DEEPSEEK_FLASH_20261004
    settings = temporal_refinement_settings()
    identity = provider_temporal_identity()
    reserve = price.reservation_cny(price.context_limit_tokens, settings.max_output_tokens)
    shared = None
    try:
        for spec, old_row in zip(
            CASE_SPECS, cast(list[dict[str, object]], baseline["cases"]), strict=True
        ):
            timeline = await store.load_completed_timeline(spec.run_id)
            if timeline.run.status != RunStatus.COMPLETED:
                raise ValueError("Proposal requires a Completed source run.")
            old = prepare_refinement(
                timeline, spec.event_id, identity=provider_refinement_identity()
            )
            if (
                old.request is None
                or old.request_hash != spec.old_request_hash
                or json.loads(canonical_request_json(old.request))
                != old_row.get("canonicalRequest")
            ):
                raise ValueError(
                    "Legacy canonical request no longer matches its registered candidate."
                )
            prepared = prepare_refinement(
                timeline, spec.event_id, settings=settings, identity=identity
            )
            if prepared.request is None:
                raise ValueError("Candidate has no usable registered refinement evidence.")
            request = prepared.request
            if request.evidence != old.request.evidence or len(request.evidence) != 3:
                raise ValueError(
                    "The comparison must use only the original three candidate frames."
                )
            paths = {
                item.evidence_id: item.artifact_path
                for item in timeline.evidence
                if item.kind == "image"
            }
            payload = DeepSeekDetailTemporalProvider(NoSendTransport(), paths)._payload(request)
            frames = []
            for frame in request.evidence:
                with paths[frame.evidence_id].open("rb") as stream:
                    data = stream.read(settings.max_image_bytes + 1)
                width, height = _dimensions(data)
                if (
                    _sha(data) != frame.image_sha256
                    or len(data) > settings.max_image_bytes
                    or width > settings.max_image_width
                ):
                    raise ValueError("Registered input image changed or exceeds the frozen limits.")
                frames.append(
                    {
                        "evidenceId": frame.evidence_id,
                        "sourceUs": frame.source_time.time_us,
                        "durationUs": frame.source_time.duration_us,
                        "sha256": frame.image_sha256,
                        "width": width,
                        "height": height,
                        "bytes": len(data),
                        "path": str(paths[frame.evidence_id]),
                    }
                )
            history = refinement_cost_history(project, spec.run_id)
            current_shared = cast(dict[str, object], history["sharedCommitment"])
            if shared is not None and shared != current_shared:
                raise ValueError("Shared commitment changed during proposal preparation.")
            shared = current_shared
            attempts = cast(list[dict[str, object]], history["attempts"])
            old_attempts = [
                item for item in attempts if item.get("requestHash") == spec.old_request_hash
            ]
            if len(old_attempts) != 1 or old_attempts[0].get("status") != "completed":
                raise ValueError(
                    "The legacy authorized attempt must remain completed and uniquely recorded."
                )
            messages = cast(list[dict[str, object]], payload["messages"])
            blocks = cast(list[dict[str, object]], messages[1]["content"])
            cases.append(
                {
                    "caseId": spec.case_id,
                    "reviewPurpose": spec.review_purpose,
                    "runId": spec.run_id,
                    "eventId": spec.event_id,
                    "candidateId": request.candidate_id,
                    "eventFingerprint": request.event_fingerprint,
                    "legacyRequestHash": spec.old_request_hash,
                    "requestHash": prepared.request_hash,
                    "canonicalRequest": json.loads(canonical_request_json(request)),
                    "basePromptVersion": request.base_prompt_version,
                    "basePromptHash": request.base_prompt_hash,
                    "inputFrames": frames,
                    "reservationCny": format(reserve, "f"),
                    "maxHttpAttempts": 1,
                    "automaticRetry": False,
                    "wirePayloadSha256": _sha(_canonical(payload).encode("utf-8")),
                    "requestParameters": {
                        key: value for key, value in payload.items() if key != "messages"
                    },
                    "sequenceTextBlocks": [
                        json.loads(cast(str, block["text"]))
                        for block in blocks
                        if block["type"] == "text"
                    ],
                    "humanLabels": None,
                    "qualityGate": None,
                }
            )
    finally:
        await store.close()
    after = protected_snapshot(project)
    if before != after or _file_sha(baseline_path) != baseline_sha:
        raise ValueError(
            "Source database, sidecar, budget or legacy proposal changed during preparation."
        )
    if shared is None:
        raise ValueError("No project commitment was inspected.")
    new_reserve = reserve * len(cases)
    current_commitment = Decimal(cast(str, shared["commitmentCny"]))
    result: dict[str, object] = {
        "schemaVersion": "actor-detail-temporal-pilot-proposal-v1",
        "project": str(project),
        "baselineProposal": {"path": str(baseline_path), "sha256": baseline_sha},
        "budgetId": "actor-detail-temporal-pilot-20261006",
        "destination": DESTINATION,
        "provider": identity.provider,
        "requestedModel": identity.requested_model,
        "promptVersion": identity.prompt_version,
        "promptHash": identity.prompt_hash,
        "schema": identity.schema_version,
        "systemPrompt": PROMPT,
        "maximumNewHttpAttempts": 2,
        "automaticRetry": False,
        "paidRequestsSent": 0,
        "authorization": {
            "legacyAuthorizedAttempts": 2,
            "legacyAttemptsConsumed": 2,
            "newBudgetAndRequestCountPermissionRequired": True,
            "newDestinationPermissionRequired": True,
            "executionAuthorized": False,
        },
        "costPlan": {
            "currency": "CNY",
            "priceVersion": price.version,
            "priceSnapshotSource": price.source_url,
            "priceSnapshotCapturedDate": price.captured_date,
            "period": "peak",
            "inputTokenCeilingPerAttempt": price.context_limit_tokens,
            "maxOutputTokensPerAttempt": settings.max_output_tokens,
            "uncachedInputCnyPerMillion": format(price.peak_uncached_input_per_million, "f"),
            "outputCnyPerMillion": format(price.peak_output_per_million, "f"),
            "reservationCnyPerAttempt": format(reserve, "f"),
            "newMaximumReservationCny": format(new_reserve, "f"),
            "sourceProjectExistingRefinementCommitment": shared,
            "minimumSourceProjectSharedRefinementCeilingCny": format(
                current_commitment + new_reserve, "f"
            ),
            "priorTaskUnknownReservationCny": format(PRIOR_UNKNOWN_CNY, "f"),
            "priorTaskUnknownReservationPreserved": True,
            "priorTaskUnknownScope": "prior base-vision task; separate from this project's refinement ledger",
            "reservationIsInvoice": False,
        },
        "realV4RecognitionVerified": False,
        "humanLabels": None,
        "qualityGate": None,
        "sourceDatabaseSidecarsAndLedgersUnchanged": True,
        "protectedFilesBefore": before,
        "protectedFilesAfter": after,
        "cases": cases,
    }
    if len(_canonical(result).encode("utf-8")) > _MAX_JSON_BYTES:
        raise ValueError("Frozen proposal exceeds its byte limit.")
    return result


def freeze_proposal(value: dict[str, object], output: Path) -> str:
    if not output.is_absolute():
        raise ValueError("Use an explicit absolute output path.")
    project = Path(cast(str, value["project"]))
    if output.resolve().is_relative_to(project.resolve()):
        raise ValueError("Write proposals outside the source project to preserve its files.")
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > _MAX_JSON_BYTES:
        raise ValueError("Frozen proposal exceeds its byte limit.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    return _sha(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--baseline-proposal", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dry_run and args.output is None:
        parser.error("--output is required unless --dry-run is selected")
    if args.dry_run and args.output is not None:
        parser.error("--dry-run does not accept an output path")
    try:
        proposal = asyncio.run(prepare_proposal(args.project, args.baseline_proposal))
        summary = {
            "paidRequestsSent": 0,
            "realV4RecognitionVerified": False,
            "newRequestHashes": [
                case["requestHash"] for case in cast(list[dict[str, object]], proposal["cases"])
            ],
            "costPlan": proposal["costPlan"],
            "sourceDatabaseSidecarsAndLedgersUnchanged": True,
            "dryRun": args.dry_run,
        }
        if args.output is not None:
            summary.update(output=str(args.output), sha256=freeze_proposal(proposal, args.output))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, AppError, _SchemaError) as error:
        print(f"Preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
