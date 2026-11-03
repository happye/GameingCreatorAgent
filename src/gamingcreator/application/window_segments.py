"""Pure identity rules for reusing vision-window results (P008 / T17).

Keys bind project, recording bytes, analysis settings identity and the ordered frame
content of one vision window. Storage lives behind the ``SegmentCache`` port; the file
implementation is ``infrastructure.window_segment_cache.WindowSegmentCache`` (TD023).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from gamingcreator.application.analysis_reuse import analysis_identity
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceRange


class SegmentCache(Protocol):
    def load(self, key: dict[str, str]) -> list[dict[str, Any]] | None: ...

    def store(self, key: dict[str, str], events: tuple[SemanticEvent, ...]) -> object: ...


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def settings_digest(
    config: AnalysisConfig, pipeline_hash: str, required_stages: list[str] | tuple[str, ...]
) -> str:
    """Hash of output-shaping settings only (spending caps excluded by analysis_identity)."""
    return digest(analysis_identity(config, pipeline_hash, required_stages))


def window_digest(window: tuple[EvidenceReference, ...]) -> str:
    """Ordered frame content identity for one vision window."""
    return digest([{"evidenceId": item.evidence_id, "sha256": item.sha256} for item in window])


def cache_key(
    *,
    project: str,
    recording: str,
    settings: str,
    window: str,
) -> dict[str, str]:
    return {
        "project": project,
        "recording": recording,
        "settings": settings,
        "window": window,
    }


def fingerprint(key: dict[str, str]) -> str:
    return digest(key)


def event_payload(event: SemanticEvent) -> dict[str, Any]:
    return {
        "sourceRange": {
            "startUs": event.source_range.start_us,
            "endUs": event.source_range.end_us,
            "durationUs": event.source_range.duration_us,
        },
        "observableFacts": list(event.observable_facts),
        "mechanicTags": list(event.mechanic_tags),
        "evidenceIds": list(event.evidence_ids),
        "modality": event.modality,
        "uncertainty": event.uncertainty,
    }


def remint_events(
    rows: list[dict[str, Any]], *, run_id: str, media_id: str
) -> tuple[SemanticEvent, ...]:
    """Rebuild run-scoped event ids the same way the vision provider does."""
    events: list[SemanticEvent] = []
    seen: set[str] = set()
    for row in rows:
        source = row["sourceRange"]
        facts = tuple(row["observableFacts"])
        tags = tuple(row["mechanicTags"])
        references = tuple(row["evidenceIds"])
        uncertainty = row.get("uncertainty")
        identity = json.dumps(
            [
                run_id,
                media_id,
                source["startUs"],
                source["endUs"],
                list(facts),
                list(tags),
                list(references),
                uncertainty,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        event_id = (
            f"{run_id}:{media_id}:event:"
            + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        )
        if event_id in seen:
            raise ValueError("window_segment_cache.duplicate_event")
        seen.add(event_id)
        events.append(
            SemanticEvent(
                event_id,
                media_id,
                run_id,
                SourceRange(source["startUs"], source["endUs"], source["durationUs"]),
                facts,
                tags,
                references,
                row["modality"],
                uncertainty,
            )
        )
    return tuple(events)
