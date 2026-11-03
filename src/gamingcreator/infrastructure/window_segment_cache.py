"""Local vision-window segment cache with content-hash keys (P008); implements SegmentCache.

Keys bind project, recording bytes, analysis settings identity, and the ordered
frame content of one vision window. Hits never rely on mtime or TTL alone: the
on-disk envelope must match a freshly computed fingerprint and payload digest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.window_segments import (  # noqa: F401 - re-exported
    cache_key,
    digest,
    event_payload,
    fingerprint,
    remint_events,
    settings_digest,
    window_digest,
)
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing

SCHEMA = "window-segment-cache-v1"


def project_digest(repository: Path, project: Path) -> str:
    repository = repository.resolve()
    project = project.resolve()
    try:
        relative = project.relative_to(repository).as_posix()
    except ValueError:
        relative = project.as_posix()
    return digest(relative)


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
        payload = {"events": [event_payload(event) for event in events]}
        body = {
            "schemaVersion": SCHEMA,
            "key": key,
            "fingerprint": fingerprint(key),
            "payload": payload,
        }
        envelope = {**body, "sha256": digest(body)}
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
        stored = raw.get("sha256")
        body = {k: v for k, v in raw.items() if k != "sha256"}
        if (
            raw.get("schemaVersion") != SCHEMA
            or raw.get("key") != key
            or raw.get("fingerprint") != fingerprint(key)
            or not isinstance(stored, str)
            or stored != digest(body)
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
