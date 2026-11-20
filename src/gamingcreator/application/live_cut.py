"""Choose source-ordered stretches of action before cutting explicitly low-value footage."""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gamingcreator.application.creation_modes import StructureAllocation
from gamingcreator.application.showcase_topics import topic_matches
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.models import TranscriptSegment

if TYPE_CHECKING:
    from gamingcreator.application.creation_modes import Score
    from gamingcreator.application.creative_planner import CreationClip


_IDLE = {
    "加载": re.compile(r"加载(?:中|界面|画面|进度)|读取(?:中|画面)|载入中|读条界面"),
    "等待": re.compile(r"等待(?:中|匹配|开始|复活|队友|其他玩家)|(?:排队|匹配)中|待机界面"),
    "重复移动": re.compile(r"重复(?:跑图|走同一|往返|绕圈)|反复(?:跑同一|往返|绕圈)"),
    "无有效内容": re.compile(
        r"无效操作|(?:角色|人物)原地(?:不动|无操作)|黑屏|近乎全黑|画面几乎全白|无清晰游戏内容"
    ),
}
_NEGATED_IDLE = re.compile(r"(?:未见|没有|没有出现|未出现|已离开|结束).{0,8}")
_DIALOGUE = re.compile(r"说话|对话|交谈|欢呼|惊呼|大笑|主播(?:喊|笑|回应)|台词")
_ACTION = re.compile(
    r"战斗|对战|交战|攻击命中|受击|击杀|格挡|反击|释放技能|技能释放|伤害数字|"
    r"结算|领取|掉落|拾取|拥抱|互动"
)
_SCENE_CUT = re.compile(r"场景切换|切换(?:至|到|为)|抵达|进入新区域")
_TRAVEL = re.compile(r"跑动|奔跑|跑图|(?:向前|沿着|继续在).{0,16}(?:移动|行走)")
_CONTINUING_TRAVEL = re.compile(r"(?:继续|仍)(?:在|沿|绕).{1,14}(?:跑动|奔跑|移动|行走)")
_TRAVEL_TAGS = {"移动", "奔跑", "行走", "跑图", "movement", "run"}
_BLOCK_SECONDS = 8


@dataclass(frozen=True, slots=True)
class Moment:
    clip: "CreationClip"
    frames: int
    dialogue: bool
    utterances: frozenset[int]
    key: bool


def _idle_reason(text: str) -> str:
    for label, pattern in _IDLE.items():
        for hit in pattern.finditer(text):
            preceding = text[max(0, hit.start() - 8) : hit.start()]
            if not _NEGATED_IDLE.search(preceding) and not text[hit.end() :].startswith("结束"):
                return label
    return ""


def _signals(
    clip: "CreationClip", topics: Sequence[str], transcripts: Sequence[TranscriptSegment], fps: int
) -> tuple[Moment, str, bool, bool]:
    framing = clip.framing
    facts = "；".join(clip.event.observable_facts)
    tags = set(clip.event.mechanic_tags)
    text = "；".join((facts, *tags))
    utterances = frozenset(
        i
        for i, transcript in enumerate(transcripts)
        if transcript.text.strip()
        and transcript.source_range.start_us < framing.end_us
        and transcript.source_range.end_us > framing.start_us
    )
    dialogue = bool(utterances or _DIALOGUE.search(text))
    key = dialogue or bool(_ACTION.search(text)) or any(topic_matches(text, t) for t in topics)
    reason = "" if key else _idle_reason(text)
    travel = not key and bool(_TRAVEL.search(facts)) and tags <= _TRAVEL_TAGS
    frames = (framing.end_us - framing.start_us) * fps // 1_000_000
    repeating = bool(_CONTINUING_TRAVEL.search(facts)) and not _SCENE_CUT.search(facts)
    return Moment(clip, frames, dialogue, utterances, key), reason, travel, repeating


def _adjacent(previous: Moment, current: Moment, fps: int) -> bool:
    return (
        previous.clip.event.run_id == current.clip.event.run_id
        and (current.clip.framing.start_us - previous.clip.framing.end_us) * fps < 1_000_000
    )


def _blocks(
    clips: Sequence["CreationClip"],
    topics: Sequence[str],
    transcripts: Mapping[str, tuple[TranscriptSegment, ...]],
    fps: int,
) -> tuple[list[list[Moment]], Counter[str]]:
    blocks: list[list[Moment]] = []
    omitted: Counter[str] = Counter()
    last: Moment | None = None
    last_travel = False
    length = 0
    for clip in clips:
        moment, reason, travel, repeating = _signals(
            clip, topics, transcripts.get(clip.event.run_id, ()), fps
        )
        adjacent = last is not None and _adjacent(last, moment, fps)
        if not reason and adjacent and last_travel and travel and repeating:
            reason = "重复移动"
        if reason:
            omitted[reason] += 1
            last, last_travel = None, False
            continue
        joins_utterance = (
            last is not None
            and last.clip.event.run_id == moment.clip.event.run_id
            and bool(last.utterances & moment.utterances)
        )
        if not joins_utterance and (not adjacent or length + moment.frames > _BLOCK_SECONDS * fps):
            blocks.append([])
            length = 0
        blocks[-1].append(moment)
        length += moment.frames
        last, last_travel = moment, travel
    return blocks, omitted


def _allocate(blocks: list[list[Moment]], target: int, score: "Score") -> dict[int, int]:
    def rank(index: int) -> tuple[bool, int, float]:
        block = blocks[index]
        return (
            any(item.dialogue for item in block),
            sum(item.frames for item in block if item.key),
            max(score(item.clip) for item in block),
        )

    ranked = sorted(range(len(blocks)), key=rank, reverse=True)
    budgets: dict[int, int] = {}
    deferred: list[int] = []
    for index in ranked:
        length = sum(item.frames for item in blocks[index])
        if length <= target:
            budgets[index] = length
            target -= length
        else:
            deferred.append(index)
    # Spend leftover time on whole observations. Declared speech is kept as a whole block.
    for index in deferred:
        if target <= 0:
            break
        block = blocks[index]
        if any(item.dialogue for item in block):
            continue
        length = 0
        for item in block:
            if length + item.frames > target:
                break
            length += item.frames
        if length:
            budgets[index] = length
            target -= length
    if not budgets and target:
        # A single analysed event may be longer than the entire brief.
        first = next((i for i in ranked if not any(item.dialogue for item in blocks[i])), None)
        if first is not None:
            budgets[first] = target
    return budgets


def _has_speech_gap(
    blocks: Sequence[list[Moment]],
    transcripts: Mapping[str, tuple[TranscriptSegment, ...]],
    fps: int,
) -> bool:
    coverage: Counter[tuple[str, int]] = Counter()
    for block in blocks:
        for item in block:
            run = item.clip.event.run_id
            framing = item.clip.framing
            for index in item.utterances:
                span = transcripts[run][index].source_range
                coverage[(run, index)] += min(span.end_us, framing.end_us) - max(
                    span.start_us, framing.start_us
                )
    for (run, index), duration in coverage.items():
        span = transcripts[run][index].source_range
        if (span.end_us - span.start_us - duration) * fps >= 1_000_000:
            return True
    return False


def live_cut(
    brief: CreativeBrief,
    clips: Sequence["CreationClip"],
    transcripts: Mapping[str, tuple[TranscriptSegment, ...]],
    fps: int,
    score: "Score",
) -> StructureAllocation:
    blocks, omitted = _blocks(clips, brief.mandatory_topics, transcripts, fps)
    selected = _allocate(blocks, brief.target_duration * fps, score)
    indexes = sorted(selected)
    chosen = [blocks[i] for i in indexes]
    notes = (
        [
            f"估计略去 {sum(omitted.values())} 段低信息画面（"
            + "、".join(f"{label} {count} 段" for label, count in omitted.items())
            + "），按素材摘要判断。"
        ]
        if omitted
        else []
    )
    if not any(transcripts.values()):
        notes.append("素材没有已保存的语音转写，预览时可核对原声与对话完整性。")
    if any(
        any(item.dialogue for item in block) and i not in selected for i, block in enumerate(blocks)
    ):
        notes.append("目标时间内未能排入所有整段对话，延长时长可保留更多对话。")
    if _has_speech_gap(chosen, transcripts, fps):
        notes.append("部分转写跨出可用取材区间，预览时可核对这部分原声。")
    if sum(selected.values()) < brief.target_duration * fps:
        notes.append("实况精剪按连续片段取材，当前成片短于目标时长。")
    return StructureAllocation(
        "live-cut",
        "实况精剪：优先保留连续事件与原声，略去有明确依据的空段",
        [[item.clip for item in block] for block in chosen],
        [selected[i] for i in indexes],
        tuple(
            "优先保留原声" if any(item.dialogue for item in block) else "实况" for block in chosen
        ),
        notes,
    )
