"""Pure, source-bound snapshots for trimming, ordering and deleting saved clips."""

from copy import deepcopy
from hashlib import sha256
from typing import Any

from gamingcreator.application.rendering import RenderClip, RenderPlan, validate_render_plan
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.time import SourceRange

REVISION_SCHEMA = "edit-decision-revision-v1"
_EDIT_KEYS = {"clipId", "startUs", "outputFrames"}
_ROW_VARIABLES = _EDIT_KEYS | {"endUs", "outputStartFrame"}


def editable_clips(edl: dict[str, Any], root_receipt_sha: str) -> list[dict[str, Any]]:
    """Return detached rows with stable root identities (never trust root clip IDs)."""
    if (
        not isinstance(root_receipt_sha, str)
        or len(root_receipt_sha) != 64
        or any(c not in "0123456789abcdef" for c in root_receipt_sha)
    ):
        raise ValueError("Invalid root receipt SHA256.")
    schema = edl.get("schemaVersion")
    if schema not in ("edit-decision-v1", REVISION_SCHEMA):
        raise ValueError("Unsupported editing schema.")
    if schema == REVISION_SCHEMA and edl.get("rootReceiptSha256") != root_receipt_sha:
        raise ValueError("Revision belongs to another root receipt.")
    rows = edl.get("segments")
    if not isinstance(rows, list) or not rows or any(not isinstance(r, dict) for r in rows):
        raise ValueError("Editing requires nonempty segment rows.")
    result: list[dict[str, Any]] = deepcopy(rows)
    for index, row in enumerate(result):
        if schema == "edit-decision-v1":
            expected = sha256(f"{root_receipt_sha}:{index}".encode()).hexdigest()
            if "clipId" in row and row["clipId"] != expected:
                raise ValueError("Root clip identity was changed.")
            row["clipId"] = expected
        elif not isinstance(row.get("clipId"), str) or not row["clipId"]:
            raise ValueError("Missing revision clip identity.")
    if len({row["clipId"] for row in result}) != len(result):
        raise ValueError("Duplicate clip identity.")
    return result


def build_revision(
    parent_edl: dict[str, Any], root_receipt_sha: str, edits: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a full snapshot containing an ordered subset, trimmed inside its parent."""
    rows = editable_clips(parent_edl, root_receipt_sha)
    fps = parent_edl.get("fpsNumerator")
    if type(fps) is not int or not 1 <= fps <= 120 or parent_edl.get("fpsDenominator") != 1:
        raise ValueError("Invalid output clock.")
    if not isinstance(edits, list) or not edits:
        raise ValueError("An edit must retain at least one clip.")
    available = {row["clipId"]: row for row in rows}
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    offset = 0
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != _EDIT_KEYS:
            raise ValueError("Edits accept only clipId, startUs and outputFrames.")
        clip_id = edit["clipId"]
        if not isinstance(clip_id, str) or clip_id not in available or clip_id in seen:
            raise ValueError("Unknown or repeated clip identity.")
        start, frames = edit["startUs"], edit["outputFrames"]
        if type(start) is not int or type(frames) is not int or frames <= 0:
            raise ValueError("Editing times and positive frames must be integers.")
        parent = available[clip_id]
        end = start + (frames * 1_000_000 + fps - 1) // fps
        if (
            type(parent.get("startUs")) is not int
            or type(parent.get("endUs")) is not int
            or type(parent.get("outputFrames")) is not int
            or not parent["startUs"] <= start < end <= parent["endUs"]
            or frames > parent["outputFrames"]
        ):
            raise ValueError("Edits may only shorten the parent source range.")
        row = deepcopy(parent)
        row.update(startUs=start, endUs=end, outputFrames=frames, outputStartFrame=offset)
        output.append(row)
        offset += frames
        seen.add(clip_id)
    revision = deepcopy(parent_edl)
    revision.update(
        schemaVersion=REVISION_SCHEMA, rootReceiptSha256=root_receipt_sha, segments=output
    )
    return revision


def validate_revision(
    root_edl: dict[str, Any],
    root_report: dict[str, Any],
    parent_edl: dict[str, Any],
    revision_edl: dict[str, Any],
    timelines: tuple[StoredTimeline, ...],
    root_receipt_sha: str,
) -> RenderPlan:
    """Validate the root and snapshot; caller verifies the persisted parent chain."""
    root_plan = validate_render_plan(root_edl, root_report, timelines)
    root_rows = editable_clips(root_edl, root_receipt_sha)
    root_by_id = {
        row["clipId"]: (row, clip) for row, clip in zip(root_rows, root_plan.clips, strict=True)
    }
    parent_rows = editable_clips(parent_edl, root_receipt_sha)
    # A revision cannot alter any envelope or source metadata inherited from the root.
    envelope_keys = {"schemaVersion", "rootReceiptSha256", "segments"}
    if not _same(
        {k: v for k, v in parent_edl.items() if k not in envelope_keys},
        {k: v for k, v in root_edl.items() if k not in envelope_keys},
    ):
        raise ValueError("Parent metadata differs from root.")
    if parent_edl.get("schemaVersion") == "edit-decision-v1" and not _same(parent_edl, root_edl):
        raise ValueError("Root parent must be the original decision.")
    offset = 0
    for row in parent_rows:
        if row["clipId"] not in root_by_id:
            raise ValueError("Parent clip identity does not belong to root.")
        root_row, _ = root_by_id[row["clipId"]]
        if not _same(
            {k: v for k, v in row.items() if k not in _ROW_VARIABLES},
            {k: v for k, v in root_row.items() if k not in _ROW_VARIABLES},
        ):
            raise ValueError("Parent source metadata differs from root.")
        expected = build_revision(root_edl, root_receipt_sha, [_edit(row)])["segments"][0]
        expected["outputStartFrame"] = offset
        if not _same(expected, row):
            raise ValueError("Invalid parent source range or frame mapping.")
        offset += row["outputFrames"]
    revision_rows = editable_clips(revision_edl, root_receipt_sha)
    rebuilt = build_revision(parent_edl, root_receipt_sha, [_edit(r) for r in revision_rows])
    if not _same(rebuilt, revision_edl):
        raise ValueError("Revision differs from its permitted editing snapshot.")
    return RenderPlan(
        tuple(
            RenderClip(
                root_by_id[row["clipId"]][1].asset,
                SourceRange(row["startUs"], row["endUs"], row["sourceDurationUs"]),
                row["outputFrames"],
            )
            for row in revision_rows
        ),
        root_plan.fps,
    )


def _edit(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in _EDIT_KEYS}


def _same(left: Any, right: Any) -> bool:
    """JSON snapshot equality also preserves integer versus boolean/float types."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(v, right[k]) for k, v in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)
