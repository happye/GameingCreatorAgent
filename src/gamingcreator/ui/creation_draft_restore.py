"""Read-only validation of browser-local full editing snapshots."""

from typing import Any

from gamingcreator.application.creation_companion_timing import (
    CompanionTimingError,
    move_start_frame,
)
from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_replacements import candidate_manifest_sha
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.showcase_topics import candidate_topic_projector
from gamingcreator.domain.creation_overlays import CreationOverlays
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary
from gamingcreator.ui import narration_jobs
from gamingcreator.ui.overlay_jobs import public_asset, resolve_assets
from gamingcreator.ui.replacement_jobs import manifest_for_chain, public_candidate
from gamingcreator.ui.revision_jobs import (
    attach_saved_candidate_topics,
    editable_clips,
    load_chain,
    prepare_revision,
    replacement_clip_ids,
    resolve_audio,
    resolve_overrides,
)


def preview(
    jobs: Any,
    request: dict[str, Any],
    *,
    follow_shots: frozenset[str] = frozenset(),
    layout_only: bool = False,
) -> dict[str, Any]:
    required = {
        "projectId",
        "parentJobId",
        "planId",
        "expectedParentReceiptSha256",
        "clips",
        "subtitleOverrides",
        "audioMix",
        "narration",
    }
    extended = {"candidateManifestSha256", "replacements", "overlays"}
    if not isinstance(request, dict) or set(request) not in (
        required,
        required | extended,
        required | extended | {"insertions"},
    ):
        raise ValueError("Expected exact draft restore fields")
    chain = load_chain(jobs, request["parentJobId"], request["planId"], read_only=True)
    if (
        chain.project_id != request["projectId"]
        or chain.digest != request["expectedParentReceiptSha256"]
    ):
        raise ValueError("Draft parent or project changed")
    revision_request = dict(request)
    is_v3 = extended <= request.keys()
    if is_v3 and not isinstance(request["replacements"], list):
        raise ValueError("Replacement operations must be an array")
    if is_v3 and request["candidateManifestSha256"] is None:
        if request["replacements"] or chain.manifest is not None:
            raise ValueError("Replacement manifest is required")
        if revision_request.get("insertions"):
            raise ValueError("Insertion manifest is required")
        revision_request.pop("insertions", None)
        revision_request.pop("candidateManifestSha256")
        revision_request.pop("replacements")
    if not is_v3 and chain.manifest is not None:
        revision_request.update(
            candidateManifestSha256=candidate_manifest_sha(chain.manifest), replacements=[]
        )
    revised, manifest = prepare_revision(jobs, revision_request, chain)
    if manifest is None:
        validate_revision(
            select_edit_decision(chain.report, chain.plan_id),
            chain.report,
            chain.edl,
            revised,
            chain.timelines,
            chain.root_sha,
        )
    overrides = resolve_overrides(request, chain.subtitle_overrides, revised, chain.root_sha)
    public_ids = {new: target for target, new in replacement_clip_ids(revised).items()}
    overrides = [
        {**item, "clipId": public_ids.get(item["clipId"], item["clipId"])} for item in overrides
    ]
    result = {
        "subtitleOverrides": overrides,
        "audioMix": resolve_audio(jobs, request, chain.audio_mix).to_json(),
    }
    if not layout_only:
        timing = project_timing(jobs, chain, revised, request, follow_shots)
        result.update(timing if is_v3 else {k: timing[k] for k in ("narration", "narrationAsset")})
    if is_v3:
        result.update(project_clips(jobs, request, chain, manifest))
    return result


def project_timing(
    jobs: Any, chain: Any, revised: dict[str, Any], request: dict[str, Any], follow: frozenset[str]
) -> dict[str, Any]:
    """Reposition inherited assets before validating bounds against the new program."""
    rows = revised["segments"]
    frames = rows[-1]["outputStartFrame"] + rows[-1]["outputFrames"]
    if follow:
        request = _move_inherited(chain, revised, request, follow)
    library = OverlayAssetLibrary(jobs.repository)
    layers = (
        CreationOverlays.from_json(request["overlays"]) if "overlays" in request else chain.overlays
    )
    try:
        layers.validate_duration(frames)
    except ValueError as error:
        raise CompanionTimingError(
            "图层超出修改后的成片时长。请启用随原镜移动、调整图层时长或修改指令。"
        ) from error
    return {
        **project_narration(jobs, request, chain, frames),
        "overlays": layers.to_json(),
        "overlayAssets": [public_asset(asset) for asset in resolve_assets(library, layers)],
    }


def _move_inherited(
    chain: Any, revised: dict[str, Any], request: dict[str, Any], follow: frozenset[str]
) -> dict[str, Any]:
    before = editable_clips(chain.edl, chain.root_sha)
    swapped = replacement_clip_ids(revised)
    after = {
        row["clipId"]: row for row in revised["segments"] if row["clipId"] not in swapped.values()
    }

    def move(frame: int, label: str) -> int:
        return move_start_frame(frame, before, after, chain.plan.fps, label)

    selection = dict(request)
    if "narration" in follow and chain.narration is not None:
        narration = chain.narration.to_json()
        narration["startFrame"] = move(narration["startFrame"], "旁白")
        selection["narration"] = narration
    if "overlays" in follow:
        layers = chain.overlays.to_json()
        for index, item in enumerate(layers["items"], 1):
            start = move(item["startFrame"], f"第 {index} 个图层")
            item["endFrame"] += start - item["startFrame"]
            item["startFrame"] = start
        selection["overlays"] = layers
    return selection


def project_clips(jobs: Any, request: dict[str, Any], chain: Any, manifest: Any) -> dict[str, Any]:
    """Rebuild target identities only after authoritative revision validation."""
    timelines = chain.timelines
    if manifest is not None:
        verified_manifest, timelines = manifest_for_chain(jobs, chain)
        if verified_manifest != manifest:
            raise ValueError("Candidate manifest changed before draft projection")
    evidence = candidate_topic_projector(
        timelines, chain.report["brief"]["mandatoryTopics"], plan_id=chain.plan_id
    )
    detached = editable_clips(chain.edl, chain.root_sha)
    attach_saved_candidate_topics(chain, detached, evidence)
    parents = {c["clipId"]: c for c in detached}
    additions = {r["newClipId"]: r for r in request.get("insertions", [])}
    candidates = {c["candidateId"]: c for c in manifest["candidates"]} if manifest else {}
    swaps = {r["targetClipId"]: r["candidateId"] for r in request["replacements"]}
    clips, bounds = [], {}
    for row in request["clips"]:
        identity = row["clipId"]
        source = parents.get(identity)
        insertion = additions.get(identity)
        if insertion is not None:
            candidate = candidates[insertion["candidateId"]]
            source = public_candidate(
                candidate,
                timelines,
                request["parentJobId"],
                chain.plan_id,
                request["candidateManifestSha256"],
                topic_evidence=evidence(candidate),
            )
            source.update(startUs=insertion["startUs"], endUs=insertion["endUs"])
        if identity in swaps:
            candidate = candidates[swaps[identity]]
            source = public_candidate(
                candidate,
                timelines,
                request["parentJobId"],
                chain.plan_id,
                request["candidateManifestSha256"],
                topic_evidence=evidence(candidate),
            )
        if source is None:
            raise ValueError("Unknown draft clip identity")
        bounds[identity] = {k: source[k] for k in ("startUs", "endUs")}
        projected = {**{k: v for k, v in source.items() if k != "sourcePath"}, **row}
        topic_evidence = projected.get("candidateTopicEvidence")
        if topic_evidence is not None and not (
            topic_evidence["sourceStartUs"]
            <= row["startUs"]
            < row["endUs"]
            <= topic_evidence["sourceEndUs"]
        ):
            projected.pop("candidateTopicEvidence")
        clips.append(projected)
    return {
        "clips": clips,
        **({"insertions": request["insertions"]} if "insertions" in request else {}),
        "bounds": bounds,
        "replacements": request["replacements"],
        "candidateManifestSha256": request["candidateManifestSha256"],
    }


def project_narration(
    jobs: Any, request: dict[str, Any], chain: Any, frames: int
) -> dict[str, Any]:
    selection = narration_jobs.resolve(
        jobs,
        request,
        chain.narration,
        chain.project_id,
        frames,
        chain.plan.fps,
        read_only=True,
    )
    artifact = (
        narration_jobs.asset(jobs, selection, chain.project_id, read_only=True)
        if selection is not None
        else None
    )
    return {
        "narration": selection.to_json() if selection is not None else None,
        "narrationAsset": narration_jobs.public(selection.asset_job_id, artifact)
        if selection is not None and artifact is not None
        else None,
    }
