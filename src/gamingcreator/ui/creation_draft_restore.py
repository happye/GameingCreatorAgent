"""Read-only validation of browser-local full editing snapshots."""

from typing import Any

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_replacements import candidate_manifest_sha
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary
from gamingcreator.ui import narration_jobs
from gamingcreator.ui.overlay_jobs import public_asset, resolve_assets, resolve_selection
from gamingcreator.ui.replacement_jobs import manifest_for_chain, public_candidate
from gamingcreator.ui.revision_jobs import (
    editable_clips,
    load_chain,
    prepare_revision,
    replacement_clip_ids,
    resolve_audio,
    resolve_overrides,
)


def preview(jobs: Any, request: dict[str, Any]) -> dict[str, Any]:
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
    if not isinstance(request, dict) or set(request) not in (required, required | extended):
        raise ValueError("Expected exact draft restore fields")
    chain = load_chain(jobs, request["parentJobId"], request["planId"], read_only=True)
    if (
        chain.project_id != request["projectId"]
        or chain.digest != request["expectedParentReceiptSha256"]
    ):
        raise ValueError("Draft parent or project changed")
    revision_request = dict(request)
    is_v3 = set(request) == required | extended
    if is_v3 and not isinstance(request["replacements"], list):
        raise ValueError("Replacement operations must be an array")
    if is_v3 and request["candidateManifestSha256"] is None:
        if request["replacements"] or chain.manifest is not None:
            raise ValueError("Replacement manifest is required")
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
    mix = resolve_audio(jobs, request, chain.audio_mix)
    last = revised["segments"][-1]
    frames = last["outputStartFrame"] + last["outputFrames"]
    library = OverlayAssetLibrary(jobs.repository)
    overlays = resolve_selection(library, request if is_v3 else {}, chain.overlays, frames)
    result = {
        "subtitleOverrides": overrides,
        "audioMix": mix.to_json(),
        **project_narration(jobs, request, chain, frames),
    }

    if is_v3:
        result.update(project_clips(jobs, request, chain, manifest))
        result.update(
            overlays=overlays.to_json(),
            overlayAssets=[public_asset(a) for a in resolve_assets(library, overlays)],
        )
    return result


def project_clips(jobs: Any, request: dict[str, Any], chain: Any, manifest: Any) -> dict[str, Any]:
    """Rebuild target identities only after authoritative revision validation."""
    timelines = manifest_for_chain(jobs, chain)[1] if manifest else chain.timelines
    parents = {c["clipId"]: c for c in editable_clips(chain.edl, chain.root_sha)}
    candidates = {c["candidateId"]: c for c in manifest["candidates"]} if manifest else {}
    swaps = {r["targetClipId"]: r["candidateId"] for r in request["replacements"]}
    clips, bounds = [], {}
    for row in request["clips"]:
        identity = row["clipId"]
        source = parents[identity]
        if identity in swaps:
            source = public_candidate(
                candidates[swaps[identity]],
                timelines,
                request["parentJobId"],
                chain.plan_id,
                request["candidateManifestSha256"],
            )
        bounds[identity] = {k: source[k] for k in ("startUs", "endUs")}
        clips.append({**{k: v for k, v in source.items() if k != "sourcePath"}, **row})
    return {
        "clips": clips,
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
