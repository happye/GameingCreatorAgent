"""Project an existing search into ten visible slots, without judging usefulness."""

from gamingcreator.application.inspection import InspectionView
from gamingcreator.application.observation_text import display_facts

RETRIEVAL_DIAGNOSTICS_VERSION = "retrieval-diagnostics-v1"


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
