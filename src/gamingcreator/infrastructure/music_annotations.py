"""Receipt-bound creator annotations kept apart from immutable music registration."""

import hashlib
import json
from typing import Any
from uuid import uuid4

from gamingcreator.domain.creation_audio import _hex
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.music_annotation import annotation_values
from gamingcreator.infrastructure.file_sharing import retry_file_sharing
from gamingcreator.infrastructure.local_files import read_bounded, write_exclusive_text
from gamingcreator.infrastructure.music_library import MusicTrack, _safe
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock

SCHEMA = "music-annotation-v1"


def _encode(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identity(track: MusicTrack) -> dict[str, str]:
    return {
        "schemaVersion": SCHEMA,
        "trackId": track.track_id,
        "trackReceiptSha256": track.receipt_sha256,
    }


def read_annotation(track: MusicTrack) -> dict[str, Any] | None:
    path = _safe(track.path.parent / "annotation.json")
    if not path.exists():
        return None
    try:
        document = json.loads(read_bounded(path, 4096))
    except RecursionError as error:
        raise ValueError("曲目标注文件已损坏。") from error
    identity = _identity(track)
    if (
        not isinstance(document, dict)
        or set(document) != identity.keys() | {"values", "sha256"}
        or any(document[key] != value for key, value in identity.items())
    ):
        raise ValueError("曲目标注与登记回执不匹配。")
    sha = document.pop("sha256")
    values = annotation_values(document["values"], track.duration_us)
    if sha != hashlib.sha256(_encode(document).encode()).hexdigest():
        raise ValueError("曲目标注文件已损坏。")
    return {**values, "annotationSha256": sha}


def save_annotation(
    track: MusicTrack, value: dict[str, Any], expected: str | None
) -> dict[str, Any]:
    if expected is not None:
        _hex(expected, 64)
    fields = annotation_values(value, track.duration_us)
    content = {**_identity(track), "values": fields}
    sha = hashlib.sha256(_encode(content).encode()).hexdigest()
    annotation = {**fields, "annotationSha256": sha}
    directory = track.path.parent
    path = _safe(directory / "annotation.json")
    _safe(directory / ".analysis-writer.lock")
    lock = ProjectWriterLock(directory)
    lock.acquire()
    try:
        current = read_annotation(track)
        current_sha = current["annotationSha256"] if current else None
        if current_sha == sha:
            return annotation
        if current_sha != expected:
            raise AppError(
                "creation.conflict", "曲目标注已更新，请刷新曲库后再编辑。", ExitCode.INPUT
            )
        temporary = _safe(directory / f"annotation-{uuid4().hex}.tmp")
        try:
            write_exclusive_text(temporary, _encode({**content, "sha256": sha}))
            retry_file_sharing(lambda: temporary.replace(path))
        finally:
            temporary.unlink(missing_ok=True)
        return annotation
    finally:
        lock.close()
