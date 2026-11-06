// Clip editing for the Edit workspace: load the server's editable clip list for a plan or a
// saved version, edit it locally (trim, order, delete, speed, transition, one-line commands),
// and save it as a new version that names its parent's receipt hash.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {clipFrames} from "./preview.js";
import {ReasoningDock} from "./reasoning.js";

const html = htm.bind(h);
// The only speeds the server accepts (creation_editing.py).
export const SPEEDS = [[1, 2, "0.5× 慢放"], [1, 1, "1× 原速"], [2, 1, "2× 快放"]];

function normalize(editor) {
    return editor.clips.map((clip) => ({...clip, speed: clip.speed || {numerator: 1, denominator: 1}, transitionIn: clip.transitionIn || {type: "cut", frames: 0}}));
}

// The server's rule: transitions only between clips, and each clip keeps at least one frame of its own.
export function transitionProblem(clips, fps) {
    for (let i = 0; i < clips.length; i++) {
        const clip = clips[i], p = clip.rangeProvenance;
        if (p) {
            const overlaps = p.analysisStartUs === p.analysisEndUs
                ? clip.startUs <= p.analysisStartUs && (p.analysisStartUs < clip.endUs || clip.startUs < p.analysisStartUs && p.analysisStartUs === clip.endUs && clip.endUs === clip.sourceDurationUs)
                : clip.startUs < p.analysisEndUs && clip.endUs > p.analysisStartUs;
            if (!overlaps) return `第 ${i + 1} 个镜头不含原观察画面，请保留观察位置或替换镜头`;
        }
        const t = clips[i].transitionIn, next = clips[i + 1]?.transitionIn.frames || 0;
        if (i === 0 && (t.type !== "cut" || t.frames !== 0)) return "第一个镜头不能有入场转场";
        if (t.frames + next >= clipFrames(clips[i], fps)) return `第 ${i + 1} 个镜头太短，放不下两侧的转场`;
    }
    return "";
}

// The sound of a version: source and music levels, and an optional narration asset placed in the output.
const audioOf = (editor) => ({mix: editor.audioMix || {bgm: null, sourceGainDb: 0, ducking: "off"}, narration: editor.narration || null, asset: editor.narrationAsset || null});

const rows = (clips) => clips.map(({clipId, startUs, endUs, speed, transitionIn}) => ({clipId, startUs, endUs, speed, transitionIn}));

export function useClipEditor(project) {
    const [state, setState] = useState({status: "idle", base: null, editor: null, clips: [], audio: audioOf({}), bounds: {}, replacements: {}, dirty: false});
    // Replacement candidates of the plan's recordings, loaded on first use per plan/version.
    const [candidates, setCandidates] = useState(null);
    const [selectedId, setSelectedId] = useState("");
    const loading = useRef(0);
    useLayoutEffect(() => {
        loading.current += 1;
        setState({status: "idle", base: null, editor: null, clips: [], audio: audioOf({}), bounds: {}, replacements: {}, dirty: false});
        setCandidates(null); setSelectedId("");
        return () => { loading.current += 1; };
    }, [project]);

    const load = useCallback(async (jobId, planId, kind) => {
        const generation = ++loading.current;
        setState((s) => ({...s, status: "loading"})); setSelectedId("");
        try {
            const editor = await client.api(`/api/creation/jobs/${encodeURIComponent(jobId)}/edit`, {planId});
            if (generation !== loading.current) return null;
            if (editor.parentJobId !== jobId || editor.planId !== planId) throw new Error("剪辑数据与所选方案不一致");
            const clips = normalize(editor);
            setCandidates(null);
            setState({status: "ready", base: {jobId, planId, kind}, editor, clips, audio: audioOf(editor), bounds: Object.fromEntries(clips.map((c) => [c.clipId, {startUs: c.startUs, endUs: c.endUs}])), replacements: {}, dirty: false});
            return editor;
        } catch (error) {
            if (generation !== loading.current) return null;
            // Plans that cannot be edited still preview and export as they are.
            setState({status: "unavailable", base: {jobId, planId, kind}, editor: null, clips: [], audio: audioOf({}), bounds: {}, replacements: {}, dirty: false, reason: error.message});
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
        // Swap a clip's footage for another analysed clip of the same recordings (1x, cut in);
        // its length stays as close to the old one as the new clip allows.
        replace: (id, candidate) => setState((s) => {
            if (s.status !== "ready") return s;
            const clips = s.clips.map((c) => {
                if (c.clipId !== id) return c;
                const length = Math.max(1, c.endUs - c.startUs);
                const next = {...c, ...candidate, clipId: c.clipId,
                    startUs: candidate.startUs, endUs: Math.min(candidate.endUs, candidate.startUs + length), speed: {numerator: 1, denominator: 1}, transitionIn: {type: "cut", frames: 0}};
                // Source paths are private; the server reconstructs them from its manifest.
                delete next.sourcePath;
                if (!candidate.rangeProvenance) delete next.rangeProvenance;
                return next;
            });
            const at = clips.findIndex((c) => c.clipId === id);
            if (clips[at + 1]) clips[at + 1] = {...clips[at + 1], transitionIn: {type: "cut", frames: 0}};
            return {...s, clips, bounds: {...s.bounds, [id]: {startUs: candidate.startUs, endUs: candidate.endUs}}, replacements: {...s.replacements, [id]: candidate.candidateId}, dirty: true};
        }),
        reset: () => setState((s) => (s.editor ? {...s, clips: normalize(s.editor), audio: audioOf(s.editor), bounds: Object.fromEntries(normalize(s.editor).map((c) => [c.clipId, {startUs: c.startUs, endUs: c.endUs}])), replacements: {}, dirty: false} : s)),
    };

    const loadCandidates = useCallback(async () => {
        if (candidates || !state.base) return candidates;
        const data = await client.api(`/api/creation/jobs/${encodeURIComponent(state.base.jobId)}/candidates`, {planId: state.base.planId});
        setCandidates(data); return data;
    }, [candidates, state.base]);

    // Save the local edit as a new version; returns the version's job id.
    const save = useCallback(async (follow) => {
        const {editor, base, clips, audio, replacements} = state;
        const kept = new Set(clips.map((c) => c.clipId));
        // A version with replaced footage (or descended from one) carries the candidate manifest.
        const swaps = Object.entries(replacements).filter(([id]) => kept.has(id)).map(([targetClipId, candidateId]) => ({targetClipId, candidateId}));
        const manifest = editor.candidateManifestSha256 || (swaps.length ? candidates?.candidateManifestSha256 : null);
        const accepted = await client.submit("revision", {
            parentJobId: base.jobId, planId: base.planId, expectedParentReceiptSha256: editor.expectedParentReceiptSha256,
            clips: rows(clips), audioMix: audio.mix, narration: audio.narration, subtitleOverrides: (editor.subtitleOverrides || []).filter((o) => kept.has(o.clipId)),
            ...(manifest ? {candidateManifestSha256: manifest, replacements: swaps} : {}),
        });
        const done = await follow(accepted.jobId);
        if (done?.status !== "completed") throw new Error(done ? `保存失败：${done.error?.message || done.status}` : "保存已取消");
        client.forgetIntent("revision");
        await load(done.jobId, base.planId, "revision");
        return done.jobId;
    }, [state, load, candidates]);

    return {...state, project, selectedId, setSelectedId, load, ops, save, candidates, loadCandidates, rows: () => rows(state.clips)};
}

export function ClipInspector({editing, index, onSeek, basket}) {
    const clip = editing.clips[index]; if (!clip) return null;
    const fps = editing.editor.fps, bound = editing.bounds[clip.clipId];
    const frames = clipFrames(clip, fps), seconds = (us) => (us / 1e6).toFixed(2);
    const fade = (s) => Math.round(s * fps);
    return html`<div class="field"><div class="k">第 ${index + 1} 个镜头 · 成片 ${(frames / fps).toFixed(2)} 秒</div>
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
        </div><p class="hint">即时预览支持交叉淡化；镜头需足够长，才能容纳两侧转场。</p></div>
        <div class="field actions-row">
            <button class="btn ghost" onClick=${() => onSeek(clip.clipId)}>从这段播放</button>
            <button class="btn ghost" disabled=${index === 0} onClick=${() => editing.ops.move(clip.clipId, -1)}>前移</button>
            <button class="btn ghost" disabled=${index === editing.clips.length - 1} onClick=${() => editing.ops.move(clip.clipId, 1)}>后移</button>
            <button class="btn ghost danger" disabled=${editing.clips.length <= 1} onClick=${() => editing.ops.remove(clip.clipId)}>删除这段</button>
        </div>
        <${ReplacePicker} key=${clip.clipId} editing=${editing} clip=${clip} basket=${basket} />`;
}

// Replace this clip's footage: basket clips of the same recordings first, then any analysed clip.
function ReplacePicker({editing, clip, basket}) {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [error, setError] = useState("");
    const start = async () => { setOpen(true); setError(""); try { await editing.loadCandidates(); } catch (e) { setError(e.message); } };
    if (!open) return html`<div class="field actions-row"><button class="btn ghost" onClick=${start}>替换这段画面</button></div>`;
    const list = editing.candidates?.candidates || [];
    // Footage already in the version is not offered again (the server refuses duplicate intervals).
    const overlaps = (c) => editing.clips.some((x) => x.clipId !== clip.clipId && x.runId === c.runId && x.startUs < c.endUs && c.startUs < x.endUs);
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const inBasket = (c) => basket?.ids.has(c.eventId);
    // Instant events (a moment, not a span) cannot become footage; keep clips of at least half a second.
    const shown = list.filter((c) => c.endUs - c.startUs >= 500000 && c.eventId !== clip.eventId && !overlaps(c))
        .filter((c) => terms.every((t) => (c.scriptDraft || "").toLowerCase().includes(t)))
        .sort((a, b) => inBasket(b) - inBasket(a));
    return html`<div class="field replace-picker"><div class="k">替换这段画面（换成 1× 原速、直接切入）</div>
        ${error ? html`<p class="hint warn">${error}</p>` : !editing.candidates ? html`<p class="note">正在读取可替换的片段…</p>` : html`
            <input class="input" type="search" value=${query} onInput=${(e) => setQuery(e.currentTarget.value)} placeholder="按描述筛选" aria-label="筛选替换片段" />
            <div class="hits">${shown.slice(0, 40).map((c) => html`<div class="hit">
                <span class="hit-text"><span class="meta">${inBasket(c) ? "片段篮 · " : ""}${(c.sourceName || "").slice(0, 12)} · ${(c.startUs / 1e6).toFixed(1)} 秒起 · 长 ${((c.endUs - c.startUs) / 1e6).toFixed(1)} 秒</span>${c.scriptDraft}</span>
                <button class="btn ghost" onClick=${() => { editing.ops.replace(clip.clipId, c); setOpen(false); }}>换成这段</button></div>`)}
                ${!shown.length && html`<p class="hint">没有可用的片段。</p>`}</div>`}
        <div class="actions-row"><button class="btn ghost" onClick=${() => setOpen(false)}>收起</button></div>
    </div>`;
}

// One-line edits in the assistant dock: preview the change on the timeline, then apply or discard.
function LocalCommandDock({editing, onPreview}) {
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

export function CommandDock({editing, onPreview}) {
    const [mode, setMode] = useState("local");
    return html`<div class="assistant-host"><label class="assistant-mode">创作助手模式
        <select class="select" aria-label="创作助手模式" value=${mode} onChange=${(e) => { onPreview(null); setMode(e.currentTarget.value); }}>
            <option value="local">本地指令（免费）</option><option value="ai">AI对话（按次确认）</option>
        </select></label>
        ${mode === "local" ? html`<${LocalCommandDock} editing=${editing} onPreview=${onPreview} />` : html`<${ReasoningDock} editing=${editing} onPreview=${onPreview} />`}
    </div>`;
}
