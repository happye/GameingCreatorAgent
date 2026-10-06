"""Project an existing search into ten visible slots, without judging usefulness."""

from gamingcreator.application.inspection import InspectionView, RankedRow
from gamingcreator.application.observation_text import display_facts
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceInstant, SourceRange

RETRIEVAL_DIAGNOSTICS_VERSION = "retrieval-diagnostics-v2"


def _evidence_summary(
    row: RankedRow, references: tuple[EvidenceReference, ...], media_id: str, duration_us: int
) -> dict[str, object]:
    """Describe registered inputs, never whether an action happened."""
    summary: dict[str, object] = {
        "status": "unavailable",
        "registeredImageCount": None,
        "registeredAudioCount": None,
        "distinctImageSourceTimeCount": None,
        "distinctImageContentCount": None,
        "firstImageSourceUs": None,
        "lastImageSourceUs": None,
        "imageSpanUs": None,
        "imageFrames": [],
        "actionUnderstandingVerified": None,
    }
    by_id = {item.evidence_id: item for item in references}
    ids = tuple(dict.fromkeys(row.evidence_ids))
    if not ids or len(by_id) != len(references) or any(item not in by_id for item in ids):
        return summary
    selected = [by_id[item] for item in ids]
    images, audio = [], []
    for item in selected:
        clock = item.source_time
        if item.media_id != media_id or clock.duration_us != duration_us:
            return summary
        if item.kind == "image" and isinstance(clock, SourceInstant):
            if not row.start_us <= clock.time_us < row.end_us:
                return summary
            images.append((clock.time_us, item.evidence_id, item.sha256))
        elif item.kind == "audio" and isinstance(clock, SourceRange):
            if max(clock.start_us, row.start_us) >= min(clock.end_us, row.end_us):
                return summary
            audio.append(item)
        else:
            return summary
    times = sorted({time for time, _, _ in images})
    digests = {digest for _, _, digest in images}
    status = (
        "registered_audio_only"
        if not images
        else "registered_single_frame"
        if len(images) == 1
        else "registered_same_instant"
        if len(times) == 1
        else "registered_repeated_content"
        if len(digests) == 1
        else "registered_multi_frame"
    )
    summary.update(
        status=status,
        registeredImageCount=len(images),
        registeredAudioCount=len(audio),
        distinctImageSourceTimeCount=len(times),
        distinctImageContentCount=len(digests),
        firstImageSourceUs=times[0] if times else None,
        lastImageSourceUs=times[-1] if times else None,
        imageSpanUs=times[-1] - times[0] if times else None,
        imageFrames=[
            {"evidenceId": identifier, "sourceUs": time, "sha256": digest}
            for time, identifier, digest in sorted(images)
        ],
    )
    return summary


def retrieval_diagnostics(
    view: InspectionView,
    *,
    project: str,
    query: str,
    mode: str,
    requested_top_k: int,
    media_id: str,
    media_sha256: str,
    duration_us: int,
    config_hash: str,
    retrieval_version: str,
    evidence: tuple[EvidenceReference, ...],
) -> dict[str, object] | None:
    """Keep response order, including missing and known duplicate positions.

    Distinct event IDs do not establish distinct real actions. Only the benchmark
    with independent human references can decide usefulness or acceptance.
    """
    if view.run_status != "completed" or not query.strip():
        return None
    slots: list[dict[str, object]] = []
    seen: dict[tuple[str, str], int] = {}
    duplicate_count = 0
    for position in range(1, 11):
        slot: dict[str, object] = {
            "position": position,
            "status": "missing",
            "candidate": None,
            "duplicateOfPosition": None,
            "humanGrade": None,
            "independenceStatus": "unreviewed",
        }
        if position <= len(view.candidates):
            row = view.candidates[position - 1]
            key = (
                ("event", row.event_id)
                if row.event_id is not None
                else ("candidate", row.candidate_id)
            )
            duplicate_of = seen.get(key)
            seen.setdefault(key, position)
            duplicate_count += duplicate_of is not None
            slot.update(
                status="known_duplicate" if duplicate_of is not None else "candidate",
                duplicateOfPosition=duplicate_of,
                candidate={
                    "rank": row.rank,
                    "candidateId": row.candidate_id,
                    "eventId": row.event_id,
                    "startUs": row.start_us,
                    "endUs": row.end_us,
                    "observableFacts": list(row.facts),
                    "displayFacts": list(display_facts(row.facts)),
                    "evidenceIds": list(row.evidence_ids),
                    "score": row.score,
                    "scoreKind": row.score_kind,
                    "evidenceSummary": _evidence_summary(row, evidence, media_id, duration_us),
                },
            )
        slots.append(slot)
    return {
        "schemaVersion": RETRIEVAL_DIAGNOSTICS_VERSION,
        "project": project,
        "runId": view.run_id,
        "mediaId": media_id,
        "mediaSha256": media_sha256,
        "durationUs": duration_us,
        "configHash": config_hash,
        "retrievalVersion": retrieval_version,
        "query": query,
        "mode": mode,
        "requestedTopK": requested_top_k,
        "limitedByRequestedTopK": requested_top_k < 10,
        "returnedCount": len(view.candidates),
        "missingCount": max(0, 10 - len(view.candidates)),
        "knownDuplicateCount": duplicate_count,
        "abstentionReason": view.abstention_reason,
        "slots": slots,
        "humanLabels": None,
        "usefulRate": None,
        "qualityGate": None,
    }
