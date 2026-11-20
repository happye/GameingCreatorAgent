// Browser-local supported editing snapshot; assets are resolved only on explicit restore.
import {useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
export const SCHEMA = "studio-clip-draft-v1";
export const FULL_SCHEMA = "studio-clip-draft-v2";
export const draftKey = (project, work, job, plan) => work ? `${SCHEMA}:${encodeURIComponent(JSON.stringify([project, work, job, plan]))}` : null;
export async function payloadHash(payload) {
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
}
export const clipRows = clips => clips.map(c => ({clipId: c.clipId, startUs: c.startUs, endUs: c.endUs,
    speed: {numerator: c.speed.numerator, denominator: c.speed.denominator},
    transitionIn: {type: c.transitionIn.type, frames: c.transitionIn.frames}}));
export function rebuild(payload, editor, speeds, frames, problem) {
    if (![SCHEMA, FULL_SCHEMA].includes(payload.schemaVersion) || payload.expectedParentReceiptSha256 !== editor.expectedParentReceiptSha256 || typeof payload.partial !== "boolean") throw Error("镜头快照与父版本不一致");
    if (payload.schemaVersion === FULL_SCHEMA && !same(Object.keys(payload).sort(),
        ["schemaVersion", "expectedParentReceiptSha256", "rows", "partial", "subtitleOverrides", "audioMix", "narration"].sort())) throw Error("编辑快照字段无效");
    if (!Array.isArray(payload.rows) || !payload.rows.length) throw Error("镜头快照为空");
    const byId = new Map(editor.clips.map(c => [c.clipId, c])), seen = new Set();
    const clips = payload.rows.map(row => {
        const parent = byId.get(row?.clipId), s = row?.speed, t = row?.transitionIn;
        if (!parent || seen.has(row.clipId)) throw Error("镜头快照含未知或重复镜头");
        seen.add(row.clipId);
        if (![row.startUs, row.endUs, s?.numerator, s?.denominator, t?.frames].every(Number.isSafeInteger)
            || row.startUs < parent.startUs || row.endUs > parent.endUs || row.startUs >= row.endUs
            || !speeds.some(([n, d]) => s.numerator === n && s.denominator === d)
            || !(t.type === "cut" && t.frames === 0 || t.type === "crossfade" && t.frames > 0)) throw Error("镜头快照字段或范围无效");
        const clip = {...parent, clipId: row.clipId, startUs: row.startUs, endUs: row.endUs,
            speed: {numerator: s.numerator, denominator: s.denominator}, transitionIn: {type: t.type, frames: t.frames}};
        if (frames(clip, editor.fps) < 1) throw Error("镜头快照含零帧镜头");
        return clip;
    });
    const reason = problem(clips, editor.fps);
    if (reason) throw Error(reason);
    return clips;
}
export async function readSnapshot(storage, key, editor, checks) {
    const raw = storage.getItem(key);
    if (raw === null) return null;
    const envelope = JSON.parse(raw), payload = envelope.payload;
    if (envelope.sha256 !== await payloadHash(payload)) throw Error("镜头快照校验失败");
    rebuild(payload, editor, ...checks);
    return payload;
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// Persist selections, never the public playback asset or a caller-supplied path.
export function fullFields(state) {
    const mix = state.audio.mix, bgm = mix.bgm, n = state.audio.narration;
    return {
        subtitleOverrides: state.subtitleOverrides.map(({clipId, text}) => ({clipId, text})),
        audioMix: {bgm: bgm ? {trackId: bgm.trackId, trackReceiptSha256: bgm.trackReceiptSha256, gainDb: bgm.gainDb} : null,
            sourceGainDb: mix.sourceGainDb, ducking: mix.ducking,
            ...(mix.sourceEnvelope ? {sourceEnvelope: mix.sourceEnvelope.map(({frame, gainDb}) => ({frame, gainDb}))} : {})},
        narration: n ? {assetJobId: n.assetJobId, receiptSha256: n.receiptSha256, startFrame: n.startFrame, gainDb: n.gainDb, ducking: n.ducking} : null,
    };
}
export function supported(state, parentFields) {
    return !Object.keys(state.replacements).length
        && same(state.overlays, parentFields.overlays) && same(state.overlayAssets, parentFields.overlayAssets);
}
export function useClipDrafts(state, project, workId, parentFields, keptCaptions, checks) {
    const key = state.base && draftKey(project, workId, state.base.jobId, state.base.planId);
    const [view, setView] = useState({key: null, payload: null, message: "", ready: false});
    const restored = useRef(null);
    const epoch = useRef(0), latest = useRef(null), previous = useRef({key: null, dirty: false}); latest.current = key;
    useLayoutEffect(() => {
        const mine = ++epoch.current;
        setView({key, payload: null, message: key ? "" : "尚无作品身份，镜头修改不会备份", ready: false});
        if (!key || state.status !== "ready") return;
        void (async () => {
            try {
                const payload = await readSnapshot(localStorage, key, state.editor, checks);
                if (mine === epoch.current) setView({key, payload, message: "", ready: true});
            } catch (e) {
                if (mine === epoch.current) setView({key, payload: null, message: `无法读取镜头快照：${e.message}；保留原存储`, ready: false});
            }
        })();
        return () => { epoch.current++; };
    }, [key, state.editor]);
    useEffect(() => {
        const prior = previous.current; previous.current = {key, dirty: state.dirty};
        if (key && prior.key === key && prior.dirty && !state.dirty && state.status === "ready") {
            epoch.current++;
            try { localStorage.removeItem(key); setView(v => ({...v, payload: null, message: ""})); }
            catch { setView(v => ({...v, message: "无法清除镜头快照；保留原存储"})); }
            return;
        }
        if (restored.current === state) return;
        if (state.status !== "ready" || !key || !view.ready || view.key !== key || !state.dirty) return;
        const mine = ++epoch.current;
        const timer = setTimeout(async () => {
            try {
                const partial = !supported(state, parentFields, keptCaptions);
                if (partial && !view.payload) {
                    if (mine === epoch.current) setView(v => ({...v, message: "当前修改无法备份为镜头快照"}));
                    return;
                }
                const payload = partial ? {...view.payload, partial: true} : {schemaVersion: FULL_SCHEMA, ...fullFields(state),
                    expectedParentReceiptSha256: state.editor.expectedParentReceiptSha256, rows: clipRows(state.clips), partial: false};
                rebuild(payload, state.editor, ...checks);
                const sha256 = await payloadHash(payload);
                if (mine !== epoch.current || latest.current !== key) return;
                const raw = JSON.stringify({payload, sha256});
                if (localStorage.getItem(key) !== raw) localStorage.setItem(key, raw);
                setView(v => ({...v, payload, message: ""}));
            } catch (e) {
                if (mine === epoch.current) setView(v => ({...v, message: `无法保存镜头快照：${e.message}；保留输入与原存储`}));
            }
        }, 250);
        return () => { clearTimeout(timer); epoch.current++; };
    }, [state, key, view.ready]);
    const discard = () => {
        epoch.current++;
        try { if (key) localStorage.removeItem(key); setView(v => ({...v, payload: null, message: "已丢弃镜头快照"})); return true; }
        catch { setView(v => ({...v, message: "无法清除镜头快照；保留原存储"})); return false; }
    };
    return {...view, payload: view.key === key ? view.payload : null, discard,
        markRestored: next => { restored.current = next; },
        invalidate: () => { epoch.current++; },
        message: view.key === key ? view.message || (view.payload?.partial ? "上次编辑快照；之后的替换或图层修改未备份" : view.payload ? "有最近编辑快照，可手动恢复" : "") : ""};
}
