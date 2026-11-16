"""E13：只读词结果 HTTP 投影，只读已核对的 sidecar，读取时不跑识别。"""

from __future__ import annotations

import asyncio
import json
import shutil
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_analyze import configuration
from test_asr_audio import DURATION_US, OFFICIAL_SAMPLE_RATE, SAMPLES, TRANSFORM, _hash, _write_wav
from test_asr_models import MODEL, REVISION
from test_asr_words_cli import FakeWords, _seed
from test_inspection_http import get, workspace

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.media import SamplingParameters
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
)
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words import (
    load_asr_words_projection,
    transcribe_project_words,
)
from gamingcreator.infrastructure.asr_words_sidecar import (
    WORDS_FILENAME,
    asr_words_directory,
    publish_asr_words_sidecar,
)
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def _query(project_id: str, run_id: str, result_hash: str) -> str:
    return "/api/asr-words?" + urlencode(
        {"projectId": project_id, "runId": run_id, "resultHash": result_hash}
    )


def _publish(repository: Path, project: Path, bundle: MediaPreprocessingResult, words=None):
    return asyncio.run(
        transcribe_project_words(
            project,
            "run-1",
            MODEL,
            repository,
            provider=FakeWords(words),
        )
    )


def _other_project(repository: Path) -> tuple[Path, MediaPreprocessingResult]:
    project = repository / "other"
    source = repository / "other-source.mp4"
    source.write_bytes(b"other-source-bytes")
    media_dir = project / "runs" / "run-1" / "media"
    media_dir.mkdir(parents=True)
    audio_path = media_dir / "audio.wav"
    _write_wav(audio_path)
    clock = AudioEvidence(
        "audio",
        audio_path,
        _hash(audio_path),
        OFFICIAL_SAMPLE_RATE,
        SAMPLES,
        (AudioFrameMapping(0, SAMPLES, 0, Fraction(1, OFFICIAL_SAMPLE_RATE)),),
    )
    asset = MediaAsset(
        "media",
        source,
        _hash(source),
        (
            MediaStream(0, "video", Fraction(1, OFFICIAL_SAMPLE_RATE), 0, SAMPLES),
            MediaStream(1, "audio", Fraction(1, OFFICIAL_SAMPLE_RATE), 0, SAMPLES),
        ),
        Fraction(0),
        DURATION_US,
        "fake-probe",
    )
    bundle = MediaPreprocessingResult(
        asset,
        (),
        clock,
        media_dir / "media-manifest.json",
        TRANSFORM,
        "fake-processor",
    )
    write_manifest(bundle, SamplingParameters(max_width=512, max_frames=5))

    async def seed() -> None:
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-1", asset, configuration())
            await store.begin_stage("run-1", "media", asset.sha256)
            await store.persist_media_bundle("run-1", bundle)
        finally:
            await store.close()

    asyncio.run(seed())
    return project, bundle


def test_http_returns_verified_sidecar_bound_to_project_run_and_hash(tmp_path):
    repository, project, bundle = _seed(tmp_path)
    summary = _publish(repository, project, bundle)
    with workspace(tmp_path / "repo") as base:
        status, _, body = get(base, _query("project", "run-1", summary.result_hash))
    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert payload["schemaVersion"] == "asr-words-http-v1"
    assert payload["readOnly"] is True
    assert payload["runId"] == "run-1"
    assert payload["mediaId"] == bundle.asset.media_id
    assert payload["model"] == MODEL
    assert payload["revision"] == REVISION
    assert payload["resultHash"] == summary.result_hash
    assert payload["sourceSha256"] == bundle.asset.sha256
    assert payload["audioSha256"] == bundle.audio.sha256
    assert payload["words"] == [
        {"startUs": 100_000, "endUs": 400_000, "text": "你好"},
    ]


def test_http_rejects_cross_project_wrong_source_and_bad_hash(tmp_path):
    repository, project, bundle = _seed(tmp_path)
    summary = _publish(repository, project, bundle)
    other, _ = _other_project(repository)
    source_dir = asr_words_directory(project, "run-1", summary.result_hash)
    copied = asr_words_directory(other, "run-1", summary.result_hash)
    copied.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, copied)
    with workspace(repository) as base:
        foreign_status, _, foreign_body = get(base, _query("other", "run-1", summary.result_hash))
        missing_status, _, missing_body = get(base, _query("project", "run-1", "a" * 64))
        tampered = json.loads((source_dir / WORDS_FILENAME).read_text(encoding="utf-8"))
        tampered["words"][0]["text"] = "被改过"
        (source_dir / WORDS_FILENAME).write_text(
            json.dumps(tampered, ensure_ascii=False), encoding="utf-8"
        )
        bad_status, _, bad_body = get(base, _query("project", "run-1", summary.result_hash))
    assert foreign_status == 404
    assert json.loads(foreign_body.decode("utf-8"))["code"] == "asr.words_not_found"
    assert json.loads(foreign_body.decode("utf-8"))["message"] == "找不到这份已核对的词级结果。"
    assert missing_status == 404
    assert json.loads(missing_body.decode("utf-8"))["code"] == "asr.words_not_found"
    assert bad_status == 400
    assert json.loads(bad_body.decode("utf-8"))["code"] == "asr.words_damaged"
    assert (
        json.loads(bad_body.decode("utf-8"))["message"]
        == "逐词结果已损坏，不能使用，也不会覆盖或重新生成。"
    )


def test_http_does_not_pick_newest_or_start_asr(tmp_path, monkeypatch):
    repository, project, bundle = _seed(tmp_path)
    first = _publish(repository, project, bundle)
    later_words = (
        AsrWord(bundle.asset.media_id, SourceRange(200_000, 500_000, DURATION_US), "后来"),
    )
    later = publish_asr_words_sidecar(
        project,
        run_id="run-1",
        media_id=bundle.asset.media_id,
        source_sha256=bundle.asset.sha256,
        audio_sha256=bundle.audio.sha256,
        clock=bundle.audio,
        asset=bundle.asset,
        model=MODEL,
        revision=REVISION,
        words=later_words,
    )
    later_hash = later.name

    def boom(*_args, **_kwargs):
        raise AssertionError("读取词结果时不能再跑识别或恢复任务")

    monkeypatch.setattr("gamingcreator.infrastructure.asr_words.transcribe_project_words", boom)
    monkeypatch.setattr(
        "gamingcreator.infrastructure.local_asr.LocalAsrProvider.transcribe_words", boom
    )
    with workspace(repository) as base:
        first_status, _, first_body = get(base, _query("project", "run-1", first.result_hash))
        later_status, _, later_body = get(base, _query("project", "run-1", later_hash))
        missing_run_status, _, missing_run_body = get(
            base, _query("project", "run-missing", first.result_hash)
        )
        extra_status, _, extra_body = get(
            base,
            _query("project", "run-1", first.result_hash) + "&latest=1",
        )
    first_payload = json.loads(first_body.decode("utf-8"))
    later_payload = json.loads(later_body.decode("utf-8"))
    assert first_status == 200
    assert first_payload["resultHash"] == first.result_hash
    assert first_payload["words"][0]["text"] == "你好"
    assert later_status == 200
    assert later_payload["resultHash"] == later_hash
    assert later_payload["words"][0]["text"] == "后来"
    assert first.result_hash != later_hash
    assert missing_run_status == 404
    assert json.loads(missing_run_body.decode("utf-8"))["code"] == "asr.run_missing"
    assert json.loads(missing_run_body.decode("utf-8"))["message"] == "找不到这个任务的已准备音频。"
    assert extra_status == 400
    assert json.loads(extra_body.decode("utf-8"))["code"] == "input.request"


def test_projection_loader_rejects_missing_run_without_transcribing(tmp_path, monkeypatch):
    repository, project, bundle = _seed(tmp_path)
    summary = _publish(repository, project, bundle)

    def boom(*_args, **_kwargs):
        raise AssertionError("读取词结果时不能再跑识别或恢复任务")

    monkeypatch.setattr("gamingcreator.infrastructure.asr_words.transcribe_project_words", boom)
    with pytest.raises(AppError) as error:
        asyncio.run(load_asr_words_projection(project, "run-missing", summary.result_hash))
    assert error.value.code == "asr.run_missing"
    assert error.value.exit_code is ExitCode.INPUT
    payload = asyncio.run(load_asr_words_projection(project, "run-1", summary.result_hash))
    assert payload["resultHash"] == summary.result_hash
    assert payload["readOnly"] is True
