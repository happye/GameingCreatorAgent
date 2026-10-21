"""TD009 sidecar readonly match / fingerprint reject contracts. No provider HTTP."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from test_detail_inspection import publish_fixture, refuse_sends, seed_project
from test_detail_query import constraint

from gamingcreator.application.detail_refinement import prepare_refinement, request_hash
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.storage import RunConfiguration, RunStatus, StoredRun, StoredTimeline
from gamingcreator.domain.actor_details import MATCHER_VERSION
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.detail_query_sidecar import match_refinement
from gamingcreator.infrastructure.detail_refinement_sidecar import (
    freeze_request,
    reuse_or_refuse,
    sidecar_directory,
)

RUN = "run-gap"
MEDIA = "media-gap"
EVENT = f"{RUN}:{MEDIA}:event:" + "ef" * 12
DURATION = 10_000_000


def _gap_timeline() -> StoredTimeline:
    asset = MediaAsset(
        MEDIA,
        Path("gap-source.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1_000_000), 0, DURATION),),
        Fraction(0),
        DURATION,
        "fixture",
    )
    config = RunConfiguration(
        AnalysisConfig("fixture", "fixture", 10, 10),
        Decimal("1"),
        "fixture",
        "b" * 64,
    )
    run = StoredRun(RUN, asset, config, "c" * 64, RunStatus.FAILED, "analysis.coverage_gap")
    evidence = EvidenceReference(
        f"{RUN}:{MEDIA}:image:000000",
        MEDIA,
        "image",
        SourceInstant(100_000, DURATION),
        Path("0.jpg"),
        "d" * 64,
        "fixture",
    )
    event = SemanticEvent(
        EVENT,
        MEDIA,
        RUN,
        SourceRange(0, 1_000_000, DURATION),
        ("角色站立。",),
        (),
        (evidence.evidence_id,),
        "visual",
        None,
    )
    return StoredTimeline(run, (), (evidence,), (), (event,), ())


def test_match_refinement_refuses_coverage_gap_without_sidecar_writes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    timeline = _gap_timeline()
    query = constraint(("hair_color", "white", "hair"))
    with pytest.raises(AppError) as refused:
        match_refinement(project, timeline, EVENT, query, profile="v1", save=False)
    assert refused.value.code == "refinement.coverage_gap"
    assert not (project / "runs").exists() or not any(project.rglob("matches/*.json"))


def test_match_refinement_readonly_exposes_matcher_v1_2_without_writes(
    tmp_path: Path, monkeypatch
) -> None:
    project, _, timeline = seed_project(tmp_path)
    publish_fixture(project, timeline)
    refuse_sends(monkeypatch)
    before = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file() and not path.name.endswith(("-shm", "-wal"))
    }
    document = match_refinement(
        project,
        timeline,
        timeline.events[0].event_id,
        constraint(("hair_color", "white", "hair")),
        profile="v1",
        save=False,
    )
    assert document["result"]["matcherVersion"] == MATCHER_VERSION
    assert MATCHER_VERSION == "actor-detail-matcher-v1.2"
    assert document["result"]["status"] == "full"
    after = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file() and not path.name.endswith(("-shm", "-wal"))
    }
    assert after == before
    assert not list((project / "runs").rglob("matches/*.json"))


def test_match_refinement_save_uses_matcher_versioned_filename(
    tmp_path: Path, monkeypatch
) -> None:
    project, _, timeline = seed_project(tmp_path)
    directory, _, _ = publish_fixture(project, timeline)
    refuse_sends(monkeypatch)
    query = constraint(("hair_color", "white", "hair"))
    document = match_refinement(
        project, timeline, timeline.events[0].event_id, query, profile="v1", save=True
    )
    matches = list((directory / "matches").glob("*.json"))
    assert len(matches) == 1
    assert matches[0].name.endswith(f"-{MATCHER_VERSION}.json")
    assert document["result"]["matcherVersion"] == MATCHER_VERSION
    # Tampering the saved report must fail closed on save.
    tampered = dict(document)
    tampered["qualityGate"] = True
    matches[0].write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(AppError) as caught:
        match_refinement(
            project, timeline, timeline.events[0].event_id, query, profile="v1", save=True
        )
    assert caught.value.code == "refinement.immutable"


def test_fingerprint_drift_orphans_old_sidecar_without_stale_reuse(tmp_path: Path) -> None:
    """TD009: changing event facts changes the refinement key; old sidecar is not reused."""
    from test_detail_budget_sidecar import timeline as budget_timeline

    stored = budget_timeline()
    prepared = prepare_refinement(stored, stored.events[0].event_id)
    assert prepared.request is not None and prepared.request_hash is not None
    digest = freeze_request(tmp_path, prepared.request)
    request_path = sidecar_directory(tmp_path, stored.run.run_id, digest) / "request.json"
    assert request_path.is_file()

    mutated_event = replace(
        stored.events[0],
        observable_facts=("画面被改写后的观察，指纹应失效。",),
    )
    mutated = replace(stored, events=(mutated_event, *stored.events[1:]))
    drifted = reuse_or_refuse(tmp_path, mutated, mutated_event.event_id)
    assert drifted.reused is False and drifted.detail is None
    assert drifted.request is not None and drifted.request_hash != digest
    # Old frozen request remains on disk but is not selected for the new fingerprint.
    assert request_path.is_file()
    intact = reuse_or_refuse(tmp_path, stored, stored.events[0].event_id)
    assert intact.request_hash == digest and intact.reused is False and intact.detail is None


def test_reuse_or_refuse_rejects_tampered_request_fingerprint(tmp_path: Path) -> None:
    """TD009: sidecar request.json fingerprint tampering fails closed."""
    from test_detail_budget_sidecar import timeline as budget_timeline

    stored = budget_timeline()
    prepared = prepare_refinement(stored, stored.events[0].event_id)
    assert prepared.request is not None
    digest = freeze_request(tmp_path, prepared.request)
    target = sidecar_directory(tmp_path, stored.run.run_id, digest) / "request.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["eventFingerprint"] = "0" * 64
    target.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AppError) as damaged:
        reuse_or_refuse(tmp_path, stored, stored.events[0].event_id)
    assert damaged.value.code == "refinement.source_mismatch"
