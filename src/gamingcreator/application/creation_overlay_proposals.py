"""Text-only proposals can adjust timing of existing, verified output layers."""

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from gamingcreator.application.creation_proposals import (
    CreationProposal,
    EditingSnapshot,
    canonical,
    create_snapshot,
)
from gamingcreator.domain.creation_overlays import CreationOverlays

if TYPE_CHECKING:
    from gamingcreator.application.creation_reasoning import ReasoningRequest

SCHEMA_VERSION = "creation-reasoning-overlays-v1"
PROMPT_VERSION = "creation-reasoning-overlays-prompt-v1"
SNAPSHOT_VERSION = "creation-overlay-snapshot-v1"


def base_snapshot(snapshot: EditingSnapshot) -> EditingSnapshot:
    data = snapshot.payload
    return create_snapshot(
        data["jobId"],
        data["planId"],
        data["parentReceiptSha256"],
        data["rootReceiptSha256"],
        data["parent_edl"],
    )


def output_frames(snapshot: EditingSnapshot) -> int:
    return int(
        max(
            r["outputStartFrame"] + r["outputFrames"]
            for r in snapshot.payload["parent_edl"]["segments"]
        )
    )


def create_overlay_snapshot(
    parent: EditingSnapshot, overlays: dict[str, Any], assets: list[dict[str, Any]]
) -> EditingSnapshot:
    selection = CreationOverlays.from_json(overlays)
    selection.validate_duration(output_frames(parent))
    indexed: dict[str, dict[str, Any]] = {}
    for asset in assets:
        fields = {"assetId", "assetReceiptSha256", "kind", "width", "height"}
        if asset.get("kind") == "text":
            fields.add("text")
        if set(asset) != fields or any(
            type(asset[k]) is not int or not 1 <= asset[k] <= 4096 for k in ("width", "height")
        ):
            raise ValueError("Invalid overlay asset context.")
        if asset["width"] * asset["height"] > 16_000_000:
            raise ValueError("Overlay asset context exceeds pixel budget.")
        if asset["assetId"] in indexed and indexed[asset["assetId"]] != asset:
            raise ValueError("Conflicting overlay asset context.")
        indexed[asset["assetId"]] = dict(asset)
    if set(indexed) != {item.asset_id for item in selection.items}:
        raise ValueError("Overlay assets must exactly match the selection.")
    for item in selection.items:
        asset = indexed[item.asset_id]
        if (item.asset_receipt_sha256, item.kind, item.text) != (
            asset["assetReceiptSha256"],
            asset["kind"],
            asset.get("text"),
        ):
            raise ValueError("Overlay asset context does not match its layer.")
    if sum(a["width"] * a["height"] * 4 for a in indexed.values()) > 128 * 1024**2:
        raise ValueError("Overlay asset context exceeds decoded budget.")
    return EditingSnapshot(
        canonical(
            {
                **parent.payload,
                "overlaySnapshotVersion": SNAPSHOT_VERSION,
                "overlays": selection.to_json(),
                "overlayAssets": [indexed[k] for k in sorted(indexed)],
            }
        )
    )


def overlay_selection(snapshot: EditingSnapshot, response: dict[str, Any]) -> CreationOverlays:
    selection = CreationOverlays.from_json(snapshot.payload["overlays"])
    if response["kind"] != "overlay_edit_proposal":
        return selection
    patch = response.get("overlayEdit")
    if not isinstance(patch, dict) or set(patch) != {"overlayId", "endFrame", "fadeOutFrames"}:
        raise ValueError("Expected exact overlay timing fields.")
    items = selection.to_json()["items"]
    found = next((item for item in items if item["overlayId"] == patch["overlayId"]), None)
    if found is None:
        raise ValueError("Unknown overlay identity.")
    if all(found[k] == patch[k] for k in ("endFrame", "fadeOutFrames")):
        raise ValueError("Overlay proposal makes no change.")
    found.update(endFrame=patch["endFrame"], fadeOutFrames=patch["fadeOutFrames"])
    result = CreationOverlays.from_json({"schemaVersion": "creation-overlays-v1", "items": items})
    result.validate_duration(output_frames(snapshot))
    return result


def validate_overlay_proposal(
    snapshot: EditingSnapshot, response: dict[str, Any]
) -> CreationProposal:
    from gamingcreator.application.creation_proposals import validate_proposal

    fields = {"schemaVersion", "kind", "message", "questions", "clips", "citations", "overlayEdit"}
    if (
        not isinstance(response, dict)
        or set(response) != fields
        or len(canonical(response)) > 200_000
    ):
        raise ValueError("Unexpected overlay reasoning fields.")
    if response["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("Unsupported overlay reasoning schema.")
    parent = base_snapshot(snapshot)
    if response["kind"] != "overlay_edit_proposal":
        if response["overlayEdit"] is not None:
            raise ValueError("Clip proposals cannot change overlays.")
        old = {k: v for k, v in response.items() if k != "overlayEdit"}
        old["schemaVersion"] = "creation-reasoning-v1"
        result = validate_proposal(parent, old)
        # Clip edits must not silently truncate inherited layers.
        if response["kind"] == "edit_proposal":
            from gamingcreator.application.creation_editing import build_revision
            from gamingcreator.application.creation_proposals import editing_parent

            revised = build_revision(
                editing_parent(parent.payload["parent_edl"]),
                parent.payload["rootReceiptSha256"],
                response["clips"],
            )
            frames = max(r["outputStartFrame"] + r["outputFrames"] for r in revised["segments"])
            overlay_selection(snapshot, response).validate_duration(frames)
        return replace(
            result, snapshot_fingerprint=snapshot.fingerprint, response_json=canonical(response)
        )
    message = response["message"]
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise ValueError("Invalid overlay proposal message.")
    if response["clips"] != [] or response["questions"] != []:
        raise ValueError("Overlay proposals cannot also edit clips or ask questions.")
    overlay_selection(snapshot, response)
    identity = response["overlayEdit"]["overlayId"]
    if response["citations"] != [identity]:
        raise ValueError("Overlay proposals must cite their existing layer.")
    seconds = output_frames(snapshot) / snapshot.payload["parent_edl"]["fpsNumerator"]
    return CreationProposal(
        snapshot.fingerprint,
        snapshot.payload["parentReceiptSha256"],
        canonical(response),
        seconds,
        seconds,
        (identity,),
    )


def overlay_reasoning_request(snapshot: EditingSnapshot, instruction: str) -> "ReasoningRequest":
    from gamingcreator.application.creation_reasoning import ReasoningRequest, reasoning_request

    old = reasoning_request(base_snapshot(snapshot), instruction)
    data = json.loads(old.user)
    assets = {a["assetId"]: a for a in snapshot.payload["overlayAssets"]}
    data["context"]["overlays"] = [
        {
            **{k: v for k, v in item.items() if k not in ("assetId", "assetReceiptSha256")},
            "spriteWidth": assets[item["assetId"]]["width"],
            "spriteHeight": assets[item["assetId"]]["height"],
        }
        for item in snapshot.payload["overlays"]["items"]
    ]
    data["context"]["totalFrames"] = output_frames(snapshot)
    data["context"]["supportedOperations"].extend(["overlay_end", "overlay_fade_out"])
    system = old.system.replace(
        "Return exactly schemaVersion, kind, message, questions, clips, citations.",
        "Return exactly schemaVersion, kind, message, questions, clips, citations, overlayEdit.",
    ).replace("schemaVersion is creation-reasoning-v1", f"schemaVersion is {SCHEMA_VERSION}")
    system += """
Additional kind overlay_edit_proposal adjusts one EXISTING independent overlay only.
overlayEdit is null for all other kinds. For overlay_edit_proposal, clips/questions are empty,
citations contains exactly the existing overlayId, and overlayEdit has exactly overlayId,
endFrame, fadeOutFrames (integer output frames). Keep start, fade-in, assets, position and text.
End must remain inside totalFrames, after start, with fades fitting the interval.
An image layer is not proof of a logo. If the intended layer is ambiguous, ask clarification.
Never claim to see/remove a logo baked into source footage. Never invent assets or identities.
"""
    return ReasoningRequest(system, canonical(data), PROMPT_VERSION, SCHEMA_VERSION)
