"""Read-only draft subtitle projection through the export pipeline."""

from dataclasses import replace
from typing import Any

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.creation_replacements import validate_revision_v4
from gamingcreator.application.creation_subtitles import present_subtitles
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.domain.creation_subtitles import quantize_srt
from gamingcreator.infrastructure.ffmpeg_render import burn_events
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
        "candidateManifestSha256",
        "replacements",
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

    if mode == "burn":
        escaped = str.maketrans("\\{}", "＼｛｝")
        events = []
        for start, end, text, lifted in burn_events(saved):
            owners = [
                cue
                for cue in saved
                if cue.start <= start and end <= cue.end and cue.text.translate(escaped) == text
            ]
            events.append(
                (start, end, text, lifted, owners[0].clip_index if len(owners) == 1 else None)
            )
    else:
        events = [(cue.start, cue.end, cue.text, False, cue.clip_index) for cue in saved]
    scale = 100 if mode == "burn" else 1000
    result = [
        {
            "startUs": int(start * scale) * (1000000 // scale),
            "endUs": int(end * scale) * (1000000 // scale),
            "text": text,
            "lifted": lifted,
            **clip_id(index),
        }
        for start, end, text, lifted, index in events
    ]
    return {
        "cues": result,
        "mode": mode,
        "subtitleSource": presentation.source,
        "wordHighlights": presentation.word_highlights,
    }
