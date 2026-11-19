"""Local outcome observations bound to one verified platform package."""

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from gamingcreator.application.creation_feedback import (
    OUTCOME_METRICS,
    CreatorStructureChoice,
    OutcomeReference,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.platform_profile import profile_digest
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.package_jobs import DOWNLOADS
from gamingcreator.ui.revision_jobs import load_chain

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs


SCHEMA = "creation-publication-feedback-v1"
SCOPE = frozenset({"projectId", "publicationJobId", "packageJobId", "packageVideoSha256"})
METRICS = OUTCOME_METRICS
FIELDS = {"source", "observedOn", "postUrl", "metrics"}
ID = re.compile(r"[a-f0-9]{32}")


def _input(message: str) -> AppError:
    return AppError("creation.feedback_input", message, ExitCode.INPUT)


def _digest(document: dict[str, Any]) -> str:
    raw = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _package_target(jobs: "CreationJobs", package_id: str) -> dict[str, Any]:
    if not isinstance(package_id, str) or not ID.fullmatch(package_id):
        raise _input("请选择已生成的发布版本和平台包。")
    state = jobs.get(package_id)
    if state["kind"] != "package" or state["status"] != "completed":
        raise _input("平台包身份或成片已变化，请重新打开对应的发布版本。")
    package = state["package"]
    return {
        "projectId": state["projectId"],
        "packageJobId": package_id,
        "publicationJobId": package["publicationJobId"],
        "packageVideoSha256": package["artifacts"]["video.mp4"]["sha256"],
        "publicationReceiptSha256": package["expectedPublicationReceiptSha256"],
        "packageZipSha256": package["artifacts"]["package.zip"]["sha256"],
        "platform": package["profile"]["Platform"],
    }


def _target(jobs: "CreationJobs", value: dict[str, Any]) -> dict[str, Any]:
    target = _package_target(jobs, value["packageJobId"])
    if any(target[key] != value[key] for key in SCOPE):
        raise _input("平台包身份或成片已变化，请重新打开对应的发布版本。")
    return target


def _receipt_target(jobs: "CreationJobs", package_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use the receipts of previously verified observations without reopening media files."""
    directory = jobs.directory(package_id)
    state = jobs.read(directory / "status.json")
    if state["kind"] != "package" or state["status"] != "completed":
        raise ValueError("Expected completed package")
    stored = jobs._projection_identity(directory, state)
    request = stored["request"]
    raw = read_bounded(jobs.safe(directory / "result/receipt.json"))
    receipt = json.loads(raw)
    profile = request["profile"]
    parent = request["expectedPublicationReceiptSha256"]
    if (
        hashlib.sha256(raw).hexdigest() != state["resultReceiptSha256"]
        or state["parentJobId"] != request["publicationJobId"]
        or receipt["parentPublicationReceiptSha256"] != parent
        or receipt["profileSha256"] != profile_digest(profile)
        or set(receipt["files"]) != set(DOWNLOADS)
    ):
        raise ValueError("Platform package receipt changed")
    return {
        "projectId": state["projectId"],
        "packageJobId": package_id,
        "publicationJobId": request["publicationJobId"],
        "publicationReceiptSha256": parent,
        "packageVideoSha256": receipt["files"]["video.mp4"],
        "packageZipSha256": receipt["files"]["package.zip"],
        "platform": profile["Platform"],
    }, profile


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
    return {"target": target, "records": _observations(jobs, target)}


def _observations(jobs: "CreationJobs", target: dict[str, Any]) -> list[dict[str, Any]]:
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
    return records


def _lineage(
    jobs: "CreationJobs", target: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    publication = jobs.directory(target["publicationJobId"])
    saved = jobs.read(publication / "status.json")
    if (
        saved["resultReceiptSha256"] != target["publicationReceiptSha256"]
        or saved["kind"] != "publication"
        or saved["status"] != "completed"
        or saved["projectId"] != target["projectId"]
    ):
        raise ValueError("Publication receipt changed")
    pub = jobs._projection_identity(publication, saved)["request"]
    render = jobs.directory(pub["renderJobId"])
    rendered = jobs.read(render / "status.json")
    if (
        rendered["resultReceiptSha256"] != pub["expectedRenderReceiptSha256"]
        or saved["parentJobId"] != pub["renderJobId"]
        or rendered["kind"] != "render"
        or rendered["status"] != "completed"
        or rendered["projectId"] != target["projectId"]
    ):
        raise ValueError("Render receipt changed")
    stored = jobs._projection_identity(render, rendered)
    request = stored["request"]
    if "revisionJobId" in request:
        chain = load_chain(jobs, request["revisionJobId"], read_only=True)
        if (
            chain.digest != stored["parentReceiptSha256"]
            or rendered["parentJobId"] != request["revisionJobId"]
        ):
            raise ValueError("Rendered revision receipt changed")
        root, plan_id = chain.root_id, chain.plan_id
    else:
        root, plan_id = request["planJobId"], request["planId"]
    source = jobs.directory(root)
    state = jobs.read(source / "status.json")
    if state["kind"] != "plan" or state["status"] != "completed":
        raise ValueError("Render has no completed source plan")
    verified = jobs.verify(source, state)
    if "revisionJobId" not in request and (
        verified["resultReceiptSha256"] != stored["parentReceiptSha256"]
        or rendered["parentJobId"] != root
    ):
        raise ValueError("Rendered plan receipt changed")
    original = jobs.read(source / "request.json")["request"]
    plan = next((item for item in verified["plans"] if item["id"] == plan_id), None)
    if plan is None or original["projectId"] != target["projectId"]:
        raise ValueError("Plan project changed")
    return {
        "title": pub["title"],
        "workId": original.get("workId"),
        "contentType": verified["brief"]["contentType"],
        "label": plan["structure"],
        "shortVersion": "variant" in profile["Fields"],
        "sourceJobId": root,
        "sourcePlanId": plan_id,
        "sourceReceiptSha256": verified.get("feedbackReceiptSha256") if plan["ready"] else None,
    }


def _choice(
    target: dict[str, Any], lineage: dict[str, Any], row: dict[str, Any], metric: str
) -> dict[str, Any] | None:
    value = row["metrics"][metric]
    if row["source"] != "creator" or value is None or lineage["sourceReceiptSha256"] is None:
        return None
    outcome = OutcomeReference(
        target["packageJobId"],
        row["observationId"],
        row["documentSha256"],
        target["platform"],
        row["observedOn"],
        metric,
        value,
    )
    return {
        **{key: lineage[key] for key in ("sourceJobId", "sourcePlanId", "sourceReceiptSha256")},
        "outcome": outcome.to_json(),
    }


def _compared_rows(
    jobs: "CreationJobs", target: dict[str, Any], lineage: dict[str, Any], metric: str
) -> list[dict[str, Any]]:
    records = _observations(jobs, target)
    result = []
    for source in ("creator", "test"):
        latest = next((row for row in records if row["source"] == source), None)
        if latest is not None:
            result.append(
                {
                    "title": lineage["title"],
                    "planLabel": lineage["label"],
                    "packageJobId": target["packageJobId"],
                    "source": source,
                    "observedOn": latest["observedOn"],
                    "metrics": latest["metrics"],
                    "shortVersion": lineage.get("shortVersion", False),
                    "choice": _choice(target, lineage, latest, metric),
                }
            )
    return result


def compare(jobs: "CreationJobs", query: dict[str, Any]) -> dict[str, Any]:
    if set(query) != SCOPE | {"metric"} or query["metric"] not in METRICS:
        raise _input("请选择要比较的指标与平台包。")
    metric = query["metric"]
    anchor, profile = _receipt_target(jobs, query["packageJobId"])
    if any(anchor[key] != query[key] for key in SCOPE):
        raise _input("平台包身份或成片已变化，请重新打开对应的发布版本。")
    original = _lineage(jobs, anchor, profile)
    rows = _compared_rows(jobs, anchor, original, metric)
    skipped = 0
    root = jobs.safe(jobs.root / "publication-feedback")
    for directory in root.iterdir() if root.exists() else ():
        if directory.name == anchor["packageJobId"] or not ID.fullmatch(directory.name):
            continue
        try:
            job = jobs.directory(directory.name)
            state = jobs.read(job / "status.json")
            if state["projectId"] != anchor["projectId"] or state["kind"] != "package":
                continue
            target, profile = _receipt_target(jobs, directory.name)
            if target["platform"] != anchor["platform"]:
                continue
            lineage = _lineage(jobs, target, profile)
            if all(lineage[key] == original[key] for key in ("workId", "contentType")):
                rows.extend(_compared_rows(jobs, target, lineage, metric))
        except (OSError, ValueError, AppError, KeyError, StopIteration):
            skipped += 1
    rows.sort(
        key=lambda row: (
            row["source"] == "test",
            row["metrics"][metric] is None,
            -(row["metrics"][metric] or 0),
            row["title"],
            row["packageJobId"],
        )
    )
    return {
        "rows": rows,
        "workId": original["workId"],
        "contentType": original["contentType"],
        "platform": anchor["platform"],
        "skipped": skipped,
    }


def verify_reference(
    jobs: "CreationJobs", request: dict[str, Any], choice: CreatorStructureChoice
) -> None:
    reference = choice.outcome
    if reference is None:
        return
    target, profile = _receipt_target(jobs, reference.package_job_id)
    lineage = _lineage(jobs, target, profile)
    path = _directory(jobs, target["packageJobId"]) / f"{reference.observation_id}.json"
    row = _read(jobs, path, target)
    if (
        target["projectId"] != request["projectId"]
        or lineage["workId"] != request.get("workId")
        or lineage["contentType"] != request["brief"]["contentType"]
        or reference.platform not in request["brief"]["platforms"]
        or _choice(target, lineage, row, reference.metric) != choice.to_json()
    ):
        raise ValueError("Outcome reference no longer matches the selected plan")


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
