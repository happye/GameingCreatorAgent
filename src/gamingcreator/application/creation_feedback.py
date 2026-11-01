"""Recommendation → choice → edits → output feedback, derived from saved creation jobs.

Pure: the caller loads job records. Nothing is uploaded or sent anywhere; the numbers describe
how this user actually used the recommendations on this machine.
"""

import hashlib
from collections import Counter
from typing import Any

EDIT_KINDS = ("删镜头", "换顺序", "裁剪", "变速", "转场", "替换镜头", "字幕", "配乐", "旁白")


def _rows(segments: object) -> list[dict[str, Any]]:
    return [row for row in segments if isinstance(row, dict)] if isinstance(segments, list) else []


DEFAULT_SETTINGS: dict[str, Any] = {
    "subtitleOverrides": [],
    "audioMix": {"bgm": None, "sourceGainDb": 0, "ducking": "off"},
    "narration": None,
}


def effective_settings(parent: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Omitted fields inherit, as revision saving does; present fields replace."""
    return {
        key: request.get(key, parent.get(key, value)) for key, value in DEFAULT_SETTINGS.items()
    }


def edit_kinds(
    parent: list[dict[str, Any]],
    request: dict[str, Any],
    parent_settings: dict[str, Any] | None = None,
) -> list[str]:
    """What one saved revision changed relative to its parent's clip rows and settings.

    The page always resends subtitle/audio settings, so a setting only counts as edited when
    it differs from what the parent version had in effect.
    """
    kinds: list[str] = []
    clips = _rows(request.get("clips"))
    before = {row.get("clipId"): row for row in parent}
    kept = [row for row in clips if row.get("clipId") in before]
    if len(kept) < len(before):
        kinds.append("删镜头")
    order = [
        row.get("clipId") for row in parent if row.get("clipId") in {r.get("clipId") for r in kept}
    ]
    if [row.get("clipId") for row in kept] != order:
        kinds.append("换顺序")
    if any(
        (row.get("startUs"), row.get("endUs"))
        != (before[row["clipId"]].get("startUs"), before[row["clipId"]].get("endUs"))
        for row in kept
    ):
        kinds.append("裁剪")
    speed = {"numerator": 1, "denominator": 1}
    if any(row.get("speed", speed) != before[row["clipId"]].get("speed", speed) for row in kept):
        kinds.append("变速")
    cut = {"type": "cut", "frames": 0}
    if any(
        row.get("transitionIn", cut) != before[row["clipId"]].get("transitionIn", cut)
        for row in kept
    ):
        kinds.append("转场")
    if request.get("replacements"):
        kinds.append("替换镜头")
    before_settings = effective_settings(parent_settings or {}, {})
    # Deleting a shot also drops its subtitle override; that alone is not a subtitle edit.
    kept_ids = {row.get("clipId") for row in kept}
    overrides = before_settings["subtitleOverrides"]
    before_settings["subtitleOverrides"] = (
        [o for o in overrides if not isinstance(o, dict) or o.get("clipId") in kept_ids]
        if isinstance(overrides, list)
        else overrides
    )
    for key, kind in (("subtitleOverrides", "字幕"), ("audioMix", "配乐"), ("narration", "旁白")):
        if key in request and request[key] != before_settings[key]:
            kinds.append(kind)
    return kinds


def plan_preferences(summary: dict[str, Any]) -> dict[str, int]:
    """How many chosen plans of each structure this user carried through to a finished video."""
    counts: Counter[str] = Counter()
    for row in summary.get("rows") or []:
        if isinstance(row, dict) and row.get("render") and isinstance(row.get("planId"), str):
            counts[row["planId"]] += 1
    return dict(sorted(counts.items()))


def summarize_feedback(jobs: list[dict[str, Any]]) -> dict[str, object]:
    """jobs: {jobId, kind, status, request, plans?, segments?, root?} for completed jobs only."""
    done = {job["jobId"]: job for job in jobs if job.get("status") == "completed"}
    plans = {key: job for key, job in done.items() if job.get("kind") == "plan"}
    chains: dict[tuple[str, str], dict[str, Any]] = {}

    def chain(root: str, plan_id: str) -> dict[str, Any] | None:
        plan_job = plans.get(root)
        if plan_job is None:
            return None
        listed = plan_job.get("plans") or []
        recommended = listed[0]["id"] if listed and listed[0].get("mode") else None
        return chains.setdefault(
            (root, plan_id),
            {
                "planJobId": root,
                "planId": plan_id,
                "recommended": recommended,
                "adopted": recommended is not None and plan_id == recommended,
                "revisions": 0,
                "edits": Counter(),
                "render": False,
                "publication": False,
                "package": False,
            },
        )

    revision_chain: dict[str, dict[str, Any]] = {}
    settings: dict[str, dict[str, Any]] = {}
    for key, job in sorted(done.items(), key=lambda item: item[1].get("createdAt", "")):
        if job.get("kind") != "revision":
            continue
        root = job.get("root") or {}
        current = chain(str(root.get("rootJobId")), str(root.get("rootPlanId")))
        if current is None:
            continue
        revision_chain[key] = current
        current["revisions"] += 1
        parent_id = job["request"].get("parentJobId")
        parent = done.get(parent_id, {})
        if parent.get("kind") == "revision":
            parent_rows = _rows(parent.get("segments"))
        else:
            # Root plan rows carry no clip IDs; the editor derives them from the root receipt.
            segments = next(
                (
                    _rows(p.get("segments"))
                    for p in parent.get("plans") or []
                    if p.get("id") == root.get("rootPlanId")
                ),
                [],
            )
            receipt = str(root.get("rootReceiptSha256"))
            parent_rows = [
                {**row, "clipId": hashlib.sha256(f"{receipt}:{index}".encode()).hexdigest()}
                for index, row in enumerate(segments)
            ]
        parent_settings = settings.get(parent_id, {})
        settings[key] = effective_settings(parent_settings, job["request"])
        if parent_rows:
            current["edits"].update(edit_kinds(parent_rows, job["request"], parent_settings))
    render_chain: dict[str, dict[str, Any]] = {}
    for key, job in done.items():
        if job.get("kind") != "render":
            continue
        request = job["request"]
        current = (
            revision_chain.get(request.get("revisionJobId", ""))
            if "revisionJobId" in request
            else chain(str(request.get("planJobId")), str(request.get("planId")))
        )
        if current is not None:
            current["render"] = True
            render_chain[key] = current
    publication_chain: dict[str, dict[str, Any]] = {}
    for key, job in done.items():
        if job.get("kind") == "publication":
            current = render_chain.get(job["request"].get("renderJobId", ""))
            if current is not None:
                current["publication"] = True
                publication_chain[key] = current
    for job in done.values():
        if job.get("kind") == "package":
            current = publication_chain.get(job["request"].get("publicationJobId", ""))
            if current is not None:
                current["package"] = True
    rows = list(chains.values())
    offered = [row for row in rows if row["recommended"] is not None]
    edits: Counter[str] = Counter()
    for row in rows:
        edits.update(row["edits"])
    return {
        "schemaVersion": "creation-feedback-v1",
        "basis": "本机已保存的创作任务记录（只读统计，未上传）",
        "plansGenerated": len(plans),
        "chains": len(rows),
        "recommendationOffered": len(offered),
        "recommendationAdopted": sum(row["adopted"] for row in offered),
        "averageRevisions": round(sum(row["revisions"] for row in rows) / len(rows), 2)
        if rows
        else None,
        "editKinds": {kind: edits[kind] for kind in EDIT_KINDS if edits[kind]},
        "funnel": {
            "chosen": len(rows),
            "rendered": sum(row["render"] for row in rows),
            "published": sum(row["publication"] for row in rows),
            "packaged": sum(row["package"] for row in rows),
        },
        "rows": [
            {**row, "edits": dict(row["edits"])}
            for row in sorted(rows, key=lambda r: (r["planJobId"], r["planId"]))
        ],
    }
