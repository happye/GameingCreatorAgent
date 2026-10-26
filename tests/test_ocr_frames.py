"""Local on-screen text: parsing, engine output, frame identity, read-only CLI, real tools."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from test_detail_query import snapshot
from test_material_tasks import seed_tasks
from test_shot_boundaries import FFMPEG, ROOT

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.ocr_frames import (
    OCR_REPORT_VERSION,
    OcrBatch,
    OcrEngineIdentity,
    build_ocr_report,
    matched_frames,
    ocr_summary,
)
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import RunStatus, StoredRun
from gamingcreator.cli.main import main
from gamingcreator.cli.ocr_frames import build_run_ocr_report, execute_ocr_frames
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset, MediaStream
from gamingcreator.domain.ocr_frames import (
    OcrLine,
    OcrReading,
    OcrWord,
    likely_text,
    normalize_text,
    parse_reading,
    recurring_texts,
)
from gamingcreator.infrastructure.ffmpeg_fullres import FfmpegFullResolutionFrames
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.windows_ocr import OcrOutputParser, WindowsOcrEngine

IDENTITY = OcrEngineIdentity("fixture-ocr", "fixture")


def test_normalization_drops_layout_spaces_between_cjk_only() -> None:
    assert normalize_text("钟 馗 斩 妖 除 魔") == "钟馗斩妖除魔"
    assert normalize_text("  BOSS   HEALTH 1200 ") == "BOSS HEALTH 1200"
    assert normalize_text("大 蚌 真 君 Lv 5") == "大蚌真君 Lv 5"
    assert likely_text("大蚌真君") and likely_text("GAME") and likely_text("1200")
    assert not likely_text("•ooo") and not likely_text("0000")  # one repeated character
    assert not likely_text("i,ii") and not likely_text("龙") and not likely_text("(W")


def record(index: int = 0, language: str = "zh-Hans-CN", text: str = "游 戏") -> dict:
    return {
        "kind": "frame",
        "index": index,
        "language": language,
        "width": 1920,
        "height": 1080,
        "lines": [
            {
                "text": text,
                "words": [{"text": "游", "x": 1, "y": 2, "width": 3, "height": 4}],
            }
        ],
    }


def test_reading_parser_validates_every_field() -> None:
    reading = parse_reading(record())
    assert reading.lines[0].words[0] == OcrWord("游", 1, 2, 3, 4)
    for broken in (
        {**record(), "index": -1},
        {**record(), "width": 0},
        {**record(), "index": True},
        {**record(), "lines": "x"},
        {**record(), "lines": [{"text": "a", "words": [{"text": "a", "x": 1.5}]}]},
    ):
        with pytest.raises(ValueError):
            parse_reading(broken)


def engine_lines(index: int, language: str, *texts: str) -> list[str]:
    """What the PowerShell script prints for one frame and language."""
    lines = [
        json.dumps(
            {
                "kind": "line",
                "index": index,
                "language": language,
                "text": text,
                "words": [{"text": text, "x": 1, "y": 2, "width": 3, "height": 4}],
            },
            ensure_ascii=False,
        )
        for text in texts
    ]
    summary = {"kind": "frame", "index": index, "language": language, "width": 64}
    return [*lines, json.dumps({**summary, "height": 32, "lineCount": len(texts)})]


def test_engine_output_parser_assembles_lines_and_rejects_malformed_output() -> None:
    parser = OcrOutputParser(2)
    assert parser.consume("\ufeff" + json.dumps({"kind": "engine", "available": ["en-US"]}))
    for line in engine_lines(1, "en-US", "GAME", "SCIENCE"):
        assert parser.consume(line + "\r\n")
    # Index 0: one language read a line, then the image failed; the line is discarded.
    assert parser.consume(engine_lines(0, "en-US", "half")[0])
    assert parser.consume(json.dumps({"kind": "failed", "index": 0, "error": "X"}))
    assert not parser.consume("WARNING: something printed by PowerShell")
    assert parser.consume('{"kind":"done"}')
    assert parser.available == ("en-US",) and parser.failed == {0} and parser.done
    assert [item.text for item in parser.readings[0].lines] == ["GAME", "SCIENCE"]
    for bad in (
        engine_lines(5, "en-US"),
        [json.dumps({"kind": "failed", "index": 9})],
        [json.dumps({"kind": "surprise"})],
        ["{not json"],
        engine_lines(0, "en-US", "a")[:1] + ['{"kind":"done"}'],  # line without its frame
        [engine_lines(0, "en-US", "a")[1]],  # frame claims a line that never came
    ):
        with pytest.raises(AppError):
            parser = OcrOutputParser(2)
            for line in bad:
                parser.consume(line)


def test_engine_refuses_output_that_never_finished(tmp_path, monkeypatch) -> None:
    async def silent(arguments, context, **kwargs):
        kwargs["stdout_line_consumer"](json.dumps({"kind": "engine", "available": ["en-US"]}))
        script = base64.b64decode(arguments[-1]).decode("utf-16-le")
        assert "'" + str(tmp_path) not in script  # the request path is never script text

    monkeypatch.setattr("gamingcreator.infrastructure.windows_ocr.run_media_process", silent)
    monkeypatch.setattr("gamingcreator.infrastructure.windows_ocr.sys.platform", "win32")
    engine = WindowsOcrEngine(tmp_path / "o’clock 'quoted'")
    with pytest.raises(AppError) as unfinished:
        asyncio.run(engine.recognize([tmp_path / "a.jpg"], ("en-US",), CancellationContext("t", 5)))
    assert unfinished.value.code == "ocr.output"
    assert list((tmp_path / "o’clock 'quoted'").iterdir()) == []


def asset(origin: Fraction = Fraction(1)) -> MediaAsset:
    return MediaAsset(
        "media-1",
        Path("C:/footage/demo.mp4"),
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1000), int(origin * 1000), 10_000),),
        origin,
        10_000_000,
        "fixture",
    )


def test_matched_frames_pair_by_exact_instant_or_refuse_everything() -> None:
    media = asset()
    saved = [("e2", 1_500_000), ("e1", 500_000)]
    extracted = [
        (1500, Fraction(1, 1000), Path("a.jpg")),
        (2500, Fraction(1, 1000), Path("b.jpg")),
    ]
    assert matched_frames(media, saved, extracted) == (
        ("e1", 500_000, Path("a.jpg")),
        ("e2", 1_500_000, Path("b.jpg")),
    )
    outside = (99_999, Fraction(1, 1000), Path("b.jpg"))  # beyond the media's end
    for wrong in (
        extracted[:1],
        [extracted[0], (2501, Fraction(1, 1000), Path("b.jpg"))],
        [extracted[0], outside],
    ):
        with pytest.raises(AppError) as refused:
            matched_frames(media, saved, wrong)
        assert refused.value.code == "media.frame_mapping"


def stored_run() -> StoredRun:
    from test_material_tasks import CONFIG

    return StoredRun("run-1", asset(), CONFIG, "hash", RunStatus.COMPLETED, None)


def line(text: str) -> OcrLine:
    return OcrLine(text, (OcrWord(text, 0, 0, 1, 1),))


def test_report_keeps_failed_empty_and_unread_frames_apart() -> None:
    frames = [("e0", 0), ("e1", 500_000), ("e2", 1_000_000), ("e3", 1_500_000)]
    batch = OcrBatch(
        ("en-US", "zh-Hans-CN"),
        (
            OcrReading(0, "zh-Hans-CN", 64, 32, (line("大 蚌 真 君"),)),
            OcrReading(0, "en-US", 64, 32, (line("i,ii"),)),
            OcrReading(1, "zh-Hans-CN", 64, 32, ()),
            OcrReading(2, "zh-Hans-CN", 64, 32, (line("大 蚌 真 君"),)),
            OcrReading(3, "zh-Hans-CN", 64, 32, (line("游 戏 科 学"),)),
        ),
        frozenset({3}),
    )
    report = build_ocr_report(
        stored_run(),
        frames,
        batch,
        IDENTITY,
        ("zh-Hans-CN", "en-US", "ja"),
        every=1,
        seconds={"extract": 1.0},
    )
    assert report["schemaVersion"] == OCR_REPORT_VERSION
    assert (report["readOnly"], report["paidRequests"], report["humanReviewed"]) == (
        True,
        0,
        False,
    )
    assert [row["status"] for row in report["frames"]] == ["text", "empty", "text", "failed"]
    assert report["frames"][3]["lines"] == []  # a failed frame keeps no text
    first = report["frames"][0]["lines"]  # languages in sorted order: en-US, zh-Hans-CN
    assert [(item["language"], item["text"], item["likelyText"]) for item in first] == [
        ("en-US", "i,ii", False),
        ("zh-Hans-CN", "大蚌真君", True),
    ]
    summary = report["summary"]
    assert (summary["framesWithText"], summary["framesWithLikelyText"]) == (2, 2)
    assert (summary["emptyFrames"], summary["failedFrames"]) == (1, 1)
    assert report["engine"]["unavailableLanguages"] == ["ja"]
    assert report["recurringTexts"][0] == {
        "text": "大蚌真君",
        "firstUs": 0,
        "lastUs": 1_000_000,
        "frames": 2,
    }
    assert any("大蚌真君" in text for text in ocr_summary(report))
    unread = build_ocr_report(
        stored_run(),
        [("e0", 0)],
        OcrBatch((), (), frozenset()),
        IDENTITY,
        ("ja",),
        every=1,
        seconds={},
    )
    assert unread["frames"][0]["status"] == "unavailable"


def test_recurring_texts_count_each_instant_once() -> None:
    spans = recurring_texts([(0, "GAME"), (0, "GAME"), (5, "GAME"), (5, "x"), (9, "龙")])
    assert [(item.text, item.first_us, item.last_us, item.frames) for item in spans] == [
        ("GAME", 0, 5, 2)
    ]


class FakeFrames:
    def __init__(self, shift: int = 0) -> None:
        self.shift = shift
        self.output: Path | None = None

    async def extract(self, media, interval, count, output, context):
        self.output = output
        output.mkdir(parents=True)
        image = output / "frame-000001.jpg"
        image.write_bytes(b"jpg")
        # seed_tasks saves one frame at pts 1100 (1/1000) with a 1 s origin: 100 ms.
        return ((1100 + self.shift, Fraction(1, 1000), image),)


class FakeEngine:
    def __init__(self, available=("zh-Hans-CN", "en-US")) -> None:
        self.available = tuple(available)
        self.seen: list[Path] = []

    def identity(self) -> OcrEngineIdentity:
        return IDENTITY

    async def recognize(self, images, languages, context):
        self.seen = [Path(item) for item in images]
        assert all(item.is_file() for item in self.seen)
        return OcrBatch(
            self.available,
            (OcrReading(0, "zh-Hans-CN", 64, 32, (line("游 戏 科 学"),)),),
            frozenset(),
        )


def test_cli_reads_text_without_touching_the_project_and_cleans_scratch(tmp_path) -> None:
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    before = snapshot(project)
    scratch = tmp_path / "scratch"
    frames, engine = FakeFrames(), FakeEngine()
    output = tmp_path / "reports" / "ocr.json"
    report = asyncio.run(execute_ocr_frames(project, "run-000", output, frames, engine, scratch))
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["frames"][0]["timeUs"] == 100_000
    assert report["recurringTexts"][0]["text"] == "游戏科学"
    assert frames.output is not None and not frames.output.exists()
    assert snapshot(project) == before
    with pytest.raises(AppError, match="新的文件"):
        asyncio.run(execute_ocr_frames(project, "run-000", output, frames, engine, scratch))
    with pytest.raises(AppError, match="项目目录"):
        asyncio.run(
            execute_ocr_frames(project, "run-000", project / "o.json", frames, engine, scratch)
        )


class ChangingFrames(FakeFrames):
    def __init__(self, source: Path) -> None:
        super().__init__()
        self.source = source

    async def extract(self, media, interval, count, output, context):
        result = await super().extract(media, interval, count, output, context)
        self.source.write_bytes(b"changed during extraction")
        return result


def test_cli_refuses_a_source_changed_during_extraction_and_cleans_up(tmp_path) -> None:
    project, bundles = seed_tasks(tmp_path / "artifacts", 1)
    frames, engine = ChangingFrames(bundles[0].asset.source_path), FakeEngine()
    with pytest.raises(AppError) as changed:
        asyncio.run(build_run_ocr_report(project, "run-000", frames, engine, tmp_path / "scratch"))
    assert changed.value.code == "input.source_changed" and engine.seen == []
    assert frames.output is not None and not frames.output.exists()


def test_cli_samples_every_nth_frame_and_reports_language_as_windows_spells_it(tmp_path):
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    report = asyncio.run(
        build_run_ocr_report(
            project,
            "run-000",
            FakeFrames(),
            FakeEngine(),
            tmp_path / "scratch",
            every=2,
            languages=("ZH-hans-cn",),
        )
    )
    assert report["every"] == 2 and report["summary"]["frames"] == 1
    assert report["engine"]["usedLanguages"] == ["zh-Hans-CN"]
    assert report["engine"]["unavailableLanguages"] == []


def test_cli_refuses_shifted_frames_bad_options_and_missing_languages(tmp_path) -> None:
    project, _ = seed_tasks(tmp_path / "artifacts", 1)
    scratch = tmp_path / "scratch"
    with pytest.raises(AppError, match="临时画面目录"):
        asyncio.run(
            build_run_ocr_report(project, "run-000", FakeFrames(), FakeEngine(), project / "s")
        )
    with pytest.raises(AppError, match="不重复"):
        asyncio.run(
            build_run_ocr_report(
                project,
                "run-000",
                FakeFrames(),
                FakeEngine(),
                scratch,
                languages=("en-US", "EN-us"),
            )
        )
    shifted = FakeFrames(shift=1)
    with pytest.raises(AppError) as refused:
        asyncio.run(build_run_ocr_report(project, "run-000", shifted, FakeEngine(), scratch))
    assert refused.value.code == "media.frame_mapping"
    assert shifted.output is not None and not shifted.output.exists()
    for every in (0, 1001):
        with pytest.raises(AppError, match="--every"):
            asyncio.run(
                build_run_ocr_report(
                    project, "run-000", FakeFrames(), FakeEngine(), scratch, every=every
                )
            )
    with pytest.raises(AppError) as missing:
        asyncio.run(
            build_run_ocr_report(
                project, "run-000", FakeFrames(), FakeEngine(available=()), scratch
            )
        )
    assert missing.value.code == "environment.ocr_unavailable"


def test_cli_command_is_registered() -> None:
    assert main(["ocr-frames", "--help"]) == 0


def make_text_video(destination: Path) -> None:
    graph = (
        "color=c=white:s=640x360:r=25:d=2,"
        "drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':text='GAME SCIENCE':"
        "fontsize=48:x=40:y=60:fontcolor=black,"
        "drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':text='钟馗斩妖':"
        "fontsize=56:x=40:y=180:fontcolor=black"
    )
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            graph,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@pytest.mark.skipif(
    sys.platform != "win32"
    or not FFMPEG.is_file()
    or not Path("C:/Windows/Fonts/msyh.ttc").is_file(),
    reason="needs Windows, its Chinese font and the project-local FFmpeg",
)
def test_real_tools_reproduce_saved_instants_and_read_known_text(tmp_path) -> None:
    source = tmp_path / "text.mp4"
    make_text_video(source)

    async def run():
        context = CancellationContext("test-ocr", 180)
        processor = FfmpegMediaProcessor(ROOT)
        bundle = await processor.preprocess(
            source, tmp_path / "prepared", SamplingParameters(Fraction(1, 2), 160, 100), context
        )
        saved = [(item.evidence_id, item.source_time.time_us) for item in bundle.images]
        extracted = await FfmpegFullResolutionFrames(ROOT).extract(
            bundle.asset, Fraction(1, 2), len(saved), tmp_path / "full", context
        )
        paired = matched_frames(bundle.asset, saved, extracted)
        engine = WindowsOcrEngine(tmp_path / "scratch")
        batch = await engine.recognize([paired[0][2]], ("zh-Hans-CN", "en-US"), context)
        return saved, paired, batch

    saved, paired, batch = asyncio.run(run())
    assert len(paired) == len(saved) >= 3
    texts = {normalize_text(item.text) for reading in batch.readings for item in reading.lines}
    if "zh-Hans-CN" in batch.available_languages:
        assert any("钟馗" in text for text in texts)
    if "en-US" in batch.available_languages:
        assert any("SCIENCE" in text.upper() for text in texts)
    assert not batch.failed
