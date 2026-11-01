"""Expanded detect-shots synthetic fixtures; no human-review / F006 claims."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from shot_hard_case_fixtures import CATALOG_PATH, FFMPEG, load_catalog, render_all_cases

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.shot_boundaries import detect_shot_boundaries
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_shots import FfmpegShotDetector

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_is_honest_and_covers_black_and_cuts() -> None:
    document = load_catalog()
    lowered = document["disclaimer"].lower()
    assert "not human-reviewed" in lowered
    assert "抽检未人评" in document["disclaimer"] or "f006" in lowered
    assert "f006" in lowered
    assert document["maxVideoBytes"] <= 8 * 1024 * 1024
    ids = {case["id"] for case in document["cases"]}
    assert "hard-cut-plus-black" in ids
    assert "triple-hard-cuts" in ids
    assert any("black" in case["id"] for case in document["cases"])
    assert CATALOG_PATH.is_file()


def _matches(expect: dict[str, object], *, cuts: int, black: int, shots: int) -> None:
    if "cuts" in expect:
        assert cuts == int(expect["cuts"])
    if "cutsMin" in expect:
        assert cuts >= int(expect["cutsMin"])
    if "black" in expect:
        assert black == int(expect["black"])
    if "shots" in expect:
        assert shots == int(expect["shots"])
    if "shotsMin" in expect:
        assert shots >= int(expect["shotsMin"])


@pytest.mark.skipif(not FFMPEG.is_file(), reason="project-local FFmpeg is not installed")
def test_synthetic_fixtures_respect_byte_cap_and_detect_patterns(tmp_path: Path) -> None:
    document = load_catalog()
    work = tmp_path / "clips"
    rendered = render_all_cases(work, catalog=document)
    try:
        assert len(rendered) == len(document["cases"])
        for _case, path in rendered:
            assert path.is_file()
            assert path.stat().st_size <= document["maxVideoBytes"]

        async def probe_one(path: Path):
            context = CancellationContext("shot-hard", 120)
            media = await FfmpegMediaProcessor(ROOT).probe(path, context)
            samples = await FfmpegShotDetector(ROOT).samples(media, context)
            return media, samples

        for case, path in rendered:
            media, samples = asyncio.run(probe_one(path))
            result = detect_shot_boundaries(samples.cuts, samples.transitions, media.duration_us)
            _matches(
                case["expect"],
                cuts=len(result.cuts),
                black=len(result.black),
                shots=len(result.shots),
            )
    finally:
        for _case, path in rendered:
            path.unlink(missing_ok=True)
        if work.exists():
            for leftover in work.iterdir():
                leftover.unlink(missing_ok=True)
            work.rmdir()