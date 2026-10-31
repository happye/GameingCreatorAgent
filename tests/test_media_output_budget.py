import asyncio
import shutil
import sys
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.media_process import MediaOutputLimit, run_media_process
from gamingcreator.infrastructure.render_limits import render_output_limit


def test_growing_file_is_stopped_reaped_and_reclaimed(tmp_path):
    output = tmp_path / "flood.nut"
    marker = tmp_path / "pid.txt"
    code = (
        "import os,sys,time;from pathlib import Path;"
        "Path(sys.argv[2]).write_text(str(os.getpid()));f=open(sys.argv[1],'wb',buffering=0);"
        "exec('while True:\\n f.write(b\\\"x\\\"*4096);time.sleep(.001)')"
    )
    with pytest.raises(AppError) as error:
        asyncio.run(
            run_media_process(
                [sys.executable, "-I", "-B", "-c", code, str(output), str(marker)],
                CancellationContext("flood", 10),
                output_limit=MediaOutputLimit(output, 65536, minimum_free_bytes=0),
            )
        )
    assert error.value.code == "media.file_limit"
    assert marker.exists() and not output.exists()


def test_disk_reserve_and_total_scratch_reject_before_start(tmp_path):
    output = tmp_path / "new.nut"
    command = [sys.executable, "-I", "-B", "-c", "raise RuntimeError('must not run')"]
    for limit, expected in [
        (MediaOutputLimit(output, 1024, shutil.disk_usage(tmp_path).free + 1), "media.disk_space"),
        (MediaOutputLimit(output, 1024, 0, directory_max_bytes=2), "media.scratch_limit"),
    ]:
        (tmp_path / "previous.txt").write_bytes(b"keep")
        with pytest.raises(AppError) as error:
            asyncio.run(
                run_media_process(command, CancellationContext("budget", 5), output_limit=limit)
            )
        assert error.value.code == expected
        assert not output.exists() and (tmp_path / "previous.txt").read_bytes() == b"keep"


def test_existing_file_is_never_claimed_or_deleted(tmp_path):
    output = tmp_path / "existing.nut"
    output.write_bytes(b"original")
    with pytest.raises(ValueError):
        asyncio.run(
            run_media_process(
                [sys.executable, "-c", "raise RuntimeError()"],
                CancellationContext("existing", 5),
                output_limit=MediaOutputLimit(output, 4, minimum_free_bytes=0),
            )
        )
    assert output.read_bytes() == b"original"


def test_ffmpeg_hard_cap_cannot_silently_publish_truncated_success(tmp_path):
    ffmpeg = Path(__file__).resolve().parents[1] / ".tools/ffmpeg/bin/ffmpeg.exe"
    if not ffmpeg.exists():
        pytest.skip("Pinned FFmpeg unavailable")
    output = tmp_path / "unbounded-audio.nut"
    with pytest.raises(AppError) as error:
        asyncio.run(
            run_media_process(
                [
                    str(ffmpeg),
                    "-v",
                    "error",
                    "-nostdin",
                    "-n",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-c:a",
                    "pcm_s16le",
                    "-fs",
                    "65536",
                    str(output),
                ],
                CancellationContext("native-cap", 10),
                output_limit=MediaOutputLimit(output, 65536, minimum_free_bytes=0),
            )
        )
    assert error.value.code == "media.file_limit" and not output.exists()


def test_budget_scales_for_validated_plan_but_has_hard_ceiling(tmp_path):
    tiny = render_output_limit(tmp_path / "small.nut", 80, 20, 64, 48)
    assert tiny.max_bytes == 8 * 1024**2
    large = render_output_limit(tmp_path / "large.nut", 12000, 30, 3840, 2160)
    assert large.max_bytes == 2 * 1024**3


def test_renderer_capacity_failure_cleans_only_its_raw_parts(tmp_path, monkeypatch):
    from test_creation_audio_render import inputs, render

    from gamingcreator.infrastructure import ffmpeg_render

    source, track = inputs(tmp_path)
    before = source.read_bytes(), track.path.read_bytes()
    monkeypatch.setattr(
        ffmpeg_render,
        "render_output_limit",
        lambda path, *args: MediaOutputLimit(path, 2048, minimum_free_bytes=0),
    )
    output = tmp_path / "limited"
    with pytest.raises(AppError) as error:
        asyncio.run(render(source, track, output))
    assert error.value.code == "media.file_limit"
    assert not list(output.glob("*.nut")) and not (output / "receipt.json").exists()
    assert before == (source.read_bytes(), track.path.read_bytes())


@pytest.mark.parametrize(
    "max_bytes,reserve,directory",
    [(True, 0, 10), (0, 0, 10), (-1, 0, 10), (10, True, 10), (10, 0, 0)],
)
def test_budget_rejects_invalid_counts(tmp_path, max_bytes, reserve, directory):
    with pytest.raises(ValueError):
        MediaOutputLimit(tmp_path / "invalid.nut", max_bytes, reserve, directory)
