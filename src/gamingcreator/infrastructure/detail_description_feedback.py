"""Read project-local description feedback without altering model results or labels."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from gamingcreator.application.detail_description_feedback import (
    DescriptionFeedback,
    decode_description_feedback,
    project_description_feedback,
)
from gamingcreator.application.detail_description_report import validate_description_report
from gamingcreator.application.detail_refinement_budget import payload_hash
from gamingcreator.domain.actor_details import CandidateDetail
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure import detail_refinement_sidecar as sidecar

DESCRIPTION_FEEDBACK_INSPECTION_VERSION = "actor-description-feedback-inspection-v1"


@dataclass(frozen=True, slots=True)
class DescriptionFeedbackSnapshot:
    feedback: DescriptionFeedback
    pilot_report_sha256: str


def read_description_feedback(project: Path) -> DescriptionFeedbackSnapshot | None:
    """Missing namespace means no record; incomplete or damaged records fail explicitly."""
    try:
        root = project.resolve()
        directory = sidecar._confined(root, root / "detail-description-feedback")
        if not directory.exists():
            return None
        if not directory.is_dir():
            raise ValueError("Feedback namespace is not a directory.")
        feedback = decode_description_feedback(
            sidecar._read_bytes(directory / "feedback.json", root).decode("utf-8")
        )
        report = sidecar._read_bytes(
            directory / "reports" / (feedback.pilot_report_sha256 + ".json"), root
        )
        digest = hashlib.sha256(report).hexdigest()
        if digest != feedback.pilot_report_sha256:
            raise ValueError("Feedback report identity changed.")
        validate_description_report(feedback, report.decode("utf-8"))
        return DescriptionFeedbackSnapshot(feedback, digest)
    except (OSError, ValueError, RecursionError, AppError):
        raise AppError(
            "detail_feedback.damaged",
            "已保存的人工描述反馈损坏或来源不一致，请检查反馈记录。",
            ExitCode.STORAGE,
        ) from None


def description_feedback_payload(
    snapshot: DescriptionFeedbackSnapshot | None, detail: CandidateDetail, request_hash: str
) -> dict[str, object] | None:
    if snapshot is None:
        return None
    try:
        reviews = project_description_feedback(
            snapshot.feedback,
            pilot_report_sha256=snapshot.pilot_report_sha256,
            run_id=detail.run_id,
            event_id=detail.event_id,
            request_hash=request_hash,
            detail=detail,
        )
    except ValueError:
        raise AppError(
            "detail_feedback.damaged",
            "人工描述反馈与已保存主体不一致，请检查反馈记录。",
            ExitCode.STORAGE,
            detail.run_id,
        ) from None
    return {
        "schemaVersion": DESCRIPTION_FEEDBACK_INSPECTION_VERSION,
        "scope": "actor-description",
        "status": "reviewed" if reviews else "unreviewed",
        "runId": detail.run_id,
        "eventId": detail.event_id,
        "requestHash": request_hash,
        "refinementPayloadHash": payload_hash(detail),
        "pilotReportSha256": snapshot.pilot_report_sha256,
        "recordedOn": snapshot.feedback.recorded_on,
        "phase0QualityGate": None,
        "reviews": [
            {
                "caseId": review.case_id,
                "shotId": review.shot_id,
                "actorId": review.actor_id,
                "verdict": review.verdict,
                "scope": review.scope,
                "source": review.source,
                "statement": review.statement,
                "recordedOn": review.recorded_on,
            }
            for review in reviews
        ],
    }
