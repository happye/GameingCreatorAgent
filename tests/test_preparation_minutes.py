"""Free-plan local media-preparation minute metering (master plan §40 / T4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.entitlements import (
    EntitlementError,
    require_preparation_minutes,
    summary,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import entitlement_usage as usage
from gamingcreator.ui.media_preparation import (
    _preparation_quota_or_none,
)


def test_summary_includes_preparation_minutes():
    data = summary({"plan": "free"}, 2, preparation_minutes_used=12.5)
    assert data["monthlyPreparationMinutes"] == 60
    assert data["preparationMinutesThisMonth"] == 12.5
    unlimited = summary(None, 0, preparation_minutes_used=3)
    assert unlimited["monthlyPreparationMinutes"] is None
    assert unlimited["preparationMinutesThisMonth"] == 3.0


def test_require_preparation_under_and_over_limit():
    require_preparation_minutes({"plan": "free"}, 10.0, 20.0)
    with pytest.raises(EntitlementError, match="准备录像额度不足"):
        require_preparation_minutes({"plan": "free"}, 50.0, 15.0)
    # Creator / founder unlimited
    require_preparation_minutes({"plan": "creator"}, 0.0, 10_000.0)
    require_preparation_minutes(None, 0.0, 10_000.0)


def test_ledger_records_once_and_resume_key_does_not_double(tmp_path: Path):
    root = tmp_path / "creations"
    root.mkdir()
    key = "abc123"
    assert usage.record_preparation_if_new(
        root, key=key, seconds=90.0, now="2026-11-01T01:00:00+00:00"
    )
    assert usage.preparation_minutes_this_month(root, now="2026-11-01T02:00:00+00:00") == 1.5
    assert usage.has_preparation_entry(root, key, now="2026-11-01T02:00:00+00:00")
    # Same key again (resume / duplicate submit): no add
    assert (
        usage.record_preparation_if_new(
            root, key=key, seconds=90.0, now="2026-11-01T03:00:00+00:00"
        )
        is False
    )
    assert usage.preparation_minutes_this_month(root, now="2026-11-01T03:00:00+00:00") == 1.5
    document = json.loads((root / usage.USAGE_NAME).read_text(encoding="utf-8"))
    assert document["schemaVersion"] == usage.SCHEMA
    assert len(document["months"]["2026-11"]["entries"]) == 1


def test_failed_batch_policy_counts_at_accept(tmp_path: Path):
    """Policy: minutes reserved when submit is accepted; a later failure still counts."""
    root = tmp_path / "creations"
    root.mkdir()
    key = "failed-batch-key"
    assert usage.record_preparation_if_new(
        root, key=key, seconds=120.0, now="2026-11-01T04:00:00+00:00"
    )
    # Simulate batch later failing: ledger unchanged and still counted
    assert usage.preparation_minutes_this_month(root, now="2026-11-15T00:00:00+00:00") == 2.0
    assert usage.has_preparation_entry(root, key, now="2026-11-15T00:00:00+00:00")


def test_quota_gate_rejects_over_limit_without_recording(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    creations = repo / ".cache" / "workspace" / "creations"
    creations.mkdir(parents=True)
    (creations / "entitlement.json").write_text(
        json.dumps({"plan": "free", "billing": "none-local-evaluation"}),
        encoding="utf-8",
    )
    # Already used 55 minutes
    usage.record_preparation_if_new(
        creations, key="prior", seconds=55 * 60, now="2026-11-01T00:00:00+00:00"
    )
    project = repo / "artifacts" / "p"
    project.mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def fake_probe(repository: Path, media: Path) -> float:
        return 10 * 60  # 10 more minutes would exceed 60

    monkeypatch.setattr("gamingcreator.ui.media_preparation.probe_duration_seconds", fake_probe)
    with pytest.raises(AppError) as denied:
        _preparation_quota_or_none(repo, project, [video])
    assert denied.value.code == "entitlement.denied"
    assert usage.preparation_minutes_this_month(creations, now="2026-11-01T00:00:00+00:00") == 55.0


def test_quota_gate_under_limit_returns_pending_record(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    creations = repo / ".cache" / "workspace" / "creations"
    creations.mkdir(parents=True)
    (creations / "entitlement.json").write_text(json.dumps({"plan": "free"}), encoding="utf-8")
    project = repo / "artifacts" / "p"
    project.mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(
        "gamingcreator.ui.media_preparation.probe_duration_seconds",
        lambda repository, media: 30.0,
    )
    pending = _preparation_quota_or_none(repo, project, [video])
    assert pending is not None
    key, seconds = pending
    assert seconds == 30.0
    assert usage.record_preparation_if_new(
        creations, key=key, seconds=seconds, now="2026-11-01T05:00:00+00:00"
    )
    assert usage.preparation_minutes_this_month(creations, now="2026-11-01T05:00:00+00:00") == 0.5
    # Same paths again: no pending charge
    assert _preparation_quota_or_none(repo, project, [video]) is None


def test_creation_jobs_summary_reads_ledger(tmp_path: Path):
    from gamingcreator.ui.creation_jobs import CreationJobs

    repo = tmp_path / "repo"
    repo.mkdir()
    service = CreationJobs(repo)
    service.select_plan("free")
    usage.record_preparation_if_new(
        service.root, key="k", seconds=180.0, now="2026-11-01T06:00:00+00:00"
    )
    data = service.entitlement_summary()
    assert data["plan"] == "free"
    assert data["monthlyPreparationMinutes"] == 60
    assert data["preparationMinutesThisMonth"] == 3.0


def test_probe_duration_with_real_ffprobe(tmp_path: Path):
    import subprocess

    repo = Path(__file__).resolve().parents[1]
    ffmpeg = repo / ".tools/ffmpeg/bin/ffmpeg.exe"
    if not ffmpeg.is_file():
        pytest.skip("Pinned FFmpeg is unavailable")
    media = tmp_path / "two-seconds.mp4"
    subprocess.run(
        [
            str(ffmpeg),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x120:d=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(media),
        ],
        check=True,
        capture_output=True,
    )
    seconds = usage.probe_duration_seconds(repo, media)
    assert 1.5 <= seconds <= 2.5
