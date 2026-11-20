"""独立的词级识别结果文件。整体 hash 放在旁边的回执里，不会改写旧的段级转录。"""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from gamingcreator.application.asr_word_timing import AsrWord
from gamingcreator.application.providers import InvocationMetadata
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import AudioEvidence, MediaAsset
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock

SCHEMA_VERSION = "asr-words-v1"
RECEIPT_SCHEMA_VERSION = "asr-words-receipt-v1"
WORDS_FILENAME = "words.json"
RECEIPT_FILENAME = "receipt.json"
_RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _fail(code: str, message: str) -> AppError:
    return AppError(code, message, ExitCode.STORAGE)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _clock_json(value: object) -> dict[str, int]:
    numerator = getattr(value, "numerator", None)
    denominator = getattr(value, "denominator", None)
    if type(numerator) is not int or type(denominator) is not int:
        raise TypeError("时钟分数无效。")
    return {"numerator": numerator, "denominator": denominator}


def clock_digest(clock: AudioEvidence, asset: MediaAsset) -> str:
    return _digest(
        {
            "sampleRate": clock.sample_rate,
            "sampleCount": clock.sample_count,
            "trimEndPts": clock.trim_end_pts,
            "decodedSampleCount": clock.decoded_sample_count,
            "originSeconds": _clock_json(asset.origin_seconds),
            "durationUs": asset.duration_us,
            "frames": [
                {
                    "sampleOffset": frame.sample_offset,
                    "sampleCount": frame.sample_count,
                    "pts": frame.pts,
                    "timeBase": _clock_json(frame.time_base),
                }
                for frame in clock.frames
            ],
        }
    )


def _require_text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise _fail("asr.words_identity", name + "无效。")
    return value


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise _fail("asr.words_identity", name + "无效。")
    return value


def _require_run_id(run_id: object) -> str:
    if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
        raise _fail("asr.words_path", "识别任务编号无效。")
    return run_id


def encode_words_document(
    *,
    run_id: str,
    media_id: str,
    source_sha256: str,
    audio_sha256: str,
    clock_digest_value: str,
    model: str,
    revision: str,
    words: tuple[AsrWord, ...] | list[AsrWord],
) -> bytes:
    run_id = _require_run_id(run_id)
    media_id = _require_text(media_id, "素材编号")
    source_sha256 = _require_sha256(source_sha256, "原片校验")
    audio_sha256 = _require_sha256(audio_sha256, "音频校验")
    clock_digest_value = _require_sha256(clock_digest_value, "时钟身份")
    model = _require_text(model, "识别模型")
    revision = _require_text(revision, "模型版本")
    rows = []
    for word in words:
        if word.media_id != media_id:
            raise _fail("asr.words_identity", "词级结果里的来源和这条记录不一致。")
        rows.append(
            {
                "startUs": word.source_range.start_us,
                "endUs": word.source_range.end_us,
                "text": word.text,
            }
        )
    document = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "mediaId": media_id,
        "sourceSha256": source_sha256,
        "audioSha256": audio_sha256,
        "clockDigest": clock_digest_value,
        "model": model,
        "revision": revision,
        "words": rows,
    }
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def words_payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def encode_words_receipt(result_hash: str, metadata: InvocationMetadata | None = None) -> bytes:
    if type(result_hash) is not str or not _HASH.fullmatch(result_hash):
        raise _fail("asr.words_identity", "词级结果校验无效。")
    document: dict[str, object] = {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "wordsSha256": result_hash,
    }
    if metadata is not None:
        usage = metadata.usage
        document["execution"] = {
            "provider": metadata.provider,
            "requestedModel": metadata.requested_model,
            "actualModel": metadata.actual_model,
            "modelRevision": metadata.model_revision,
            "promptVersion": metadata.prompt_version,
            "schemaVersion": metadata.schema_version,
            "attempt": metadata.attempt,
            "priceVersion": metadata.price_version,
            "elapsedMs": metadata.elapsed_ms,
            "requestId": metadata.request_id,
            "inputTokens": usage.input_tokens,
            "cachedInputTokens": usage.cached_input_tokens,
            "outputTokens": usage.output_tokens,
            "costCny": None if usage.cost_cny is None else str(usage.cost_cny),
            "costStatus": str(usage.cost_status),
            "executionDetails": json.loads(metadata.execution_details or "{}"),
        }
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _confined(root: Path, path: Path) -> Path:
    if _linked(root):
        raise _fail("asr.words_path", "项目目录不能是符号链接。")
    current = path
    while True:
        if _linked(current):
            raise _fail("asr.words_path", "词级结果路径拒绝符号链接。")
        if current == root:
            break
        if current.parent == current:
            raise _fail("asr.words_path", "词级结果路径逃出了项目目录。")
        current = current.parent
    try:
        resolved_root = root.resolve()
        cursor = path
        missing: list[str] = []
        while not cursor.exists() and cursor != cursor.parent:
            missing.append(cursor.name)
            cursor = cursor.parent
        resolved = cursor.resolve()
        for name in reversed(missing):
            resolved = resolved / name
    except OSError:
        raise _fail("asr.words_path", "词级结果路径逃出了项目目录。") from None
    if not resolved.is_relative_to(resolved_root):
        raise _fail("asr.words_path", "词级结果路径逃出了项目目录。")
    return resolved


def asr_words_directory(project: Path, run_id: str, result_hash: str) -> Path:
    root = project.resolve()
    run_id = _require_run_id(run_id)
    if type(result_hash) is not str or not _HASH.fullmatch(result_hash):
        raise _fail("asr.words_path", "词级结果校验无效。")
    return _confined(root, root / "runs" / run_id / "asr-words" / result_hash)


def load_reusable_asr_words_sidecar(
    project: Path,
    *,
    run_id: str,
    media_id: str,
    source_sha256: str,
    audio_sha256: str,
    clock: AudioEvidence,
    asset: MediaAsset,
    model: str,
    revision: str,
    result_hash: str,
) -> Path | None:
    """Return a published sidecar only when source, model, clock and whole-file hash match."""
    if asset.media_id != media_id or asset.sha256 != source_sha256 or clock.sha256 != audio_sha256:
        return None
    try:
        directory = asr_words_directory(project, run_id, result_hash)
    except AppError:
        return None
    return _verified_sidecar(
        directory,
        run_id=run_id,
        media_id=media_id,
        source_sha256=source_sha256,
        audio_sha256=audio_sha256,
        clock_digest_value=clock_digest(clock, asset),
        model=model,
        revision=revision,
        result_hash=result_hash,
    )


def _verified_sidecar(
    directory: Path,
    *,
    run_id: str,
    media_id: str,
    source_sha256: str,
    audio_sha256: str,
    clock_digest_value: str,
    model: str,
    revision: str,
    result_hash: str,
) -> Path | None:
    words_path = directory / WORDS_FILENAME
    receipt_path = directory / RECEIPT_FILENAME
    if (
        _linked(words_path)
        or _linked(receipt_path)
        or not words_path.is_file()
        or not receipt_path.is_file()
    ):
        return None
    try:
        payload = read_bounded(words_path)
        receipt_payload = read_bounded(receipt_path)
        receipt = json.loads(receipt_payload.decode("utf-8"))
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if (
        type(receipt) is not dict
        or receipt.get("schemaVersion") != RECEIPT_SCHEMA_VERSION
        or receipt.get("wordsSha256") != result_hash
        or words_payload_sha256(payload) != result_hash
        or directory.name != result_hash
        or type(document) is not dict
        or document.get("schemaVersion") != SCHEMA_VERSION
        or document.get("runId") != run_id
        or document.get("mediaId") != media_id
        or document.get("sourceSha256") != source_sha256
        or document.get("audioSha256") != audio_sha256
        or document.get("clockDigest") != clock_digest_value
        or document.get("model") != model
        or document.get("revision") != revision
        or type(document.get("words")) is not list
    ):
        return None
    return directory


def publish_asr_words_sidecar(
    project: Path,
    *,
    run_id: str,
    media_id: str,
    source_sha256: str,
    audio_sha256: str,
    clock: AudioEvidence,
    asset: MediaAsset,
    model: str,
    revision: str,
    words: tuple[AsrWord, ...] | list[AsrWord],
    metadata: InvocationMetadata | None = None,
) -> Path:
    if asset.media_id != media_id:
        raise _fail("asr.words_identity", "词级结果里的来源和这条记录不一致。")
    if asset.sha256 != source_sha256:
        raise _fail("asr.words_identity", "原片校验和记录不一致。")
    if clock.sha256 != audio_sha256:
        raise _fail("asr.words_identity", "音频校验和记录不一致。")
    payload = encode_words_document(
        run_id=run_id,
        media_id=media_id,
        source_sha256=source_sha256,
        audio_sha256=audio_sha256,
        clock_digest_value=clock_digest(clock, asset),
        model=model,
        revision=revision,
        words=words,
    )
    result_hash = words_payload_sha256(payload)
    directory = asr_words_directory(project, run_id, result_hash)
    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True)
    lock = ProjectWriterLock(parent)
    staging: Path | None = None
    published = False
    try:
        lock.acquire()
        reused = _verified_sidecar(
            directory,
            run_id=run_id,
            media_id=media_id,
            source_sha256=source_sha256,
            audio_sha256=audio_sha256,
            clock_digest_value=clock_digest(clock, asset),
            model=model,
            revision=revision,
            result_hash=result_hash,
        )
        if reused is not None:
            published = True
            return reused
        if (
            directory.exists()
            or (directory / WORDS_FILENAME).exists()
            or (directory / RECEIPT_FILENAME).exists()
        ):
            raise _fail("asr.words_exists", "词级结果已存在，不会覆盖旧文件。")
        staging = parent / (".tmp-" + uuid4().hex)
        staging.mkdir()
        _write_published_file(staging / WORDS_FILENAME, payload)
        _write_published_file(
            staging / RECEIPT_FILENAME, encode_words_receipt(result_hash, metadata)
        )
        staging.rename(directory)
        published = True
        return directory
    except FileExistsError:
        raise _fail("asr.words_exists", "词级结果已存在，不会覆盖旧文件。") from None
    finally:
        if not published and staging is not None and staging.exists() and staging != directory:
            shutil.rmtree(staging, ignore_errors=True)
        lock.close()


def _write_published_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise
    except OSError as error:
        raise ValueError("无法写入文件。") from error
