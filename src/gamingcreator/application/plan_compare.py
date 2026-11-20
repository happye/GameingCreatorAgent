"""Read-only comparison of two already generated rule plans."""

from collections.abc import Sequence
from copy import deepcopy
from fractions import Fraction
from typing import Any

SCHEMA = "plan-comparison-v1"
CONTIGUOUS_GAP_US = 250_000


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _positive_fps(fps: Any) -> float | None:
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps <= 0:
        return None
    return float(fps)


def shot_count(segments: Any) -> int | None:
    """Count output shots from actual segments. Back-to-back cuts of one source count as one."""
    shots = list_source_shots(segments)
    return None if shots is None else len(shots)


def total_output_frames(segments: Any) -> int | None:
    """Sum output frames from the actual plan. A missing frame count stays unknown, not zero."""
    if not isinstance(segments, list):
        return None
    total = 0
    for segment in segments:
        if not isinstance(segment, dict):
            return None
        frames = _int_or_none(segment.get("outputFrames"))
        if frames is None:
            return None
        total += frames
    return total


def plan_side_metrics(plan: Any, fps: Any = None) -> dict[str, Any]:
    """Totals come from actual segments, never from the template name. Missing fields stay unknown."""
    segments = plan.get("segments") if isinstance(plan, dict) else None
    frames = total_output_frames(segments)
    rate = _positive_fps(fps)
    duration = None if frames is None or rate is None else frames / rate
    if not isinstance(plan, dict) or "gaps" not in plan or not isinstance(plan["gaps"], list):
        gaps = None
    else:
        gaps = list(plan["gaps"])
    return {
        "totalFrames": frames,
        "durationSeconds": duration,
        "shotCount": shot_count(segments),
        "gaps": gaps,
    }


def source_identity(segment: Any) -> tuple[str | None, str] | None:
    """Footage identity used for alignment: run and source hash, never role or wording."""
    if not isinstance(segment, dict):
        return None
    sha = segment.get("sourceSha256")
    if not isinstance(sha, str) or not sha:
        return None
    run = segment.get("runId")
    if run is None:
        return (None, sha)
    if isinstance(run, bool) or not isinstance(run, (str, int)):
        return None
    return (str(run), sha)


def _same_contiguous(previous: dict[str, Any], segment: dict[str, Any]) -> bool:
    if source_identity(previous) is None or source_identity(segment) != source_identity(previous):
        return False
    start_us = _int_or_none(segment.get("startUs"))
    prev_end = _int_or_none(previous.get("endUs"))
    return (
        start_us is not None
        and prev_end is not None
        and start_us >= prev_end
        and start_us - prev_end <= CONTIGUOUS_GAP_US
    )


def list_source_shots(segments: Any) -> list[dict[str, Any]] | None:
    """Merge back-to-back cuts of one source into shots, with output spans when known."""
    if not isinstance(segments, list):
        return None
    shots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    cursor: int | None = 0
    for segment in segments:
        if not isinstance(segment, dict):
            return None
        frames = _int_or_none(segment.get("outputFrames"))
        if current is None or not _same_contiguous(current["last"], segment):
            start = cursor
            end = None if cursor is None or frames is None else cursor + frames
            current = {
                "identity": source_identity(segment),
                "startFrame": start,
                "endFrame": end,
                "frames": frames,
                "last": segment,
            }
            shots.append(current)
        else:
            if current["frames"] is None or frames is None:
                current["frames"] = None
                current["endFrame"] = None
            else:
                current["frames"] += frames
                if current["endFrame"] is not None:
                    current["endFrame"] += frames
            current["last"] = segment
        if frames is None:
            cursor = None
        elif cursor is not None:
            cursor += frames
    for index, shot in enumerate(shots, 1):
        shot["shotIndex"] = index
        del shot["last"]
        del shot["frames"]
    return shots


def _position(shot: dict[str, Any], fps: Any = None) -> dict[str, Any]:
    rate = _positive_fps(fps)
    start = shot.get("startFrame")
    end = shot.get("endFrame")
    return {
        "shotIndex": shot["shotIndex"],
        "startFrame": start,
        "endFrame": end,
        "startSeconds": None if start is None or rate is None else start / rate,
        "endSeconds": None if end is None or rate is None else end / rate,
    }


def align_source_shots(  # noqa: C901
    left_segments: Any, right_segments: Any, fps: Any = None
) -> list[dict[str, Any]] | None:
    """Pair shots by run and footage hash. Do not guess from role or description.

    When the same source is merged on one side and split on the other, do not
    claim that either side is missing the footage.
    """
    left_shots = list_source_shots(left_segments)
    right_shots = list_source_shots(right_segments)
    if left_shots is None or right_shots is None:
        return None

    def row_for(
        identity: tuple[str | None, str] | None,
        left: dict[str, Any] | None,
        right: dict[str, Any] | None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        run_id, sha = identity if identity is not None else (None, None)
        row = {
            "runId": run_id,
            "sourceSha256": sha,
            "left": None if left is None else _position(left, fps),
            "right": None if right is None else _position(right, fps),
        }
        if reason is not None:
            row["reason"] = reason
        return row

    def group(shots: list[dict[str, Any]]) -> dict[tuple[str | None, str], list[dict[str, Any]]]:
        buckets: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
        for shot in shots:
            identity = shot["identity"]
            if identity is None:
                continue
            buckets.setdefault(identity, []).append(shot)
        return buckets

    left_groups = group(left_shots)
    right_groups = group(right_shots)
    seen: set[tuple[str | None, str]] = set()
    rows: list[dict[str, Any]] = []
    for left in left_shots:
        identity = left["identity"]
        if identity is None:
            rows.append(row_for(None, left, None))
            continue
        if identity in seen:
            continue
        seen.add(identity)
        left_group = left_groups[identity]
        right_group = right_groups.get(identity, [])
        if left_group and right_group and len(left_group) != len(right_group):
            for shot in left_group:
                rows.append(row_for(identity, shot, None, "split"))
            for shot in right_group:
                rows.append(row_for(identity, None, shot, "split"))
        elif right_group:
            for shot, other in zip(left_group, right_group, strict=False):
                rows.append(row_for(identity, shot, other))
        else:
            for shot in left_group:
                rows.append(row_for(identity, shot, None))
    for right in right_shots:
        identity = right["identity"]
        if identity is None:
            rows.append(row_for(None, None, right))
            continue
        if identity in seen:
            continue
        seen.add(identity)
        for shot in right_groups[identity]:
            rows.append(row_for(identity, None, shot))
    return rows


def format_exact_us(us: int) -> str:
    """Keep the exact microsecond count; also show an exact second fraction when it is not a whole second."""
    seconds = Fraction(us, 1_000_000)
    if seconds.denominator == 1:
        return f"{us} 微秒（{seconds.numerator} 秒）"
    return f"{us} 微秒（{seconds.numerator}/{seconds.denominator} 秒）"


def format_exact_speed(source_us: int, output_frames: int, fps: Any) -> str | None:
    """Playback speed as an exact fraction: source duration over output duration."""
    if source_us <= 0 or output_frames <= 0:
        return None
    rate = _fps_fraction(fps)
    if rate is None:
        return None
    ratio = Fraction(source_us, 1) * rate / (Fraction(output_frames, 1) * 1_000_000)
    if ratio.denominator == 1:
        return str(ratio.numerator)
    return f"{ratio.numerator}/{ratio.denominator}"


def _fps_fraction(fps: Any) -> Fraction | None:
    if isinstance(fps, bool):
        return None
    if isinstance(fps, int) and fps > 0:
        return Fraction(fps, 1)
    if isinstance(fps, float) and fps > 0:
        return Fraction(fps).limit_denominator()
    return None


def trim_speed_metrics(
    start_us: int | None, end_us: int | None, output_frames: int | None, fps: Any
) -> dict[str, Any]:
    source_us = None if start_us is None or end_us is None else end_us - start_us
    rate = _fps_fraction(fps)
    _output_us = (
        None
        if output_frames is None or rate is None
        else int(Fraction(output_frames, 1) / rate * 1_000_000)
    )
    # Keep output_us exact via Fraction when it is not an integer microsecond.
    output_us_exact = None
    if output_frames is not None and rate is not None:
        output_us_exact = Fraction(output_frames, 1) / rate * 1_000_000
    speed = None
    if source_us is not None and output_frames is not None:
        speed = format_exact_speed(source_us, output_frames, fps)
    return {
        "startUs": start_us,
        "endUs": end_us,
        "sourceUs": source_us,
        "outputFrames": output_frames,
        "outputUs": None
        if output_us_exact is None
        else (
            int(output_us_exact)
            if output_us_exact.denominator == 1
            else f"{output_us_exact.numerator}/{output_us_exact.denominator}"
        ),
        "speed": speed,
    }


def interval_identity(segment: Any) -> tuple[str | None, str, int, int] | None:
    """One source interval. Role, event id and filename do not identify a shot."""
    source = source_identity(segment)
    if source is None or not isinstance(segment, dict):
        return None
    start = _int_or_none(segment.get("startUs"))
    end = _int_or_none(segment.get("endUs"))
    if start is None or end is None:
        return None
    return (source[0], source[1], start, end)


def list_interval_shots(segments: Any) -> list[dict[str, Any]] | None:
    """Keep different source ranges as separate shots, including back-to-back cuts of one file."""
    if not isinstance(segments, list):
        return None
    shots: list[dict[str, Any]] = []
    cursor: int | None = 0
    for segment in segments:
        if not isinstance(segment, dict):
            return None
        frames = _int_or_none(segment.get("outputFrames"))
        start = cursor
        end = None if cursor is None or frames is None else cursor + frames
        shots.append(
            {
                "identity": interval_identity(segment),
                "startFrame": start,
                "endFrame": end,
                "outputFrames": frames,
                "shotIndex": len(shots) + 1,
                "startUs": _int_or_none(segment.get("startUs")),
                "endUs": _int_or_none(segment.get("endUs")),
            }
        )
        if frames is None:
            cursor = None
        elif cursor is not None:
            cursor += frames
    return shots


def classify_shot_changes(  # noqa: C901
    left_segments: Any, right_segments: Any, fps: Any = None
) -> list[dict[str, Any]] | None:
    """Mark added, missing and reordered shots by source interval, never by duplicate ids."""
    left_shots = list_interval_shots(left_segments)
    right_shots = list_interval_shots(right_segments)
    if left_shots is None or right_shots is None:
        return None

    def status_for(
        key: tuple[Any, ...] | None, left: dict[str, Any] | None, right: dict[str, Any] | None
    ) -> str:
        if key is None or (left is None and right is None):
            return "unknown"
        if left is None:
            return "added"
        if right is None:
            return "missing"
        if left["shotIndex"] != right["shotIndex"]:
            return "reordered"
        return "same"

    def row_for(
        identity: tuple[Any, ...] | None,
        left: dict[str, Any] | None,
        right: dict[str, Any] | None,
        status: str,
    ) -> dict[str, Any]:
        run_id, sha, start_us, end_us = (
            (None, None, None, None) if identity is None else (*identity,)
        )
        return {
            "runId": run_id,
            "sourceSha256": sha,
            "startUs": start_us,
            "endUs": end_us,
            "status": status,
            "left": None if left is None else _position(left, fps),
            "right": None if right is None else _position(right, fps),
            "leftTrim": None
            if left is None
            else trim_speed_metrics(
                left.get("startUs"), left.get("endUs"), left.get("outputFrames"), fps
            ),
            "rightTrim": None
            if right is None
            else trim_speed_metrics(
                right.get("startUs"), right.get("endUs"), right.get("outputFrames"), fps
            ),
        }

    used: set[int] = set()
    used_occ: dict[tuple[Any, ...], int] = {}
    rows: list[dict[str, Any]] = []
    for left in left_shots:
        key = left["identity"]
        occ = used_occ.get(key, 0) if key is not None else 0
        match_index = None
        if key is not None:
            for index, right in enumerate(right_shots):
                if index in used or right["identity"] != key:
                    continue
                match_index = index
                break
        matched: dict[str, Any] | None = (
            right_shots[match_index] if match_index is not None else None
        )
        if match_index is not None:
            used.add(match_index)
        status = status_for(key, left, matched)
        if key is not None:
            used_occ[key] = occ + 1
        rows.append(row_for(key, left, matched, status))
    for index, right in enumerate(right_shots):
        if index in used:
            continue
        key = right["identity"]
        rows.append(row_for(key, None, right, status_for(key, None, right)))
    return rows


def _plain_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def list_theme_reasons(plan: Any) -> dict[str, Any]:
    """List recorded topic reasons and quoted notes only. Never invent from a template or rule."""
    uses: list[dict[str, Any]] = []
    segments = plan.get("segments") if isinstance(plan, dict) else None
    if isinstance(segments, list):
        for index, segment in enumerate(segments, start=1):
            if not isinstance(segment, dict):
                continue
            raw = segment.get("topicUses")
            if not isinstance(raw, list):
                continue
            for item in raw:
                if not isinstance(item, dict):
                    continue
                topic = _plain_text(item.get("topic"))
                rationale = _plain_text(item.get("rationale"))
                quote = _plain_text(item.get("observationQuote"))
                if topic is None and rationale is None and quote is None:
                    continue
                uses.append(
                    {
                        "shotIndex": index,
                        "topic": topic,
                        "rationale": rationale,
                        "observationQuote": quote,
                    }
                )
    return {"provided": bool(uses), "uses": uses}


def open_plan_comparison(
    plans: Sequence[dict[str, Any]],
    left_id: str,
    right_id: str,
    fps: Any = None,
) -> dict[str, Any]:
    """Pair two generated plans for a read-only look. Do not adopt, score, or call a model."""
    if not isinstance(left_id, str) or not isinstance(right_id, str) or not left_id or not right_id:
        raise ValueError("对照需要两个已生成方案。")
    if left_id == right_id:
        raise ValueError("对照需要两个不同的已生成方案。")
    by_id: dict[str, dict[str, Any]] = {}
    for plan in plans:
        identity = plan.get("id")
        if isinstance(identity, str) and identity not in by_id:
            by_id[identity] = plan
    if left_id not in by_id or right_id not in by_id:
        raise ValueError("只能对照已经生成的方案。")
    left = deepcopy(by_id[left_id])
    right = deepcopy(by_id[right_id])
    result = {
        "schemaVersion": SCHEMA,
        "readonly": True,
        "left": left,
        "right": right,
        "leftMetrics": plan_side_metrics(left, fps),
        "rightMetrics": plan_side_metrics(right, fps),
        "sourceAlignment": align_source_shots(left.get("segments"), right.get("segments"), fps),
        "shotChanges": classify_shot_changes(left.get("segments"), right.get("segments"), fps),
        "leftThemeReasons": list_theme_reasons(left),
        "rightThemeReasons": list_theme_reasons(right),
    }
    rate = _positive_fps(fps)
    if rate is not None:
        result["fps"] = rate
    return result


EXPORT_SCHEMA = "plan-comparison-export-v1"
EXPORT_NOTE = "只包含这次对照的差异和来源，不会写回报告、证据或偏好。"


def _export_side(plan: Any, metrics: Any, reasons: Any) -> dict[str, Any]:
    identity = plan.get("id") if isinstance(plan, dict) else None
    side: dict[str, Any] = {
        "planId": identity if isinstance(identity, str) and identity else None,
        "metrics": deepcopy(metrics) if metrics is not None else None,
        "themeReasons": deepcopy(reasons) if reasons is not None else None,
    }
    signature = plan.get("contentSignature") if isinstance(plan, dict) else None
    if isinstance(signature, str) and signature:
        side["contentSignature"] = signature
    return side


def list_comparison_sources(alignment: Any, changes: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def add(run_id: Any, sha: Any, start_us: Any = None, end_us: Any = None) -> None:
        if run_id is None and sha is None and start_us is None and end_us is None:
            return
        key = (run_id, sha, start_us, end_us)
        if key in seen:
            return
        seen.add(key)
        item: dict[str, Any] = {}
        if run_id is not None:
            item["runId"] = run_id
        if sha is not None:
            item["sourceSha256"] = sha
        if start_us is not None:
            item["startUs"] = start_us
        if end_us is not None:
            item["endUs"] = end_us
        sources.append(item)

    if isinstance(changes, list):
        for row in changes:
            if not isinstance(row, dict):
                continue
            add(row.get("runId"), row.get("sourceSha256"), row.get("startUs"), row.get("endUs"))
    if isinstance(alignment, list):
        for row in alignment:
            if not isinstance(row, dict):
                continue
            run_id, sha = row.get("runId"), row.get("sourceSha256")
            if any(
                item.get("runId") == run_id and item.get("sourceSha256") == sha for item in sources
            ):
                continue
            add(run_id, sha)
    return sources


def comparison_export_document(pair: Any) -> dict[str, Any]:
    """Build a download document of this comparison only. Do not write reports, evidence, or preferences."""
    if (
        not isinstance(pair, dict)
        or pair.get("readonly") is not True
        or "left" not in pair
        or "right" not in pair
    ):
        raise ValueError("只能下载已经打开的只读对照。")
    document = {
        "schemaVersion": EXPORT_SCHEMA,
        "readonly": True,
        "note": EXPORT_NOTE,
        "left": _export_side(
            pair.get("left"), pair.get("leftMetrics"), pair.get("leftThemeReasons")
        ),
        "right": _export_side(
            pair.get("right"), pair.get("rightMetrics"), pair.get("rightThemeReasons")
        ),
        "sources": list_comparison_sources(pair.get("sourceAlignment"), pair.get("shotChanges")),
        "sourceAlignment": deepcopy(pair.get("sourceAlignment")),
        "shotChanges": deepcopy(pair.get("shotChanges")),
    }
    if "fps" in pair:
        document["fps"] = pair["fps"]
    return document


def comparison_export_filename(pair: Any) -> str:
    def token(value: Any, fallback: str) -> str:
        text = value if isinstance(value, str) and value else fallback
        cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)
        return cleaned or fallback

    left = pair.get("left") if isinstance(pair, dict) else None
    right = pair.get("right") if isinstance(pair, dict) else None
    left_id = left.get("id") if isinstance(left, dict) else None
    right_id = right.get("id") if isinstance(right, dict) else None
    return f"plan-comparison-{token(left_id, 'left')}-{token(right_id, 'right')}.json"
