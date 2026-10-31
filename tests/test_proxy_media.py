"""Editing proxies: bounded bytes, verified duration, reuse, and nothing partial left behind."""

import asyncio
import hashlib
import subprocess
from pathlib import Path

import pytest

import gamingcreator.infrastructure.proxy_media as proxy_media
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.proxy_media import (
    HARD_CAP_BYTES,
    make_proxy,
    proxy_budget,
    proxy_directory,
    read_proxy,
)

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"


@pytest.fixture
def repository(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            str(FFMPEG),
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x480:rate=30:duration=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    return tmp_path, source, hashlib.sha256(source.read_bytes()).hexdigest()


def build(repo, source, sha, duration=4_000_000):
    context = CancellationContext("proxy", 120)
    # The pinned tools are used in place; nothing large is copied into the test directory.
    return asyncio.run(make_proxy(repo, source, sha, duration, context, FFMPEG.parent))


def leftovers(repo):
    root = repo / ".cache/workspace/proxies"
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def test_budget_is_bounded_and_scales():
    assert proxy_budget(1_000_000) < proxy_budget(60_000_000) <= HARD_CAP_BYTES
    assert proxy_budget(100 * 3600 * 1_000_000) == HARD_CAP_BYTES
    with pytest.raises(ValueError):
        proxy_budget(0)


def test_proxy_is_small_verified_and_reused(repository):
    repo, source, sha = repository
    first = build(repo, source, sha)
    assert first["reused"] is False and first["bytes"] < first["budgetBytes"]
    assert abs(first["durationUs"] - 4_000_000) <= 500_000
    assert first["bytes"] < source.stat().st_size
    assert leftovers(repo) == [sha]
    again = build(repo, source, sha)
    assert again["reused"] is True and again["proxySha256"] == first["proxySha256"]
    proxy = proxy_directory(repo, sha) / "proxy.mp4"
    proxy.write_bytes(proxy.read_bytes() + b"tamper")
    assert read_proxy(repo, sha) is None


def test_budget_breach_keeps_nothing(repository, monkeypatch):
    repo, source, sha = repository
    monkeypatch.setattr(proxy_media, "proxy_budget", lambda duration: 4096)
    with pytest.raises((AppError, ValueError)):
        build(repo, source, sha)
    assert leftovers(repo) == []


def test_duration_mismatch_keeps_nothing(repository):
    repo, source, sha = repository
    with pytest.raises(ValueError):
        build(repo, source, sha, duration=9_000_000)
    assert leftovers(repo) == []
    assert read_proxy(repo, sha) is None
