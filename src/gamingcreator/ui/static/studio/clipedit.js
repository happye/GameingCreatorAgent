// Clip editing for the Edit workspace: load the server's editable clip list for a plan or a
// saved version, edit it locally (trim, order, delete, speed, transition, one-line commands),
// and save it as a new version that names its parent's receipt hash.
import {h} from "../vendor/preact.module.js";
import {useCallback, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {clipFrames} from "./preview.js";
import {ReasoningDock} from "./reasoning.js";

import {useClipDrafts, readSnapshot, rebuild, FULL_SCHEMA, V3_SCHEMA, V4_SCHEMA} from "./clip_drafts.js";

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

// Validate without rewriting the user's text; the server owns SRT normalization.
export function captionProblem(overrides) {
    for (const {text} of overrides) {
        if ([...text].length > 2000) return "镜头字幕不能超过 2000 字";
        if (text && (!text.trim() || text.includes("-->") || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(text))) return "镜头字幕不能仅含空白、空字符或 SRT 时间标记";
    }
    return "";
}
const captionsOf = (editor) => ({subtitleOverrides: editor.subtitleOverrides || []});
const keptCaptions = (overrides, clips) => overrides.filter((o) => clips.some((c) => c.clipId === o.clipId));

// The sound of a version: source and music levels, and an optional narration asset placed in the output.
const audioOf = (editor) => ({mix: editor.audioMix || {bgm: null, sourceGainDb: 0, ducking: "off"}, narration: editor.narration || null, asset: editor.narrationAsset || null});

const rows = (clips) => clips.map(({clipId, startUs, endUs, speed, transitionIn}) => ({clipId, startUs, endUs, speed, transitionIn}));
const overlaysOf = (editor) => ({overlays: editor.overlays?.items || [], overlayAssets: editor.overlayAssets || []});
const isPendingInsertion = (editing, id) => editing.insertions?.some((op) => op.newClipId === id);
const forcedCut = (clips, index, replacements) => replacements[clips[index].clipId] || replacements[clips[index - 1]?.clipId];
function composedInsertions(state, clips) {
    if (!state.insertions?.length) return state.insertions;
    const kept = new Set(clips.map(clip => clip.clipId));
    const operations = state.insertions.filter(op => kept.has(op.newClipId))
        .map(op => ({...op, editMode: "composed-v1"}));
    return operations.length ? operations : state.editor.insertions ?? null;
}

function revisionFields(state) {
    const {editor, base, clips, audio, replacements, overlays, subtitleOverrides} = state;
    const kept = new Set(clips.map((c) => c.clipId));
    const swaps = Object.entries(replacements).filter(([id]) => kept.has(id))
        .map(([targetClipId, candidateId]) => ({targetClipId, candidateId}));
    const manifest = state.candidateManifestSha256 || editor.candidateManifestSha256;
    return {
        parentJobId: base.jobId, planId: base.planId, expectedParentReceiptSha256: editor.expectedParentReceiptSha256,
        clips: rows(clips), audioMix: audio.mix, narration: audio.narration,
        subtitleOverrides: subtitleOverrides.filter((o) => kept.has(o.clipId)),
        overlays: {schemaVersion: "creation-overlays-v1", items: overlays},
        ...(manifest ? {candidateManifestSha256: manifest, replacements: swaps} : {}),
        ...(state.insertions !== null ? {insertions: state.insertions} : {}),
    };
}

function replaceClip(state, id, candidate, manifest) {
    if (state.status !== "ready" || isPendingInsertion(state, id)) return state;
    const clips = state.clips.map((clip) => {
        if (clip.clipId !== id) return clip;
        const length = Math.max(1, clip.endUs - clip.startUs);
        const next = {...clip, ...candidate, clipId: id, startUs: candidate.startUs,
            endUs: Math.min(candidate.endUs, candidate.startUs + length),
            speed: {numerator: 1, denominator: 1}, transitionIn: {type: "cut", frames: 0}};
        delete next.sourcePath;
        if (!candidate.rangeProvenance) delete next.rangeProvenance;
        return next;
    });
    const at = clips.findIndex((c) => c.clipId === id);
    if (clips[at + 1]) clips[at + 1] = {...clips[at + 1], transitionIn: {type: "cut", frames: 0}};
    return {...state, clips, candidateManifestSha256: state.candidateManifestSha256 ?? state.editor.candidateManifestSha256 ?? manifest,
        insertions: composedInsertions(state, clips), subtitleOverrides: state.subtitleOverrides.filter((o) => o.clipId !== id),
        bounds: {...state.bounds, [id]: {startUs: candidate.startUs, endUs: candidate.endUs}},
        replacements: {...state.replacements, [id]: candidate.candidateId}, dirty: true};
}

export function useClipEditor(project, workId = null) {
    const [state, setState] = useState({status: "idle", base: null, editor: null, clips: [], audio: audioOf({}), ...overlaysOf({}), ...captionsOf({}), bounds: {}, replacements: {}, insertions: null, candidateManifestSha256: null, dirty: false});
    const drafts = useClipDrafts(state, project, workId, {audio: audioOf(state.editor || {}), ...overlaysOf(state.editor || {})}, keptCaptions, [SPEEDS, clipFrames, transitionProblem]);
    const current = useRef(state); current.current = state;
    const overlayEpoch = useRef(0), restoreEpoch = useRef(0);
    const editEpoch = useRef(0);
    const saving = useRef(false);
    // Step undo/redo of local edits (not saved versions): snapshots of the editable fields.
    const history = useRef({past: [], future: [], key: null});
    const snap = (s) => ({clips: s.clips, subtitleOverrides: s.subtitleOverrides, audio: s.audio, overlays: s.overlays, overlayAssets: s.overlayAssets, bounds: s.bounds, replacements: s.replacements, insertions: s.insertions, candidateManifestSha256: s.candidateManifestSha256, dirty: s.dirty});
    const clearHistory = () => { history.current = {past: [], future: [], key: null}; };
    // Apply an edit and remember the state before it; repeated edits with the same key merge.
    const edit = useCallback((updater, key = null) => { restoreEpoch.current++; return setState((s) => {
        if (saving.current) return s;
        const next = updater(s);
        if (next === s || s.status !== "ready") return next;
        editEpoch.current += 1;
        const h = history.current;
        if (!(key && h.key === key)) h.past = [...h.past.slice(-49), snap(s)];
        h.future = []; h.key = key;
        return next;
    }); }, []);
    // Replacement candidates of the plan's recordings, loaded on first use per plan/version.
    const [candidates, setCandidates] = useState(null);
    const [selectedId, setSelectedId] = useState("");
    const loading = useRef(0);
    useLayoutEffect(() => {
        loading.current += 1;
        overlayEpoch.current += 1;
        editEpoch.current += 1;
        setState({status: "idle", base: null, editor: null, clips: [], audio: audioOf({}), ...overlaysOf({}), ...captionsOf({}), bounds: {}, replacements: {}, insertions: null, candidateManifestSha256: null, dirty: false});
        setCandidates(null); setSelectedId(""); clearHistory();
        return () => { loading.current += 1; };
    }, [project, workId]);

    const load = useCallback(async (jobId, planId, kind) => {
        drafts.invalidate();
        const generation = ++loading.current;
        overlayEpoch.current += 1;
        editEpoch.current += 1;
        setState((s) => ({...s, status: "loading"})); setSelectedId("");
        try {
            const editor = await client.api(`/api/creation/jobs/${encodeURIComponent(jobId)}/edit`, {planId});
            if (generation !== loading.current) return null;
            if (editor.parentJobId !== jobId || editor.planId !== planId) throw new Error("剪辑数据与所选方案不一致");
            const clips = normalize(editor);
            setCandidates(null); clearHistory();
            setState({status: "ready", base: {jobId, planId, kind}, editor, clips, audio: audioOf(editor), ...overlaysOf(editor), ...captionsOf(editor), bounds: Object.fromEntries(clips.map((c) => [c.clipId, {startUs: c.startUs, endUs: c.endUs}])), replacements: {}, insertions: editor.insertions ?? null, candidateManifestSha256: editor.candidateManifestSha256 ?? null, dirty: false});
            return editor;
        } catch (error) {
            if (generation !== loading.current) return null;
            // Plans that cannot be edited still preview and export as they are.
            setState({status: "unavailable", base: {jobId, planId, kind}, editor: null, clips: [], audio: audioOf({}), ...overlaysOf({}), ...captionsOf({}), bounds: {}, replacements: {}, insertions: null, candidateManifestSha256: null, dirty: false, reason: error.message});
            return null;
        }
    }, []);

    const change = useCallback((mutate, key = null, expectedEpoch = null) => edit((s) => {
        if (expectedEpoch !== null && editEpoch.current !== expectedEpoch) return s;
        if (s.status !== "ready") return s;
        const clips = mutate(s.clips.map((c) => ({...c})));
        if (clips[0]) clips[0].transitionIn = {type: "cut", frames: 0};
        if (Object.keys(s.replacements).length) clips.forEach((clip, index) => {
            if (forcedCut(clips, index, s.replacements)) clip.transitionIn = {type: "cut", frames: 0};
        });
        return {...s, clips, insertions: composedInsertions(s, clips), subtitleOverrides: keptCaptions(s.subtitleOverrides, clips), dirty: true};
    }, key), [edit]);

    const ops = {
        caption: (clipId, text) => edit((s) => {
            if (s.status !== "ready" || !s.clips.some((c) => c.clipId === clipId)) return s;
            const subtitleOverrides = s.subtitleOverrides.filter((o) => o.clipId !== clipId);
            if (text !== null) subtitleOverrides.push({clipId, text});
            return {...s, subtitleOverrides, dirty: true};
        }),
        trim: (id, field, seconds) => change((clips) => {
            const clip = clips.find((c) => c.clipId === id), bound = state.bounds[id], fps = state.editor.fps;
            const us = Math.round(seconds * 1e6), minLength = Math.ceil(1e6 / fps);
            if (field === "startUs") clip.startUs = Math.min(Math.max(bound.startUs, us), clip.endUs - minLength);
            else clip.endUs = Math.max(Math.min(bound.endUs, us), clip.startUs + minLength);
            return clips;
        }, `trim:${id}:${field}`),
        speed: (id, numerator, denominator) => change((clips) => { clips.find((c) => c.clipId === id).speed = {numerator, denominator}; return clips; }),
        transition: (id, frames) => change((clips) => { clips.find((c) => c.clipId === id).transitionIn = frames ? {type: "crossfade", frames} : {type: "cut", frames: 0}; return clips; }),
        move: (id, delta) => change((clips) => {
            const i = clips.findIndex((c) => c.clipId === id), j = i + delta;
            if (j < 0 || j >= clips.length) return clips;
            [clips[i], clips[j]] = [clips[j], clips[i]];
            return clips;
        }),
        remove: (id) => {
            const clips = current.current.clips;
            if (clips.length <= 1) return;
            const index = clips.findIndex((c) => c.clipId === id);
            const remaining = clips.filter((c) => c.clipId !== id);
            change((rows) => (rows.length > 1 ? rows.filter((c) => c.clipId !== id) : rows));
            setSelectedId((currentId) => currentId === id ? (remaining[Math.min(Math.max(index, 0), remaining.length - 1)]?.clipId || "") : currentId);
        },
        // A previewed one-line command: take its clip rows, keep everything else we know about each clip.
        apply: (newRows, expectedEpoch) => change((clips) => {
            const byId = new Map(clips.map((c) => [c.clipId, c]));
            return newRows.map((row) => ({...byId.get(row.clipId), ...row}));
        }, null, expectedEpoch),
        applyProposal: (proposal, expectedEpoch = null) => edit((s) => {
            if (s.status !== "ready" || (expectedEpoch !== null && editEpoch.current !== expectedEpoch)) return s;
            const byId = new Map(s.clips.map((c) => [c.clipId, c]));
            const clips = proposal.clips.map((row) => {
                const next = {...byId.get(row.clipId), ...row};
                if ((proposal.replacements || []).some((r) => r.targetClipId === row.clipId) && !row.rangeProvenance) delete next.rangeProvenance;
                return next;
            });
            return {...s, clips, subtitleOverrides: proposal.subtitleOverrides ?? keptCaptions(s.subtitleOverrides, clips).filter((o) => !(proposal.replacements || []).some((r) => r.targetClipId === o.clipId)), overlays: proposal.overlays?.items ?? s.overlays,
                insertions: Object.hasOwn(proposal, "insertions") ? proposal.insertions : s.insertions, bounds: proposal.bounds ?? s.bounds, replacements: proposal.replacements ? Object.fromEntries(proposal.replacements.map((r) => [r.targetClipId, r.candidateId])) : s.replacements,
                candidateManifestSha256: proposal.candidateManifestSha256 ?? s.candidateManifestSha256, dirty: true};
        }),
        mix: (patch) => edit((s) => (s.status === "ready" ? {...s, audio: {...s.audio, mix: {...s.audio.mix, ...patch}}, dirty: true} : s)),
        // Stage C keyframes; an empty envelope drops the key so saved JSON stays as before.
        envelope: (points, key = null) => edit((s) => {
            if (s.status !== "ready") return s;
            const {sourceEnvelope: _old, ...mix} = s.audio.mix;
            return {...s, audio: {...s.audio, mix: points.length ? {...mix, sourceEnvelope: points} : mix}, dirty: true};
        }, key),
        overlays: (items, assets, expectedEpoch) => edit((s) => (s.status === "ready" && (expectedEpoch === undefined || expectedEpoch === overlayEpoch.current)
            ? {...s, overlays: items, overlayAssets: assets ?? s.overlayAssets, dirty: true} : s)),
        narration: (selection, asset, key = null) => edit((s) => (s.status === "ready" ? {...s, audio: {...s.audio, narration: selection, asset: selection ? asset ?? s.audio.asset : null}, dirty: true} : s), key),
        // Drag and keyboard only change the start; never write a closed-over asset or selection back.
        narrationStart: (startFrame) => edit((s) => {
            if (s.status !== "ready" || !s.audio?.narration || !s.audio?.asset) return s;
            if (s.audio.narration.startFrame === startFrame) return s;
            return {...s, audio: {...s.audio, narration: {...s.audio.narration, startFrame}}, dirty: true};
        }),
        // Swap a clip's footage for another analysed clip of the same recordings (1x, cut in);
        // its length stays as close to the old one as the new clip allows.
        replace: (id, candidate) => edit((s) => replaceClip(s, id, candidate, candidates?.candidateManifestSha256 ?? null)),
        undo: () => { restoreEpoch.current++; setState((s) => {
            const h = history.current, previous = h.past.at(-1);
            if (!previous || s.status !== "ready") return s;
            h.past = h.past.slice(0, -1); h.future = [...h.future, snap(s)]; h.key = null;
            editEpoch.current += 1;
            return {...s, ...previous};
        }); },
        redo: () => { restoreEpoch.current++; setState((s) => {
            const h = history.current, next = h.future.at(-1);
            if (!next || s.status !== "ready") return s;
            h.future = h.future.slice(0, -1); h.past = [...h.past, snap(s)]; h.key = null;
            editEpoch.current += 1;
            return {...s, ...next};
        }); },
        reset: () => { restoreEpoch.current++; overlayEpoch.current += 1; editEpoch.current += 1; clearHistory(); setState((s) => (s.editor ? {...s, clips: normalize(s.editor), audio: audioOf(s.editor), ...overlaysOf(s.editor), ...captionsOf(s.editor), bounds: Object.fromEntries(normalize(s.editor).map((c) => [c.clipId, {startUs: c.startUs, endUs: c.endUs}])), replacements: {}, insertions: s.editor.insertions ?? null, candidateManifestSha256: s.editor.candidateManifestSha256 ?? null, dirty: false} : s)); },
    };

    const discardDraft = () => { restoreEpoch.current++; return drafts.discard(); };
    const restoreDraft = async (confirm, canRestore = () => true) => {
        if (!canRestore()) return;
        if (state.dirty && !confirm()) return;
        const before = state, mine = ++restoreEpoch.current, generation = loading.current;
        const key = drafts.key, raw = localStorage.getItem(key);
        const valid = () => canRestore() && current.current === before && mine === restoreEpoch.current
            && generation === loading.current && localStorage.getItem(key) === raw;
        try {
            const editor = await client.api(`/api/creation/jobs/${encodeURIComponent(state.base.jobId)}/edit`, {planId: state.base.planId});
            if (!valid() || editor.parentJobId !== state.base.jobId || editor.planId !== state.base.planId) return;
            if (editor.expectedParentReceiptSha256 !== state.editor.expectedParentReceiptSha256) throw Error("父版本已变化，不能恢复编辑快照");
            const payload = await readSnapshot(localStorage, key, editor, [SPEEDS, clipFrames, transitionProblem]);
            if (!valid() || !payload) return;
            let clips = rebuild(payload, editor, SPEEDS, clipFrames, transitionProblem);
            let restored = {...overlaysOf(editor), bounds: Object.fromEntries(normalize(editor).map(c => [c.clipId, {startUs: c.startUs, endUs: c.endUs}])), replacements: {}, insertions: editor.insertions ?? null, candidateManifestSha256: editor.candidateManifestSha256 ?? null, audio: audioOf(editor), subtitleOverrides: keptCaptions(editor.subtitleOverrides || [], clips)};
            if ([FULL_SCHEMA, V3_SCHEMA, V4_SCHEMA].includes(payload.schemaVersion)) {
                const projected = await client.api('/api/creation/draft-restore-preview', {}, {body: {
                    projectId: project, parentJobId: state.base.jobId, planId: state.base.planId,
                    expectedParentReceiptSha256: editor.expectedParentReceiptSha256, clips: rows(clips),
                    subtitleOverrides: payload.subtitleOverrides, audioMix: payload.audioMix, narration: payload.narration,
                    ...([V3_SCHEMA, V4_SCHEMA].includes(payload.schemaVersion) ? {candidateManifestSha256: payload.candidateManifestSha256, replacements: payload.replacements, overlays: payload.overlays, ...(payload.schemaVersion === V4_SCHEMA ? {insertions: payload.insertions} : {})} : {}),
                }});
                if (!valid()) return;
                restored = {...restored, audio: audioOf(projected), subtitleOverrides: projected.subtitleOverrides};
                if ([V3_SCHEMA, V4_SCHEMA].includes(payload.schemaVersion)) {
                    clips = projected.clips;
                    const reason = transitionProblem(clips, editor.fps);
                    if (reason) throw Error(reason);
                    restored = {...restored, ...overlaysOf(projected), bounds: projected.bounds,
                        replacements: Object.fromEntries(projected.replacements.map(r => [r.targetClipId, r.candidateId])),
                        candidateManifestSha256: projected.candidateManifestSha256, insertions: projected.insertions?.length || editor.insertions ? projected.insertions ?? [] : null};
                }
            }
            // The snapshot may have changed while either read-only request was in flight.
            if (!valid()) return;
            drafts.invalidate(); overlayEpoch.current++;
            edit(s => { if (s !== before) return s;
                const next = {...s, clips, ...restored, dirty: true};
                drafts.markRestored(next); return next; });
        } catch (e) { if (valid()) setState(s => {
            const next = {...s, draftError: `无法恢复编辑快照：${e.message}`};
            drafts.markRestored(next); return next; }); }
    };

    const loadCandidates = useCallback(async () => {
        if (candidates || !state.base) return candidates;
        const generation = loading.current, base = state.base;
        const data = await client.api(`/api/creation/jobs/${encodeURIComponent(base.jobId)}/candidates`, {planId: base.planId});
        if (generation !== loading.current || current.current.base !== base) return null;
        setCandidates(data); return data;
    }, [candidates, state.base]);

    // Save the local edit as a new version; returns the version's job id.
    const save = useCallback(async (follow) => {
        if (saving.current) throw Error("正在保存版本");
        const {base, subtitleOverrides} = state;
        const problem = captionProblem(subtitleOverrides);
        if (problem) throw new Error(problem);
        saving.current = true;
        try {
            const accepted = await client.submit("revision", revisionFields(state));
            const done = await follow(accepted.jobId);
            if (done?.status !== "completed") throw new Error(done ? `保存失败：${done.error?.message || done.status}` : "保存已取消");
            drafts.discard();
            client.forgetIntent("revision");
            await load(done.jobId, base.planId, "revision");
            return done.jobId;
        } finally { saving.current = false; }
    }, [state, load]);

    return {...state, drafts: {...drafts, discard: discardDraft}, restoreDraft, project, overlayEpoch: overlayEpoch.current, editEpoch: editEpoch.current, selectedId, setSelectedId, load, ops, save, candidates, loadCandidates, rows: () => rows(state.clips),
        canUndo: history.current.past.length > 0, canRedo: history.current.future.length > 0};
}

export function ClipInspector({editing, index, onSeek, basket}) {
    const clip = editing.clips[index]; if (!clip) return null;
    const fps = editing.editor.fps, bound = editing.bounds[clip.clipId];
    const frames = clipFrames(clip, fps), seconds = (us) => (us / 1e6).toFixed(2);
    const fade = (s) => Math.round(s * fps);
    const replacing = !!editing.replacements[clip.clipId], inserted = isPendingInsertion(editing, clip.clipId);
    const mustCut = !!forcedCut(editing.clips, index, editing.replacements);
    const caption = editing.subtitleOverrides.find((o) => o.clipId === clip.clipId);
    return html`${editing.insertions?.length ? html`<p class="hint">插入、裁剪、删除和其他镜头的替换可一起保存；旁白和图层保持原时刻。</p>` : null}<div class="field"><div class="k">第 ${index + 1} 个镜头 · 成片 ${(frames / fps).toFixed(2)} 秒</div>
            <div class="v">${clip.role ? `【${clip.role}】` : ""}${clip.scriptDraft || "无描述"}</div></div>
        <div class="field"><div class="k">取材范围（原片秒，可在 ${seconds(bound.startUs)}–${seconds(bound.endUs)} 内裁短）</div>
            <div class="pair even">
                <label class="form-row">入点<input class="input" type="number" step="0.1" min=${seconds(bound.startUs)} max=${seconds(bound.endUs)} value=${seconds(clip.startUs)}
                    onChange=${(e) => editing.ops.trim(clip.clipId, "startUs", Number(e.currentTarget.value))} /></label>
                <label class="form-row">出点<input class="input" type="number" step="0.1" min=${seconds(bound.startUs)} max=${seconds(bound.endUs)} value=${seconds(clip.endUs)}
                    onChange=${(e) => editing.ops.trim(clip.clipId, "endUs", Number(e.currentTarget.value))} /></label>
            </div></div>
        <div class="field"><div class="pair even">
            <label class="form-row">速度<select class="select" disabled=${replacing} value=${`${clip.speed.numerator}/${clip.speed.denominator}`}
                onChange=${(e) => { const [n, d] = e.currentTarget.value.split("/").map(Number); editing.ops.speed(clip.clipId, n, d); }}>
                ${SPEEDS.map(([n, d, label]) => html`<option value=${`${n}/${d}`}>${label}</option>`)}</select></label>
            <label class="form-row">进入方式<select class="select" disabled=${index === 0 || mustCut} value=${String(clip.transitionIn.frames)}
                onChange=${(e) => editing.ops.transition(clip.clipId, Number(e.currentTarget.value))}>
                <option value="0">直接切换</option><option value=${String(fade(0.25))}>交叉淡化 0.25 秒</option><option value=${String(fade(0.5))}>交叉淡化 0.5 秒</option></select></label>
        </div><p class="hint">${mustCut ? "替换镜头及其下一段使用直接切换。" : "即时预览支持交叉淡化；镜头需足够长，才能容纳两侧转场。"}</p></div>
        <div class="field">
            <label class="form-row">镜头字幕<textarea class="input" rows="3" disabled=${replacing} value=${caption?.text ?? ""}
                onInput=${(e) => editing.ops.caption(clip.clipId, e.currentTarget.value)} /></label>
            <p class="hint" role="status" aria-label="镜头字幕状态">${!caption ? "自动字幕：有原片转录时使用语音字幕，无转录则无字幕。" : caption.text === "" ? "此镜头不显示字幕。" : "手写字幕：覆盖整个镜头。"}</p>
            <p class="hint">仅修改成片字幕，不修改原片转录。最多 2000 字；保存后导出生效。在导出页选择 SRT 或烧入字幕，即可预览内容与时机；字体排版以导出为准。</p>
            ${replacing && html`<p class="hint">先保存替换版本，再编辑新镜头字幕。</p>`}
            <div class="actions-row"><button class="btn ghost" disabled=${replacing || !caption} onClick=${() => editing.ops.caption(clip.clipId, null)}>恢复自动字幕</button>
                <button class="btn ghost" disabled=${replacing} onClick=${() => editing.ops.caption(clip.clipId, "")}>此镜头不显示字幕</button></div>
        </div>
        <div class="field actions-row">
            <button class="btn ghost" onClick=${() => onSeek(clip.clipId)}>从这段播放</button>
            <button class="btn ghost" disabled=${index === 0} onClick=${() => editing.ops.move(clip.clipId, -1)}>前移</button>
            <button class="btn ghost" disabled=${index === editing.clips.length - 1} onClick=${() => editing.ops.move(clip.clipId, 1)}>后移</button>
            <button class="btn ghost danger" disabled=${editing.clips.length <= 1} onClick=${() => editing.ops.remove(clip.clipId)}>删除这段</button>
        </div>
        ${inserted ? html`<p class="hint">新插入的镜头如需换画面，请先保存版本。</p>` : html`<${ReplacePicker} key=${clip.clipId} editing=${editing} clip=${clip} basket=${basket} />`}`;
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
                <span class="hit-text"><span class="meta">候选${list.indexOf(c) + 1} · ${inBasket(c) ? "片段篮 · " : ""}${(c.sourceName || "").slice(0, 12)} · ${(c.startUs / 1e6).toFixed(1)} 秒起 · 长 ${((c.endUs - c.startUs) / 1e6).toFixed(1)} 秒</span>${c.scriptDraft}</span>
                <button class="btn ghost" onClick=${() => { editing.ops.replace(clip.clipId, c); setOpen(false); }}>换成这段</button></div>`)}
                ${!shown.length && html`<p class="hint">没有可用的片段。</p>`}</div>`}
        <div class="actions-row"><button class="btn ghost" onClick=${() => setOpen(false)}>收起</button></div>
    </div>`;
}

function useTimelinePreview(editing, qualifier, onPreview) {
    const [result, setResult] = useState(null), [message, setMessage] = useState("");
    const key = JSON.stringify([editing.base, editing.editEpoch, editing.status, qualifier]);
    const active = useRef(null);
    useLayoutEffect(() => {
        const scope = {showing: false};
        active.current = scope;
        setResult(null);
        setMessage((old) => old.includes("将会：") ? "" : old);
        return () => { active.current = null; if (scope.showing) onPreview(null); };
    }, [key]);
    const preview = (data, detail) => {
        const replacements = data.proposal
            ? Object.fromEntries(data.proposal.replacements.map((r) => [r.targetClipId, r.candidateId]))
            : editing.replacements;
        if (Object.keys(replacements).length && data.clips.some((row, index) => {
            return (forcedCut(data.clips, index, replacements) && row.transitionIn.frames > 0)
                || (replacements[row.clipId] && row.speed.numerator !== row.speed.denominator);
        })) throw Error("替换镜头需保持原速，前后须直接切换。请调整指令或先保存版本。");
        active.current.showing = true;
        const projection = data.proposal ?? (editing.insertions?.length
            ? {insertions: composedInsertions(editing, data.clips)} : undefined);
        setResult({data, epoch: editing.editEpoch}); onPreview(data.clips, projection); setMessage(detail);
    };
    const clear = (detail) => {
        active.current.showing = false;
        setResult(null); onPreview(null); setMessage(detail);
    };
    return {result, message, setMessage, active, preview, clear};
}

async function commandPreview(text, editing) {
    const mixed = /^(?:请|帮我|把|将)*第([1-9]\d*)(?:个)?镜头(?:换成|替换为)候选([1-9]\d*)\s*(?:[，,；;]\s*(?:然后|再)?|然后|再)\s*(.+)$/s.exec(text);
    const fps = editing.editor.fps;
    const run = (instruction, clips) => client.api("/api/creation/timeline-commands", {}, {body: {text: instruction, fps, clips}});
    if (!mixed) return run(text, editing.rows());
    if ([...text].length > 500) throw Error("请输入1–500字的修改要求。");
    const [, shotNumber, candidateNumber, remainder] = mixed;
    const target = editing.clips[Number(shotNumber) - 1];
    if (!target) throw Error(`找不到第${shotNumber}个镜头。`);
    if (isPendingInsertion(editing, target.clipId)) throw Error("请先保存新插入的镜头，再替换它。");
    const available = await editing.loadCandidates();
    const candidate = available?.candidates[Number(candidateNumber) - 1];
    if (!candidate || candidate.eventId === target.eventId || candidate.endUs - candidate.startUs < 500000) {
        throw Error(`候选${candidateNumber}不可用于替换该镜头。请核对「替换这段画面」中的编号。`);
    }
    const draft = replaceClip(editing, target.clipId, candidate, available.candidateManifestSha256);
    const result = await run(remainder, rows(draft.clips));
    if (!result.clips.some((row) => row.clipId === target.clipId)) throw Error("后续指令删掉了刚替换的镜头，请调整指令。");
    const finalClips = result.clips;
    const insertions = composedInsertions(draft, finalClips);
    const proposal = await client.api("/api/creation/draft-restore-preview", {}, {body: {
        projectId: editing.project,
        ...revisionFields({...draft, clips: finalClips, insertions}),
    }});
    const beforeSeconds = editing.clips.reduce((count, clip) => count + clipFrames(clip, fps) - clip.transitionIn.frames, 0) / fps;
    const clips = proposal.clips.map((clip) => ({...clip, rangeProvenance: clip.rangeProvenance ?? null}));
    return {...result, beforeSeconds, clips, proposal: {...proposal, insertions},
        changes: [`第${shotNumber}个镜头换成候选${candidateNumber}`, ...result.changes]};
}

// One-line edits in the assistant dock: preview the change on the timeline, then apply or discard.
function LocalCommandDock({editing, onPreview, blocked}) {
    const [text, setText] = useState("");
    const ready = editing.status === "ready" && !blocked;
    const draft = useTimelinePreview(editing, [text, blocked], onPreview);
    const preview = async (event) => {
        event.preventDefault();
        if (!ready || !text.trim()) return;
        const scope = draft.active.current;
        try {
            const data = await commandPreview(text.trim(), editing);
            if (draft.active.current !== scope) return;
            draft.preview(data, `将会：${data.changes.join("；")}（${data.beforeSeconds.toFixed(1)} → ${data.afterSeconds.toFixed(1)} 秒）`);
        } catch (error) { if (draft.active.current === scope) draft.clear(`没有改动：${error.message}`); }
    };
    const apply = () => {
        if (!ready || !draft.result) return;
        const {data, epoch} = draft.result;
        if (data.proposal) editing.ops.applyProposal(data.proposal, epoch);
        else editing.ops.apply(data.clips, epoch);
        draft.clear("已应用，可以预览检查，满意后导出或保存版本。");
        setText("");
    };
    const cancel = () => draft.clear("已取消，时间轴没有变化。");
    return html`<form class="dock assistant" onSubmit=${preview}>
        <strong>创作助手</strong>
        <input class="input" value=${text} disabled=${!ready} onInput=${(e) => setText(e.currentTarget.value)}
            placeholder=${ready ? "一句话修改，例如：删掉第3个镜头、第2个镜头慢放、前5秒太慢" : "选中方案后可以用一句话修改镜头"} aria-label="一句话修改镜头" />
        ${draft.result ? html`<button type="button" class="btn" onClick=${apply}>应用</button><button type="button" class="btn ghost" onClick=${cancel}>取消</button>`
            : html`<button class="btn ghost" disabled=${!ready || !text.trim()}>预览改动</button>`}
        <span class="dock-msg" role="status">${draft.message}</span>
        <p class="hint">可组合指令，例如「第2个镜头换成候选8，然后删掉第3个镜头」。候选编号在「替换这段画面」里查看。</p>
    </form>`;
}

// P030: shorten shots so cuts land on the selected BGM's local beat estimate; preview first.
export function BeatSnap({editing, onPreview, blocked}) {
    const [busy, setBusy] = useState(false);
    const bgm = editing.audio?.mix?.bgm;
    const draft = useTimelinePreview(editing, [bgm?.trackId, bgm?.trackReceiptSha256, blocked], onPreview);
    if (!bgm || editing.status !== "ready") return null;
    const preview = async () => {
        if (blocked) return;
        const scope = draft.active.current;
        setBusy(true); draft.setMessage("正在本机分析配乐节拍…");
        try {
            const data = await client.api("/api/creation/beat-snap", {}, {body: {fps: editing.editor.fps, clips: editing.rows(), sources: editing.clips.map((c) => c.runId || ""), trackId: bgm.trackId, trackReceiptSha256: bgm.trackReceiptSha256}});
            if (draft.active.current !== scope) return;
            draft.preview(data, `约 ${data.bpm} BPM（本机估计，置信度 ${data.confidence}）。将会：${data.changes.join("；")}（${data.beforeSeconds.toFixed(1)} → ${data.afterSeconds.toFixed(1)} 秒）`);
        } catch (error) { if (draft.active.current === scope) draft.clear(`没有改动：${error.message}`); }
        finally { setBusy(false); }
    };
    const apply = () => { if (blocked) return; editing.ops.apply(draft.result.data.clips, draft.result.epoch); draft.clear("已应用：镜头只缩短不加长；预览检查后保存版本。"); };
    const cancel = () => draft.clear("已取消，时间轴没有变化。");
    return html`<div class="field beat-snap"><div class="k">按配乐节拍对齐剪辑点（本机，免费）</div>
        <p class="hint">只缩短镜头，让每次切换落在它之前最近的拍点（0.7 秒内）。节拍是本机估计，未人工核对。</p>
        <div class="actions-row">${draft.result ? html`<button type="button" class="btn" onClick=${apply}>应用</button><button type="button" class="btn ghost" onClick=${cancel}>取消</button>`
            : html`<button type="button" class="btn ghost" disabled=${busy || blocked} onClick=${preview}>${busy ? "分析中…" : "预览对齐节拍"}</button>`}</div>
        <p class="hint" role="status" aria-label="节拍对齐状态">${draft.message}</p>
    </div>`;
}

export function CommandDock({editing, onPreview, blocked, onOverlayPreview = () => {}}) {
    const [mode, setMode] = useState("local");
    return html`<div class="assistant-host"><label class="assistant-mode">创作助手模式
        <select class="select" aria-label="创作助手模式" value=${mode} onChange=${(e) => { onPreview(null); onOverlayPreview(null); setMode(e.currentTarget.value); }}>
            <option value="local">本地指令（免费）</option><option value="ai">AI对话（预算内自动）</option><option value="ai-replacement">AI换镜头（预算内自动）</option><option value="ai-insertion">AI插入镜头（预算内自动）</option>
            <option value="ai-mixed">AI组合剪辑（预算内自动）</option>
        </select></label>
        ${mode === "local" ? html`<${LocalCommandDock} editing=${editing} blocked=${blocked} onPreview=${onPreview} />` : html`<${ReasoningDock} key=${mode} mode=${mode.slice(3) || "edit"} editing=${editing} onPreview=${onPreview} onOverlayPreview=${onOverlayPreview} />`}
    </div>`;
}
