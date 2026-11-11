"""Stage C waveform peaks from project FFmpeg (display only)."""

import subprocess
from pathlib import Path

import pytest

from gamingcreator.infrastructure.audio_peaks import audio_peaks, peaks_from_pcm

REPOSITORY = Path(__file__).resolve().parents[1]
FFMPEG = REPOSITORY / ".tools/ffmpeg/bin/ffmpeg.exe"
needs_ffmpeg = pytest.mark.skipif(not FFMPEG.exists(), reason="project FFmpeg missing")


def make(path: Path, *inputs: str) -> Path:
    subprocess.run(
        [str(FFMPEG), "-v", "error", "-y", *inputs, "-t", "2", str(path)],
        check=True,
        capture_output=True,
    )
    return path


def test_peaks_are_bucket_maxima():
    pcm = b"".join(v.to_bytes(2, "little", signed=True) for v in (0, 100, -16384, 0))
    assert peaks_from_pcm(pcm, 2) == [0.003, 0.5]
    assert peaks_from_pcm(b"", 3) == []


@needs_ffmpeg
def test_silence_then_tone(tmp_path):
    source = make(
        tmp_path / "a.wav",
        "-f",
        "lavfi",
        "-i",
        "aevalsrc='if(lt(t,1),0,0.5*sin(2*PI*100*t))':s=8000",
    )
    peaks = audio_peaks(REPOSITORY, source, 0, 2_000_000, 4)
    assert peaks is not None and len(peaks) == 4
    assert peaks[0] < 0.05 and min(peaks[2:]) > 0.3  # edge bucket may ring
    later = audio_peaks(REPOSITORY, source, 1_000_000, 2_000_000, 2)
    assert later is not None and min(later) > 0.3


@needs_ffmpeg
def test_video_without_audio_is_none_and_ranges_are_bounded(tmp_path):
    source = make(tmp_path / "v.mp4", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10")
    assert audio_peaks(REPOSITORY, source, 0, 1_000_000, 10) is None
    for start, end, buckets in ((5, 5, 10), (0, 700_000_000, 10), (0, 1_000_000, 0)):
        with pytest.raises(ValueError):
            audio_peaks(REPOSITORY, source, start, end, buckets)
