"""Pure candidate snapshots and source-bound replacement revisions.

Callers verify the root and every preceding ancestor before validating a v4 step.
Filesystem bytes and receipt publication remain the caller's responsibility.
"""

import json
from copy import deepcopy
from dataclasses import fields, is_dataclass
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any

from gamingcreator.application.creation_editing import build_revision, editable_clips
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.time import SourceInstant, SourceRange

REVISION_SCHEMA_V4 = "edit-decision-revision-v4"


def _project(value: Any) -> Any:
    if isinstance(value, Fraction):
        return [value.numerator, value.denominator]
    if isinstance(value, SourceInstant):
        return {"type": "SourceInstant", "time": [value.time_us, value.duration_us]}
    if isinstance(value, SourceRange):
        return [value.start_us, value.end_us, value.duration_us]
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _project(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_project(item) for item in value]
    if isinstance(value, dict):
        return {key: _project(item) for key, item in value.items()}
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        _project(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _digest(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("Invalid receipt digest.")


def _unique(items: Any, key: str) -> list[Any]:
    rows = sorted(items, key=lambda row: getattr(row, key))
    if len({getattr(row, key) for row in rows}) != len(rows):
        raise ValueError("Duplicate timeline identity.")
    return rows


def timeline_fingerprint(timeline: StoredTimeline) -> str:
    """Hash content and source clocks; exclude invocation accounting and stage state."""
    run = timeline.run
    asset = _project(run.asset)
    asset["streams"] = _project(_unique(run.asset.streams, "index"))
    return _sha(
        {
            "run_id": run.run_id,
            "status": run.status,
            "config_hash": run.config_hash,
            "pipeline_version": run.configuration.pipeline_version,
            "pipeline_hash": run.configuration.pipeline_hash,
            "asset": asset,
            "events": _project(_unique(timeline.events, "event_id")),
            "evidence": _project(_unique(timeline.evidence, "evidence_id")),
            "transcripts": sorted((_project(t) for t in timeline.transcripts), key=_canonical),
        }
    )


def build_candidate_manifest(
    root_receipt_sha: str,
    project_id: str,
    allowed_run_ids: list[str],
    timelines: tuple[StoredTimeline, ...],
) -> dict[str, Any]:
    _digest(root_receipt_sha)
    if (
        not isinstance(project_id, str)
        or not project_id
        or not allowed_run_ids
        or any(not isinstance(run, str) or not run for run in allowed_run_ids)
        or len(set(allowed_run_ids)) != len(allowed_run_ids)
    ):
        raise ValueError("Invalid project or selected runs.")
    runs = {t.run.run_id: t for t in timelines}
    if len(runs) != len(timelines) or set(runs) != set(allowed_run_ids):
        raise ValueError("Timelines must exactly match selected root runs.")
    fingerprints = {}
    candidates = []
    for run_id in sorted(runs):
        timeline = runs[run_id]
        if timeline.run.status != RunStatus.COMPLETED:
            raise ValueError("Candidate run must be Completed.")
        fingerprint = timeline_fingerprint(timeline)
        fingerprints[run_id] = fingerprint
        asset = timeline.run.asset
        evidence = {e.evidence_id: e for e in timeline.evidence}
        for event in sorted(timeline.events, key=lambda e: e.event_id):
            if (
                event.run_id != run_id
                or event.media_id != asset.media_id
                or (event.source_range.duration_us != asset.duration_us)
                or any(
                    e not in evidence or evidence[e].media_id != asset.media_id
                    for e in event.evidence_ids
                )
            ):
                raise ValueError("Candidate event or evidence has foreign source identity.")
            candidates.append(
                {
                    "candidateId": _sha([root_receipt_sha, fingerprint, event.event_id]),
                    "runId": run_id,
                    "eventId": event.event_id,
                    "mediaId": asset.media_id,
                    "sourceSha256": asset.sha256,
                    "sourcePath": str(asset.source_path),
                    "sourceDurationUs": asset.duration_us,
                    "startUs": event.source_range.start_us,
                    "endUs": event.source_range.end_us,
                    "evidenceIds": list(event.evidence_ids),
                    "scriptDraft": "；".join(event.observable_facts),
                    "uncertainty": event.uncertainty,
                }
            )
    return {
        "schemaVersion": "creation-candidates-v1",
        "rootReceiptSha256": root_receipt_sha,
        "projectId": project_id,
        "allowedRunIds": sorted(allowed_run_ids),
        "runFingerprints": fingerprints,
        "candidates": candidates,
    }


def candidate_manifest_sha(manifest: dict[str, Any]) -> str:
    """Canonical content digest, distinct from an on-disk receipt file digest."""
    return _sha(manifest)


def build_revision_v4(
    parent_edl: dict[str, Any],
    root_receipt_sha: str,
    parent_receipt_sha: str,
    clips: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    _digest(root_receipt_sha)
    _digest(parent_receipt_sha)
    if (
        manifest.get("schemaVersion") != "creation-candidates-v1"
        or manifest.get("rootReceiptSha256") != root_receipt_sha
    ):
        raise ValueError("Candidate manifest belongs to another root.")
    parent = deepcopy(parent_edl)
    if parent.get("schemaVersion") == REVISION_SCHEMA_V4:
        if parent.get("candidateManifestSha256") != candidate_manifest_sha(manifest):
            raise ValueError("Descendants must retain the parent's candidate manifest.")
        parent["schemaVersion"] = "edit-decision-revision-v3"
    rows = editable_clips(parent, root_receipt_sha)
    if (
        not isinstance(clips, list)
        or not clips
        or any(
            not isinstance(c, dict)
            or set(c) != {"clipId", "startUs", "endUs", "speed", "transitionIn"}
            for c in clips
        )
    ):
        raise ValueError("Replacement edits require exact v3 clip fields.")
    ids = [c["clipId"] for c in clips]
    if (
        any(not isinstance(i, str) for i in ids)
        or len(set(ids)) != len(ids)
        or not set(ids) <= {r["clipId"] for r in rows}
    ):
        raise ValueError("Clips must be a unique ordered parent subset.")
    if not isinstance(replacements, list) or any(
        not isinstance(r, dict)
        or set(r) != {"targetClipId", "candidateId"}
        or not isinstance(r["targetClipId"], str)
        or not isinstance(r["candidateId"], str)
        for r in replacements
    ):
        raise ValueError("Invalid replacement operations.")
    targets = [r["targetClipId"] for r in replacements]
    if len(set(targets)) != len(targets) or not set(targets) <= set(ids):
        raise ValueError("Replacement targets must occur exactly once in clips.")
    candidates = {c["candidateId"]: c for c in manifest["candidates"]}
    operations = {r["targetClipId"]: r["candidateId"] for r in replacements}
    edits = deepcopy(clips)
    new_ids = {}
    for index, clip in enumerate(edits):
        target = clip["clipId"]
        if target not in operations:
            continue
        candidate_id = operations[target]
        if candidate_id not in candidates or _canonical(clip["speed"]) != _canonical(
            {"numerator": 1, "denominator": 1}
        ):
            raise ValueError("Replacement requires a known candidate and speed 1x.")
        candidate = candidates[candidate_id]
        row = deepcopy(candidate)
        row.pop("candidateId")
        row.update(clipId=target, outputFrames=1, outputStartFrame=0)
        rows = [row if r["clipId"] == target else r for r in rows]
        clip["transitionIn"] = {"type": "cut", "frames": 0}
        if index + 1 < len(edits):
            edits[index + 1]["transitionIn"] = {"type": "cut", "frames": 0}
        new_ids[target] = _sha(
            [
                "replacement-v1",
                root_receipt_sha,
                parent_receipt_sha,
                target,
                candidate_id,
                clip["startUs"],
                clip["endUs"],
            ]
        )
    parent["segments"] = rows
    result = build_revision(parent, root_receipt_sha, edits)
    for row in result["segments"]:
        target = row["clipId"]
        if target in new_ids:
            row.update(clipId=new_ids[target], replacesClipId=target)
    intervals = [(r["sourceSha256"], r["startUs"], r["endUs"]) for r in result["segments"]]
    if len(set(intervals)) != len(intervals):
        raise ValueError("Duplicate source interval.")
    result.update(
        schemaVersion=REVISION_SCHEMA_V4,
        candidateManifestSha256=candidate_manifest_sha(manifest),
        replacements=[{**r, "newClipId": new_ids[r["targetClipId"]]} for r in replacements],
    )
    return result


def validate_revision_v4(
    parent_edl: dict[str, Any],
    revision_edl: dict[str, Any],
    root_receipt_sha: str,
    parent_receipt_sha: str,
    clips: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    manifest: dict[str, Any],
    timelines: tuple[StoredTimeline, ...],
) -> RenderPlan:
    """Validate one step after the caller has verified its entire parent chain."""
    expected_manifest = build_candidate_manifest(
        root_receipt_sha, manifest["projectId"], manifest["allowedRunIds"], timelines
    )
    if _canonical(expected_manifest) != _canonical(manifest):
        raise ValueError("Candidate manifest differs from actual timelines.")
    rebuilt = build_revision_v4(
        parent_edl, root_receipt_sha, parent_receipt_sha, clips, replacements, manifest
    )
    if _canonical(rebuilt) != _canonical(revision_edl):
        raise ValueError("Replacement revision differs from its saved request.")
    runs = {t.run.run_id: t for t in timelines}
    rendered = []
    for row in rebuilt["segments"]:
        timeline = runs.get(row["runId"])
        event = (
            next((e for e in timeline.events if e.event_id == row["eventId"]), None)
            if timeline
            else None
        )
        if timeline is None or event is None:
            raise ValueError("Unknown replacement source.")
        asset = timeline.run.asset
        expected = {
            "mediaId": asset.media_id,
            "sourceSha256": asset.sha256,
            "sourcePath": str(asset.source_path),
            "sourceDurationUs": asset.duration_us,
            "evidenceIds": list(event.evidence_ids),
            "scriptDraft": "；".join(event.observable_facts),
            "uncertainty": event.uncertainty,
        }
        if any(_canonical(row.get(k)) != _canonical(v) for k, v in expected.items()) or not (
            event.source_range.start_us
            <= row["startUs"]
            < row["endUs"]
            <= event.source_range.end_us
        ):
            raise ValueError("Replacement source binding is invalid.")
        rendered.append(
            RenderClip(
                asset,
                SourceRange(row["startUs"], row["endUs"], asset.duration_us),
                row["outputFrames"],
                Fraction(row["speed"]["numerator"], row["speed"]["denominator"]),
            )
        )
    return RenderPlan(
        tuple(rendered),
        rebuilt["fpsNumerator"],
        tuple(r["transitionIn"]["frames"] for r in rebuilt["segments"]),
    )
