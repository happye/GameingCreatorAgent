"""Offline template narration drafts from saved clip descriptions, sized to the output clock."""

import re
from fractions import Fraction
from typing import Any

from gamingcreator.domain.creation import CreativeBrief

# Measured on local Huihui: 21 characters took 5.688 seconds. Budget below that and keep a margin.
CHARS_PER_SECOND = Fraction(7, 2)
FILL_RATIO = Fraction(9, 10)
MAX_CLIP_CHARS = 24
_OPENINGS = {
    "feature_showcase": "{game}玩法速览",
    "guide": "{game}攻略要点",
    "campaign": "{game}活动投稿",
}
_FRAME_MARKER = re.compile(r"f\d+(?:至f\d+)?(?:中|显示|切换为|延续|开始)?")


def _sentence(description: object) -> str:
    """First observable clause of a saved description, without per-frame markers."""
    if not isinstance(description, str):
        return ""
    for clause in re.split(r"[；;。！？!?\n]", _FRAME_MARKER.sub("", description)):
        clause = clause.strip(" ，,、：:'\"“”")
        if clause:
            if len(clause) > MAX_CLIP_CHARS:
                # Prefer a whole phrase; never invent words or ellipses.
                cut = max(clause.rfind(mark, 0, MAX_CLIP_CHARS + 1) for mark in "，,、")
                clause = clause[:cut] if cut >= 6 else clause[:MAX_CLIP_CHARS]
            return clause.rstrip(" ，,、")
    return ""


def build_narration_script(
    brief: CreativeBrief, clips: list[dict[str, Any]], output_frames: int, fps: int
) -> dict[str, object]:
    if any(type(n) is not int or n <= 0 for n in (output_frames, fps)):
        raise ValueError("Narration script needs a positive output clock.")
    budget = int(Fraction(output_frames, fps) * CHARS_PER_SECOND * FILL_RATIO)
    opening = _OPENINGS.get(brief.content_type, "{game}实机片段").format(game=brief.game.strip())
    parts = [opening] if len(opening) + 1 <= budget else []
    used = sum(len(part) + 1 for part in parts)
    candidates: list[tuple[dict[str, Any], str]] = []
    for clip in clips:
        sentence = _sentence(clip.get("scriptDraft"))
        if sentence and (not candidates or candidates[-1][1] != sentence):
            candidates.append((clip, sentence))
    # One narration spans the whole video, so sample clips evenly over output time.
    chosen: list[tuple[dict[str, Any], str]] = []
    for count in range(len(candidates), 0, -1):
        picks = sorted({round(i * (len(candidates) - 1) / max(1, count - 1)) for i in range(count)})
        trial = [candidates[i] for i in picks]
        if used + sum(len(sentence) + 1 for _, sentence in trial) <= budget:
            chosen = trial
            break
    parts += [sentence for _, sentence in chosen]
    lines: list[dict[str, object]] = [
        {"clipId": clip["clipId"], "outputStartFrame": clip.get("outputStartFrame"), "text": text}
        for clip, text in chosen
    ]
    omitted = len(clips) - len(chosen)
    text = "。".join(parts) + "。" if parts else ""
    return {
        "schemaVersion": "creation-narration-script-v1",
        "generator": "offline-template-v1",
        "status": "template-draft-human-review-required",
        "text": text,
        "lines": lines,
        "omittedClips": omitted,
        "budgetCharacters": budget,
        "estimatedSeconds": float(Fraction(len(text)) / CHARS_PER_SECOND),
        "outputSeconds": output_frames / fps,
        "charactersPerSecond": float(CHARS_PER_SECOND),
    }
