"""Generator expectations are closed to unknown EXEs and mixed library sets."""

from pathlib import Path

import media_generator_clocks as clocks
import pytest


@pytest.mark.parametrize("identity", list(clocks.RECORDS))
def test_fixed_sets_keep_absolute_and_relative_clock_distinct(identity, monkeypatch):
    record = clocks.RECORDS[identity]
    monkeypatch.setattr(clocks, "_sha256", lambda path: record["files"][path.name])
    clock = clocks.generator_clock(Path("bin/ffmpeg.exe"))
    assert clock.absolute_video_start_us == 2_500_000
    assert (clock.origin_us, clock.duration_us, clock.head_hint_seconds) in [
        (2_478_000, 2_022_000, "0.022"),
        (2_478_667, 2_026_667, "0.021"),
    ]
    assert clock.relative_video_start_us in (22_000, 21_333)
    assert len(record["evidence_input_sha256"]) == 64


def test_unknown_executable_is_rejected_before_reading_libraries(monkeypatch):
    reads = []

    def unknown(path):
        reads.append(path)
        return "0" * 64

    monkeypatch.setattr(clocks, "_sha256", unknown)
    with pytest.raises(AssertionError, match="Unknown synthetic media generator"):
        clocks.generator_clock(Path("bin/ffmpeg.exe"))
    assert reads == [Path("bin/ffmpeg.exe")]


@pytest.mark.parametrize("identity", list(clocks.RECORDS))
@pytest.mark.parametrize("component", ["dll", "probe"])
def test_known_executable_with_mismatching_component_is_rejected(identity, component, monkeypatch):
    record = clocks.RECORDS[identity]
    damaged = (
        next(name for name in record["files"] if name.endswith(".dll"))
        if component == "dll"
        else "ffprobe.exe"
    )
    monkeypatch.setattr(
        clocks,
        "_sha256",
        lambda path: "0" * 64 if path.name == damaged else record["files"][path.name],
    )
    with pytest.raises(AssertionError, match="tool/DLL SHA256 mismatch"):
        clocks.generator_clock(Path("bin/ffmpeg.exe"))
