"""Read-only alignment of stored events and shipped search candidates.

Timeline rows follow source time. Candidate rows keep the order returned by
search: score descending, then start time, then identifier. This module does
not rank, read files, or talk to a provider.
"""

from dataclasses import dataclass

from gamingcreator.application.retrieval import CandidateClip
from gamingcreator.application.storage import StoredTimeline


@dataclass(frozen=True, slots=True)
class TimelineRow:
    event_id: str
    start_us: int
    end_us: int
    facts: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankedRow:
    rank: int
    event_id: str | None
    candidate_id: str
    start_us: int
    end_us: int
    facts: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    score: float
    score_kind: str


@dataclass(frozen=True, slots=True)
class InspectionView:
    artifact: str
    run_id: str
    run_status: str
    timeline: tuple[TimelineRow, ...]
    candidates: tuple[RankedRow, ...]
    abstention_reason: str | None


def inspection_view(
    timeline: StoredTimeline,
    candidates: tuple[CandidateClip, ...],
    artifact: str,
    *,
    abstention_reason: str | None = None,
) -> InspectionView:
    rows = tuple(
        sorted(
            (
                TimelineRow(
                    event.event_id,
                    event.source_range.start_us,
                    event.source_range.end_us,
                    event.observable_facts,
                    tuple(event.evidence_ids),
                )
                for event in timeline.events
            ),
            key=lambda row: (row.start_us, row.end_us, row.event_id),
        )
    )
    ranked = tuple(
        RankedRow(
            index,
            item.event_id,
            item.candidate_id,
            item.source_range.start_us,
            item.source_range.end_us,
            item.observable_facts,
            item.evidence_ids,
            item.score,
            item.score_kind,
        )
        for index, item in enumerate(candidates, 1)
    )
    return InspectionView(
        artifact,
        timeline.run.run_id,
        str(timeline.run.status),
        rows,
        ranked,
        abstention_reason,
    )
