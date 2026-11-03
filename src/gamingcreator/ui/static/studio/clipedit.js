// Clip editing for the Edit workspace: load the server's editable clip list for a plan or a
// saved version, edit it locally (trim, order, delete, speed, transition, one-line commands),
// and save it as a new version that names its parent's receipt hash.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {clipFrames} from "./preview.js";

const html = htm.bind(h);
// The only speeds the server accepts (creation_editing.py).
export const SPEEDS = [[1, 2, "0.5× 慢放"], [1, 1, "1× 原速"], [2, 1, "2× 快放"]];

function normalize(editor) {
    return editor.clips.map((clip) => ({...clip, speed: clip.speed || {numerator: 1, denominator: 1}, transitionIn: clip.transitionIn || {type: "cut", frames: 0}}));
}

// The server's rule: transitions only between clips, and each clip keeps at least one frame of its own.
export function transitionProblem(clips, fps) {
    for (let i = 0; i < clips.length; i++) {
        const t = clips[i].transitionIn, next = clips[i + 1]?.transitionIn.frames || 0;
        if (i === 0 && (t.type !== "cut" || t.frames !== 0)) return "第一段不能有入场转场";
        if (t.frames + next >= clipFrames(clips[i], fps)) return `第 ${i + 1} 段太短，放不下两侧的转场`;
    }
    return "";
}

// The sound of a version: source and music levels, and an optional narration asset placed in the output.
const audioOf = (editor) => ({mix: editor.audioMix || {bgm: null, sourceGainDb: 0, ducking: "off"}, narration: editor.narration || null, asset: editor.narrationAsset || null});

const rows = (clips) => clips.map(({clipId, startUs, endUs, speed, transitionIn}) => ({clipId, startUs, endUs, speed, transitionIn}));

export function useClipEditor(project) {
    const [state, setState] = useState({status: "idle", base: null, editor: null, clips: [], audio: audioOf({}), bounds: {}, dirty: false});
    const [selectedId, setSelectedId] = useState("");

    const load = useCallback(async (jobId, planId, kind) => {
        setState((s) => ({...s, status: "loading"})); setSelectedId("");
        try {
            const editor = await client.api(`/api/creation/jobs/${encodeURIComponent(jobId)}/edit`, {planId});
            if (editor.parentJobId !== jobId || editor.planId !== planId) throw new Error("剪辑数据与所选方案不一致");
            const clips = normalize(editor);
            setState({status: "ready", base: {jobId, planId, kind}, editor, clips, audio: audioOf(editor), bounds: Object.fromEntries(clips.map((c) => [c.clipId, {startUs: c.startUs, endUs: c.endUs}])), dirty: false});
            return editor;
        } catch (error) {
            // Plans that cannot be edited still preview and export as they are.
            setState({status: "unavailable", base: {jobId, planId, kind}, editor: null, clips: [], audio: audioOf({}), bounds: {}, dirty: false, reason: error.message});
            return null;
        }
    }, []);

    const change = useCallback((mutate) => setState((s) => {
        if (s.status !== "ready") return s;
        const clips = mutate(s.clips.map((c) => ({...c})));
        if (clips[0]) clips[0].transitionIn = {type: "cut", frames: 0};
        return {...s, clips, dirty: true};
    }), []);

    const ops = {
        trim: (id, field, seconds) => change((clips) => {
            const clip = clips.find((c) => c.clipId === id), bound = state.bounds[id], fps = state.editor.fps;
            const us = Math.round(seconds * 1e6), minLength = Math.ceil(1e6 / fps);
            if (field === "startUs") clip.startUs = Math.min(Math.max(bound.startUs, us), clip.endUs - minLength);
            else clip.endUs = Math.max(Math.min(bound.endUs, us), clip.startUs + minLength);
            return clips;
        }),
        speed: (id, numerator, denominator) => change((clips) => { clips.find((c) => c.clipId === id).speed = {numerator, denominator}; return clips; }),
        transition: (id, frames) => change((clips) => { clips.find((c) => c.clipId === id).transitionIn = frames ? {type: "crossfade", frames} : {type: "cut", frames: 0}; return clips; }),
        move: (id, delta) => change((clips) => {
            const i = clips.findIndex((c) => c.clipId === id), j = i + delta;
            if (j < 0 || j >= clips.length) return clips;
            [clips[i], clips[j]] = [clips[j], clips[i]];
            return clips;
        }),
        remove: (id) => change((clips) => (clips.length > 1 ? clips.filter((c) => c.clipId !== id) : clips)),
        // A previewed one-line command: take its clip rows, keep everything else we know about each clip.
        apply: (newRows) => change((clips) => {
            const byId = new Map(clips.map((c) => [c.clipId, c]));
            return newRows.map((row) => ({...byId.get(row.clipId), ...row}));
        }),
        mix: (patch) => setState((s) => (s.status === "ready" ? {...s, audio: {...s.audio, mix: {...s.audio.mix, ...patch}}, dirty: true} : s)),
        narration: (selection, asset) => setState((s) => (s.status === "ready" ? {...s, audio: {...s.audio, narration: selection, asset: selection ? asset ?? s.audio.asset : null}, dirty: true} : s)),
        reset: () => setState((s) => (s.editor ? {...s, clips: normalize(s.editor), audio: audioOf(s.editor), dirty: false} : s)),
    };

    // Save the local edit as a new version; returns the version's job id.
    const save = useCallback(async (follow) => {
        const {editor, base, clips, audio} = state;
        const kept = new Set(clips.map((c) => c.clipId));
        const accepted = await client.submit("revision", {
            parentJobId: base.jobId, planId: base.planId, expectedParentReceiptSha256: editor.expectedParentReceiptSha256,
            clips: rows(clips), audioMix: audio.mix, narration: audio.narration, subtitleOverrides: (editor.subtitleOverrides || []).filter((o) => kept.has(o.clipId)),
        });
        const done = await follow(accepted.jobId);
        if (done?.status !== "completed") throw new Error(done ? `保存失败：${done.error?.message || done.status}` : "保存已取消");
        client.forgetIntent("revision");
        await load(done.jobId, base.planId, "revision");
        return done.jobId;
    }, [state, load]);

    return {...state, selectedId, setSelectedId, load, ops, save, rows: () => rows(state.clips)};
}

export function ClipInspector({editing, index, onSeek}) {
    const clip = editing.clips[index]; if (!clip) return null;
    const fps = editing.editor.fps, bound = editing.bounds[clip.clipId];
    const frames = clipFrames(clip, fps), seconds = (us) => (us / 1e6).toFixed(2);
    const fade = (s) => Math.round(s * fps);
    return html`<div class="field"><div class="k">第 ${index + 1} 段 · 成片 ${(frames / fps).toFixed(2)} 秒</div>
            <div class="v">${clip.role ? `【${clip.role}】` : ""}${clip.scriptDraft || "无描述"}</div></div>
        <div class="field"><div class="k">取材范围（原片秒，可在 ${seconds(bound.startUs)}–${seconds(bound.endUs)} 内裁短）</div>
            <div class="pair even">
                <label class="form-row">入点<input class="input" type="number" step="0.1" min=${seconds(bound.startUs)} max=${seconds(bound.endUs)} value=${seconds(clip.startUs)}
                    onChange=${(e) => editing.ops.trim(clip.clipId, "startUs", Number(e.currentTarget.value))} /></label>
                <label class="form-row">出点<input class="input" type="number" step="0.1" min=${seconds(bound.startUs)} max=${seconds(bound.endUs)} value=${seconds(clip.endUs)}
                    onChange=${(e) => editing.ops.trim(clip.clipId, "endUs", Number(e.currentTarget.value))} /></label>
            </div></div>
        <div class="field"><div class="pair even">
            <label class="form-row">速度<select class="select" value=${`${clip.speed.numerator}/${clip.speed.denominator}`}
                onChange=${(e) => { const [n, d] = e.currentTarget.value.split("/").map(Number); editing.ops.speed(clip.clipId, n, d); }}>
                ${SPEEDS.map(([n, d, label]) => html`<option value=${`${n}/${d}`}>${label}</option>`)}</select></label>
            <label class="form-row">进入方式<select class="select" disabled=${index === 0} value=${String(clip.transitionIn.frames)}
                onChange=${(e) => editing.ops.transition(clip.clipId, Number(e.currentTarget.value))}>
                <option value="0">直接切换</option><option value=${String(fade(0.25))}>交叉淡化 0.25 秒</option><option value=${String(fade(0.5))}>交叉淡化 0.5 秒</option></select></label>
        </div><p class="hint">预览里转场显示为直接切换；导出的成片里会是淡化。</p></div>
        <div class="field actions-row">
            <button class="btn ghost" onClick=${() => onSeek(clip.clipId)}>从这段播放</button>
            <button class="btn ghost" disabled=${index === 0} onClick=${() => editing.ops.move(clip.clipId, -1)}>前移</button>
            <button class="btn ghost" disabled=${index === editing.clips.length - 1} onClick=${() => editing.ops.move(clip.clipId, 1)}>后移</button>
            <button class="btn ghost danger" disabled=${editing.clips.length <= 1} onClick=${() => editing.ops.remove(clip.clipId)}>删除这段</button>
        </div>`;
}

// One-line edits in the assistant dock: preview the change on the timeline, then apply or discard.
export function CommandDock({editing, onPreview}) {
    const [text, setText] = useState("");
    const [result, setResult] = useState(null);
    const [message, setMessage] = useState("");
    const ready = editing.status === "ready";
    useEffect(() => { setResult(null); setMessage(""); onPreview(null); }, [editing.base?.jobId, editing.base?.planId]);
    const preview = async (event) => {
        event.preventDefault();
        if (!ready || !text.trim()) return;
        try {
            const data = await client.api("/api/creation/timeline-commands", {}, {body: {text: text.trim(), fps: editing.editor.fps, clips: editing.rows()}});
            setResult(data); onPreview(data.clips);
            setMessage(`将会：${data.changes.join("；")}（${data.beforeSeconds.toFixed(1)} → ${data.afterSeconds.toFixed(1)} 秒）`);
        } catch (error) { setResult(null); onPreview(null); setMessage(`没有改动：${error.message}`); }
    };
    const apply = () => { editing.ops.apply(result.clips); setResult(null); onPreview(null); setText(""); setMessage("已应用，可以预览检查，满意后导出或保存版本。"); };
    const cancel = () => { setResult(null); onPreview(null); setMessage("已取消，时间轴没有变化。"); };
    return html`<form class="dock assistant" onSubmit=${preview}>
        <strong>创作助手</strong>
        <input class="input" value=${text} disabled=${!ready} onInput=${(e) => setText(e.currentTarget.value)}
            placeholder=${ready ? "一句话修改，例如：删掉第3个镜头、第2个镜头慢放、前5秒太慢" : "选中方案后可以用一句话修改镜头"} aria-label="一句话修改镜头" />
        ${result ? html`<button type="button" class="btn" onClick=${apply}>应用</button><button type="button" class="btn ghost" onClick=${cancel}>取消</button>`
            : html`<button class="btn ghost" disabled=${!ready || !text.trim()}>预览改动</button>`}
        <span class="dock-msg" role="status">${message}</span>
    </form>`;
}
