"""List saved advertising edits by verified root and parent receipts."""

import hashlib
import json
from collections import defaultdict
from typing import Any

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.local_files import read_bounded


def _summary(
    jobs: Any, state: dict[str, Any], parent: dict[str, Any], plans: set[str], fps: int
) -> dict[str, Any]:
    job_id = state["jobId"]
    directory = jobs.directory(job_id)
    stored = jobs._projection_identity(directory, state)
    request = stored["request"]
    plan_id = request["planId"]
    if (
        plan_id not in plans
        or parent.get("planId", plan_id) != plan_id
        or request["parentJobId"] != parent["revisionJobId"]
        or request["expectedParentReceiptSha256"] != parent["revisionReceiptSha256"]
        or stored["parentReceiptSha256"] != parent["revisionReceiptSha256"]
    ):
        raise ValueError("Revision does not belong to this ad plan")
    receipt_raw = read_bounded(jobs.safe(directory / "result/receipt.json"))
    if hashlib.sha256(receipt_raw).hexdigest() != state["resultReceiptSha256"]:
        raise ValueError("Revision receipt changed")
    receipt = json.loads(receipt_raw)
    required = {"edit-decision.json", "revision.json"}
    if "candidateManifestSha256" in request:
        required.add("candidates.json")
    files = receipt["files"]
    if set(files) != required or any(
        hash_file(jobs.safe(directory / "result" / name)) != files[name]
        for name in required - {"edit-decision.json"}
    ):
        raise ValueError("Revision metadata or candidate manifest changed")
    raw = read_bounded(jobs.safe(directory / "result/edit-decision.json"), 32_000_000)
    if hashlib.sha256(raw).hexdigest() != files["edit-decision.json"]:
        raise ValueError("Revision edit decision changed")
    edit = json.loads(raw)
    if edit["selectedPlan"] != plan_id:
        raise ValueError("Revision plan selection changed")
    segments = edit["segments"]
    last = segments[-1]
    speeds = {
        (row["speed"]["numerator"], row["speed"]["denominator"]) if "speed" in row else (1, 1)
        for row in segments
    }
    return {
        "planId": plan_id,
        "revisionJobId": job_id,
        "revisionReceiptSha256": state["resultReceiptSha256"],
        "createdAt": state["createdAt"],
        "fps": fps,
        "frames": last["outputStartFrame"] + last["outputFrames"],
        "hasMusic": (
            request["audioMix"].get("bgm") is not None
            if "audioMix" in request
            else parent["hasMusic"]
        ),
        "hasNarration": (
            request["narration"] is not None if "narration" in request else parent["hasNarration"]
        ),
        "speeds": [{"numerator": n, "denominator": d} for n, d in sorted(speeds)],
        **jobs._name(job_id),
    }


def revisions_for_plan(jobs: Any, plan: dict[str, Any], ready: set[str]) -> dict[str, Any]:
    """Read local revision receipts and edit decisions without opening source media."""
    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for state in jobs._statuses():
        if (
            state.get("kind") == "revision"
            and state.get("status") == "completed"
            and state.get("projectId") == plan["projectId"]
            and state.get("jobId") == state["directory"].name
            and isinstance(state.get("parentJobId"), str)
        ):
            children[state["parentJobId"]].append(state)
    root = {
        "revisionJobId": plan["jobId"],
        "revisionReceiptSha256": plan["resultReceiptSha256"],
        "hasMusic": False,
        "hasNarration": False,
    }
    pending = [(root, 0)]
    rows = []
    unavailable = 0
    while pending:
        parent, depth = pending.pop()
        for state in children.pop(parent["revisionJobId"], []):
            if depth == 63:
                unavailable += 1
                continue
            try:
                row = _summary(jobs, state, parent, ready, plan["fps"])
            except (AppError, OSError, ValueError, TypeError, KeyError, IndexError):
                unavailable += 1
                continue
            rows.append(row)
            pending.append((row, depth + 1))
    rows.sort(key=lambda row: (row["createdAt"], row["revisionJobId"]), reverse=True)
    return {"revisions": rows, "unavailable": unavailable}
