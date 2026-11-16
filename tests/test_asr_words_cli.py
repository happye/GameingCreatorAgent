"""E11：transcribe-words 命令行只接受项目、任务和模型，并返回结果位置和词数。"""

from __future__ import annotations

import asyncio
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction
from pathlib import Path

import pytest
from test_analyze import configuration
from test_asr_audio import DURATION_US, OFFICIAL_SAMPLE_RATE, SAMPLES, TRANSFORM, _hash, _write_wav
from test_asr_models import MODEL, REVISION, _write_catalog

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import (
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.cli.main import _parser, main
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
)
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.asr_words import transcribe_project_words
from gamingcreator.infrastructure.ffmpeg_media import write_manifest
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def _metadata() -> InvocationMetadata:
    return InvocationMetadata(
        provider="local-asr",
        requested_model=MODEL,
        actual_model=MODEL,
        model_revision=REVISION,
        prompt_version="none",
        schema_version="transcript-v1",
        attempt=1,
        usage=ProviderUsage(),
        elapsed_ms=12,
    )


class FakeWords:
    def __init__(self, words: tuple[AsrWord, ...] | None = None) -> None:
        self.calls = 0
        self.words = words

    async def transcribe_words(self, request, context):
        self.calls += 1
        words = self.words or (
            AsrWord(
                request.media_asset.media_id, SourceRange(100_000, 400_000, DURATION_US), "你好"
            ),
        )
        return ProviderResult(ProviderStatus.COMPLETED, words, _metadata())


def _seed(
    tmp_path: Path, *, with_audio: bool = True
) -> tuple[Path, Path, MediaPreprocessingResult]:
    repository = tmp_path / "repo"
    _write_catalog(repository)
    project = repository / "project"
    source = repository / "source.mp4"
    source.write_bytes(b"original-source-bytes")
    media_dir = project / "runs" / "run-1" / "media"
    media_dir.mkdir(parents=True)
    audio_path = media_dir / "audio.wav"
    clock = None
    if with_audio:
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
    return repository, project, bundle


def test_parser_requires_project_run_and_model_and_rejects_output_or_audio_url():
    parser = _parser()
    args = parser.parse_args(
        ["transcribe-words", "--project", "proj", "--run", "run-1", "--model", MODEL]
    )
    assert args.command == "transcribe-words"
    assert args.project == Path("proj")
    assert args.run == "run-1"
    assert args.model == MODEL
    assert not hasattr(args, "output")
    with pytest.raises(AppError) as missing_model:
        parser.parse_args(["transcribe-words", "--project", "proj", "--run", "run-1"])
    assert missing_model.value.code == "input.arguments"
    assert missing_model.value.message == "参数格式错误，请使用 --help 查看命令。"
    with pytest.raises(AppError) as unexpected_output:
        parser.parse_args(
            [
                "transcribe-words",
                "--project",
                "proj",
                "--run",
                "run-1",
                "--model",
                MODEL,
                "--output",
                "out",
            ]
        )
    assert unexpected_output.value.code == "input.arguments"
    with pytest.raises(AppError) as unexpected_url:
        parser.parse_args(
            [
                "transcribe-words",
                "--project",
                "proj",
                "--run",
                "run-1",
                "--model",
                MODEL,
                "--audio-url",
                "file://audio.wav",
            ]
        )
    assert unexpected_url.value.code == "input.arguments"
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        code = main(
            [
                "transcribe-words",
                "--project",
                "proj",
                "--run",
                "run-1",
                "--model",
                MODEL,
                "--output",
                "out",
            ]
        )
    assert code == int(ExitCode.INPUT)
    printed = json.loads(stderr.getvalue())
    assert printed["code"] == "input.arguments"
    assert printed["message"] == "参数格式错误，请使用 --help 查看命令。"


def test_analyze_command_does_not_gain_word_timing_flags():
    parser = _parser()
    with pytest.raises(AppError) as word_flag:
        parser.parse_args(["analyze", "--word-timestamps"])
    assert word_flag.value.code == "input.arguments"
    with pytest.raises(AppError) as words_flag:
        parser.parse_args(["analyze", "--transcribe-words"])
    assert words_flag.value.code == "input.arguments"


def test_cli_returns_result_path_and_word_count_and_leaves_old_transcript(tmp_path, monkeypatch):
    repository, project, bundle = _seed(tmp_path)
    old = project / "runs" / "run-1" / "result.json"
    old.write_bytes('{"schemaVersion":"transcript-v1","text":"旧句"}\n'.encode())
    before = old.read_bytes()
    provider = FakeWords()

    async def first():
        return await transcribe_project_words(
            project, "run-1", MODEL, repository, provider=provider
        )

    summary = asyncio.run(first())
    assert provider.calls == 1
    assert summary.word_count == 1
    assert summary.reused is False
    assert summary.model == MODEL
    assert summary.revision == REVISION
    assert (summary.result_directory / "words.json").is_file()
    assert (summary.result_directory / "receipt.json").is_file()
    payload = json.loads((summary.result_directory / "words.json").read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == "asr-words-v1"
    assert payload["words"][0]["text"] == "你好"
    first_words = (summary.result_directory / "words.json").read_bytes()
    assert old.read_bytes() == before

    async def second():
        return await transcribe_project_words(
            project, "run-1", MODEL, repository, provider=provider
        )

    reused = asyncio.run(second())
    assert provider.calls == 2
    assert reused.reused is True
    assert reused.result_hash == summary.result_hash
    assert reused.result_directory == summary.result_directory
    assert reused.word_count == 1
    assert (summary.result_directory / "words.json").read_bytes() == first_words

    class FakeProvider:
        def __init__(self, repo, settings):
            assert settings.model_name == MODEL
            assert repo == repository

        async def transcribe_words(self, request, context):
            return await provider.transcribe_words(request, context)

    monkeypatch.setattr("gamingcreator.infrastructure.local_asr.LocalAsrProvider", FakeProvider)
    monkeypatch.chdir(repository)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = main(
            [
                "transcribe-words",
                "--project",
                str(project),
                "--run",
                "run-1",
                "--model",
                MODEL,
            ]
        )
    assert code == 0
    printed = json.loads(stdout.getvalue())
    assert printed["schemaVersion"] == "asr-words-cli-v1"
    assert printed["runId"] == "run-1"
    assert printed["mediaId"] == "media"
    assert printed["wordCount"] == 1
    assert printed["resultHash"] == summary.result_hash
    assert printed["resultPath"] == str(summary.result_directory / "words.json")
    assert printed["reused"] is True
    assert Path(printed["resultPath"]).is_file()
    assert old.read_bytes() == before


def test_missing_model_or_run_is_reported_in_chinese(tmp_path):
    repository, project, _bundle = _seed(tmp_path)
    with pytest.raises(AppError) as missing_model:
        asyncio.run(
            transcribe_project_words(
                project, "run-1", "not-installed", repository, provider=FakeWords()
            )
        )
    assert missing_model.value.code == "environment.asr"
    assert missing_model.value.message == "本机没有安装这个识别模型。"
    with pytest.raises(AppError) as missing_run:
        asyncio.run(
            transcribe_project_words(
                project, "run-missing", MODEL, repository, provider=FakeWords()
            )
        )
    assert missing_run.value.code == "asr.run_missing"
    assert missing_run.value.message == "找不到这个任务的已准备音频。"


def test_default_worker_request_does_not_enable_word_timestamps(tmp_path):
    repository, _project, bundle = _seed(tmp_path)
    from gamingcreator.infrastructure.asr_audio import prepared_asr_audio_request
    from gamingcreator.infrastructure.asr_models import select_installed_asr_settings
    from gamingcreator.infrastructure.local_asr import LocalAsrProvider

    provider = LocalAsrProvider(repository, select_installed_asr_settings(repository, MODEL))
    request = prepared_asr_audio_request("run-1", bundle)
    default = json.loads(provider._worker_request_json(request, word_timestamps=False))
    worded = json.loads(provider._worker_request_json(request, word_timestamps=True))
    assert "wordTimestamps" not in default
    assert worded["wordTimestamps"] is True
    worded.pop("wordTimestamps")
    assert worded == default
