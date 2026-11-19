"""Read-only draft subtitle projection through the export pipeline."""

from dataclasses import replace
from typing import Any

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_replacements import validate_revision_v4
from gamingcreator.application.creation_subtitles import present_subtitles, subtitle_layout
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.domain.creation_narration import NarrationSelection
from gamingcreator.domain.creation_subtitles import quantize_srt
from gamingcreator.infrastructure.ffmpeg_render import escape_ass_text
from gamingcreator.ui import narration_jobs
from gamingcreator.ui.revision_jobs import (
    load_chain,
    prepare_revision,
    replacement_clip_ids,
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
    allowed = required | {
        "subtitleOverrides",
        "narration",
        "candidateManifestSha256",
        "replacements",
        "insertions",
        "wordHighlights",
        "asrWords",
    }
    if not isinstance(request, dict) or not required <= request.keys() or request.keys() - allowed:
        raise ValueError("Expected draft subtitle preview fields")
    word_on = request.get("wordHighlights", False)
    asr_words = request.get("asrWords")
    if "wordHighlights" in request and type(word_on) is not bool:
        raise ValueError("Expected draft subtitle preview fields")
    if asr_words is not None and (
        not isinstance(asr_words, dict)
        or asr_words.keys() != {"runId", "resultHash"}
        or not isinstance(asr_words["runId"], str)
        or not isinstance(asr_words["resultHash"], str)
        or not asr_words["runId"]
        or not asr_words["resultHash"]
    ):
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
        from gamingcreator.application.creation_insertions import validate_revision_v5

        validator: Any = validate_revision_v5 if "insertions" in request else validate_revision_v4
        plan = validator(
            chain.edl,
            revised,
            chain.root_sha,
            chain.digest,
            request["clips"],
            request["replacements"],
            *([request["insertions"]] if "insertions" in request else []),
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
    narration, artifact = chain.narration, chain.narration_asset
    if "narration" in request:
        proposed = request["narration"]
        narration = None if proposed is None else NarrationSelection.from_json(proposed)
        if narration != chain.narration:
            artifact = (
                None
                if narration is None
                else narration_jobs.asset(jobs, narration, chain.project_id, read_only=True)
            )
    cues = revision_subtitles(
        replace(
            chain,
            edl=revised,
            plan=plan,
            timelines=timelines,
            subtitle_overrides=overrides,
            narration=narration,
            narration_asset=artifact,
        ),
        mode,
    )
    replacements = replacement_clip_ids(revised)
    reserved = [
        index
        for index, clip in enumerate(request["clips"])
        if any(
            item["clipId"] == replacements.get(clip["clipId"], clip["clipId"]) for item in overrides
        )
    ]
    words = None
    sidecar_available = False
    if word_on and asr_words is not None:
        import asyncio

        from gamingcreator.infrastructure.asr_words import load_trusted_asr_words

        words = asyncio.run(
            load_trusted_asr_words(
                jobs.project(request["projectId"]), asr_words["runId"], asr_words["resultHash"]
            )
        )
        sidecar_available = words is not None
    presentation = present_subtitles(
        cues,
        words=words,
        sidecar_available=sidecar_available,
        plan=plan if sidecar_available else None,
        reserved_clip_indexes=reserved,
    )
    saved = quantize_srt(presentation.cues)
    clip_ids = [clip["clipId"] for clip in request["clips"]]

    def clip_id(index: object) -> dict[str, str]:
        if type(index) is not int or index < 0 or index >= len(clip_ids):
            return {}
        return {"clipId": clip_ids[index]}

    scale = 100 if mode == "burn" else 1000
    events = (
        subtitle_layout(saved, scale)
        if mode == "burn" or any(cue.clip_index is None for cue in saved)
        else ((cue.start, cue.end, cue, 0) for cue in saved)
    )
    result = [
        {
            "startUs": int(start * scale) * (1000000 // scale),
            "endUs": int(end * scale) * (1000000 // scale),
            "text": escape_ass_text(cue.text) if mode == "burn" else cue.text,
            "lifted": bool(lane),
            **({"lane": lane} if lane > 1 else {}),
            **({"source": "narration"} if cue.clip_index is None else clip_id(cue.clip_index)),
        }
        for start, end, cue, lane in events
    ]
    return {
        "cues": result,
        "mode": mode,
        "subtitleSource": presentation.source,
        "wordHighlights": presentation.word_highlights,
    }
