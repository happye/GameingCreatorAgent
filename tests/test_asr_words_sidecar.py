"""独立带 hash 的词级 sidecar：身份齐全，hash 在旁边回执，不改旧 ASR 记录。"""

import hashlib
import json
import threading
import wave
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import pytest

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.providers import InvocationMetadata, ProviderUsage
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import AudioEvidence, AudioFrameMapping, MediaAsset, MediaStream
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words_sidecar import (
    SCHEMA_VERSION,
    clock_digest,
    load_reusable_asr_words_sidecar,
    publish_asr_words_sidecar,
)


def _source_and_clock(tmp_path: Path) -> tuple[MediaAsset, AudioEvidence]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"synthetic source identity")
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(10)
        output.writeframes(b"\\x00\\x00" * 10)
    asset = MediaAsset(
        "media",
        source,
        hashlib.sha256(source.read_bytes()).hexdigest(),
        (
            MediaStream(0, "video", Fraction(1, 10), 0, 20),
            MediaStream(1, "audio", Fraction(1, 10), 0, 20),
        ),
        Fraction(0),
        2_000_000,
        "fake-probe",
    )
    clock = AudioEvidence(
        "audio",
        audio,
        hashlib.sha256(audio.read_bytes()).hexdigest(),
        10,
        10,
        (AudioFrameMapping(0, 3, 0, Fraction(1, 10)), AudioFrameMapping(3, 7, 5, Fraction(1, 10))),
    )
    return asset, clock


def _publish(project: Path, asset: MediaAsset, clock: AudioEvidence, **extra):
    words = extra.pop(
        "words",
        (AsrWord(asset.media_id, SourceRange(100000, 1000000, 2_000_000), "测试"),),
    )
    metadata = extra.pop(
        "metadata",
        InvocationMetadata(
            provider="local-asr",
            requested_model="Systran/faster-whisper-tiny",
            actual_model="Systran/faster-whisper-tiny",
            model_revision="d90ca5fe260221311c53c58e660288d3deb8d356",
            prompt_version="none",
            schema_version="transcript-v1",
            attempt=1,
            usage=ProviderUsage(),
            elapsed_ms=12,
        ),
    )
    return publish_asr_words_sidecar(
        project,
        run_id=extra.pop("run_id", "run-1"),
        media_id=asset.media_id,
        source_sha256=asset.sha256,
        audio_sha256=clock.sha256,
        clock=clock,
        asset=asset,
        model=extra.pop("model", "Systran/faster-whisper-tiny"),
        revision=extra.pop("revision", "d90ca5fe260221311c53c58e660288d3deb8d356"),
        words=words,
        metadata=metadata,
        **extra,
    )


def test_sidecar_schema_identities_and_hash_live_in_adjacent_receipt(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    directory = _publish(project, asset, clock)
    words_path = directory / "words.json"
    receipt_path = directory / "receipt.json"
    payload = words_path.read_bytes()
    document = json.loads(payload)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == SCHEMA_VERSION == "asr-words-v1"
    assert list(document) == [
        "schemaVersion",
        "runId",
        "mediaId",
        "sourceSha256",
        "audioSha256",
        "clockDigest",
        "model",
        "revision",
        "words",
    ]
    assert document["runId"] == "run-1"
    assert document["mediaId"] == asset.media_id
    assert document["sourceSha256"] == asset.sha256
    assert document["audioSha256"] == clock.sha256
    assert document["clockDigest"] == clock_digest(clock, asset)
    assert document["model"] == "Systran/faster-whisper-tiny"
    assert document["revision"] == "d90ca5fe260221311c53c58e660288d3deb8d356"
    assert document["words"] == [{"startUs": 100000, "endUs": 1000000, "text": "测试"}]
    assert "wordsSha256" not in document
    assert "sha256" not in document
    assert receipt["schemaVersion"] == "asr-words-receipt-v1"
    assert receipt["wordsSha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["execution"]["provider"] == "local-asr"
    assert receipt["execution"]["elapsedMs"] == 12
    assert directory.name == receipt["wordsSha256"]
    shifted = AudioEvidence(
        clock.evidence_id,
        clock.path,
        clock.sha256,
        clock.sample_rate,
        clock.sample_count,
        (AudioFrameMapping(0, 3, 1, Fraction(1, 10)), AudioFrameMapping(3, 7, 6, Fraction(1, 10))),
    )
    assert clock_digest(shifted, asset) != document["clockDigest"]


def test_sidecar_does_not_add_fields_or_rewrite_old_asr_records(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    run = project / "runs" / "run-1"
    run.mkdir(parents=True)
    old_result = run / "result.json"
    old_receipt = run / "receipt.json"
    old_result.write_bytes(
        '{"schemaVersion":"transcript-v1","transcripts":[{"text":"旧句"}]}\n'.encode()
    )
    old_receipt.write_bytes(b'{"schemaVersion":"asr-receipt-v1","files":{"result.json":"abc"}}\n')
    before_result = old_result.read_bytes()
    before_receipt = old_receipt.read_bytes()
    directory = _publish(project, asset, clock)
    assert old_result.read_bytes() == before_result
    assert old_receipt.read_bytes() == before_receipt
    assert b"asr-words-v1" not in before_receipt
    assert directory != run
    assert directory.parent == run / "asr-words"


def test_existing_sidecar_is_not_overwritten(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    directory = _publish(project, asset, clock)
    original = (directory / "words.json").read_bytes()
    receipt = (directory / "receipt.json").read_bytes()
    reused = _publish(project, asset, clock)
    assert reused == directory
    assert (directory / "words.json").read_bytes() == original
    assert (directory / "receipt.json").read_bytes() == receipt


def _asr_words_root(project: Path) -> Path:
    return project / "runs" / "run-1" / "asr-words"


def test_failed_publish_leaves_no_visible_partial(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    from gamingcreator.infrastructure import asr_words_sidecar as sidecar

    real = sidecar._write_published_file
    calls = {"count": 0}

    def boom(path, payload):
        calls["count"] += 1
        if calls["count"] >= 2:
            raise OSError("simulated failure")
        return real(path, payload)

    with patch("gamingcreator.infrastructure.asr_words_sidecar._write_published_file", boom):
        with pytest.raises(OSError, match="simulated failure"):
            _publish(project, asset, clock)
    root = _asr_words_root(project)
    leftovers = list(root.rglob("*.json")) if root.exists() else []
    assert leftovers == []
    if root.exists():
        assert [path.name for path in root.iterdir() if path.name.startswith(".tmp-")] == []


def test_concurrent_same_output_does_not_overwrite(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    succeeded: list[Path] = []
    errors: list[AppError] = []

    def worker() -> None:
        try:
            succeeded.append(_publish(project, asset, clock))
        except AppError as error:
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(succeeded) == 1
    assert len(errors) == 1
    assert errors[0].code in {"asr.words_exists", "storage.writer_busy"}
    words = succeeded[0] / "words.json"
    receipt = json.loads((succeeded[0] / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["wordsSha256"] == hashlib.sha256(words.read_bytes()).hexdigest()
    assert (succeeded[0] / "receipt.json").is_file()


def _load(project, asset, clock, result_hash, **extra):
    return load_reusable_asr_words_sidecar(
        project,
        run_id=extra.pop("run_id", "run-1"),
        media_id=extra.pop("media_id", asset.media_id),
        source_sha256=extra.pop("source_sha256", asset.sha256),
        audio_sha256=extra.pop("audio_sha256", clock.sha256),
        clock=clock,
        asset=asset,
        model=extra.pop("model", "Systran/faster-whisper-tiny"),
        revision=extra.pop("revision", "d90ca5fe260221311c53c58e660288d3deb8d356"),
        result_hash=result_hash,
        **extra,
    )


def test_reuse_requires_matching_identity_and_whole_hash(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    first = _publish(project, asset, clock)
    original = (first / "words.json").read_bytes()
    digest = first.name
    assert _load(project, asset, clock, digest) == first
    assert _load(project, asset, clock, digest, model="other-model") is None
    assert _load(project, asset, clock, digest, revision="0" * 40) is None
    assert _load(project, asset, clock, digest, source_sha256="b" * 64) is None
    shifted = AudioEvidence(
        clock.evidence_id,
        clock.path,
        clock.sha256,
        clock.sample_rate,
        clock.sample_count,
        (AudioFrameMapping(0, 3, 1, Fraction(1, 10)), AudioFrameMapping(3, 7, 6, Fraction(1, 10))),
    )
    assert _load(project, asset, shifted, digest) is None
    assert _load(project, asset, clock, "c" * 64) is None
    other = _publish(project, asset, clock, model="other-model")
    assert other != first
    assert _load(project, asset, clock, digest) == first
    assert _load(project, asset, clock, other.name, model="other-model") == other
    assert _load(project, asset, clock, other.name) is None
    assert (first / "words.json").read_bytes() == original


def test_damaged_sidecar_is_not_treated_as_hit_or_overwritten(tmp_path):
    asset, clock = _source_and_clock(tmp_path)
    project = tmp_path / "project"
    directory = _publish(project, asset, clock)
    words = directory / "words.json"
    before = words.read_bytes()
    words.write_bytes(before + b" ")
    assert _load(project, asset, clock, directory.name) is None
    with pytest.raises(AppError, match="不会覆盖"):
        _publish(project, asset, clock)
    assert words.read_bytes() == before + b" "
