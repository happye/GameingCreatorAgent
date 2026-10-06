"""Long media timing records are consumed without removing diagnostic boundaries."""

import asyncio
import sys
from pathlib import Path

import pytest
from test_media_process import process_kernel

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.ffmpeg_media import AudioLogParser, VisualLogParser
from gamingcreator.infrastructure.media_process import _read_consumed_lines, run_media_process


def test_split_utf8_crlf_and_final_record_are_consumed_once():
    records = []

    def consume(line):
        if line.startswith("record:"):
            records.append(line)
            return True
        return False

    async def scenario():
        reader = asyncio.StreamReader()
        overflow = asyncio.Event()
        task = asyncio.create_task(_read_consumed_lines(reader, 32, overflow, consume))
        content = "record:中文\r\nnote\nrecord:尾行".encode()
        for byte in content:
            reader.feed_data(bytes([byte]))
            await asyncio.sleep(0)
        reader.feed_eof()
        assert await task == b"note\n" and not overflow.is_set()

    asyncio.run(scenario())
    assert records == ["record:中文\r\n", "record:尾行"]


def test_visual_stream_keeps_negative_origin_and_irregular_pts():
    parser = VisualLogParser()
    assert not parser.consume("diagnostic, not a timing record\n")
    assert parser.consume("[Parsed_showinfo_2 @ X] config in time_base: 1/90000\n")
    for index, pts in enumerate((-450000, -448470, -447030, -443970)):
        assert parser.consume(f"[Parsed_showinfo_2 @ X] n: {index} pts: {pts} pts_time: 0\n")
    clock, timestamps = parser.finish()
    assert clock.numerator == 1 and clock.denominator == 90000
    assert timestamps == (-450000, -448470, -447030, -443970)


@pytest.mark.parametrize("next_pts", [10, 9])
def test_visual_stream_rejects_repeated_or_backwards_pts(next_pts):
    parser = VisualLogParser()
    parser.consume("[Parsed_showinfo_2 @ X] config in time_base: 1/1000\n")
    parser.consume("[Parsed_showinfo_2 @ X] n: 0 pts: 10 pts_time: 0\n")
    with pytest.raises(AppError) as error:
        parser.consume(f"[Parsed_showinfo_2 @ X] n: 1 pts: {next_pts} pts_time: 0\n")
    assert error.value.code == "media.frame_mapping"


def test_visual_stream_requires_one_clock_and_at_least_one_frame():
    parser = VisualLogParser()
    with pytest.raises(AppError):
        parser.finish()
    parser.consume("[Parsed_showinfo_2 @ X] config in time_base: 1/1000\n")
    with pytest.raises(AppError):
        parser.finish()
    with pytest.raises(AppError):
        parser.consume("[Parsed_showinfo_2 @ X] config in time_base: 1/90000\n")


def test_audio_stream_separates_decoded_count_and_keeps_trimmed_piecewise_mapping():
    mapped = AudioLogParser(16000, "mapped")
    decoded = AudioLogParser(16000, "decoded", retain_frames=False)
    for index, (pts, decoded_samples, mapped_samples) in enumerate(
        [(0, 325, 325), (320, 341, 341), (671, 342, 336)]
    ):
        for name, samples in (("decoded", decoded_samples), ("mapped", mapped_samples)):
            line = f"[ashowinfo@{name} @ X] n:{index} pts:{pts} rate:16000 nb_samples:{samples}\n"
            assert mapped.consume(line) or decoded.consume(line)
    frames = mapped.finish()
    assert [frame.sample_offset for frame in frames] == [0, 325, 666]
    assert [frame.pts for frame in frames] == [0, 320, 671]
    assert [frame.sample_count for frame in frames] == [325, 341, 336]
    assert mapped.sample_count == 1002 and decoded.sample_count == 1008
    assert decoded.finish() == ()
    assert not mapped.consume("[ashowinfo@foreign @ X] n:0 pts:0 rate:16000 nb_samples:1")


def test_audio_stream_rejects_wrong_rate_or_missing_records():
    parser = AudioLogParser(16000, "mapped")
    with pytest.raises(AppError) as missing:
        parser.finish()
    assert missing.value.code == "media.audio_mapping"
    with pytest.raises(AppError) as changed:
        parser.consume("[ashowinfo@mapped @ X] n:0 pts:0 rate:48000 nb_samples:320")
    assert changed.value.code == "media.audio_mapping"


def test_process_streams_many_known_records_and_retains_small_diagnostics():
    count = 0

    def consume(line):
        nonlocal count
        if line.startswith("record:"):
            count += 1
            return True
        return False

    code = "import os;os.write(1,b'done');os.write(2,b'note\\n'+(b'record:'+b'x'*120+b'\\n')*4096+b'record: eof')"
    result = asyncio.run(
        run_media_process(
            [sys.executable, "-I", "-B", "-c", code],
            CancellationContext("stream", 10),
            max_stderr_bytes=32,
            stderr_line_consumer=consume,
        )
    )
    assert count == 4097 and result.stdout == b"done" and result.stderr == b"note\n"


@pytest.mark.parametrize(
    "content",
    ["b'private diagnostic\\n'*2000", "b'record:'+b'x'*70000+b'\\n'"],
)
def test_unknown_output_and_long_consumed_line_remain_bounded(content):
    with pytest.raises(AppError) as error:
        asyncio.run(
            run_media_process(
                [sys.executable, "-I", "-B", "-c", f"import os;os.write(2,{content})"],
                CancellationContext("stream", 10),
                max_stderr_bytes=128,
                stderr_line_consumer=lambda line: line.startswith("record:"),
            )
        )
    assert error.value.code == "media.output_limit"
    assert "private diagnostic" not in str(error.value)


@pytest.mark.parametrize("ending", ["parse_error", "cancel", "timeout"])
def test_stream_failure_or_cancellation_reaps_started_process(tmp_path: Path, ending: str):
    pid_path = tmp_path / "stream-pid.txt"
    kernel = process_kernel() if sys.platform == "win32" else None
    pinned = None
    context = CancellationContext("stream", 0.5 if ending == "timeout" else 10)

    def consume(line):
        nonlocal pinned
        if not line.startswith("record:"):
            return False
        if kernel is not None and pinned is None:
            pinned = kernel.OpenProcess(0x100000, False, int(pid_path.read_text()))
            assert pinned
        if ending == "parse_error":
            raise AppError("media.frame_mapping", "映射无效。", ExitCode.INPUT)
        if ending == "cancel":
            context.cancelled.set()
        return True

    code = "import os,sys,time;from pathlib import Path;Path(sys.argv[1]).write_text(str(os.getpid()))\nwhile True:\n os.write(2,b'record: frame\\n');time.sleep(0.01)"
    try:
        with pytest.raises(asyncio.CancelledError if ending == "cancel" else AppError) as error:
            asyncio.run(
                run_media_process(
                    [sys.executable, "-I", "-B", "-c", code, str(pid_path)],
                    context,
                    stderr_line_consumer=consume,
                )
            )
        if ending != "cancel":
            assert error.value.code == (
                "media.timeout" if ending == "timeout" else "media.frame_mapping"
            )
        if kernel is not None:
            assert pinned and kernel.WaitForSingleObject(pinned, 5000) == 0
        else:
            assert not Path(f"/proc/{pid_path.read_text()}").exists()
    finally:
        if kernel is not None and pinned:
            kernel.CloseHandle(pinned)
