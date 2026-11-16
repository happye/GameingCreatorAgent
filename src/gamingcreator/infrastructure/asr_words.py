"""对已有项目任务做本机逐词识别，并发布独立的词级结果。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gamingcreator.application.asr_word_timing import AsrWord, stitch_window_words
from gamingcreator.application.providers import (
    AsrRequest,
    CancellationContext,
    ProviderResult,
    ProviderStatus,
)
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import AudioEvidence, MediaAsset
from gamingcreator.infrastructure.asr_audio import (
    prepared_asr_audio_request,
    verify_prepared_asr_audio,
)
from gamingcreator.infrastructure.asr_models import select_installed_asr_settings
from gamingcreator.infrastructure.asr_words_sidecar import (
    WORDS_FILENAME,
    load_reusable_asr_words_sidecar,
    publish_asr_words_sidecar,
    words_payload_sha256,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

SUMMARY_SCHEMA_VERSION = "asr-words-cli-v1"


class WordTranscriptProvider(Protocol):
    async def transcribe_words(
        self, request: AsrRequest, context: CancellationContext
    ) -> ProviderResult[tuple[AsrWord, ...]]: ...


@dataclass(frozen=True, slots=True)
class WordTranscriptionSummary:
    run_id: str
    media_id: str
    result_hash: str
    result_directory: Path
    word_count: int
    reused: bool
    model: str
    revision: str

    def to_json(self) -> dict[str, object]:
        return {
            "schemaVersion": SUMMARY_SCHEMA_VERSION,
            "runId": self.run_id,
            "mediaId": self.media_id,
            "model": self.model,
            "revision": self.revision,
            "resultHash": self.result_hash,
            "resultPath": str(self.result_directory / WORDS_FILENAME),
            "wordCount": self.word_count,
            "reused": self.reused,
        }


async def transcribe_project_words(
    project: Path,
    run_id: str,
    model: str,
    repository: Path,
    *,
    provider: WordTranscriptProvider | None = None,
    context: CancellationContext | None = None,
    timeout_seconds: float = 600,
) -> WordTranscriptionSummary:
    settings = select_installed_asr_settings(repository, model)
    if context is None:
        context = CancellationContext(run_id, timeout_seconds)
    elif context.run_id != run_id:
        raise AppError(
            "asr.run_identity",
            "取消范围必须指向这次识别任务。",
            ExitCode.INPUT,
            run_id,
        )
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        context.check_cancelled()
        try:
            bundle = await store.load_media_bundle(run_id)
        except AppError as error:
            if error.code not in {"storage.stage_state", "storage.run_missing"}:
                raise
            raise AppError(
                "asr.run_missing",
                "找不到这个任务的已准备音频。",
                ExitCode.INPUT,
                run_id,
            ) from None
    except asyncio.CancelledError:
        raise AppError("asr.cancelled", "逐词识别已取消。", ExitCode.CANCELLED, run_id) from None
    finally:
        await store.close()
    try:
        request = prepared_asr_audio_request(run_id, bundle)
        verify_prepared_asr_audio(request)
        asset = request.media_asset
        clock = request.audio_clock
        if request.audio_evidence is None or asset is None or clock is None:
            raise AppError(
                "asr.no_audio",
                "这个任务没有可用的原片准备音频。",
                ExitCode.INPUT,
                run_id,
            )
        existing = await _find_existing_words(
            project, run_id, asset, clock, settings.model_name, settings.model_revision
        )
        context.check_cancelled()
        if existing is not None:
            return existing
        if provider is None:
            from gamingcreator.infrastructure.local_asr import LocalAsrProvider

            provider = LocalAsrProvider(repository, settings)
        result = await provider.transcribe_words(request, context)
        if result.status == ProviderStatus.CANCELLED:
            code = result.error.code if result.error is not None else "asr.cancelled"
            raise AppError(code, "逐词识别已取消。", ExitCode.CANCELLED, run_id)
        if (
            result.status == ProviderStatus.FAILED
            and result.error is not None
            and result.error.code == "asr.timeout"
        ):
            raise AppError("asr.timeout", "逐词识别超时。", ExitCode.ENVIRONMENT, run_id)
        if result.status == ProviderStatus.FAILED or result.output is None:
            code = result.error.code if result.error is not None else "asr.failed"
            if code == "environment.asr":
                raise _unavailable_words(run_id, "逐词识别目前不可用。")
            raise AppError(code, "逐词识别失败。", ExitCode.ENVIRONMENT, run_id)
        context.check_cancelled()
        words = stitch_window_words((result.output,))
        directory = publish_asr_words_sidecar(
            project,
            run_id=run_id,
            media_id=asset.media_id,
            source_sha256=asset.sha256,
            audio_sha256=clock.sha256,
            clock=clock,
            asset=asset,
            model=settings.model_name,
            revision=settings.model_revision,
            words=words,
            metadata=result.metadata,
            context=context,
        )
        payload = (directory / WORDS_FILENAME).read_bytes()
        return WordTranscriptionSummary(
            run_id,
            asset.media_id,
            words_payload_sha256(payload),
            directory,
            len(words),
            False,
            settings.model_name,
            settings.model_revision,
        )
    except asyncio.CancelledError:
        raise AppError("asr.cancelled", "逐词识别已取消。", ExitCode.CANCELLED, run_id) from None


async def _find_existing_words(
    project: Path,
    run_id: str,
    asset: MediaAsset,
    clock: AudioEvidence,
    model: str,
    revision: str,
) -> WordTranscriptionSummary | None:
    from gamingcreator.infrastructure.asr_words_sidecar import asr_words_directory, clock_digest

    root = asr_words_directory(project, run_id, "0" * 64).parent
    if not root.exists():
        return None
    for directory in sorted(root.iterdir()):
        if directory.name.startswith("."):
            continue
        published_model, published_revision = _published_model_identity(
            project, run_id, directory.name
        )
        if (published_model, published_revision) != (model, revision):
            continue
        document = await load_asr_words_projection(project, run_id, directory.name)
        if (
            document["mediaId"] != asset.media_id
            or document["sourceSha256"] != asset.sha256
            or document["audioSha256"] != clock.sha256
            or document["clockDigest"] != clock_digest(clock, asset)
        ):
            raise _damaged_words(run_id)
        words = _words_from_document(document, asset.media_id, asset.duration_us)
        return WordTranscriptionSummary(
            run_id,
            asset.media_id,
            directory.name,
            directory,
            len(words or ()),
            True,
            model,
            revision,
        )
    return None


PROJECTION_SCHEMA_VERSION = "asr-words-http-v1"


def _missing_words(run_id: str) -> AppError:
    return AppError(
        "asr.words_not_found",
        "找不到这份已核对的词级结果。",
        ExitCode.INPUT,
        run_id,
    )


def _damaged_words(run_id: str) -> AppError:
    return AppError(
        "asr.words_damaged",
        "逐词结果已损坏，不能使用，也不会覆盖或重新生成。",
        ExitCode.INPUT,
        run_id,
    )


def _permission_words(run_id: str) -> AppError:
    return AppError(
        "asr.words_permission",
        "没有权限读取这份逐词结果。",
        ExitCode.INPUT,
        run_id,
    )


def _unavailable_words(run_id: str, message: str | None = None) -> AppError:
    return AppError(
        "environment.asr",
        message or "逐词识别目前不可用。",
        ExitCode.ENVIRONMENT,
        run_id,
    )


def _inspect_published_words(project: Path, run_id: str, result_hash: str) -> str:
    """Classify an on-disk sidecar: missing, damaged, permission, or present."""
    from gamingcreator.infrastructure.asr_words_sidecar import (
        WORDS_FILENAME,
        asr_words_directory,
        words_payload_sha256,
    )
    from gamingcreator.infrastructure.local_files import read_bounded

    try:
        directory = asr_words_directory(project, run_id, result_hash)
        path = directory / WORDS_FILENAME
        if not directory.is_dir() or not path.is_file():
            return "missing"
        payload = read_bounded(path)
        json.loads(payload.decode("utf-8"))
    except PermissionError:
        return "permission"
    except FileNotFoundError:
        return "missing"
    except AppError as error:
        if error.code == "asr.words_path":
            return "missing"
        return "damaged"
    except (OSError, UnicodeError, ValueError):
        return "damaged"
    if words_payload_sha256(payload) != result_hash:
        return "damaged"
    return "present"


def _published_model_identity(project: Path, run_id: str, result_hash: str) -> tuple[str, str]:
    from gamingcreator.infrastructure.asr_words_sidecar import WORDS_FILENAME, asr_words_directory
    from gamingcreator.infrastructure.local_files import read_bounded

    try:
        path = asr_words_directory(project, run_id, result_hash) / WORDS_FILENAME
    except AppError:
        raise
    try:
        exists = path.is_file()
    except PermissionError:
        raise _permission_words(run_id) from None
    if not exists:
        raise _missing_words(run_id)
    try:
        payload = read_bounded(path)
        document = json.loads(payload.decode("utf-8"))
    except PermissionError:
        raise _permission_words(run_id) from None
    except (AppError, OSError, UnicodeError, ValueError):
        raise _damaged_words(run_id) from None
    if not isinstance(document, dict):
        raise _damaged_words(run_id)
    model, revision = document.get("model"), document.get("revision")
    if (
        type(model) is not str
        or not model.strip()
        or type(revision) is not str
        or not revision.strip()
    ):
        raise _damaged_words(run_id)
    return model, revision


async def load_asr_words_projection(
    project: Path, run_id: str, result_hash: str
) -> dict[str, object]:
    """从已发布的词级结果读取只读投影，不执行识别、不恢复任务。"""
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        try:
            bundle = await store.load_media_bundle(run_id)
        except AppError as error:
            if error.code not in {"storage.stage_state", "storage.run_missing"}:
                raise
            raise AppError(
                "asr.run_missing",
                "找不到这个任务的已准备音频。",
                ExitCode.INPUT,
                run_id,
            ) from None
        asset = bundle.asset
        clock = bundle.audio
        if asset is None or clock is None:
            raise _missing_words(run_id)
        verify_prepared_asr_audio(prepared_asr_audio_request(run_id, bundle))
        model, revision = _published_model_identity(project, run_id, result_hash)
        directory = load_reusable_asr_words_sidecar(
            project,
            run_id=run_id,
            media_id=asset.media_id,
            source_sha256=asset.sha256,
            audio_sha256=clock.sha256,
            clock=clock,
            asset=asset,
            model=model,
            revision=revision,
            result_hash=result_hash,
        )
        if directory is None:
            kind = _inspect_published_words(project, run_id, result_hash)
            if kind == "permission":
                raise _permission_words(run_id)
            if kind == "damaged":
                raise _damaged_words(run_id)
            raise _missing_words(run_id)
        document = json.loads((directory / WORDS_FILENAME).read_text(encoding="utf-8"))
        return {
            "schemaVersion": PROJECTION_SCHEMA_VERSION,
            "runId": document["runId"],
            "mediaId": document["mediaId"],
            "sourceSha256": document["sourceSha256"],
            "audioSha256": document["audioSha256"],
            "clockDigest": document["clockDigest"],
            "model": document["model"],
            "revision": document["revision"],
            "resultHash": result_hash,
            "words": document["words"],
            "readOnly": True,
        }
    finally:
        await store.close()


def _words_from_document(
    document: dict[str, object], media_id: str, duration_us: int
) -> tuple[AsrWord, ...] | None:
    from gamingcreator.application.asr_word_timing import AsrWord
    from gamingcreator.domain.time import SourceRange

    rows = document.get("words")
    if type(rows) is not list:
        raise _damaged_words(str(document.get("runId", "")))
    if not rows:
        return None
    words = []
    for row in rows:
        if type(row) is not dict:
            raise _damaged_words(str(document.get("runId", "")))
        start, end, text = row.get("startUs"), row.get("endUs"), row.get("text")
        if (
            type(start) is not int
            or type(end) is not int
            or type(text) is not str
            or not text.strip()
        ):
            raise _damaged_words(str(document.get("runId", "")))
        if not 0 <= start < end <= duration_us:
            raise _damaged_words(str(document.get("runId", "")))
        words.append(AsrWord(media_id, SourceRange(start, end, duration_us), text))
    return tuple(words)


async def _load_verified_asr_words(
    project: Path, run_id: str, result_hash: str
) -> tuple[AsrWord, ...] | None:
    """Explicit bindings must verify; only a trusted empty result permits fallback."""
    document = await load_asr_words_projection(project, run_id, result_hash)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        bundle = await store.load_media_bundle(run_id)
        asset = bundle.asset
        if asset is None:
            raise _missing_words(run_id)
        return _words_from_document(document, asset.media_id, asset.duration_us)
    finally:
        await store.close()


async def load_trusted_asr_words(
    project: Path,
    run_id: str,
    result_hash: str,
    *,
    strict: bool = False,
) -> tuple[AsrWord, ...] | None:
    """Preserve optional-reader compatibility; explicit render bindings use strict mode."""
    try:
        return await _load_verified_asr_words(project, run_id, result_hash)
    except AppError:
        if strict:
            raise
        return None


def parse_word_highlight_request(
    request: dict[str, object],
) -> tuple[bool, tuple[str, str] | None]:
    """开关关闭时不启用词级烧录；绑定必须是明确的任务和校对码。"""
    if "wordHighlights" not in request and "asrWords" not in request:
        return False, None
    if "wordHighlights" in request and type(request["wordHighlights"]) is not bool:
        raise ValueError("word highlight flag")
    enabled = request.get("wordHighlights") is True
    if "asrWords" not in request:
        return enabled, None
    raw = request["asrWords"]
    if not isinstance(raw, dict) or set(raw) != {"runId", "resultHash"}:
        raise ValueError("word highlight binding")
    run_id = raw.get("runId")
    result_hash = raw.get("resultHash")
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or not isinstance(result_hash, str)
        or not result_hash.strip()
    ):
        raise ValueError("word highlight binding")
    return enabled, (run_id, result_hash)


async def resolve_word_burn_cues(
    project: Path,
    plan: RenderPlan,
    segment_cues: Iterable[SubtitleCue],
    request: dict[str, object],
    reserved_clip_indexes: Iterable[int] | None = None,
) -> tuple[SubtitleCue, ...] | None:
    """只有烧录且开关打开并核对过结果时，才给出词级烧录字幕。"""
    from gamingcreator.application.creation_subtitles import present_subtitles

    if request.get("subtitleMode") != "burn":
        return None
    enabled, binding = parse_word_highlight_request(request)
    if not enabled or binding is None:
        return None
    words = await load_trusted_asr_words(project, binding[0], binding[1], strict=True)
    if words and not any(clip.asset.media_id == words[0].media_id for clip in plan.clips):
        raise AppError("asr.words_identity", "逐词结果不属于成片素材。", ExitCode.INPUT)
    burned = present_subtitles(
        segment_cues,
        words=words,
        sidecar_available=words is not None,
        plan=plan,
        reserved_clip_indexes=reserved_clip_indexes,
    )
    return burned.cues if burned.word_highlights else None
