"""Free-plan local media-preparation minute metering (master plan §40 / T4)."""

from __future__ import annotations

import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.entitlements import (
    EntitlementError,
    require_preparation_minutes,
    summary,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.infrastructure import entitlement_usage as usage
from gamingcreator.ui.media_preparation import MediaPreparationJobs


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


def test_analysis_minutes_separate_from_preparation_and_never_double_on_rollover(
    tmp_path, monkeypatch
):
    root = tmp_path / ".cache/workspace/creations"
    root.mkdir(parents=True)
    (root / "entitlement.json").write_text('{"plan":"free"}', encoding="utf-8")

    def source(duration_us):
        stream = MediaStream(0, "video", Fraction(1, 1_000_000), 0, duration_us)
        return MediaAsset(
            "fixture",
            tmp_path / "clip.mp4",
            "a" * 64,
            (stream,),
            Fraction(0),
            duration_us,
            "fixture",
        )

    full = source(60 * 60_000_000)
    extra = source(1)
    november, december = "2026-11-30T23:59:59+00:00", "2026-12-01T00:00:00+00:00"
    stamp = november

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(stamp)

    monkeypatch.setattr(usage, "datetime", Clock)
    assert usage.record_preparation_if_new(root, key="media", seconds=120, now=november)
    usage.admit_workspace_analysis(tmp_path, tmp_path / "project", "a" * 32, full)
    assert usage.analysis_usage_this_month(root, november) == (full.duration_us, 1)
    assert usage.preparation_minutes_this_month(root, november) == 2
    with pytest.raises(AppError, match="本月分析额度不足"):
        usage.admit_workspace_analysis(tmp_path, tmp_path / "copied-project", "a" * 32, full)
    with pytest.raises(AppError, match="本月分析额度不足") as denied:
        usage.admit_workspace_analysis(tmp_path, tmp_path / "project", "b" * 32, extra)
    assert denied.value.code == "entitlement.analysis_minutes"
    stamp = december
    usage.admit_workspace_analysis(tmp_path, tmp_path / "project", "a" * 32, full)
    assert usage.analysis_usage_this_month(root, december) == (0, 0)
    with pytest.raises(AppError, match="原片身份不一致"):
        usage.admit_workspace_analysis(tmp_path, tmp_path / "project", "a" * 32, extra)
    usage.admit_workspace_analysis(tmp_path, tmp_path / "project", "b" * 32, extra)
    assert usage.analysis_usage_this_month(root, december) == (1, 1)


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


def test_submit_checks_quota_after_probe_at_utc_rollover(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    creations = repo / ".cache" / "workspace" / "creations"
    creations.mkdir(parents=True)
    (creations / "entitlement.json").write_text(
        json.dumps({"plan": "free", "billing": "none-local-evaluation"}),
        encoding="utf-8",
    )
    november = "2026-11-30T23:59:59+00:00"
    december = "2026-12-01T00:00:00+00:00"
    usage.record_preparation_if_new(creations, key="prior", seconds=55 * 60, now=november)
    project = repo / "artifacts" / "p"
    project.mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    (repo / "config.example.json").write_bytes(
        (Path(__file__).resolve().parents[1] / "config.example.json").read_bytes()
    )
    stamp = november
    rolls_over = False

    def fake_probe(_repository: Path, _media: Path) -> float:
        nonlocal stamp
        if rolls_over:
            stamp = december
        return 600.0

    monkeypatch.setattr("gamingcreator.ui.media_preparation.probe_duration_seconds", fake_probe)
    monkeypatch.setattr("gamingcreator.ui.media_preparation._clock", lambda: stamp)
    monkeypatch.setattr(MediaPreparationJobs, "_run", lambda _self, _job: None)
    jobs = MediaPreparationJobs(repo)
    request = {
        "project": "artifacts/p",
        "paths": [str(video)],
        "profile": "frames",
        "maxCostCny": "1",
        "timeoutSeconds": 30,
    }
    try:
        with pytest.raises(AppError) as denied:
            jobs.submit(request)
        assert denied.value.code == "entitlement.denied"
        rolls_over = True
        assert jobs.submit(request)["jobId"]
    finally:
        jobs.close()
    assert usage.preparation_minutes_this_month(creations, november) == 55
    assert usage.preparation_minutes_this_month(creations, december) == 10


def test_reservation_checks_latest_total_and_keeps_duplicate_and_month_semantics(tmp_path: Path):
    november = "2026-11-30T23:59:59+00:00"
    december = "2026-12-01T00:00:00+00:00"
    selection = {"plan": "free"}
    assert usage.record_preparation_if_new(tmp_path, key="prior", seconds=55 * 60, now=november)
    assert usage.record_preparation_if_new(
        tmp_path, key="first", seconds=300, selection=selection, now=november
    )
    with pytest.raises(EntitlementError):
        usage.record_preparation_if_new(
            tmp_path, key="second", seconds=300, selection=selection, now=november
        )
    assert not usage.record_preparation_if_new(
        tmp_path, key="first", seconds=300, selection=selection, now=november
    )
    assert usage.preparation_minutes_this_month(tmp_path, november) == 60
    assert not usage.has_preparation_entry(tmp_path, "second", november)
    assert usage.record_preparation_if_new(
        tmp_path, key="first", seconds=300, selection=selection, now=december
    )
    assert usage.preparation_minutes_this_month(tmp_path, december) == 5


def test_creation_jobs_summary_reads_ledger(tmp_path: Path):
    from gamingcreator.ui.creation_jobs import CreationJobs

    repo = tmp_path / "repo"
    repo.mkdir()
    service = CreationJobs(repo)
    service.select_plan("free")
    usage.record_preparation_if_new(service.root, key="k", seconds=180.0)
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
