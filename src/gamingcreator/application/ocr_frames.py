"""Read-only on-screen text report for one saved run; never feeds analysis or ranking."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Protocol

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import StoredRun
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.ocr_frames import (
    OcrReading,
    likely_text,
    normalize_text,
    recurring_texts,
)

OCR_REPORT_VERSION = "ocr-frames-v1"
DEFAULT_LANGUAGES = ("zh-Hans-CN", "en-US")


@dataclass(frozen=True, slots=True)
class OcrEngineIdentity:
    engine: str
    platform: str


@dataclass(frozen=True, slots=True)
class OcrBatch:
    available_languages: tuple[str, ...]
    readings: tuple[OcrReading, ...]
    failed: frozenset[int]


class OcrEngine(Protocol):
    def identity(self) -> OcrEngineIdentity: ...

    async def recognize(
        self, images: Sequence[Path], languages: Sequence[str], context: CancellationContext
    ) -> OcrBatch: ...


class FullResolutionFrames(Protocol):
    async def extract(
        self,
        asset: MediaAsset,
        interval_seconds: Fraction,
        count: int,
        output: Path,
        context: CancellationContext,
    ) -> tuple[tuple[int, Fraction, Path], ...]: ...


def matched_frames(
    asset: MediaAsset,
    saved: Sequence[tuple[str, int]],
    extracted: Sequence[tuple[int, Fraction, Path]],
) -> tuple[tuple[str, int, Path], ...]:
    """Pair re-extracted images with saved evidence; any instant difference refuses all.

    ``saved`` is (evidence id, source microseconds) in source order. The re-extraction must
    reproduce exactly the same instants, so each image provably shows the saved frame's moment.
    """
    ordered = sorted(saved, key=lambda item: (item[1], item[0]))
    try:
        instants = [asset.instant(pts, time_base).time_us for pts, time_base, _ in extracted]
    except ValueError:  # an extracted frame outside the media cannot be a saved frame
        instants = []
    if instants != [time for _, time in ordered]:
        raise AppError(
            "media.frame_mapping",
            "重新取出的原分辨率帧与保存的取帧时刻不一致，未识别文字。",
            ExitCode.INPUT,
        )
    return tuple(
        (evidence, time, image)
        for (evidence, time), (_, _, image) in zip(ordered, extracted, strict=True)
    )


def build_ocr_report(
    run: StoredRun,
    frames: Sequence[tuple[str, int]],
    batch: OcrBatch,
    identity: OcrEngineIdentity,
    languages: Sequence[str],
    *,
    every: int,
    seconds: dict[str, float],
) -> dict[str, object]:
    """Per-frame readings on the source clock, recurring texts and honest counts.

    ``frames`` are the recognized (evidence id, source microseconds) in request order.
    Frames the engine could not read stay "failed"; frames without text stay empty.
    """
    # A frame the engine failed on keeps no text, even if one language read it first.
    by_frame: dict[int, list[OcrReading]] = {}
    for reading in batch.readings:
        if reading.index not in batch.failed:
            by_frame.setdefault(reading.index, []).append(reading)
    rows: list[dict[str, object]] = []
    texts: list[tuple[int, str]] = []
    likely_frames = 0
    for index, (evidence_id, time_us) in enumerate(frames):
        readings = sorted(by_frame.get(index, []), key=lambda item: item.language)
        lines = [
            {
                "language": reading.language,
                "text": normalize_text(line.text),
                "likelyText": likely_text(normalize_text(line.text)),
                "words": [
                    {
                        "text": word.text,
                        "x": word.x,
                        "y": word.y,
                        "width": word.width,
                        "height": word.height,
                    }
                    for word in line.words
                ],
            }
            for reading in readings
            for line in reading.lines
            if normalize_text(line.text)
        ]
        texts.extend((time_us, str(line["text"])) for line in lines)
        likely_frames += any(line["likelyText"] is True for line in lines)
        status = (
            "failed"
            if index in batch.failed
            else "unavailable"
            if not readings
            else "text"
            if lines
            else "empty"
        )
        rows.append(
            {
                "evidenceId": evidence_id,
                "timeUs": time_us,
                "status": status,
                "imageWidth": readings[0].width if readings else None,
                "imageHeight": readings[0].height if readings else None,
                "lines": lines,
            }
        )
    spans = recurring_texts(texts)
    used = [language for language in languages if language in batch.available_languages]
    return {
        "schemaVersion": OCR_REPORT_VERSION,
        "runId": run.run_id,
        "runStatus": str(run.status),
        "mediaId": run.asset.media_id,
        "sourceName": run.asset.source_path.name,
        "sourceSha256": run.asset.sha256,
        "durationUs": run.asset.duration_us,
        "engine": {
            "name": identity.engine,
            "platform": identity.platform,
            "requestedLanguages": list(languages),
            "availableLanguages": list(batch.available_languages),
            "usedLanguages": used,
            "unavailableLanguages": [item for item in languages if item not in used],
            "imageSource": "native-resolution re-extraction at saved frame instants",
        },
        "every": every,
        "seconds": seconds,
        "summary": {
            "frames": len(rows),
            "framesWithText": sum(1 for row in rows if row["status"] == "text"),
            "framesWithLikelyText": likely_frames,
            "emptyFrames": sum(1 for row in rows if row["status"] == "empty"),
            "failedFrames": sum(1 for row in rows if row["status"] == "failed"),
        },
        "recurringTexts": [
            {
                "text": span.text,
                "firstUs": span.first_us,
                "lastUs": span.last_us,
                "frames": span.frames,
            }
            for span in spans
        ],
        "frames": rows,
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
        "notes": (
            "Windows自带文字识别对原片原分辨率帧的结果，未经人工核对；风格化标题常读不出，"
            "也会有零碎误读（likelyText=false）。只读，不进入分析、检索排名或验收。"
        ),
    }


def ocr_summary(report: dict[str, object]) -> list[str]:
    """Plain-language lines for the console."""
    summary, engine, spans = report["summary"], report["engine"], report["recurringTexts"]
    assert isinstance(summary, dict) and isinstance(engine, dict) and isinstance(spans, list)
    lines = [
        f"素材：{report['sourceName']}；识别 {summary['frames']} 帧"
        f"（语言：{'、'.join(engine['usedLanguages']) or '无'}）",
        f"有文字 {summary['framesWithText']} 帧，其中像真实文字的 {summary['framesWithLikelyText']} 帧；"
        f"空白 {summary['emptyFrames']} 帧，读取失败 {summary['failedFrames']} 帧",
    ]
    if engine["unavailableLanguages"]:
        lines.append(f"本机没有这些识别语言，未使用：{'、'.join(engine['unavailableLanguages'])}")
    for span in spans[:8]:
        lines.append(
            f"  “{span['text']}” 出现 {span['frames']} 帧，"
            f"{span['firstUs'] / 1_000_000:.1f}–{span['lastUs'] / 1_000_000:.1f}秒"
        )
    lines.append("这是本机文字识别结果，未经人工核对；不改变分析、排名或验收。")
    return lines
