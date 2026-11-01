"""OCR hard-case fixtures: byte-capped synthetics; no human-eval / F006 claims."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from ocr_hard_case_fixtures import (
    CATALOG_PATH,
    DIFFICULTIES,
    FFMPEG,
    ROOT,
    load_catalog,
    render_all_cases,
)

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.ocr_frames import normalize_text
from gamingcreator.infrastructure.windows_ocr import WindowsOcrEngine

FONT = Path("C:/Windows/Fonts/msyh.ttc")


def test_catalog_is_honest_and_complete() -> None:
    document = load_catalog()
    lowered = document["disclaimer"].lower()
    assert "not human-reviewed" in lowered
    assert "f006" in lowered
    assert document["maxImageBytes"] <= 512 * 1024
    difficulties = {case["difficulty"] for case in document["cases"]}
    assert difficulties == DIFFICULTIES or DIFFICULTIES.issubset(difficulties)
    assert "plain_control" in difficulties
    assert "low_contrast" in difficulties
    assert "stylized_title" in difficulties
    for case in document["cases"]:
        assert case["expectedSubstrings"]
        assert case["draw"]


@pytest.mark.skipif(
    not FFMPEG.is_file() or not FONT.is_file(),
    reason="needs project-local FFmpeg and Windows Chinese font to synthesize fixtures",
)
def test_synthetic_fixtures_respect_byte_cap(tmp_path: Path) -> None:
    document = load_catalog()
    work = tmp_path / "frames"
    rendered = render_all_cases(work, catalog=document)
    try:
        assert len(rendered) == len(document["cases"])
        for _case, path in rendered:
            assert path.is_file()
            assert path.stat().st_size <= document["maxImageBytes"]
            assert path.stat().st_size > 100
    finally:
        for _case, path in rendered:
            path.unlink(missing_ok=True)
        if work.exists():
            for leftover in work.iterdir():
                leftover.unlink(missing_ok=True)
            work.rmdir()


@pytest.mark.skipif(
    sys.platform != "win32" or not FFMPEG.is_file() or not FONT.is_file(),
    reason="needs Windows OCR, Chinese font, and project-local FFmpeg",
)
def test_windows_ocr_smokes_hard_cases_without_quality_claims(tmp_path: Path) -> None:
    """Run the real engine on hard cases. Plain control is a smoke check only.

    Low-contrast / stylized titles are allowed to miss text. This test never asserts
    overall accuracy and must not be read as human review or F006 evidence.
    """
    document = load_catalog()
    work = tmp_path / "frames"
    scratch = tmp_path / "ocr-scratch"
    rendered = render_all_cases(work, catalog=document)
    engine = WindowsOcrEngine(scratch)
    try:
        paths = [path for _case, path in rendered]
        batch = asyncio.run(
            engine.recognize(paths, ("zh-Hans-CN", "en-US"), CancellationContext("ocr-hard", 180))
        )
        assert not batch.failed
        assert len(batch.readings) >= 1 or batch.available_languages == ()
        by_id = {case["id"]: path for case, path in rendered}
        # Map readings back by request index.
        texts_by_index: dict[int, set[str]] = {}
        for reading in batch.readings:
            bucket = texts_by_index.setdefault(reading.index, set())
            for line in reading.lines:
                bucket.add(normalize_text(line.text))
        for index, (case, _path) in enumerate(rendered):
            joined = " ".join(sorted(texts_by_index.get(index, ())))
            if case["difficulty"] == "plain_control" and "zh-Hans-CN" in batch.available_languages:
                assert any(
                    needle in joined for needle in case["expectedSubstrings"]
                ), f"plain control smoke missed substrings for {case['id']}: {joined!r}"
            # Hard cases: structural only — presence or absence of text is not graded.
            assert case["id"] in by_id
    finally:
        for _case, path in rendered:
            path.unlink(missing_ok=True)
        if work.exists():
            for leftover in work.iterdir():
                leftover.unlink(missing_ok=True)
            work.rmdir()
        if scratch.exists():
            for leftover in scratch.rglob("*"):
                if leftover.is_file():
                    leftover.unlink(missing_ok=True)


def test_catalog_path_is_under_tests_fixtures() -> None:
    assert CATALOG_PATH.is_file()
    assert "ocr-hard-cases" in CATALOG_PATH.parts
    assert ROOT.joinpath("tests").exists()