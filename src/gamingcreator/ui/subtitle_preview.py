"""Read-only draft subtitle projection through the export pipeline."""

from dataclasses import replace
from typing import Any

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_replacements import validate_revision_v4
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.domain.creation_subtitles import quantize_srt
from gamingcreator.infrastructure.ffmpeg_render import burn_events
from gamingcreator.ui.revision_jobs import (
    load_chain,
    prepare_revision,
    resolve_overrides,
    revision_subtitles,
)


def preview(jobs: Any, request: dict[str, Any]) -> dict[str, Any]:
    required = {
        "projectId",
        "parentJobId",
        "planId",
        "expectedParentReceiptSha256",
        "clips",
        "subtitleMode",
    }
    allowed = required | {"subtitleOverrides", "candidateManifestSha256", "replacements"}
    if not isinstance(request, dict) or not required <= request.keys() or request.keys() - allowed:
        raise ValueError("Expected draft subtitle preview fields")
    mode = request["subtitleMode"]
    if mode not in ("none", "sidecar", "burn"):
        raise ValueError("Unknown subtitle mode")
    chain = load_chain(jobs, request["parentJobId"], request["planId"], read_only=True)
    if (
        chain.project_id != request["projectId"]
        or chain.digest != request["expectedParentReceiptSha256"]
    ):
        raise ValueError("Draft parent or project changed")
    revised, manifest = prepare_revision(jobs, request, chain)
    timelines = chain.timelines
    if manifest is not None:
        from gamingcreator.ui.replacement_jobs import manifest_for_chain

        _, timelines = manifest_for_chain(jobs, chain)
        plan = validate_revision_v4(
            chain.edl,
            revised,
            chain.root_sha,
            chain.digest,
            request["clips"],
            request["replacements"],
            manifest,
            timelines,
        )
    else:
        plan = validate_revision(
            select_edit_decision(chain.report, chain.plan_id),
            chain.report,
            chain.edl,
            revised,
            timelines,
            chain.root_sha,
        )
    overrides = resolve_overrides(request, chain.subtitle_overrides, revised, chain.root_sha)
    cues = revision_subtitles(
        replace(chain, edl=revised, plan=plan, timelines=timelines, subtitle_overrides=overrides),
        mode,
    )
    saved = quantize_srt(cues)
    events = (
        burn_events(saved)
        if mode == "burn"
        else ((cue.start, cue.end, cue.text, False) for cue in saved)
    )
    scale = 100 if mode == "burn" else 1000
    result = [
        {
            "startUs": int(start * scale) * (1000000 // scale),
            "endUs": int(end * scale) * (1000000 // scale),
            "text": text,
            "lifted": lifted,
        }
        for start, end, text, lifted in events
    ]
    return {"cues": result, "mode": mode}
