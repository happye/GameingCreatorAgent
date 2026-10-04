"""Verified offline E5 ONNX provider with killable inference and identity-safe cache."""

import asyncio
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Self, cast

from gamingcreator.application.asr import ModelFile
from gamingcreator.application.providers import (
    CancellationContext,
    CostStatus,
    EmbeddingRequest,
    InvocationMetadata,
    ProviderFailure,
    ProviderResult,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import Embedding, EmbeddingSpace
from gamingcreator.infrastructure.asr_runtime import verify_native
from gamingcreator.infrastructure.media_process import run_media_process

WORKER_SCHEMA = "local-e5-onnx-v2"
REQUIRED_FILES = frozenset(
    {
        "onnx/model_quantized.onnx",
        "tokenizer.json",
        "config.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
    }
)
MAX_TEXTS = 1024


@dataclass(frozen=True, slots=True)
class LocalEmbeddingSettings:
    model_directory: Path
    model_files: tuple[ModelFile, ...]
    model_name: str
    revision: str
    dimension: int = 384
    cpu_threads: int = 2
    native_library_directory: Path | None = None
    native_files: tuple[ModelFile, ...] = ()


async def _hash(path: Path, context: CancellationContext) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            context.check_cancelled()
            result.update(chunk)
            await asyncio.sleep(0)
    context.check_cancelled()
    return result.hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


class LocalEmbeddingProvider:
    def __init__(
        self, repository: Path, settings: LocalEmbeddingSettings, *, use_cache: bool = True
    ) -> None:
        self.repository = repository.resolve()
        self.settings = settings
        self.use_cache = use_cache
        scope = hashlib.sha256(
            _canonical(
                {
                    "revision": settings.revision,
                    "files": [
                        asdict(item)
                        for item in sorted(settings.model_files, key=lambda item: item.name)
                    ],
                    "inference": WORKER_SCHEMA,
                    "pooling": "attention-mask-mean",
                    "maxTokens": 512,
                    "batchSize": 1,
                }
            )
        ).hexdigest()
        self.space = EmbeddingSpace(
            "local-onnx-e5",
            settings.model_name,
            f"{settings.revision}:{scope}",
            settings.dimension,
            "l2",
        )

    @classmethod
    def from_manifest(cls, repository: Path, *, use_cache: bool = True) -> Self:
        root = repository.resolve()
        try:
            pin: dict[str, Any] = json.loads(
                (root / "docs/references/embedding-model.json").read_text(encoding="utf-8")
            )
            native_pin: dict[str, Any] = json.loads(
                (root / "docs/references/asr-native-toolchain.json").read_text(encoding="utf-8")
            )
            revision = pin["revision"]
            if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
                raise ValueError("Invalid revision")
            if (
                pin["normalization"] != "l2"
                or pin["pooling"] != "attention-mask-mean"
                or pin["dimension"] != 384
                or pin["maxTokens"] != 512
                or pin["queryPrefix"] != "query: "
                or pin["documentPrefix"] != "passage: "
                or pin["modelFile"] != "onnx/model_quantized.onnx"
            ):
                raise ValueError("Unsupported embedding configuration")
            files = tuple(
                ModelFile(item["name"], item["size"], item["sha256"]) for item in pin["files"]
            )
            native_directory = (root / ".tools/native/msvc" / native_pin["version"]).resolve()
            if not native_directory.is_relative_to(root):
                raise ValueError("External runtime directory")
            native_files = tuple(
                ModelFile(name, (native_directory / name).stat().st_size, digest)
                for name, digest in native_pin["files"].items()
            )
            return cls(
                root,
                LocalEmbeddingSettings(
                    root / ".cache/models/multilingual-e5-small" / revision,
                    files,
                    pin["model"],
                    revision,
                    pin["dimension"],
                    native_library_directory=native_directory,
                    native_files=native_files,
                ),
                use_cache=use_cache,
            )
        except (OSError, ValueError, TypeError, KeyError):
            raise AppError(
                "embedding.assets_missing",
                "请准备项目内固定模型和本地运行库。",
                ExitCode.ENVIRONMENT,
            ) from None

    def _metadata(
        self,
        request: EmbeddingRequest,
        started: float,
        *,
        complete: bool,
        cached: int,
        native: object = None,
    ) -> InvocationMetadata:
        return InvocationMetadata(
            provider=self.space.provider,
            requested_model=self.settings.model_name,
            actual_model=self.settings.model_name if complete else None,
            model_revision=self.settings.revision,
            prompt_version="e5-query-passage-v1",
            schema_version=request.schema_version,
            attempt=1,
            usage=ProviderUsage(
                original_cost=Decimal("0"),
                currency="CNY",
                cost_cny=Decimal("0"),
                cost_status=CostStatus.CONFIRMED,
            ),
            elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
            execution_details=json.dumps(
                {
                    "workerSchema": WORKER_SCHEMA,
                    "space": asdict(self.space),
                    "modelIntegrityVerified": complete,
                    "device": "cpu",
                    "cpuThreads": self.settings.cpu_threads,
                    "batchSize": 1,
                    "cachedTexts": cached,
                    "cacheEnabled": self.use_cache,
                    "totalTexts": len(request.texts),
                    "apiCostOnly": True,
                    "hardwareCostMeasured": False,
                    "nativeLibraries": native,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
        )

    async def _verify(self, context: CancellationContext) -> None:
        settings, root = self.settings, self.repository
        directory = settings.model_directory.resolve()
        if (
            not directory.is_relative_to(root)
            or not directory.is_dir()
            or not re.fullmatch(r"[a-f0-9]{40}", settings.revision)
            or len(settings.model_files) != len(REQUIRED_FILES)
            or {item.name for item in settings.model_files} != REQUIRED_FILES
            or settings.dimension != 384
            or type(settings.cpu_threads) is not int
            or not 1 <= settings.cpu_threads <= 32
        ):
            raise ValueError("embedding.assets_invalid")
        for item in settings.model_files:
            path = (directory / item.name).resolve()
            if (
                not path.is_relative_to(directory)
                or not path.is_file()
                or type(item.size) is not int
                or item.size <= 0
                or not re.fullmatch(r"[a-f0-9]{64}", item.sha256)
                or path.stat().st_size != item.size
                or await _hash(path, context) != item.sha256
            ):
                raise ValueError("embedding.model_integrity")
        if sys.platform == "win32":
            if settings.native_library_directory is None:
                raise ValueError("embedding.runtime_missing")
            try:
                verify_native(settings.native_library_directory, settings.native_files, root)
            except (OSError, ValueError):
                raise ValueError("embedding.runtime_integrity") from None

    def _cache_path(self, text: str) -> Path:
        key = hashlib.sha256(
            _canonical(
                {
                    "space": asdict(self.space),
                    "textHash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )
        ).hexdigest()
        directory = self.repository / ".cache/embeddings"
        path = (directory / f"{key}.json").resolve()
        if not path.is_relative_to(self.repository):
            raise ValueError("embedding.cache_path")
        return path

    def _vector(self, vector: object) -> tuple[float, ...]:
        if not isinstance(vector, list) or len(vector) != self.space.dimension:
            raise ValueError("embedding.response_invalid")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
            raise ValueError("embedding.response_invalid")
        result = tuple(float(value) for value in vector)
        if not math.isclose(sum(value * value for value in result), 1.0, abs_tol=0.001):
            raise ValueError("embedding.response_invalid")
        return result

    def _cached(self, text: str) -> tuple[float, ...] | None:
        path = self._cache_path(text)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > 32 * 1024:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
                return None
            payload = value["payload"]
            if (
                not isinstance(payload, dict)
                or set(payload) != {"space", "textHash", "vector"}
                or payload["space"] != asdict(self.space)
                or payload["textHash"] != hashlib.sha256(text.encode("utf-8")).hexdigest()
                or value["sha256"] != hashlib.sha256(_canonical(payload)).hexdigest()
            ):
                return None
            return self._vector(payload["vector"])
        except (OSError, ValueError, TypeError):
            return None

    def _cache(self, text: str, vector: tuple[float, ...]) -> None:
        path = self._cache_path(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "space": asdict(self.space),
            "textHash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "vector": list(vector),
        }
        envelope = {"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}
        with TemporaryDirectory(prefix="write-", dir=path.parent) as directory:
            temporary = Path(directory) / "vector.json"
            temporary.write_bytes(_canonical(envelope))
            temporary.replace(path)

    async def embed(
        self, request: EmbeddingRequest, context: CancellationContext
    ) -> ProviderResult[tuple[Embedding, ...]]:
        started, cached_count = time.monotonic(), 0
        try:
            context.check_cancelled()
            if (
                request.run_id != context.run_id
                or not request.run_id
                or request.schema_version != "embedding-v1"
                or not 1 <= len(request.texts) <= MAX_TEXTS
                or any(
                    not isinstance(text, str)
                    or not 1 <= len(text) <= 8192
                    or not text.startswith(("query: ", "passage: "))
                    for text in request.texts
                )
            ):
                raise ValueError("embedding.request_invalid")
            async with asyncio.timeout(context.timeout_seconds):
                await self._verify(context)
                vectors = [self._cached(text) if self.use_cache else None for text in request.texts]
                cached_count = sum(vector is not None for vector in vectors)
                missing = [index for index, vector in enumerate(vectors) if vector is None]
                native = None
                if missing:
                    cache = (self.repository / ".cache/embedding-requests").resolve()
                    if not cache.is_relative_to(self.repository):
                        raise ValueError("embedding.cache_path")
                    cache.mkdir(parents=True, exist_ok=True)
                    interpreter = (self.repository / ".venv/Scripts/python.exe").resolve()
                    if not interpreter.is_relative_to(self.repository) or not interpreter.is_file():
                        raise ValueError("embedding.runtime_missing")
                    with TemporaryDirectory(prefix="embed-", dir=cache) as directory:
                        path = Path(directory) / "request.json"
                        path.write_bytes(
                            _canonical(
                                {
                                    "schema": WORKER_SCHEMA,
                                    "repository": str(self.repository),
                                    "modelDirectory": str(self.settings.model_directory.resolve()),
                                    "modelFiles": [
                                        asdict(item) for item in self.settings.model_files
                                    ],
                                    "nativeDirectory": None
                                    if self.settings.native_library_directory is None
                                    else str(self.settings.native_library_directory.resolve()),
                                    "nativeFiles": [
                                        asdict(item) for item in self.settings.native_files
                                    ],
                                    "texts": [request.texts[index] for index in missing],
                                    "cpuThreads": self.settings.cpu_threads,
                                }
                            )
                        )
                        output = await run_media_process(
                            [
                                str(interpreter),
                                "-I",
                                "-B",
                                str(Path(__file__).with_name("embedding_worker.py")),
                                str(path),
                            ],
                            context,
                            max_stdout_bytes=16 * 1024 * 1024,
                            max_stderr_bytes=1024 * 1024,
                        )
                        response = json.loads(output.stdout)
                        if (
                            not isinstance(response, dict)
                            or response.get("schema") != WORKER_SCHEMA
                            or set(response) != {"schema", "vectors", "nativeLibraries"}
                        ):
                            raise ValueError("embedding.response_invalid")
                        values = response["vectors"]
                        if not isinstance(values, list) or len(values) != len(missing):
                            raise ValueError("embedding.response_invalid")
                        native = response["nativeLibraries"]
                        decoded = [self._vector(value) for value in values]
                        # Do not cache a response from weights modified during native inference.
                        await self._verify(context)
                        for index, vector in zip(missing, decoded, strict=True):
                            context.check_cancelled()
                            vectors[index] = vector
                            if self.use_cache:
                                self._cache(request.texts[index], vector)
                context.check_cancelled()
                output_embeddings = tuple(
                    Embedding(
                        f"{request.run_id}:{index}",
                        self.space,
                        cast(tuple[float, ...], vector),
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    )
                    for index, (text, vector) in enumerate(zip(request.texts, vectors, strict=True))
                )
            return ProviderResult(
                ProviderStatus.COMPLETED,
                output_embeddings,
                self._metadata(request, started, complete=True, cached=cached_count, native=native),
            )
        except asyncio.CancelledError:
            code, status = "embedding.cancelled", ProviderStatus.CANCELLED
        except TimeoutError:
            code, status = "embedding.timeout", ProviderStatus.FAILED
        except AppError as error:
            code, status = (
                (
                    "embedding.timeout"
                    if error.code == "media.timeout"
                    else "embedding.worker_failed"
                ),
                ProviderStatus.FAILED,
            )
        except (OSError, ValueError, TypeError) as error:
            code = (
                str(error)
                if isinstance(error, ValueError) and str(error).startswith("embedding.")
                else "embedding.response_invalid"
            )
            status = ProviderStatus.FAILED
        return ProviderResult(
            status,
            None,
            self._metadata(request, started, complete=False, cached=cached_count),
            ProviderFailure(code, False),
        )
