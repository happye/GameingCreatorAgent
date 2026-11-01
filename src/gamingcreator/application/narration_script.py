"""Offline template narration drafts from saved clip descriptions, sized to the output clock."""

import re
from fractions import Fraction
from typing import Any

from gamingcreator.application.knowledge import query_words
from gamingcreator.domain.creation import CreativeBrief

# Measured on local Huihui: 21 characters took 5.688 seconds. Budget below that and keep a margin.
CHARS_PER_SECOND = Fraction(7, 2)
FILL_RATIO = Fraction(9, 10)
MAX_CLIP_CHARS = 24
MAX_KNOWLEDGE_CHARS = 32
_OPENINGS = {
    "feature_showcase": "{game}玩法速览",
    "guide": "{game}攻略要点",
    "campaign": "{game}活动投稿",
    "commentary": "{game}实况解说",
    "live_cut": "{game}实况精剪",
    "highlight": "{game}高光时刻",
    "ad": "一起来玩{game}",
}
_CLOSINGS = {"campaign": "快来一起参与活动", "commentary": "感谢收看", "ad": "现在就来体验"}
_FRAME_MARKER = re.compile(r"f\d+(?:至f\d+)?(?:中|显示|切换为|延续|开始)?")


def knowledge_query(brief: CreativeBrief) -> str:
    """The words a draft looks up in the game's knowledge entries."""
    return " ".join((*brief.mandatory_topics, brief.objective))


def _knowledge_clause(text: object, words: list[str]) -> str:
    """A whole clause of an entry, preferring one that holds a looked-up word; never cut short.

    Cutting a rule at a comma can reverse it ("可以无限使用，除非…"), so a clause too long to
    quote whole is not quoted at all.
    """
    if not isinstance(text, str):
        return ""
    clauses = [c.strip(" ，,、：:'\"“”") for c in re.split(r"[；;。！？!?\n]", text)]
    fitting = [c for c in clauses if c and len(c) <= MAX_KNOWLEDGE_CHARS]
    matched = [c for c in fitting if any(w in c.casefold() for w in words)]
    if matched:
        return matched[0]
    first = next((c for c in clauses if c), "")
    return first if first in fitting else ""


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
    brief: CreativeBrief,
    clips: list[dict[str, Any]],
    output_frames: int,
    fps: int,
    knowledge: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    if any(type(n) is not int or n <= 0 for n in (output_frames, fps)):
        raise ValueError("Narration script needs a positive output clock.")
    budget = int(Fraction(output_frames, fps) * CHARS_PER_SECOND * FILL_RATIO)
    opening = _OPENINGS.get(brief.content_type, "{game}实机片段").format(game=brief.game.strip())
    parts = [opening] if len(opening) + 1 <= budget else []
    used = sum(len(part) + 1 for part in parts)
    closing = _CLOSINGS.get(brief.content_type, "")
    if closing and used + len(closing) + 1 <= budget:
        used += len(closing) + 1
    else:
        closing = ""
    candidates: list[tuple[dict[str, Any], str]] = []
    for clip in clips:
        sentence = _sentence(clip.get("scriptDraft"))
        if sentence and (not candidates or candidates[-1][1] != sentence):
            candidates.append((clip, sentence))
    # Guide steps are numbered by their position in this draft, so edits never leave gaps.
    steps = brief.content_type == "guide"

    def spoken(trial: list[tuple[dict[str, Any], str]]) -> list[tuple[dict[str, Any], str]]:
        return [
            (clip, f"第{k}步，{text}" if steps else text) for k, (clip, text) in enumerate(trial, 1)
        ]

    # One narration spans the whole video, so sample clips evenly over output time.
    chosen: list[tuple[dict[str, Any], str]] = []
    for count in range(len(candidates), 0, -1):
        picks = sorted({round(i * (len(candidates) - 1) / max(1, count - 1)) for i in range(count)})
        trial = spoken([candidates[i] for i in picks])
        if used + sum(len(sentence) + 1 for _, sentence in trial) <= budget:
            chosen = trial
            break
    used += sum(len(sentence) + 1 for _, sentence in chosen)
    # One matching knowledge sentence if it still fits; its source is shown, not spoken.
    citations: list[dict[str, str]] = []
    knowledge_sentence = ""
    words = query_words(knowledge_query(brief))
    for entry in knowledge or []:
        candidate = _knowledge_clause(entry.get("text"), words)
        if candidate and used + len(candidate) + 1 <= budget:
            knowledge_sentence = candidate
            citations.append(
                {"entryId": entry["entryId"], "text": candidate, "citation": entry["citation"]}
            )
            break
    parts += (
        [sentence for _, sentence in chosen]
        + ([knowledge_sentence] if knowledge_sentence else [])
        + ([closing] if closing else [])
    )
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
        "citations": citations,
        "budgetCharacters": budget,
        "estimatedSeconds": float(Fraction(len(text)) / CHARS_PER_SECOND),
        "outputSeconds": output_frames / fps,
        "charactersPerSecond": float(CHARS_PER_SECOND),
    }
