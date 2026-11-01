"""Batch make-proxy: queue many runs, share one SHA, keep single-item cleanup."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

import gamingcreator.infrastructure.proxy_media as proxy_media
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.storage import RunConfiguration
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.infrastructure.proxy_batch import make_proxies_for_runs
from gamingcreator.infrastructure.proxy_media import read_proxy
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
PIPELINE_HASH = "b" * 64


def _write_clip(path: Path, seconds: int = 2, *, frequency: int = 440, width: int = 320) -> str:
    subprocess.run(
        [
            str(FFMPEG),
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={width}x240:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    assert path.stat().st_size < 2_000_000
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _asset(path: Path, digest: str, seconds: int) -> MediaAsset:
    return MediaAsset(
        digest,
        path.resolve(),
        digest,
        (MediaStream(0, "video", Fraction(1), 0, seconds),),
        Fraction(0),
        seconds * 1_000_000,
        "proxy-batch-fixture-v1",
    )


def _config() -> RunConfiguration:
    return RunConfiguration(
        AnalysisConfig("fixture-provider", "fixture-model", 3, 2),
        Decimal("1"),
        "proxy-batch-test-v1",
        PIPELINE_HASH,
    )


async def _seed(project: Path, runs: list[tuple[str, Path, str, int]]) -> None:
    store = await SqliteTimelineStore.open(project)
    try:
        for run_id, path, digest, seconds in runs:
            await store.create_run(run_id, _asset(path, digest, seconds), _config())
    finally:
        await store.close()


def leftovers(repo: Path) -> list[str]:
    root = repo / ".cache/workspace/proxies"
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


@pytest.fixture
def repo_project(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    project = tmp_path / "project"
    repo.mkdir()
    project.mkdir()
    return repo, project


def test_batch_builds_shares_and_isolates_failures(repo_project: tuple[Path, Path], monkeypatch):
    repo, project = repo_project
    first = project / "a.mp4"
    second = project / "b.mp4"
    sha_a = _write_clip(first, 2, frequency=440, width=320)
    sha_b = _write_clip(second, 2, frequency=880, width=360)
    asyncio.run(
        _seed(
            project,
            [
                ("run-a1", first, sha_a, 2),
                ("run-a2", first, sha_a, 2),  # same source SHA
                ("run-b", second, sha_b, 2),
            ],
        )
    )

    report = asyncio.run(
        make_proxies_for_runs(
            project,
            repo,
            ["run-a1", "run-a2", "run-b", "missing-run"],
            tools=FFMPEG.parent,
        )
    )
    assert report["schemaVersion"] == "make-proxy-batch-v1"
    by_id = {item["runId"]: item for item in report["items"]}
    assert by_id["run-a1"]["status"] == "built"
    assert by_id["run-a2"]["status"] == "shared"
    assert by_id["run-a2"]["sharedWithRunId"] == "run-a1"
    assert by_id["run-b"]["status"] == "built"
    assert by_id["missing-run"]["status"] == "failed"
    assert report["summary"]["built"] == 2
    assert report["summary"]["shared"] == 1
    assert report["summary"]["failed"] == 1
    assert leftovers(repo) == sorted([sha_a, sha_b])
    assert read_proxy(repo, sha_a) is not None
    assert read_proxy(repo, sha_b) is not None

    # Second pass reuses; a deliberate budget breach on a new source leaves nothing for that SHA.
    third = project / "c.mp4"
    sha_c = _write_clip(third, 2, frequency=660, width=400)
    asyncio.run(_seed(project, [("run-c", third, sha_c, 2)]))
    monkeypatch.setattr(proxy_media, "proxy_budget", lambda duration: 4096)
    again = asyncio.run(
        make_proxies_for_runs(
            project,
            repo,
            ["run-a1", "run-c"],
            tools=FFMPEG.parent,
        )
    )
    by_id = {item["runId"]: item for item in again["items"]}
    assert by_id["run-a1"]["status"] == "reused"
    assert by_id["run-c"]["status"] == "failed"
    assert sha_c not in leftovers(repo)
    assert leftovers(repo) == sorted([sha_a, sha_b])


def test_all_eligible_queues_every_seeded_run(repo_project: tuple[Path, Path]):
    repo, project = repo_project
    clip = project / "one.mp4"
    digest = _write_clip(clip, 2)
    asyncio.run(_seed(project, [("run-1", clip, digest, 2), ("run-2", clip, digest, 2)]))
    report = asyncio.run(make_proxies_for_runs(project, repo, None, tools=FFMPEG.parent))
    assert [item["runId"] for item in report["items"]] == ["run-1", "run-2"]
    assert report["summary"]["built"] == 1
    assert report["summary"]["shared"] == 1