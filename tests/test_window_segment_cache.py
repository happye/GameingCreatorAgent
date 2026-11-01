"""Window-level segment cache: content-hash keys, no TTL hits (P008 / T17)."""

from __future__ import annotations

import json
from pathlib import Path

from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.window_segment_cache import (
    WindowSegmentCache,
    cache_key,
    fingerprint,
    remint_events,
    window_digest,
)


def test_store_load_hit_and_content_invalidation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    cache = WindowSegmentCache(project)
    key = cache_key(
        project="p" * 64,
        recording="r" * 64,
        settings="s" * 64,
        window="w" * 64,
    )
    # Remint before store so event ids match formula; store strips run-scoped ids via payload
    reminted = remint_events(
        [
            {
                "sourceRange": {"startUs": 0, "endUs": 1_000_000, "durationUs": 10_000_000},
                "observableFacts": ["事实"],
                "mechanicTags": ["tag"],
                "evidenceIds": ["ev1"],
                "modality": "visual",
                "uncertainty": None,
            }
        ],
        run_id="run-a",
        media_id="media",
    )
    path = cache.store(key, reminted)
    assert path.is_file() and fingerprint(key) in path.name

    loaded = cache.load(key)
    assert loaded is not None
    again = remint_events(loaded, run_id="run-b", media_id="media")
    assert again[0].run_id == "run-b"
    assert again[0].observable_facts == ("事实",)
    assert again[0].event_id != reminted[0].event_id

    # Corrupt payload bytes without updating envelope digest -> miss
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["events"][0]["observableFacts"] = ["篡改"]
    path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    assert cache.load(key) is None

    # Fresh store then change key window digest -> different file / miss on old key
    cache.store(key, reminted)
    other = cache_key(
        project=key["project"],
        recording=key["recording"],
        settings=key["settings"],
        window="x" * 64,
    )
    assert cache.load(other) is None


def test_window_digest_changes_with_frame_bytes() -> None:
    instant = SourceInstant(0, 10_000_000)
    first = EvidenceReference("e1", "m", "image", instant, Path("a.jpg"), "a" * 64, "t1")
    second = EvidenceReference("e1", "m", "image", instant, Path("a.jpg"), "b" * 64, "t1")
    assert window_digest((first,)) != window_digest((second,))
