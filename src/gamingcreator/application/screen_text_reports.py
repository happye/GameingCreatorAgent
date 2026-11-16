"""只读读取已有屏幕文字（OCR）报告。

复用已有报告文件和画面指纹校验，不重新识别，也不写回原分析或数据库。
读失败时给出原因，不当成“没有文字”的成功结果；诊断里不带本机路径。
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from gamingcreator.application.ocr_frames import OCR_REPORT_VERSION

FRAME_TEXT_VERSION = "frame-text-v1"
MAX_CACHED_REPORT_BYTES = 16 * 1024 * 1024


def frames_digest(frames: Sequence[tuple[str, int]]) -> str:
    """Identity of the exact saved instants a report read, in order."""
    return hashlib.sha256(
        "".join(f"{evidence}\t{time_us}\n" for evidence, time_us in frames).encode()
    ).hexdigest()


def scanned_frames(saved: Sequence[tuple[str, int]], every: int) -> tuple[tuple[str, int], ...]:
    """The saved frames a scan with this step reads, in the order the OCR report lists them."""
    return tuple(sorted(saved, key=lambda item: (item[1], item[0])))[::every]


SUPPORTED = (FRAME_TEXT_VERSION, OCR_REPORT_VERSION)
MAX_SCREEN_TEXT_MATCHES = 10
NOTICE_UNPREPARED = "尚未准备屏幕文字，未开始新的识别任务。"
NOTICE_DAMAGED = "屏幕文字报告已损坏，不能使用这份结果，也不会开始新的识别任务。"
NOTICE_PERMISSION = "没有权限读取屏幕文字报告，未开始新的识别任务。"
NOTICE_UNAVAILABLE = "屏幕文字结果目前不可用，未开始新的识别任务。"
DAMAGED_REASONS = {
    "报告正文与整体校验回执不一致。",
    "报告整体校验回执无法读取。",
    "报告不是合法的 JSON。",
    "报告格式无效。",
    "报告的 schema 不受支持。",
    "报告过大，已拒绝读取。",
    "报告缺少必要字段。",
    "报告里的画面指纹与当前已保存帧对不上。",
    "报告里的画面指纹与报告内帧对不上。",
}


@dataclass(frozen=True)
class ScreenTextLine:
    text: str
    likely_text: bool | None = None


@dataclass(frozen=True)
class ScreenTextFrame:
    time_us: int
    lines: tuple[ScreenTextLine, ...]
    evidence_id: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class LoadedScreenTextReport:
    schema_version: str
    run_id: str
    source_sha256: str
    duration_us: int
    frames_digest: str | None
    every: int | None
    frames: tuple[ScreenTextFrame, ...]
    content_verified: bool = False


@dataclass(frozen=True)
class ScreenTextReportRead:
    ok: bool
    reason: str
    report: LoadedScreenTextReport | None


@dataclass(frozen=True)
class ScreenTextSource:
    """Registered footage identity for one run in the current project."""

    run_id: str
    source_sha256: str
    duration_us: int | None = None


@dataclass(frozen=True)
class BoundScreenTextFrame:
    run_id: str
    source_sha256: str
    evidence_id: str
    time_us: int
    lines: tuple[ScreenTextLine, ...]


@dataclass(frozen=True)
class ScreenTextHit:
    frame: BoundScreenTextFrame
    text: str


def accept_report_identity(
    read: ScreenTextReportRead,
    sources: Sequence[ScreenTextSource],
    query_run_ids: Sequence[str],
) -> ScreenTextReportRead:
    """Keep a report only when it belongs to this query and matches registered footage.

    A failed read stays a failed read. Wrong or stale sourceSha256 never becomes a hit.
    """
    if not read.ok or read.report is None:
        return read
    report = read.report
    allowed = set(query_run_ids)
    if report.run_id not in allowed:
        return _fail("这份报告不属于本次查询范围。")
    registered = next((item for item in sources if item.run_id == report.run_id), None)
    if registered is None:
        return _fail("这份报告不属于本次查询范围。")
    if report.source_sha256 != registered.source_sha256:
        return _fail("报告里的原片哈希已过期或与登记素材不一致，已排除。")
    if registered.duration_us is not None and report.duration_us != registered.duration_us:
        return _fail("报告里的原片身份与登记素材不一致，已排除。")
    return read


def bind_report_frames(
    report: LoadedScreenTextReport, saved: Sequence[tuple[str, int]]
) -> tuple[BoundScreenTextFrame, ...]:
    """Attach each OCR instant to a real saved frame id.

    Ambiguous times, unknown instants and mismatched ids are skipped.
    Evidence ids are taken from the registered frames, never invented.
    """
    instants = scanned_frames(saved, report.every or 1)
    unique_times = _unique_times(instants)
    bound: list[BoundScreenTextFrame] = []
    for frame in report.frames:
        evidence_id = _bound_evidence(frame, instants, unique_times)
        if evidence_id is None:
            continue
        bound.append(
            BoundScreenTextFrame(
                run_id=report.run_id,
                source_sha256=report.source_sha256,
                evidence_id=evidence_id,
                time_us=frame.time_us,
                lines=frame.lines,
            )
        )
    return tuple(bound)


def _unique_times(instants: Sequence[tuple[str, int]]) -> dict[int, str]:
    unique: dict[int, str] = {}
    ambiguous: set[int] = set()
    for evidence_id, time_us in instants:
        existing = unique.get(time_us)
        if existing is None:
            unique[time_us] = evidence_id
        elif existing != evidence_id:
            ambiguous.add(time_us)
    for time_us in ambiguous:
        unique.pop(time_us, None)
    return unique


def _bound_evidence(
    frame: ScreenTextFrame,
    instants: Sequence[tuple[str, int]],
    unique_times: dict[int, str],
) -> str | None:
    registered = set(instants)
    if frame.evidence_id:
        return frame.evidence_id if (frame.evidence_id, frame.time_us) in registered else None
    return unique_times.get(frame.time_us)


def screen_text_key(text: str) -> str:
    """Literal lookup key: compatibility-normalize, then case-fold. Never shown as output."""
    return unicodedata.normalize("NFKC", text).casefold()


def match_screen_text(
    frames: Sequence[BoundScreenTextFrame], query: str
) -> tuple[ScreenTextHit, ...]:
    """Keep original line text for hits. Do not slice the original with normalized indexes."""
    key = screen_text_key(query)
    if not key.strip():
        return ()
    hits: list[ScreenTextHit] = []
    for frame in frames:
        for line in frame.lines:
            if key in screen_text_key(line.text):
                hits.append(ScreenTextHit(frame, line.text))
    return unique_screen_text_hits(tuple(hits))


def unique_screen_text_hits(hits: Sequence[ScreenTextHit]) -> tuple[ScreenTextHit, ...]:
    """Drop repeated original lines on the same run and evidence.

    Different runs or different evidence ids stay distinct, even when the text matches.
    Several different lines at one instant keep their own identity.
    """
    seen: set[tuple[str, str, str]] = set()
    unique: list[ScreenTextHit] = []
    for hit in hits:
        key = (hit.frame.run_id, hit.frame.evidence_id, hit.text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return tuple(unique)


def screen_text_matches(
    hits: Sequence[ScreenTextHit], query_run_ids: Sequence[str]
) -> tuple[dict[str, object], ...]:
    """Stable official group: query run order, then source time, then original line order.

    At most ten rows. Never ranked by a similarity score, random value, or file mtime.
    """
    run_order = {run_id: index for index, run_id in enumerate(query_run_ids)}
    ranked = sorted(
        enumerate(hits),
        key=lambda item: (
            run_order.get(item[1].frame.run_id, len(run_order)),
            item[1].frame.time_us,
            item[0],
        ),
    )
    return tuple(_match_row(hit) for _, hit in ranked[:MAX_SCREEN_TEXT_MATCHES])


def _match_row(hit: ScreenTextHit) -> dict[str, object]:
    return {
        "runId": hit.frame.run_id,
        "sourceSha256": hit.frame.source_sha256,
        "evidenceId": hit.frame.evidence_id,
        "timeUs": hit.frame.time_us,
        "text": hit.text,
    }


def _unprepared_notice(diagnostics: Sequence[str]) -> str:
    if any("没有权限" in item for item in diagnostics):
        return NOTICE_PERMISSION
    if any(item in DAMAGED_REASONS for item in diagnostics):
        return NOTICE_DAMAGED
    if any("不可用" in item for item in diagnostics):
        return NOTICE_UNAVAILABLE
    return diagnostics[0]


def collect_screen_text_group(
    *,
    query: str,
    query_run_ids: Sequence[str],
    sources: Sequence[ScreenTextSource],
    reports: Sequence[Path | None],
    saved_by_run: Mapping[str, Sequence[tuple[str, int]]],
) -> dict[str, object]:
    """Build the official group from existing reports only. Missing reports yield an empty group."""
    hits: list[ScreenTextHit] = []
    diagnostics: list[str] = []
    accepted = 0
    for path in reports:
        accepted += _collect_one(
            path, query, query_run_ids, sources, saved_by_run, hits, diagnostics
        )
    prepared = accepted > 0
    if prepared:
        notice = ""
    elif diagnostics:
        notice = _unprepared_notice(diagnostics)
    else:
        notice = NOTICE_UNPREPARED
    return {
        "screenTextMatches": screen_text_matches(unique_screen_text_hits(hits), query_run_ids),
        "screenTextPrepared": prepared,
        "screenTextNotice": notice,
        "screenTextDiagnostics": tuple(diagnostics),
    }


def _collect_one(
    path: Path | None,
    query: str,
    query_run_ids: Sequence[str],
    sources: Sequence[ScreenTextSource],
    saved_by_run: Mapping[str, Sequence[tuple[str, int]]],
    hits: list[ScreenTextHit],
    diagnostics: list[str],
) -> int:
    if path is None:
        return 0
    read = read_screen_text_report(path)
    if not read.ok and read.reason == "找不到这份屏幕文字报告。":
        return 0
    if not read.ok or read.report is None:
        _add_diagnostic(diagnostics, read.reason)
        return 0
    identified = accept_report_identity(read, sources, query_run_ids)
    if not identified.ok or identified.report is None:
        _add_diagnostic(diagnostics, identified.reason)
        return 0
    if not identified.report.content_verified:
        _add_diagnostic(diagnostics, "旧屏幕文字报告没有整体校验回执，无法验证正文，已跳过检索。")
        return 0
    digest = check_frames_digest(identified.report, saved_by_run.get(identified.report.run_id, ()))
    if not digest.ok or digest.report is None:
        _add_diagnostic(diagnostics, digest.reason)
        return 0
    bound = bind_report_frames(digest.report, saved_by_run.get(digest.report.run_id, ()))
    hits.extend(match_screen_text(bound, query))
    return 1


def _add_diagnostic(diagnostics: list[str], reason: str) -> None:
    safe = _safe_reason(reason)
    if safe and safe not in diagnostics:
        diagnostics.append(safe)


def _safe_reason(reason: str) -> str:
    if "\\" in reason or "/" in reason:
        return "这份屏幕文字报告无法读取。"
    return reason


def attach_screen_text_group(
    search_result: dict[str, object], group: dict[str, object]
) -> dict[str, object]:
    """Put the screen-text group beside the original retrieval, without changing it."""
    return {**search_result, **group}


def read_screen_text_report(path: Path) -> ScreenTextReportRead:
    """Parse one existing report and check its schema. Never writes, never scans."""
    try:
        size = path.stat().st_size
    except PermissionError:
        return _fail("没有权限读取屏幕文字报告。")
    except OSError:
        return _fail("找不到这份屏幕文字报告。")
    if size > MAX_CACHED_REPORT_BYTES:
        return _fail("报告过大，已拒绝读取。")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CACHED_REPORT_BYTES + 1)
        if len(raw) > MAX_CACHED_REPORT_BYTES:
            return _fail("报告过大，已拒绝读取。")
        payload = json.loads(raw)
    except PermissionError:
        return _fail("没有权限读取屏幕文字报告。")
    except (OSError, ValueError):
        return _fail("报告不是合法的 JSON。")
    if not isinstance(payload, dict):
        return _fail("报告格式无效。")
    parsed = _parse(payload)
    if not parsed.ok or parsed.report is None:
        return parsed
    receipt = path.with_name(path.name + ".sha256")
    try:
        with receipt.open("rb") as stream:
            expected = stream.read(66).decode("ascii").strip()
    except FileNotFoundError:
        return parsed  # Legacy viewing only; search explicitly refuses unverified text.
    except (OSError, UnicodeError):
        return _fail("报告整体校验回执无法读取。")
    if not _is_sha(expected) or expected != hashlib.sha256(raw).hexdigest():
        return _fail("报告正文与整体校验回执不一致。")
    return ScreenTextReportRead(True, "", replace(parsed.report, content_verified=True))


def check_frames_digest(
    report: LoadedScreenTextReport, saved: Sequence[tuple[str, int]]
) -> ScreenTextReportRead:
    """Reuse the workbench framesDigest check against this run's saved frame instants."""
    if report.schema_version == FRAME_TEXT_VERSION:
        if report.frames_digest is None or report.every is None:
            return _fail("报告缺少必要字段。")
        if report.frames_digest != frames_digest(scanned_frames(saved, report.every)):
            return _fail("报告里的画面指纹与当前已保存帧对不上。")
        return ScreenTextReportRead(True, "", report)
    return _check_official_frames(report, saved)


def _check_official_frames(
    report: LoadedScreenTextReport, saved: Sequence[tuple[str, int]]
) -> ScreenTextReportRead:
    saved_set = set(saved)
    instants = tuple(
        (frame.evidence_id, frame.time_us) for frame in report.frames if frame.evidence_id
    )
    if len(instants) != len(report.frames):
        return _fail("报告缺少必要字段。")
    if any(item not in saved_set for item in instants):
        return _fail("报告里的画面指纹与当前已保存帧对不上。")
    if report.frames_digest is not None and report.frames_digest != frames_digest(instants):
        return _fail("报告里的画面指纹与报告内帧对不上。")
    return ScreenTextReportRead(True, "", report)


def _fail(reason: str) -> ScreenTextReportRead:
    return ScreenTextReportRead(False, reason, None)


def _is_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _parse(payload: dict[str, Any]) -> ScreenTextReportRead:
    schema = payload.get("schemaVersion")
    if schema not in SUPPORTED:
        return _fail("报告的 schema 不受支持。")
    run_id = payload.get("runId")
    source = payload.get("sourceSha256")
    duration = payload.get("durationUs")
    if not isinstance(run_id, str) or not run_id:
        return _fail("报告缺少必要字段。")
    if not _is_sha(source):
        return _fail("报告缺少必要字段。")
    if type(duration) is not int:
        return _fail("报告缺少必要字段。")
    every = payload.get("every")
    if every is not None and (type(every) is not int or every < 1):
        return _fail("报告格式无效。")
    digest = payload.get("framesDigest")
    if digest is not None and not _is_sha(digest):
        return _fail("报告格式无效。")
    frames = _frames(payload.get("frames"))
    if frames is None:
        return _fail("报告格式无效。")
    if schema == FRAME_TEXT_VERSION and not _is_sha(digest):
        return _fail("报告缺少必要字段。")
    return ScreenTextReportRead(
        True,
        "",
        LoadedScreenTextReport(
            schema_version=str(schema),
            run_id=run_id,
            source_sha256=str(source),
            duration_us=duration,
            frames_digest=digest if isinstance(digest, str) else None,
            every=every if type(every) is int else None,
            frames=frames,
        ),
    )


def _frames(value: object) -> tuple[ScreenTextFrame, ...] | None:
    if not isinstance(value, list):
        return None
    frames: list[ScreenTextFrame] = []
    for row in value:
        parsed = _frame(row)
        if parsed is None:
            return None
        frames.append(parsed)
    return tuple(frames)


def _frame(row: object) -> ScreenTextFrame | None:
    if not isinstance(row, dict) or type(row.get("timeUs")) is not int:
        return None
    evidence = row.get("evidenceId")
    if evidence is not None and not isinstance(evidence, str):
        return None
    status = row.get("status")
    if status is not None and not isinstance(status, str):
        return None
    raw_lines = row.get("lines", [])
    if not isinstance(raw_lines, list):
        return None
    lines: list[ScreenTextLine] = []
    for item in raw_lines:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            return None
        likely = item.get("likelyText")
        if likely is not None and type(likely) is not bool:
            return None
        lines.append(ScreenTextLine(item["text"], likely if type(likely) is bool else None))
    return ScreenTextFrame(row["timeUs"], tuple(lines), evidence, status)
