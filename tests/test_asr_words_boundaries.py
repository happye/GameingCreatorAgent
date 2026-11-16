"""E23：错的模型、时钟、校对码，以及原片改字节、取消、缺模型，都不能当成成功；旧库、证据和账本字节保持不变。"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from test_asr_models import MODEL
from test_asr_words_cli import FakeWords, _seed

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.asr_words import (
    load_asr_words_projection,
    load_trusted_asr_words,
    transcribe_project_words,
)


def _fingerprint(paths: list[Path]) -> dict[str, str]:
    """只核字节，不把 SQLite 只读打开时改动 shm 时间戳当成改写。"""
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.exists()
    }


def _official_paths(repository: Path, project: Path, result_directory: Path) -> list[Path]:
    media = project / "runs" / "run-1" / "media"
    db = project / "timeline.sqlite3"
    return [
        project / "runs" / "run-1" / "result.json",
        result_directory / "words.json",
        result_directory / "receipt.json",
        media / "audio.wav",
        media / "media-manifest.json",
        repository / "source.mp4",
        db,
        Path(str(db) + "-wal"),
        Path(str(db) + "-shm"),
        repository / "entitlement-usage.json",
        project / ".static-observation-generation" / "ledger" / "generation-ledger.sqlite3",
    ]


def _plant_ledgers_and_transcript(repository: Path, project: Path) -> None:
    result = project / "runs" / "run-1" / "result.json"
    result.write_text('{"schemaVersion":"transcript-v1","text":"旧段级结果"}\n', encoding="utf-8")
    (repository / "entitlement-usage.json").write_text(
        '{"schemaVersion":"entitlement-usage-v1","protected":true}\n', encoding="utf-8"
    )
    ledger = project / ".static-observation-generation" / "ledger"
    ledger.mkdir(parents=True)
    (ledger / "generation-ledger.sqlite3").write_bytes(b"protected-generation-ledger")


def test_rejected_attempts_do_not_fake_success_or_rewrite_official_bytes(tmp_path):
    repository, project, _bundle = _seed(tmp_path)
    _plant_ledgers_and_transcript(repository, project)
    summary = asyncio.run(
        transcribe_project_words(project, "run-1", MODEL, repository, provider=FakeWords())
    )
    paths = _official_paths(repository, project, summary.result_directory)
    before = _fingerprint(paths)
    words_before = (summary.result_directory / "words.json").read_bytes()
    source = repository / "source.mp4"
    audio = project / "runs" / "run-1" / "media" / "audio.wav"
    source_before = source.read_bytes()
    audio_before = audio.read_bytes()

    missing = FakeWords()
    with pytest.raises(AppError) as missing_model:
        asyncio.run(
            transcribe_project_words(
                project, "run-1", "not-installed", repository, provider=missing
            )
        )
    assert missing_model.value.code == "environment.asr"
    assert missing_model.value.message == "本机没有安装这个识别模型。"
    assert missing.calls == 0
    assert _fingerprint(paths) == before

    cancelled = FakeWords()
    context = CancellationContext("run-1", 5)
    context.cancelled.set()
    with pytest.raises(AppError) as cancelled_error:
        asyncio.run(
            transcribe_project_words(
                project, "run-1", MODEL, repository, provider=cancelled, context=context
            )
        )
    assert cancelled_error.value.code == "asr.cancelled"
    assert cancelled_error.value.message == "逐词识别已取消。"
    assert cancelled_error.value.exit_code == ExitCode.CANCELLED
    assert cancelled.calls == 0
    assert _fingerprint(paths) == before

    assert asyncio.run(load_trusted_asr_words(project, "run-1", "c" * 64)) is None
    with pytest.raises(AppError) as bad_hash:
        asyncio.run(load_asr_words_projection(project, "run-1", "c" * 64))
    assert bad_hash.value.code == "asr.words_not_found"
    assert _fingerprint(paths) == before
    trusted = asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash))
    assert trusted is not None
    assert _fingerprint(paths) == before

    source.write_bytes(source_before + b"-tampered")
    after_source = _fingerprint(paths)
    mutated = FakeWords()
    with pytest.raises(AppError) as source_error:
        asyncio.run(transcribe_project_words(project, "run-1", MODEL, repository, provider=mutated))
    assert source_error.value.code in {"asr.input_integrity", "storage.integrity"}
    assert mutated.calls == 0
    assert asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash)) is None
    with pytest.raises(AppError) as source_projection:
        asyncio.run(load_asr_words_projection(project, "run-1", summary.result_hash))
    assert source_projection.value.code in {"asr.input_integrity", "storage.integrity"}
    assert _fingerprint(paths) == after_source
    assert (summary.result_directory / "words.json").read_bytes() == words_before

    source.write_bytes(source_before)
    assert _fingerprint(paths) == before
    assert asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash)) is not None

    audio.write_bytes(audio_before + b"x")
    after_audio = _fingerprint(paths)
    clocked = FakeWords()
    with pytest.raises(AppError) as clock_error:
        asyncio.run(transcribe_project_words(project, "run-1", MODEL, repository, provider=clocked))
    assert clock_error.value.code in {"asr.input_integrity", "storage.integrity"}
    assert clocked.calls == 0
    assert asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash)) is None
    with pytest.raises(AppError) as clock_projection:
        asyncio.run(load_asr_words_projection(project, "run-1", summary.result_hash))
    assert clock_projection.value.code in {"asr.input_integrity", "storage.integrity"}
    assert _fingerprint(paths) == after_audio

    audio.write_bytes(audio_before)
    recovered = asyncio.run(load_trusted_asr_words(project, "run-1", summary.result_hash))
    assert recovered is not None
    assert _fingerprint(paths) == before
    assert source.read_bytes() == source_before
    assert audio.read_bytes() == audio_before
    assert (summary.result_directory / "words.json").read_bytes() == words_before
