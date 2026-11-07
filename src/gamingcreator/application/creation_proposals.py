"""Trusted snapshots and bounded, source-preserving model proposals; no I/O."""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from gamingcreator.application.creation_editing import build_revision, editable_clips
from gamingcreator.application.creation_replacements import build_revision_v4

SCHEMA_VERSION = "creation-reasoning-v1"
CLIP_KEYS = {"clipId", "startUs", "endUs", "speed", "transitionIn"}


def editing_parent(edl: dict[str, Any]) -> dict[str, Any]:
    """Compatibility for pure editing math after server load_chain verified v4."""
    if edl.get("schemaVersion") == "edit-decision-revision-v4":
        return {**edl, "schemaVersion": "edit-decision-revision-v3"}
    return edl


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


@dataclass(frozen=True)
class EditingSnapshot:
    """Construct only from a server-verified load_chain result, never client clips."""

    payload_json: str

    @property
    def fingerprint(self) -> str:
        return sha256(self.payload_json.encode("utf-8")).hexdigest()

    @property
    def payload(self) -> dict[str, Any]:
        return dict(json.loads(self.payload_json))


def create_snapshot(
    job_id: str,
    plan_id: str,
    parent_receipt_sha256: str,
    root_receipt_sha256: str,
    parent_edl: dict[str, Any],
) -> EditingSnapshot:
    editable_clips(editing_parent(parent_edl), root_receipt_sha256)
    for value in (parent_receipt_sha256, root_receipt_sha256):
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid receipt SHA256.")
    if not job_id or not plan_id:
        raise ValueError("Snapshot requires job and plan identities.")
    return EditingSnapshot(
        canonical(
            {
                "jobId": job_id,
                "planId": plan_id,
                "parentReceiptSha256": parent_receipt_sha256,
                "rootReceiptSha256": root_receipt_sha256,
                "parent_edl": parent_edl,
            }
        )
    )


def clip_rows(snapshot: EditingSnapshot) -> list[dict[str, Any]]:
    data = snapshot.payload
    return [
        {
            "clipId": r["clipId"],
            "startUs": r["startUs"],
            "endUs": r["endUs"],
            "speed": r.get("speed", {"numerator": 1, "denominator": 1}),
            "transitionIn": r.get("transitionIn", {"type": "cut", "frames": 0}),
        }
        for r in editable_clips(editing_parent(data["parent_edl"]), data["rootReceiptSha256"])
    ]


@dataclass(frozen=True)
class CreationProposal:
    snapshot_fingerprint: str
    parent_receipt_sha256: str
    response_json: str
    before_seconds: float
    after_seconds: float
    changes: tuple[str, ...]

    @property
    def response(self) -> dict[str, Any]:
        result = dict(json.loads(self.response_json))
        result["message"] = "模型建议（仅基于文字，尚未应用）：" + result["message"]
        return result


def _strings(value: Any, limit: int, length: int) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > limit
        or any(not isinstance(s, str) or not s.strip() or len(s) > length for s in value)
    ):
        raise ValueError("Invalid bounded string array.")
    return value


def _response(value: dict[str, Any], existing: list[dict[str, Any]]) -> set[str]:
    if set(value) != {"schemaVersion", "kind", "message", "questions", "clips", "citations"}:
        raise ValueError("Unexpected reasoning fields.")
    if value["schemaVersion"] != SCHEMA_VERSION or value["kind"] not in (
        "clarification",
        "edit_proposal",
        "unsupported",
    ):
        raise ValueError("Unsupported reasoning schema or kind.")
    _strings([value["message"]], 1, 2000)
    questions = _strings(value["questions"], 8, 500)
    citations = _strings(value["citations"], 200, 128)
    ids = {r["clipId"] for r in existing}
    if len(set(citations)) != len(citations) or not set(citations) <= ids:
        raise ValueError("Unknown or duplicate citations.")
    clips = value["clips"]
    if not isinstance(clips, list) or len(clips) > min(200, len(existing)):
        raise ValueError("Invalid clip array.")
    if value["kind"] != "edit_proposal":
        if clips:
            raise ValueError("Clarification and unsupported results cannot edit.")
        return set()
    if not clips or questions:
        raise ValueError("Editing requires clips and no pending questions.")
    if any(not isinstance(c, dict) or set(c) != CLIP_KEYS for c in clips):
        raise ValueError("Editing requires exact v3 clip rows.")
    # Changed positions include reordered survivors; deleted IDs must also be cited.
    changed = {r["clipId"] for i, r in enumerate(existing) if i >= len(clips) or clips[i] != r}
    if not changed <= set(citations):
        raise ValueError("Every changed or deleted clip needs a citation.")
    return changed


def _seconds(edl: dict[str, Any]) -> float:
    rows = edl["segments"]
    return float(max(r["outputStartFrame"] + r["outputFrames"] for r in rows) / edl["fpsNumerator"])


def validate_proposal(snapshot: EditingSnapshot, output: dict[str, Any]) -> CreationProposal:
    if not isinstance(output, dict) or len(canonical(output)) > 200_000:
        raise ValueError("Invalid or oversized model output.")
    if "overlaySnapshotVersion" in snapshot.payload:
        from gamingcreator.application.creation_overlay_proposals import validate_overlay_proposal

        return validate_overlay_proposal(snapshot, output)
    rows = clip_rows(snapshot)
    changes = _response(output, rows)
    data = snapshot.payload
    parent = data["parent_edl"]
    after = parent
    if output["kind"] == "edit_proposal":
        after = build_revision(editing_parent(parent), data["rootReceiptSha256"], output["clips"])
    return CreationProposal(
        snapshot.fingerprint,
        data["parentReceiptSha256"],
        canonical(output),
        _seconds(parent),
        _seconds(after),
        tuple(sorted(changes)),
    )


def revision_for_application(
    proposal: CreationProposal,
    current_snapshot: EditingSnapshot,
    *,
    candidate_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reload the trusted chain before calling; caller owns manual consent and persistence."""
    if (
        proposal.snapshot_fingerprint != current_snapshot.fingerprint
        or proposal.parent_receipt_sha256 != current_snapshot.payload["parentReceiptSha256"]
    ):
        raise ValueError("Stale proposal; request a new preview.")
    output = json.loads(proposal.response_json)
    # Revalidate on application even when an adapter reconstructed this object.
    validate_proposal(current_snapshot, output)
    if output["kind"] == "overlay_edit_proposal":
        output = {**output, "clips": clip_rows(current_snapshot)}
    elif output["kind"] != "edit_proposal":
        raise ValueError("This response has no edit to apply.")
    data = current_snapshot.payload
    if data["parent_edl"].get("schemaVersion") == "edit-decision-revision-v4":
        if candidate_manifest is None:
            raise ValueError("A v4 parent requires its verified candidate manifest.")
        return build_revision_v4(
            data["parent_edl"],
            data["rootReceiptSha256"],
            data["parentReceiptSha256"],
            output["clips"],
            [],
            candidate_manifest,
        )
    return build_revision(data["parent_edl"], data["rootReceiptSha256"], output["clips"])
