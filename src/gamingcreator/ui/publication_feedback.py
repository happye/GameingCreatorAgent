"""Local outcome observations bound to one verified platform package."""

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs


SCHEMA = "creation-publication-feedback-v1"
SCOPE = frozenset({"projectId", "publicationJobId", "packageJobId", "packageVideoSha256"})
METRICS = frozenset({"ctrBps", "retention3sBps", "completionBps"})
FIELDS = {"source", "observedOn", "postUrl", "metrics"}
ID = re.compile(r"[a-f0-9]{32}")


def _input(message: str) -> AppError:
    return AppError("creation.feedback_input", message, ExitCode.INPUT)


def _digest(document: dict[str, Any]) -> str:
    raw = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _target(jobs: "CreationJobs", value: dict[str, Any]) -> dict[str, Any]:
    ids = (value["publicationJobId"], value["packageJobId"])
    if not all(isinstance(item, str) and ID.fullmatch(item) for item in ids):
        raise _input("请选择已生成的发布版本和平台包。")
    state = jobs.get(value["packageJobId"])
    package = state.get("package", {})
    if (
        state["kind"] != "package"
        or state["status"] != "completed"
        or state["projectId"] != value["projectId"]
        or package.get("publicationJobId") != value["publicationJobId"]
        or package.get("artifacts", {}).get("video.mp4", {}).get("sha256")
        != value["packageVideoSha256"]
    ):
        raise _input("平台包身份或成片已变化，请重新打开对应的发布版本。")
    return {
        **{key: value[key] for key in SCOPE},
        "publicationReceiptSha256": package["expectedPublicationReceiptSha256"],
        "packageZipSha256": package["artifacts"]["package.zip"]["sha256"],
        "platform": package["profile"]["Platform"],
    }


def _observation(value: dict[str, Any]) -> dict[str, Any]:
    if value["source"] not in ("creator", "test"):
        raise _input("请选择手录或测试来源。")
    observed = value["observedOn"]
    try:
        if not isinstance(observed, str) or date.fromisoformat(observed).isoformat() != observed:
            raise ValueError("Expected an ISO calendar date")
    except ValueError as error:
        raise _input("请填写有效的观察日期。") from error
    metrics = value["metrics"]
    if (
        not isinstance(metrics, dict)
        or set(metrics) != METRICS
        or any(
            metric is not None and (type(metric) is not int or not 0 <= metric <= 10_000)
            for metric in metrics.values()
        )
    ):
        raise _input("指标须留空或在 0–100% 内，最多保留两位小数。")
    url = value["postUrl"]
    if url is not None:
        try:
            if not isinstance(url, str) or len(url) > 2048 or re.search(r"[\x00-\x20\x7f\\]", url):
                raise ValueError("Invalid URL text")
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
                raise ValueError("Expected a public HTTPS URL")
        except ValueError as error:
            raise _input("帖子链接须为 HTTPS 地址，或留空。") from error
    if url is None and all(metric is None for metric in metrics.values()):
        raise _input("请填写至少一个指标或帖子链接。")
    return {key: value[key] for key in FIELDS}


def _directory(jobs: "CreationJobs", package_id: str) -> Path:
    return jobs.safe(jobs.root / "publication-feedback" / package_id)


def _read(jobs: "CreationJobs", path: Path, target: dict[str, Any]) -> dict[str, Any]:
    record = json.loads(read_bounded(jobs.safe(path), 16_384))
    if not isinstance(record, dict):
        raise ValueError("Invalid feedback document")
    digest = record.pop("documentSha256", None)
    if (
        set(record) != FIELDS | {"schemaVersion", "target", "recordedAt", "observationId"}
        or record.get("schemaVersion") != SCHEMA
        or record.get("observationId") != path.stem
        or record.get("target") != target
        or _digest(record) != digest
    ):
        raise ValueError("Feedback identity or checksum changed")
    return {**record, "documentSha256": digest}


def history(jobs: "CreationJobs", query: dict[str, Any]) -> dict[str, Any]:
    if set(query) != SCOPE:
        raise _input("请提供完整的平台包身份。")
    target = _target(jobs, query)
    directory = _directory(jobs, target["packageJobId"])
    records = []
    if directory.exists():
        try:
            records = [
                _read(jobs, path, target)
                for path in directory.glob("*.json")
                if ID.fullmatch(path.stem)
            ]
        except (OSError, ValueError) as error:
            raise AppError(
                "creation.feedback_integrity", "成效记录校验失败，请保留原记录。", ExitCode.STORAGE
            ) from error
    records.sort(
        key=lambda row: (row["observedOn"], row["recordedAt"], row["observationId"]), reverse=True
    )
    return {"target": target, "records": records}


def record(jobs: "CreationJobs", value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SCOPE | FIELDS:
        raise _input("请填写完整的发布成效参数。")
    input_fields = _observation(value)
    target = _target(jobs, value)
    directory = _directory(jobs, target["packageJobId"])
    directory.mkdir(parents=True, exist_ok=True)
    observation_id = _digest({"target": target, **input_fields})[:32]
    path = directory / f"{observation_id}.json"
    jobs.safe(directory / ".analysis-writer.lock")
    lock = ProjectWriterLock(directory)
    lock.acquire()
    try:
        if path.exists():
            saved = _read(jobs, path, target)
            if {key: saved[key] for key in FIELDS} != input_fields:
                raise AppError(
                    "creation.feedback_conflict",
                    "已保存的成效记录与本次请求冲突。",
                    ExitCode.STORAGE,
                )
            return saved
        payload = {
            "schemaVersion": SCHEMA,
            "target": target,
            "observationId": observation_id,
            **input_fields,
            "recordedAt": datetime.now(UTC).isoformat(),
        }
        saved = {**payload, "documentSha256": _digest(payload)}
        jobs.save(path, saved)
        return saved
    finally:
        lock.close()
