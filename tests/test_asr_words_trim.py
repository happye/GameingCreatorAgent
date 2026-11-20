"""E17：裁剪或删除镜头后只保留镜头内的词，原证据和段级转录不被改写。"""

from __future__ import annotations

import asyncio
import hashlib
from fractions import Fraction
from pathlib import Path

from test_asr_models import MODEL
from test_asr_word_timing import clip
from test_asr_words_cli import FakeWords, _seed

from gamingcreator.application.asr_word_timing import AsrWord, map_words_to_edit_timeline
from gamingcreator.application.creation_subtitles import present_subtitles
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words import load_trusted_asr_words, transcribe_project_words


def _words() -> tuple[AsrWord, ...]:
    return (
        AsrWord("a", SourceRange(0, 400_000, 10_000_000), "前"),
        AsrWord("a", SourceRange(400_000, 800_000, 10_000_000), "中"),
        AsrWord("a", SourceRange(800_000, 1_200_000, 10_000_000), "后"),
        AsrWord("a", SourceRange(2_000_000, 2_400_000, 10_000_000), "更后"),
    )


def _texts(cues) -> list[str]:
    return [cue.text for cue in cues]


def _fingerprint(paths: list[Path]) -> dict[str, str]:
    """只核字节，不把 SQLite 只读打开时改动 shm 时间戳当成改写。"""
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.exists()
    }


def test_trim_drops_words_outside_the_clip_and_clips_overlap():
    words = _words()
    # 原镜头 0–1.2s 裁到 0.4–0.8s，只留下“中”；跨边界的词只保留交叠部分。
    trimmed = RenderPlan((clip(400_000, 800_000, 12), clip(2_000_000, 3_000_000, 30)), 30)
    overlapping = (
        AsrWord("a", SourceRange(300_000, 500_000, 10_000_000), "边"),
        *words,
    )
    cues = map_words_to_edit_timeline(trimmed, overlapping)
    assert _texts(cues) == ["边", "中", "更后"]
    edge, mid, later = cues
    assert edge.start == Fraction(0)
    assert edge.end == Fraction(1, 10)
    assert mid.start == Fraction(0)
    assert mid.end == Fraction(2, 5)
    assert later.start == Fraction(2, 5)
    assert later.end == Fraction(4, 5)
    # 删除第一段后，第二段顶到输出起点，镜头外的词不能跟过来。
    deleted = RenderPlan((clip(2_000_000, 3_000_000, 30),), 30)
    remaining = map_words_to_edit_timeline(deleted, words)
    assert _texts(remaining) == ["更后"]
    assert remaining[0].start == Fraction(0)
    assert remaining[0].end == Fraction(2, 5)
    full = map_words_to_edit_timeline(
        RenderPlan((clip(0, 1_200_000, 36), clip(2_000_000, 3_000_000, 30)), 30),
        words,
    )
    assert _texts(full) == ["前", "中", "后", "更后"]
    segment = SubtitleCue(Fraction(0), Fraction(2), "整段台词", "asr", 0)
    presented = present_subtitles(
        (segment,), words=overlapping, sidecar_available=True, plan=trimmed
    )
    assert presented.source == "words"
    assert presented.cues == cues


def test_mapping_does_not_change_evidence_or_transcript_bytes(tmp_path):
    repository, project, bundle = _seed(tmp_path)
    old_transcript = project / "runs" / "run-1" / "result.json"
    old_transcript.write_bytes('{"schemaVersion":"transcript-v1","text":"旧句段级转录"}'.encode())
    summary = asyncio.run(
        transcribe_project_words(project, "run-1", MODEL, repository, provider=FakeWords())
    )
    sidecar = Path(summary.result_directory) / "words.json"
    receipt = Path(summary.result_directory) / "receipt.json"
    evidence = project / "runs" / "run-1" / "media" / "audio.wav"
    manifest = project / "runs" / "run-1" / "media" / "media-manifest.json"
    source = repository / "source.mp4"
    database = project / "timeline.sqlite3"
    tracked = [
        old_transcript,
        sidecar,
        receipt,
        evidence,
        manifest,
        source,
        database,
        Path(str(database) + "-wal"),
        Path(str(database) + "-shm"),
    ]
    existed = {path for path in tracked if path.exists()}
    before = _fingerprint(tracked)

    trusted = asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash))
    assert trusted is not None
    # FakeWords 的词在 0.1–0.4s，镜头只留到 0.05s，映射不到词，退回段级字幕。
    trimmed = RenderPlan(
        (RenderClip(bundle.asset, SourceRange(0, 50_000, bundle.asset.duration_us), 2),),
        30,
    )
    segment = SubtitleCue(Fraction(0), Fraction(1), "旧句段级转录", "asr", 0)
    presentation = present_subtitles(
        (segment,), words=trusted, sidecar_available=True, plan=trimmed
    )
    assert presentation.source == "segment"
    assert presentation.cues == (segment,)
    assert _fingerprint(tracked) == before
    assert {path for path in tracked if path.exists()} == existed
