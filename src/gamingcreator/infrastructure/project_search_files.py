"""Exclusive project-search records; receipt is written last, without SQLite changes."""

import hashlib
import json
import os
import re
from pathlib import Path

from gamingcreator.domain.errors import AppError, ExitCode

MAX_RECORD_BYTES = 8 * 1024 * 1024


def _directory(project: Path, search_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", search_id):
        raise AppError("input.project_search", "查询记录身份无效。", ExitCode.INPUT)
    project = project.resolve()
    directory = project / "project-searches" / search_id
    if not directory.resolve().is_relative_to(project):
        raise AppError("storage.project_search", "查询目录超出项目。", ExitCode.STORAGE)
    return directory


def _bytes(document: dict[str, object]) -> bytes:
    data = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError("Oversized project-search record.")
    return data


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_project_search(project: Path, document: dict[str, object]) -> Path:
    search_id = document.get("searchId")
    if type(search_id) is not str or document.get("schemaVersion") != "project-search-v1":
        raise AppError("input.project_search", "查询记录版本／身份无效。", ExitCode.INPUT)
    directory = _directory(project, search_id)
    try:
        data = _bytes(document)
        directory.mkdir(parents=True)
        _write(directory / "result.json", data)
        _write(
            directory / "receipt.json",
            _bytes(
                {
                    "schemaVersion": "project-search-receipt-v1",
                    "searchId": search_id,
                    "resultSha256": hashlib.sha256(data).hexdigest(),
                    "modelAnalysisCalls": 0,
                    "newReservations": 0,
                }
            ),
        )
        return directory / "result.json"
    except (OSError, ValueError, UnicodeError):
        raise AppError(
            "storage.project_search", "查询记录保存失败，请保留项目中的原记录。", ExitCode.STORAGE
        ) from None


def read_project_search(project: Path, search_id: str) -> dict[str, object]:
    directory = _directory(project, search_id)
    try:
        documents = []
        for name in ("result.json", "receipt.json"):
            path = directory / name
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Record file escaped its directory.")
            with path.open("rb") as stream:
                data = stream.read(MAX_RECORD_BYTES + 1)
            if len(data) > MAX_RECORD_BYTES:
                raise ValueError("Oversized record.")
            documents.append(data)
        raw, receipt = (json.loads(data) for data in documents)
        if (
            type(raw) is not dict
            or raw.get("schemaVersion") != "project-search-v1"
            or raw.get("searchId") != search_id
            or receipt
            != {
                "schemaVersion": "project-search-receipt-v1",
                "searchId": search_id,
                "resultSha256": hashlib.sha256(documents[0]).hexdigest(),
                "modelAnalysisCalls": 0,
                "newReservations": 0,
            }
        ):
            raise ValueError("Receipt does not match the saved record.")
        return raw
    except (OSError, ValueError, UnicodeError):
        raise AppError(
            "storage.project_search", "查询记录缺失或校验失败，请保留原资料。", ExitCode.STORAGE
        ) from None
