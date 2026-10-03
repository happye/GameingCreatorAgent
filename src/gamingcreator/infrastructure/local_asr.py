"""Offline ASR boundary; inference and lazy segment iteration live in a killable process."""

import asyncio
import hashlib
import json
import re
import sys
import time
import wave
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from gamingcreator.application.asr import LocalAsrSettings
from gamingcreator.application.providers import (
    AsrRequest,
    CancellationContext,
    CostStatus,
    InvocationMetadata,
    ProviderCapabilities,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.models import TranscriptSegment
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.media_process import run_media_process

MODEL_FILES = frozenset({"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"})
WORKER_SCHEMA = "local-asr-worker-v1"
MAX_SEGMENTS = 10000


class _AsrFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


async def _hash(path: Path, context: CancellationContext) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            context.check_cancelled()
            digest.update(chunk)
            await asyncio.sleep(0)
    context.check_cancelled()
    return digest.hexdigest()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise _AsrFailure("asr.response_invalid")
    return cast(dict[str, object], value)


def _sample(seconds: object, rate: int, rounding: str, max_samples: int) -> int:
    if type(seconds) not in (str, int, float):
        raise _AsrFailure("asr.response_invalid")
    try:
        value = Decimal(str(seconds))
        if not value.is_finite() or value < 0 or value > Decimal(max_samples) / rate:
            raise _AsrFailure("asr.response_invalid")
        return int((value * rate).to_integral_value(rounding=rounding))
    except (ArithmeticError, ValueError):
        raise _AsrFailure("asr.response_invalid") from None


class LocalAsrProvider:
    def __init__(self, repository: Path, settings: LocalAsrSettings) -> None:
        self.repository = repository.resolve()
        self.settings = settings

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            audio=True,
            structured_output=True,
            local_time_semantics="WAV samples mapped through the recorded piecewise source clock",
        )

    def _execution(self) -> dict[str, object]:
        return {
            "workerSchema": WORKER_SCHEMA,
            "modelDirectory": str(self.settings.model_directory.resolve()),
            "modelFiles": [
                {"name": item.name, "size": item.size, "sha256": item.sha256}
                for item in self.settings.model_files
            ],
            "device": "cpu",
            "computeType": self.settings.compute_type,
            "cpuThreads": self.settings.cpu_threads,
            "beamSize": self.settings.beam_size,
            "vadFilter": self.settings.vad_filter,
            "apiCostOnly": True,
            "hardwareCostMeasured": False,
        }

    def _metadata(
        self,
        request: AsrRequest,
        start: float,
        *,
        actual_model: str | None = None,
        worker_elapsed_ms: int | None = None,
        language: str | None = None,
    ) -> InvocationMetadata:
        details = self._execution()
        details["workerElapsedMs"] = worker_elapsed_ms
        details["detectedLanguage"] = language
        details["requestedLanguage"] = request.language
        details["gameTerms"] = list(request.game_terms)
        details["modelIntegrityVerified"] = actual_model is not None
        return InvocationMetadata(
            provider="faster-whisper-local",
            requested_model=self.settings.model_name,
            actual_model=actual_model,
            model_revision=self.settings.model_revision,
            prompt_version="asr-hotwords-v1",
            schema_version=request.schema_version,
            attempt=1,
            usage=ProviderUsage(
                original_cost=Decimal(0),
                currency="CNY",
                cost_cny=Decimal(0),
                cost_status=CostStatus.CONFIRMED,
            ),
            elapsed_ms=max(0, int((time.monotonic() - start) * 1000)),
            price_version="local-no-network-api-v1",
            execution_details=json.dumps(details, ensure_ascii=False, sort_keys=True),
        )

    async def _validate_model(self, context: CancellationContext) -> None:
        settings = self.settings
        directory = settings.model_directory.resolve()
        native = settings.native_library_directory
        if (
            not directory.is_relative_to(self.repository)
            or (native is not None and not native.resolve().is_relative_to(self.repository))
            or not settings.model_name
            or not re.fullmatch(r"[a-f0-9]{40}", settings.model_revision)
            or settings.compute_type != "int8"
            or type(settings.cpu_threads) is not int
            or settings.cpu_threads <= 0
            or type(settings.beam_size) is not int
            or not 0 < settings.beam_size <= 100
            or type(settings.vad_filter) is not bool
            or len(settings.model_files) != len(MODEL_FILES)
            or {item.name for item in settings.model_files} != MODEL_FILES
        ):
            raise _AsrFailure("asr.configuration_invalid")
        if (sys.platform == "win32" and native is None) or (
            native is not None and not native.is_dir()
        ):
            raise _AsrFailure("asr.runtime_unavailable")
        for item in settings.model_files:
            if (
                type(item.size) is not int
                or item.size <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", item.sha256)
            ):
                raise _AsrFailure("asr.configuration_invalid")
            path = directory / item.name
            if (
                not path.resolve().is_relative_to(directory)
                or not path.is_file()
                or path.stat().st_size != item.size
                or await _hash(path, context) != item.sha256
            ):
                raise _AsrFailure("asr.model_integrity")

    async def _validate_audio(self, request: AsrRequest, context: CancellationContext) -> None:
        evidence, asset, clock = request.audio_evidence, request.media_asset, request.audio_clock
        if (
            evidence is None
            or asset is None
            or clock is None
            or evidence.kind != "audio"
            or evidence.evidence_id != clock.evidence_id
            or evidence.media_id != asset.media_id
            or evidence.artifact_path.resolve() != clock.path.resolve()
            or evidence.sha256 != clock.sha256
            or not isinstance(evidence.source_time, SourceRange)
            or evidence.source_time.duration_us != asset.duration_us
            or not any(stream.kind == "audio" for stream in asset.streams)
        ):
            raise _AsrFailure("asr.audio_identity")
        if (
            await _hash(asset.source_path, context) != asset.sha256
            or await _hash(clock.path, context) != clock.sha256
        ):
            raise _AsrFailure("asr.input_integrity")
        try:
            with wave.open(str(clock.path), "rb") as audio:
                if (
                    audio.getnchannels() != 1
                    or audio.getsampwidth() != 2
                    or audio.getcomptype() != "NONE"
                    or audio.getframerate() != clock.sample_rate
                    or audio.getnframes() != clock.sample_count
                ):
                    raise _AsrFailure("asr.audio_invalid")
        except (wave.Error, EOFError):
            raise _AsrFailure("asr.audio_invalid") from None

    def _parse_output(
        self, output: bytes, request: AsrRequest
    ) -> tuple[tuple[TranscriptSegment, ...], int, str]:
        try:
            result = _object(json.loads(output))
        except (ValueError, UnicodeError):
            raise _AsrFailure("asr.response_invalid") from None
        if result.get("schema") != WORKER_SCHEMA:
            raise _AsrFailure("asr.response_invalid")
        if result.get("status") == "failed":
            code = result.get("code")
            allowed = {
                "asr.worker_input",
                "asr.runtime_unavailable",
                "asr.model_load",
                "asr.inference",
            }
            raise _AsrFailure(code if isinstance(code, str) and code in allowed else "asr.worker")
        if set(result) != {
            "schema",
            "status",
            "model",
            "revision",
            "language",
            "elapsedMs",
            "segments",
        }:
            raise _AsrFailure("asr.response_invalid")
        rows, elapsed, language = result["segments"], result["elapsedMs"], result["language"]
        if (
            result["status"] != "completed"
            or result["model"] != self.settings.model_name
            or result["revision"] != self.settings.model_revision
            or not isinstance(rows, list)
            or len(rows) > MAX_SEGMENTS
            or type(elapsed) is not int
            or elapsed < 0
            or not isinstance(language, str)
            or not re.fullmatch(r"[a-z]{2,3}", language)
        ):
            raise _AsrFailure("asr.response_invalid")
        assert request.audio_clock is not None and request.media_asset is not None
        clock, asset = request.audio_clock, request.media_asset
        segments = []
        previous_start = -1
        for value in rows:
            row = _object(value)
            if set(row) != {"start", "end", "text"} or not isinstance(row["text"], str):
                raise _AsrFailure("asr.response_invalid")
            text = row["text"].strip()
            start = _sample(row["start"], clock.sample_rate, ROUND_FLOOR, clock.sample_count)
            end = _sample(row["end"], clock.sample_rate, ROUND_CEILING, clock.sample_count)
            if not text or len(text) > 16384 or start < previous_start or end > clock.sample_count:
                raise _AsrFailure("asr.response_invalid")
            try:
                mapping = clock.map_interval(start, end, asset)
            except ValueError:
                raise _AsrFailure("asr.response_invalid") from None
            uncertainty = None
            if mapping.uncertain:
                uncertainty = json.dumps(
                    {
                        "reason": "piecewise_audio_clock",
                        "discontinuitySampleOffsets": list(mapping.discontinuity_offsets),
                        "clampedStartSeconds": str(mapping.clamped_start_seconds),
                        "clampedEndSeconds": str(mapping.clamped_end_seconds),
                    },
                    sort_keys=True,
                )
            segments.append(
                TranscriptSegment(asset.media_id, mapping.source_range, text, uncertainty)
            )
            previous_start = start
        return tuple(segments), elapsed, language

    async def transcribe(
        self, request: AsrRequest, context: CancellationContext
    ) -> ProviderResult[tuple[TranscriptSegment, ...]]:
        start = time.monotonic()
        try:
            context.check_cancelled()
            if request.run_id != context.run_id:
                raise _AsrFailure("asr.run_identity")
            if request.audio_evidence is None:
                if request.audio_clock is not None or (
                    request.media_asset is not None
                    and any(stream.kind == "audio" for stream in request.media_asset.streams)
                ):
                    raise _AsrFailure("asr.audio_identity")
                return ProviderResult(ProviderStatus.NO_AUDIO, (), self._metadata(request, start))
            if (
                not re.fullmatch(r"[a-z]{2,3}|auto", request.language)
                or any(not isinstance(term, str) or not term.strip() for term in request.game_terms)
                or sum(len(term) for term in request.game_terms) > 4096
            ):
                raise _AsrFailure("asr.request_invalid")
            async with asyncio.timeout(context.timeout_seconds):
                await self._validate_audio(request, context)
                await self._validate_model(context)
                interpreter = self.repository / ".venv" / "Scripts" / "python.exe"
                if not interpreter.is_file():
                    raise _AsrFailure("asr.runtime_unavailable")
                request_directory = self.repository / ".cache" / "asr-requests"
                request_directory.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=request_directory) as temporary:
                    request_path = Path(temporary) / "request.json"
                    request_path.write_text(
                        json.dumps(
                            {
                                "schema": WORKER_SCHEMA,
                                "audioPath": str(request.audio_evidence.artifact_path.resolve()),
                                "modelDirectory": str(self.settings.model_directory.resolve()),
                                "model": self.settings.model_name,
                                "revision": self.settings.model_revision,
                                "nativeDirectory": (
                                    str(self.settings.native_library_directory.resolve())
                                    if self.settings.native_library_directory is not None
                                    else None
                                ),
                                "computeType": self.settings.compute_type,
                                "cpuThreads": self.settings.cpu_threads,
                                "beamSize": self.settings.beam_size,
                                "vadFilter": self.settings.vad_filter,
                                "language": request.language,
                                "gameTerms": list(request.game_terms),
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    result = await run_media_process(
                        [
                            str(interpreter),
                            "-I",
                            "-B",
                            "-m",
                            "gamingcreator.infrastructure.asr_worker",
                            str(request_path),
                        ],
                        context,
                        max_stdout_bytes=4 * 1024 * 1024,
                        max_stderr_bytes=1024 * 1024,
                    )
                    segments, elapsed, language = self._parse_output(result.stdout, request)
                await self._validate_audio(request, context)
                context.check_cancelled()
            return ProviderResult(
                ProviderStatus.COMPLETED if segments else ProviderStatus.NO_SPEECH,
                segments,
                self._metadata(
                    request,
                    start,
                    actual_model=self.settings.model_name,
                    worker_elapsed_ms=elapsed,
                    language=language,
                ),
            )
        except asyncio.CancelledError:
            return ProviderResult(
                ProviderStatus.CANCELLED,
                None,
                self._metadata(request, start),
                ProviderFailure("asr.cancelled", False),
            )
        except TimeoutError:
            code = "asr.timeout"
        except _AsrFailure as error:
            code = error.code
        except AppError as error:
            code = {
                "input.media_decode": "asr.worker_exit",
                "environment.media_tool": "asr.runtime_unavailable",
                "media.timeout": "asr.timeout",
                "media.output_limit": "asr.output_limit",
            }.get(error.code, "asr.worker")
        except (OSError, ValueError):
            code = "asr.input_invalid"
        return ProviderResult(
            ProviderStatus.FAILED,
            None,
            self._metadata(request, start),
            ProviderFailure(code, False),
        )
