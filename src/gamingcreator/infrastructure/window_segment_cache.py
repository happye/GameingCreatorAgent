"""Local vision-window segment cache with content-hash keys (P008).

Keys bind project, recording bytes, analysis settings identity, and the ordered
frame content of one vision window. Hits never rely on mtime or TTL alone: the
on-disk envelope must match a freshly computed fingerprint and payload digest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.analysis_reuse import analysis_identity
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing

SCHEMA = "window-segment-cache-v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def settings_digest(
    config: AnalysisConfig, pipeline_hash: str, required_stages: list[str] | tuple[str, ...]
) -> str:
    """Hash of output-shaping settings only (spending caps excluded by analysis_identity)."""
    return _digest(analysis_identity(config, pipeline_hash, required_stages))


def window_digest(window: tuple[EvidenceReference, ...]) -> str:
    """Ordered frame content identity for one vision window."""
    return _digest([{"evidenceId": item.evidence_id, "sha256": item.sha256} for item in window])


def project_digest(repository: Path, project: Path) -> str:
    repository = repository.resolve()
    project = project.resolve()
    try:
        relative = project.relative_to(repository).as_posix()
    except ValueError:
        relative = project.as_posix()
    return _digest(relative)


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
    return _digest(key)


def _event_payload(event: SemanticEvent) -> dict[str, Any]:
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


class WindowSegmentCache:
    """Filesystem cache under ``<project>/.cache/window-segments``."""

    def __init__(self, project: Path) -> None:
        self.project = project.resolve()
        root = self.project / ".cache" / "window-segments"
        if any(
            is_link(parent)
            for parent in (root, *root.parents)
            if parent.is_relative_to(self.project)
        ):
            raise ValueError("window_segment_cache.path")
        root.mkdir(parents=True, exist_ok=True)
        resolved = resolve_existing(root)
        if not resolved.is_relative_to(self.project):
            raise ValueError("window_segment_cache.path")
        self.root = resolved

    def path_for(self, key: dict[str, str]) -> Path:
        name = fingerprint(key) + ".json"
        path = self.root / name
        if path.resolve().parent != self.root:
            raise ValueError("window_segment_cache.path")
        return path

    def store(self, key: dict[str, str], events: tuple[SemanticEvent, ...]) -> Path:
        payload = {"events": [_event_payload(event) for event in events]}
        body = {
            "schemaVersion": SCHEMA,
            "key": key,
            "fingerprint": fingerprint(key),
            "payload": payload,
        }
        envelope = {**body, "sha256": _digest(body)}
        path = self.path_for(key)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        temporary.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2) + chr(10),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def load(self, key: dict[str, str]) -> list[dict[str, Any]] | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        digest = raw.get("sha256")
        body = {k: v for k, v in raw.items() if k != "sha256"}
        if (
            raw.get("schemaVersion") != SCHEMA
            or raw.get("key") != key
            or raw.get("fingerprint") != fingerprint(key)
            or not isinstance(digest, str)
            or digest != _digest(body)
        ):
            return None
        payload = raw.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            return None
        events = payload["events"]
        if not isinstance(events, list) or not all(isinstance(item, dict) for item in events):
            return None
        typed: list[dict[str, Any]] = events
        return typed
