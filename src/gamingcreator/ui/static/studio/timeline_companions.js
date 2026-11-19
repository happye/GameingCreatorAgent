import {narrationFits} from "./audio.js";
import {editTimeline} from "./preview.js";

// Translate the frame through its original source time using the export frame clock.
// In a dissolve, the shot that has just started owns the anchor.
function movedStart(frame, before, after, replaced, fps, label) {
    const shot = before.findLast(item => item.outStartFrame <= frame && frame < item.outStartFrame + item.outFrames);
    const next = shot && !replaced.has(shot.clipId) ? after.get(shot.clipId) : null;
    if (!next) throw Error(`${label}的起点所在原镜头已删除或替换。请调整指令或取消随原镜移动。`);
    const sourceScale = BigInt(fps) * BigInt(shot.speed.denominator);
    const sourceOffset = BigInt(shot.startUs - next.startUs) * sourceScale
        + BigInt(frame - shot.outStartFrame) * 1000000n * BigInt(shot.speed.numerator);
    const offset = sourceOffset * BigInt(next.speed.denominator)
        / (BigInt(shot.speed.denominator) * 1000000n * BigInt(next.speed.numerator));
    if (sourceOffset < 0n || offset >= BigInt(next.outFrames)) {
        throw Error(`${label}的起点对应画面已裁掉。请调整指令或取消随原镜移动。`);
    }
    return next.outStartFrame + Number(offset);
}

export function projectCompanions(editing, clips, follow, replaced = []) {
    const moveNarration = follow?.narration && editing.audio.narration;
    const moveOverlays = follow?.overlays && editing.overlays.length;
    if (!moveNarration && !moveOverlays) return {};
    const fps = editing.editor.fps;
    const before = editTimeline(editing.clips, fps), after = editTimeline(clips, fps);
    const byId = new Map(after.map(item => [item.clipId, item]));
    const swapped = new Set(replaced);
    const last = after.at(-1), frames = last.outStartFrame + last.outFrames;
    const shift = (frame, label) => movedStart(frame, before, byId, swapped, fps, label);
    const fields = {};
    if (moveNarration) {
        const startFrame = shift(moveNarration.startFrame, "旁白");
        if (!narrationFits(startFrame, frames, fps, editing.audio.asset)) {
            throw Error("旁白随原镜移动后超出成片。请缩短旁白、调整指令或取消随原镜移动。");
        }
        fields.narration = {...moveNarration, startFrame};
    }
    if (moveOverlays) {
        const items = editing.overlays.map((item, i) => {
            const label = `第 ${i + 1} 个图层`;
            const startFrame = shift(item.startFrame, label);
            const endFrame = startFrame + item.endFrame - item.startFrame;
            if (endFrame > frames) throw Error(`${label}随原镜移动后超出成片。请缩短图层、调整指令或取消随原镜移动。`);
            return {...item, startFrame, endFrame};
        });
        fields.overlays = {schemaVersion: "creation-overlays-v1", items};
    }
    return fields;
}
