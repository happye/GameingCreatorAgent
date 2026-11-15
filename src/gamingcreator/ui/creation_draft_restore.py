"""Read-only validation of browser-local full editing snapshots."""

from typing import Any

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_replacements import candidate_manifest_sha
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary
from gamingcreator.ui import narration_jobs
from gamingcreator.ui.overlay_jobs import resolve_selection
from gamingcreator.ui.revision_jobs import (
    load_chain,
    prepare_revision,
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
    if not isinstance(request, dict) or set(request) != required:
        raise ValueError("Expected exact draft restore fields")
    chain = load_chain(jobs, request["parentJobId"], request["planId"], read_only=True)
    if (
        chain.project_id != request["projectId"]
        or chain.digest != request["expectedParentReceiptSha256"]
    ):
        raise ValueError("Draft parent or project changed")
    revision_request = dict(request)
    if chain.manifest is not None:
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
    mix = resolve_audio(jobs, request, chain.audio_mix)
    last = revised["segments"][-1]
    frames = last["outputStartFrame"] + last["outputFrames"]
    resolve_selection(OverlayAssetLibrary(jobs.repository), {}, chain.overlays, frames)
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
        "subtitleOverrides": overrides,
        "audioMix": mix.to_json(),
        "narration": selection.to_json() if selection is not None else None,
        "narrationAsset": narration_jobs.public(selection.asset_job_id, artifact)
        if selection is not None and artifact is not None
        else None,
    }
