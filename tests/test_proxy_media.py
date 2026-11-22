"""Editing proxies: bounded bytes, verified duration, reuse, and nothing partial left behind."""

import asyncio
import hashlib
import json
import os
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


def test_same_size_tampered_proxy_is_rejected_and_not_reused(repository):
    repo, source, sha = repository
    first = build(repo, source, sha)
    proxy = proxy_directory(repo, sha) / "proxy.mp4"
    original = proxy.read_bytes()
    assert len(original) == first["bytes"]
    tampered = bytearray(original)
    tampered[len(tampered) // 2] ^= 0xFF
    before = proxy.stat()
    proxy.write_bytes(tampered)
    os.utime(proxy, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert proxy.stat().st_size == first["bytes"]
    assert read_proxy(repo, sha) is None
    again = build(repo, source, sha)
    assert again["reused"] is False
    rebuilt = proxy.read_bytes()
    assert rebuilt != bytes(tampered)
    assert hashlib.sha256(rebuilt).hexdigest() == again["proxySha256"]
    assert read_proxy(repo, sha) is not None


def test_budget_breach_keeps_nothing(repository, monkeypatch):
    repo, source, sha = repository
    monkeypatch.setattr(proxy_media, "proxy_budget", lambda duration: 4096)
    with pytest.raises((AppError, ValueError)):
        build(repo, source, sha)
    assert leftovers(repo) == []


def test_replaced_source_or_malformed_receipt_is_refused(repository):
    repo, source, sha = repository
    other = source.with_name("other.mp4")
    other.write_bytes(source.read_bytes() + b"x")
    with pytest.raises(ValueError, match="registered recording"):
        build(repo, other, sha)
    assert leftovers(repo) == []
    build(repo, source, sha)
    receipt = proxy_directory(repo, sha) / "receipt.json"
    for broken in ("[]", json.dumps({"sourceSha256": sha})):
        receipt.write_text(broken, encoding="utf-8")
        assert read_proxy(repo, sha) is None


def test_duration_mismatch_keeps_nothing(repository):
    repo, source, sha = repository
    with pytest.raises(ValueError):
        build(repo, source, sha, duration=9_000_000)
    assert leftovers(repo) == []
    assert read_proxy(repo, sha) is None


def test_original_replaced_during_proxy_build_is_not_published(repository, monkeypatch):
    repo, source, sha = repository
    original_duration = proxy_media._duration_us

    async def replace_source_after_decode(*args):
        duration = await original_duration(*args)
        source.write_bytes(source.read_bytes() + b"different source")
        return duration

    monkeypatch.setattr(proxy_media, "_duration_us", replace_source_after_decode)
    with pytest.raises(ValueError, match="Source bytes"):
        build(repo, source, sha)
    assert leftovers(repo) == []


def test_rebuilding_does_not_overwrite_an_unregistered_proxy_file(repository):
    from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor

    repo, source, sha = repository
    unknown = proxy_directory(repo, sha) / "proxy.mp4"
    unknown.parent.mkdir(parents=True)
    unknown.write_bytes(b"retained user file")
    with pytest.raises(AppError) as caught:
        build(repo, source, sha)
    assert caught.value.code == "storage.proxy_unsafe"
    with pytest.raises(AppError) as invalid_source:
        asyncio.run(FfmpegMediaProcessor(repo).probe(unknown, CancellationContext("fixture", 10)))
    assert invalid_source.value.code == "media.proxy_not_source"
    assert unknown.read_bytes() == b"retained user file"


def test_stale_build_folders_are_reclaimed_but_recent_ones_kept(repository):
    import os
    import time

    repo, source, sha = repository
    root = repo / ".cache/workspace/proxies"
    stale, recent = root / ".building-stale", root / ".building-recent"
    for folder in (stale, recent):
        folder.mkdir(parents=True)
        (folder / "proxy.mp4").write_bytes(b"partial")
    old = time.time() - proxy_media.STALE_BUILD_SECONDS - 60
    os.utime(stale, (old, old))
    build(repo, source, sha)
    assert not stale.exists() and recent.exists()
