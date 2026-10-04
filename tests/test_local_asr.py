"""Controlled fake worker/model tests prove contracts, never ASR accuracy or real inference."""

import asyncio
import ctypes
import hashlib
import json
import sys
import types
import wave
from contextlib import nullcontext
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.asr import LocalAsrSettings, ModelFile
from gamingcreator.application.providers import AsrRequest, CancellationContext, ProviderStatus
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import AudioEvidence, AudioFrameMapping, MediaAsset, MediaStream
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure import asr_worker, local_asr
from gamingcreator.infrastructure.local_asr import LocalAsrProvider
from gamingcreator.infrastructure.media_process import ProcessOutput, run_media_process


@pytest.fixture
def fixture(tmp_path: Path):
    """Tiny synthetic WAV and fake model bytes. No model package is imported."""
    repository = tmp_path / "项目"
    repository.mkdir()
    interpreter = repository / ".venv" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    source = repository / "source.mp4"
    source.write_bytes(b"synthetic source identity")
    audio = repository / "audio.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(10)
        output.writeframes(b"\x00\x00" * 10)
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
    reference = EvidenceReference(
        "audio",
        "media",
        "audio",
        SourceRange(0, 1_200_000, 2_000_000),
        audio,
        clock.sha256,
        "fake-transform",
    )
    model_directory = repository / ".cache" / "models" / "fake"
    model_directory.mkdir(parents=True)
    model_files = []
    for name in sorted(local_asr.MODEL_FILES):
        content = name.encode()
        (model_directory / name).write_bytes(content)
        model_files.append(ModelFile(name, len(content), hashlib.sha256(content).hexdigest()))
    native_directory = repository / ".tools/native/fake"
    native_directory.mkdir(parents=True)
    native_files = []
    from gamingcreator.infrastructure.asr_runtime import NATIVE_FILES

    for name in sorted(NATIVE_FILES):
        content = name.encode()
        (native_directory / name).write_bytes(content)
        native_files.append(ModelFile(name, len(content), hashlib.sha256(content).hexdigest()))
    settings = LocalAsrSettings(
        model_directory,
        "fake-tiny",
        "a" * 40,
        tuple(model_files),
        native_directory,
        native_library_files=tuple(native_files),
    )
    request = AsrRequest("run", reference, "transcript-v1", media_asset=asset, audio_clock=clock)
    return repository, settings, request


def worker_output(settings, segments=(), **overrides):
    value = {
        "schema": local_asr.WORKER_SCHEMA,
        "status": "completed",
        "model": settings.model_name,
        "revision": settings.model_revision,
        "language": "zh",
        "elapsedMs": 17,
        "segments": list(segments),
        "nativeLibraries": [
            {
                "name": item.name,
                "path": str(settings.native_library_directory / item.name),
                "sha256": item.sha256,
            }
            for item in settings.native_library_files
        ],
    }
    value.update(overrides)
    return ProcessOutput(json.dumps(value).encode(), b"")


def install_fake(monkeypatch, output, capture=None):
    async def controlled(arguments, context, **limits):
        context.check_cancelled()
        if capture is not None:
            capture.append((arguments, json.loads(Path(arguments[-1]).read_text()), limits))
        return output

    monkeypatch.setattr(local_asr, "run_media_process", controlled)


def test_no_audio_does_not_validate_or_load_missing_model(fixture, monkeypatch):
    repository, settings, request = fixture
    settings = replace(settings, model_directory=repository / "missing")

    async def forbidden(*args, **kwargs):
        raise AssertionError("no_audio must not start worker")

    monkeypatch.setattr(local_asr, "run_media_process", forbidden)
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(
            replace(
                request,
                audio_evidence=None,
                audio_clock=None,
                media_asset=replace(request.media_asset, streams=(request.media_asset.streams[0],)),
            ),
            CancellationContext("run", 5),
        )
    )
    assert result.status == ProviderStatus.NO_AUDIO and result.output == ()
    assert result.metadata.actual_model is None
    assert result.metadata.usage.input_tokens is None
    assert result.metadata.usage.cost_cny == Decimal(0)
    assert json.loads(result.metadata.execution_details)["apiCostOnly"] is True


def test_missing_evidence_for_known_audio_stream_is_failure(fixture):
    repository, settings, request = fixture
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(
            replace(request, audio_evidence=None, audio_clock=None), CancellationContext("run", 5)
        )
    )
    assert result.status == ProviderStatus.FAILED
    assert result.error.code == "asr.audio_identity"


def test_extreme_decimal_time_is_typed_failure(fixture, monkeypatch):
    repository, settings, request = fixture
    install_fake(
        monkeypatch,
        worker_output(settings, [{"start": "1e999999", "end": "1e999999", "text": "bad time"}]),
    )
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.FAILED
    assert result.error.code == "asr.response_invalid"


def test_fake_worker_maps_piecewise_clock_and_records_provenance(fixture, monkeypatch):
    repository, settings, request = fixture
    capture = []
    install_fake(
        monkeypatch,
        worker_output(settings, [{"start": "0.1", "end": "0.8", "text": "测试"}]),
        capture,
    )
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.COMPLETED
    (segment,) = result.output
    assert segment.source_range == SourceRange(100000, 1000000, 2000000)
    assert json.loads(segment.uncertainty)["discontinuitySampleOffsets"] == [3]
    details = json.loads(result.metadata.execution_details)
    assert details["modelFiles"] == [vars_for_file(item) for item in settings.model_files]
    assert details["device"] == "cpu" and details["computeType"] == "int8"
    assert details["workerElapsedMs"] == 17
    arguments, payload, limits = capture[0]
    assert arguments[1:5] == ["-I", "-B", "-m", "gamingcreator.infrastructure.asr_worker"]
    assert payload["audioPath"] == str(request.audio_clock.path.resolve())
    assert limits["max_stdout_bytes"] == 4 * 1024 * 1024
    assert not Path(arguments[-1]).exists()


def vars_for_file(item):
    return {"name": item.name, "size": item.size, "sha256": item.sha256}


def test_outward_sample_quantization_does_not_restore_vad_twice(fixture, monkeypatch):
    repository, settings, request = fixture
    install_fake(
        monkeypatch, worker_output(settings, [{"start": "0.10001", "end": "0.19999", "text": "A"}])
    )
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.output[0].source_range == SourceRange(100000, 200000, 2000000)
    assert result.output[0].uncertainty is None


@pytest.mark.parametrize(
    "clock_frames",
    [
        (AudioFrameMapping(0, 6, 0, Fraction(1, 10)), AudioFrameMapping(6, 4, 4, Fraction(1, 10))),
        (AudioFrameMapping(0, 10, -1, Fraction(1, 10)),),
    ],
)
def test_overlap_or_clamping_is_retained_as_uncertainty(fixture, monkeypatch, clock_frames):
    repository, settings, request = fixture
    request = replace(request, audio_clock=replace(request.audio_clock, frames=clock_frames))
    request = replace(
        request,
        audio_evidence=replace(
            request.audio_evidence,
            source_time=request.audio_clock.map_interval(
                0, request.audio_clock.sample_count, request.media_asset
            ).source_range,
        ),
    )
    install_fake(monkeypatch, worker_output(settings, [{"start": "0", "end": "1", "text": "A"}]))
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.COMPLETED
    assert result.output[0].uncertainty is not None


def test_empty_fake_response_is_typed_no_speech(fixture, monkeypatch):
    repository, settings, request = fixture
    install_fake(monkeypatch, worker_output(settings))
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.NO_SPEECH and result.output == ()


@pytest.mark.parametrize(
    "change,expected",
    [
        (lambda r: replace(r, media_asset=None), "asr.audio_identity"),
        (lambda r: replace(r, audio_clock=None), "asr.audio_identity"),
        (lambda r: replace(r, run_id="other"), "asr.run_identity"),
        (
            lambda r: replace(r, audio_evidence=replace(r.audio_evidence, media_id="other")),
            "asr.audio_identity",
        ),
        (
            lambda r: replace(r, audio_evidence=replace(r.audio_evidence, sha256="0" * 64)),
            "asr.audio_identity",
        ),
        (lambda r: replace(r, language="invalid/private"), "asr.request_invalid"),
    ],
)
def test_request_identity_is_rejected_before_worker(fixture, monkeypatch, change, expected):
    repository, settings, request = fixture

    async def forbidden(*args, **kwargs):
        raise AssertionError("invalid input must not start worker")

    monkeypatch.setattr(local_asr, "run_media_process", forbidden)
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(
            change(request), CancellationContext("run", 5)
        )
    )
    assert result.status == ProviderStatus.FAILED and result.error.code == expected


@pytest.mark.parametrize("file_name", sorted(local_asr.MODEL_FILES))
@pytest.mark.parametrize("operation", ["missing", "modified"])
def test_each_missing_or_modified_model_file_fails_offline(
    fixture, monkeypatch, file_name, operation
):
    repository, settings, request = fixture
    path = settings.model_directory / file_name
    if operation == "missing":
        path.unlink()
    else:
        path.write_bytes(b"x" * path.stat().st_size)
    install_fake(monkeypatch, worker_output(settings))
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.FAILED and result.error.code == "asr.model_integrity"


def test_model_directory_must_be_project_local(fixture, monkeypatch, tmp_path):
    repository, settings, request = fixture
    install_fake(monkeypatch, worker_output(settings))
    result = asyncio.run(
        LocalAsrProvider(repository, replace(settings, model_directory=tmp_path)).transcribe(
            request, CancellationContext("run", 5)
        )
    )
    assert result.error.code == "asr.configuration_invalid"


@pytest.mark.parametrize(
    "bad_segment",
    [
        {"start": "NaN", "end": "1", "text": "A"},
        {"start": "-0.1", "end": "1", "text": "A"},
        {"start": "1", "end": "0", "text": "A"},
        {"start": "0.19", "end": "0.11", "text": "A"},
        {"start": "0.15", "end": "0.15", "text": "A"},
        {"start": "0", "end": "2", "text": "A"},
        {"start": "0", "end": "1", "text": " "},
        {"start": True, "end": "1", "text": "A"},
        {"start": "0", "end": "1", "text": "A", "extra": "private"},
    ],
)
def test_malformed_worker_times_and_segments_never_publish_partial_output(
    fixture, monkeypatch, bad_segment
):
    repository, settings, request = fixture
    install_fake(monkeypatch, worker_output(settings, [bad_segment]))
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.status == ProviderStatus.FAILED and result.output is None
    assert result.error.code == "asr.response_invalid"


def test_worker_failure_and_nonzero_exit_use_asr_errors(fixture, monkeypatch):
    repository, settings, request = fixture
    install_fake(
        monkeypatch,
        ProcessOutput(
            b'{"schema":"local-asr-worker-v1","status":"failed","code":"asr.model_load"}',
            b"private",
        ),
    )
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.error.code == "asr.model_load"

    async def failure(*args, **kwargs):
        raise AppError("input.media_decode", "媒体文件无法解码。", ExitCode.INPUT)

    monkeypatch.setattr(local_asr, "run_media_process", failure)
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.error.code == "asr.worker_exit"


def test_changed_source_during_inference_is_not_published(fixture, monkeypatch):
    repository, settings, request = fixture

    async def mutate(*args, **kwargs):
        request.media_asset.source_path.write_bytes(b"changed")
        return worker_output(settings, [{"start": "0", "end": "1", "text": "A"}])

    monkeypatch.setattr(local_asr, "run_media_process", mutate)
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 5))
    )
    assert result.error.code == "asr.input_integrity" and result.output is None


def test_cancellation_before_worker_returns_typed_cancelled(fixture, monkeypatch):
    repository, settings, request = fixture
    context = CancellationContext("run", 5)
    context.cancelled.set()
    result = asyncio.run(LocalAsrProvider(repository, settings).transcribe(request, context))
    assert result.status == ProviderStatus.CANCELLED and result.error.code == "asr.cancelled"


def test_real_controlled_process_cancellation_reaps_worker(fixture, monkeypatch, tmp_path):
    """Actual process containment, but the process sleeps and performs no inference."""
    repository, settings, request = fixture
    pid_path = tmp_path / "controlled-worker.pid"
    code = "import os,sys,time;from pathlib import Path;Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)"
    kernel = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
    handle = None
    if kernel is not None:
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    async def controlled(*args, **kwargs):
        return await run_media_process(
            [sys.executable, "-I", "-B", "-c", code, str(pid_path)], args[1]
        )

    monkeypatch.setattr(local_asr, "run_media_process", controlled)

    async def scenario():
        nonlocal handle
        context = CancellationContext("run", 5)
        task = asyncio.create_task(
            LocalAsrProvider(repository, settings).transcribe(request, context)
        )
        for _ in range(100):
            if pid_path.exists():
                break
            await asyncio.sleep(0.02)
        assert pid_path.exists()
        if kernel is not None:
            handle = kernel.OpenProcess(0x100000, False, int(pid_path.read_text()))
            assert handle
        context.cancelled.set()
        result = await task
        assert result.status == ProviderStatus.CANCELLED

    try:
        asyncio.run(scenario())
        if kernel is not None:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        else:
            assert not Path(f"/proc/{pid_path.read_text()}").exists()
    finally:
        if kernel is not None and handle:
            kernel.CloseHandle(handle)


def test_total_timeout_bounds_a_controlled_worker(fixture, monkeypatch):
    repository, settings, request = fixture

    async def controlled(arguments, context, **kwargs):
        return await run_media_process(
            [sys.executable, "-I", "-B", "-c", "import time;time.sleep(30)"], context
        )

    monkeypatch.setattr(local_asr, "run_media_process", controlled)
    result = asyncio.run(
        LocalAsrProvider(repository, settings).transcribe(request, CancellationContext("run", 0.2))
    )
    assert result.error.code == "asr.timeout" and result.output is None


def test_fake_model_is_cpu_offline_and_generator_is_fully_materialized(monkeypatch, tmp_path):
    monkeypatch.setattr(asr_worker, "verify_native", lambda *args: None)
    monkeypatch.setattr(asr_worker, "loaded_runtime_libraries", lambda *args: [])
    monkeypatch.setattr(
        asr_worker.os, "add_dll_directory", lambda path: nullcontext(), raising=False
    )
    monkeypatch.setattr(asr_worker.ctypes, "WinDLL", lambda path: object(), raising=False)
    calls = []
    completed = []

    class FakeModel:
        def __init__(self, directory, **kwargs):
            calls.append((directory, kwargs))

        def transcribe(self, audio, **kwargs):
            assert not (tmp_path / "ready.json").exists()
            calls.append((audio, kwargs))

            def lazy():
                yield types.SimpleNamespace(start=0.1, end=0.2, text="fake")
                ready = json.loads((tmp_path / "ready.json").read_text())
                assert ready["schema"] == local_asr.WORKER_SCHEMA
                assert ready["stage"] == "inference_started" and type(ready["pid"]) is int
                assert ready["completedSegments"] == 1
                completed.append(True)

            return lazy(), types.SimpleNamespace(language="en")

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    request = {
        "modelDirectory": "fake-local",
        "audioPath": "fake.wav",
        "model": "fake",
        "revision": "a" * 40,
        "nativeDirectory": "fake-native",
        "nativeFiles": [],
        "repository": str(tmp_path),
        "cpuThreads": 2,
        "beamSize": 5,
        "vadFilter": True,
        "language": "auto",
        "gameTerms": ["Atom"],
    }
    result = asr_worker._infer(request, tmp_path / "ready.json")
    assert result["status"] == "completed" and completed == [True]
    assert calls[0][1] == {
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 2,
        "num_workers": 1,
        "local_files_only": True,
    }
    assert calls[1][1]["language"] is None and calls[1][1]["hotwords"] == "Atom"


def test_fake_lazy_failure_is_sanitized_and_discards_partial_segments(monkeypatch):
    monkeypatch.setattr(asr_worker, "verify_native", lambda *args: None)
    monkeypatch.setattr(asr_worker, "loaded_runtime_libraries", lambda *args: [])
    monkeypatch.setattr(
        asr_worker.os, "add_dll_directory", lambda path: nullcontext(), raising=False
    )
    monkeypatch.setattr(asr_worker.ctypes, "WinDLL", lambda path: object(), raising=False)

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            def lazy():
                yield types.SimpleNamespace(start=0, end=1, text="partial")
                raise RuntimeError("private traceback")

            return lazy(), types.SimpleNamespace(language="zh")

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    result = asr_worker._infer(
        {
            "nativeDirectory": "fake-native",
            "nativeFiles": [],
            "repository": "fake-repository",
            "modelDirectory": "fake",
            "cpuThreads": 2,
            "audioPath": "fake.wav",
            "language": "zh",
            "beamSize": 5,
            "vadFilter": True,
            "gameTerms": [],
        }
    )
    assert result == {
        "schema": local_asr.WORKER_SCHEMA,
        "status": "failed",
        "code": "asr.inference",
    }
    assert "private" not in json.dumps(result)
