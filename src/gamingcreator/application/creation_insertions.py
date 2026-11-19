"""Source-bound insertion revisions; callers verify the complete parent chain."""

from copy import deepcopy
from typing import Any

from gamingcreator.application.creation_replacements import (
    _canonical,
    _sha,
    build_revision_v4,
    validate_revision_v4,
)

REVISION_SCHEMA_V5 = "edit-decision-revision-v5"
MAX_INSERTIONS = 8


def insertion_id(parent_sha: str, operation: dict[str, Any]) -> str:
    return _sha(
        [
            "insertion-v1",
            parent_sha,
            operation["afterClipId"],
            operation["candidateId"],
            operation["startUs"],
            operation["endUs"],
        ]
    )


def build_revision_v5(
    parent: dict[str, Any],
    root_sha: str,
    parent_sha: str,
    clips: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    insertions: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Add proven candidate rows, or edit a verified v5 parent without adding rows."""
    if not isinstance(insertions, list) or len(insertions) > MAX_INSERTIONS:
        raise ValueError("Invalid insertion count.")
    if len(insertions) > 1 and any(
        not isinstance(op, dict) or op.get("editMode") != "composed-v1" for op in insertions
    ):
        raise ValueError("Multiple insertions must all be composed operations.")
    from gamingcreator.application.creation_editing import editable_clips

    projected = deepcopy(parent)
    if projected.get("schemaVersion") == REVISION_SCHEMA_V5:
        projected["schemaVersion"] = "edit-decision-revision-v4"
    compatible = (
        {**projected, "schemaVersion": "edit-decision-revision-v3"}
        if projected.get("schemaVersion") == "edit-decision-revision-v4"
        else projected
    )
    projected["segments"] = editable_clips(compatible, root_sha)
    for row in projected["segments"]:
        row.setdefault("speed", {"numerator": 1, "denominator": 1})
        row.setdefault("transitionIn", {"type": "cut", "frames": 0})
    if projected.get("schemaVersion") != "edit-decision-revision-v4":
        projected.update(schemaVersion="edit-decision-revision-v3", rootReceiptSha256=root_sha)
    parent_ids = {row["clipId"] for row in projected["segments"]}
    # Insert at the first position after each original anchor, in reverse proposal order.
    for operation in reversed(insertions):
        _add_insertion(
            projected, parent_sha, clips, replacements, operation, manifest, parent_ids=parent_ids
        )
    result = build_revision_v4(projected, root_sha, parent_sha, clips, replacements, manifest)
    if (
        replacements
        and insertions
        and insertions[0].get("editMode") == "composed-v1"
        and any(
            _canonical(edit["transitionIn"]) != _canonical(saved["transitionIn"])
            for edit, saved in zip(clips, result["segments"], strict=True)
        )
    ):
        raise ValueError("Replacement clips and their following clips must use cut transitions.")
    result.update(schemaVersion=REVISION_SCHEMA_V5, insertions=deepcopy(insertions))
    return result


def _validate_insertion_operation(operation: dict[str, Any]) -> bool:
    fields = {
        "afterClipId",
        "candidateId",
        "startUs",
        "endUs",
        "newClipId",
    }
    if not isinstance(operation, dict) or set(operation) not in (fields, fields | {"editMode"}):
        raise ValueError("Invalid insertion operation fields.")
    composed = "editMode" in operation
    if composed and operation["editMode"] != "composed-v1":
        raise ValueError("Invalid insertion edit mode.")
    if not all(
        isinstance(operation[key], str) for key in ("afterClipId", "candidateId", "newClipId")
    ):
        raise ValueError("Invalid insertion identity fields.")
    if type(operation["startUs"]) is not int or type(operation["endUs"]) is not int:
        raise ValueError("Unknown insertion candidate or source clock.")
    return composed


def _add_insertion(
    projected: dict[str, Any],
    parent_sha: str,
    clips: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    operation: dict[str, Any],
    manifest: dict[str, Any],
    *,
    parent_ids: set[str],
) -> None:
    expected_ids = [r["clipId"] for r in projected["segments"]]
    composed = _validate_insertion_operation(operation)
    if not composed and replacements:
        raise ValueError("Insertion cannot also replace footage.")
    start, end = operation["startUs"], operation["endUs"]
    identity = insertion_id(parent_sha, operation)
    if operation["newClipId"] != identity or identity in expected_ids:
        raise ValueError("Insertion identity differs from trusted operation.")
    candidates = {r["candidateId"]: r for r in manifest["candidates"]}
    candidate = candidates.get(operation["candidateId"])
    if candidate is None:
        raise ValueError("Unknown insertion candidate or source clock.")
    fps = projected["fpsNumerator"]
    if start != candidate["startUs"] or not start < end <= candidate["endUs"]:
        raise ValueError("Insertion must start at the trusted candidate start.")
    if (end - start) * fps < 1_000_000:
        raise ValueError("Insertion must contain an output frame.")
    if operation["afterClipId"] not in parent_ids:
        raise ValueError("Unknown insertion anchor.")
    index = expected_ids.index(operation["afterClipId"]) + 1
    rows = projected["segments"]
    if index < len(rows) and rows[index].get("transitionIn") != {"type": "cut", "frames": 0}:
        raise ValueError("Insertion would change the following transition.")
    row = {k: v for k, v in candidate.items() if k != "candidateId"}
    row.update(
        clipId=identity,
        startUs=start,
        endUs=end,
        outputFrames=1,
        outputStartFrame=0,
        speed={"numerator": 1, "denominator": 1},
        transitionIn={"type": "cut", "frames": 0},
    )
    rows.insert(index, row)
    if composed:
        if not isinstance(clips, list) or not any(
            isinstance(edit, dict) and edit.get("clipId") == identity for edit in clips
        ):
            raise ValueError("Composed insertion must retain the inserted clip.")
        if isinstance(replacements, list) and any(
            isinstance(edit, dict) and edit.get("targetClipId") == identity for edit in replacements
        ):
            raise ValueError("Save the inserted clip before replacing it.")
        return
    expected_ids.insert(index, identity)
    if [r["clipId"] for r in clips] != expected_ids:
        raise ValueError("Insertion must retain all parent clips in order.")
    original = {r["clipId"]: r for r in rows}
    for edit in clips:
        source = row if edit["clipId"] == identity else original[edit["clipId"]]
        if any(
            _canonical(edit[k]) != _canonical(source[k])
            for k in ("startUs", "endUs", "speed", "transitionIn")
        ):
            raise ValueError("Insertion must preserve every existing clip.")


def validate_revision_v5(
    parent: dict[str, Any],
    revised: dict[str, Any],
    root_sha: str,
    parent_sha: str,
    clips: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    insertions: list[dict[str, Any]],
    manifest: dict[str, Any],
    timelines: Any,
) -> Any:
    expected = build_revision_v5(
        parent, root_sha, parent_sha, clips, replacements, insertions, manifest
    )
    if _canonical(expected) != _canonical(revised):
        raise ValueError("Insertion revision differs from its saved request.")
    # Reuse source/event binding validation on the exact rebuilt projection.
    projected = deepcopy(expected)
    projected["schemaVersion"] = "edit-decision-revision-v4"
    empty = build_revision_v4(projected, root_sha, parent_sha, clips_for(expected), [], manifest)
    return validate_revision_v4(
        projected, empty, root_sha, parent_sha, clips_for(expected), [], manifest, timelines
    )


def clips_for(edl: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {k: r[k] for k in ("clipId", "startUs", "endUs", "speed", "transitionIn")}
        for r in edl["segments"]
    ]
