// Sound for the Edit workspace: narration (draft script → local or paid cloud voice → placed in the output),
// background music (pick or upload, level), and a preview that plays both in
// step with the plan player. Everything here becomes part of the next saved version.
import {h} from "../vendor/preact.module.js";
import {envelopeDb} from "./waveform.js";
import {useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {AudioPreviewGraph} from "./audio-preview-graph.js";
import {KnowledgePanel} from "./knowledge.js";
import {useNarrationAI} from "./narration_ai.js";
import {clearDraft, draftKey, readDraft, writeDraft} from "./narration_drafts.js";

const html = htm.bind(h);
const GAINS = [0, -3, -6, -12, -18, -24];
const sameOrigin = (url) => { try { const u = new URL(url, location.origin); return u.origin === location.origin ? u.pathname + u.search : null; } catch { return null; } };
export const musicUrl = (track) => `/api/creation/music/${encodeURIComponent(track.trackId)}/audio?${new URLSearchParams({receipt: track.trackReceiptSha256})}`;
const codepoints = (value) => [...String(value ?? "")].length;


const downloadTxt = (value) => {
    const blob = new Blob([value], {type: "text/plain;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "narration-draft.txt";
        anchor.rel = "noopener";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    } finally {
        URL.revokeObjectURL(url);
    }
};

// Same integer rule as validate_narration_fit: a start is allowed only when
// sampleCount * fps <= (totalFrames - startFrame) * sampleRate.
export function maxNarrationStart(totalFrames, fps, asset) {
    if (!totalFrames || !fps) return 0;
    const count = asset?.sampleCount;
    const rate = asset?.sampleRate;
    if (Number.isSafeInteger(count) && count > 0 && Number.isSafeInteger(rate) && rate > 0) {
        return Math.max(0, totalFrames - Math.ceil((count * fps) / rate));
    }
    const seconds = Number(asset?.durationSeconds) || 0;
    if (!(seconds > 0)) return Math.max(0, totalFrames - 1);
    return Math.max(0, totalFrames - Math.ceil(seconds * fps - 1e-9));
}

export function narrationFits(startFrame, totalFrames, fps, asset) {
    if (startFrame < 0 || startFrame >= totalFrames) return false;
    const count = asset?.sampleCount;
    const rate = asset?.sampleRate;
    if (Number.isSafeInteger(count) && count > 0 && Number.isSafeInteger(rate) && rate > 0) {
        return count * fps <= (totalFrames - startFrame) * rate;
    }
    return startFrame <= maxNarrationStart(totalFrames, fps, asset);
}

// Narration that does not fit after its start point is refused by the server; say so before saving.
export function narrationProblem(audio, totalUs, fps) {
    const {narration, asset} = audio;
    if (!narration || !asset || !totalUs || !fps) return "";
    const totalFrames = Math.round((totalUs * fps) / 1e6);
    if (narrationFits(narration.startFrame, totalFrames, fps, asset)) return "";
    const room = Math.max(0, totalFrames - narration.startFrame) / fps;
    return `旁白 ${asset.durationSeconds.toFixed(1)} 秒，起点后只剩 ${room.toFixed(1)} 秒：请改短文字或提前起点（不会自动截断）`;
}

// Keep narration and music in step with the plan player; the source video follows its level.
export function useAudioPreview(player, audio, fps, video, tracks, identity) {
    const graph = useRef(null);
    const [audioError, setAudioError] = useState("");
    const voice = useRef(null), music = useRef(null);
    const track = tracks.find((t) => t.trackId === audio.mix.bgm?.trackId);
    const voiceSrc = audio.asset ? sameOrigin(audio.asset.audioUrl) : null;
    const musicSrc = track ? musicUrl(track) : null;
    useEffect(() => {
        const videos = video.current?.parentElement?.querySelectorAll("video[data-preview-slot]");
        try {
            graph.current = new AudioPreviewGraph([...videos, music.current, voice.current], setAudioError);
        } catch (error) {
            [...(videos || []), voice.current, music.current].forEach(el => { if (el) { el.pause(); el.muted = true; } });
            setAudioError(`即时音频试听不可用：${error.message}。请导出成片试听。`);
        }
        return () => { graph.current?.dispose(); graph.current = null; };
    }, []);
    useEffect(() => { graph.current?.reset(); }, [identity]);
    useEffect(() => {
        // Keyframed source volume: the preview follows the playhead, as the render does.
        const envelope = audio.mix.sourceEnvelope;
        const mix = envelope?.length ? {...audio.mix, sourceGainDb: Math.max(-60, (audio.mix.sourceGainDb || 0) + envelopeDb(envelope, player.outUs * fps / 1e6))} : audio.mix;
        graph.current?.configure(mix === audio.mix ? audio : {...audio, mix});
        graph.current?.enable(player.playing && !player.buffering);
    });
    useEffect(() => {
        const sync = (el, src, offsetS, gainDb, loop = false) => {
            if (!el) return;
            if (!graph.current?.node || graph.current.failed) { el.pause(); return; }
            if (!src || !player.playing || player.buffering || offsetS < 0) { el.pause(); return; }
            if (!el.src.endsWith(src)) el.src = src;
            el.volume = 1;
            if (Number.isFinite(el.duration) && el.duration > 0 && offsetS >= el.duration) {
                if (!loop) { el.pause(); return; }
                offsetS %= el.duration;
            }
            el.loop = loop;
            // Keep bed/narration on the output clock even while playing; pause-only seeks
            // left looped music free to drift past the 0.12s dissolve assertion (TD030).
            const drift = Math.abs(el.currentTime - offsetS);
            const phase = loop && Number.isFinite(el.duration) && el.duration > 0
                ? Math.min(drift, Math.abs(drift - el.duration))
                : drift;
            if (phase > 0.015) el.currentTime = offsetS;
            if (el.paused) void el.play().catch(() => {});
        };
        const out = player.outUs / 1e6;
        sync(voice.current, voiceSrc, out - (audio.narration?.startFrame || 0) / fps, audio.narration?.gainDb);
        sync(music.current, musicSrc, out, audio.mix.bgm?.gainDb, true);
    }, [player.playing, player.buffering, player.outUs, voiceSrc, musicSrc, audio, fps]);
    return html`${audioError && html`<p class="note warn" role="alert">${audioError}</p>`}<audio ref=${voice} preload="auto" hidden></audio><audio ref=${music} preload="auto" hidden></audio>`;
}

export function useMusicCatalog() {
    const [state, setState] = useState({tracks: [], refreshing: true, error: ""});
    const pending = useRef(null), mounted = useRef(false), channel = useRef(null);
    const reload = async (updatedTrack = null) => {
        if (!mounted.current) return;
        if (updatedTrack) channel.current?.postMessage("updated");
        pending.current?.abort();
        const controller = new AbortController();
        pending.current = controller;
        setState(source => ({
            tracks: updatedTrack ? source.tracks.map(track => track.trackId === updatedTrack.trackId
                && track.trackReceiptSha256 === updatedTrack.trackReceiptSha256 ? updatedTrack : track) : source.tracks,
            refreshing: true, error: "",
        }));
        try {
            const {tracks} = await client.api("/api/creation/music", {}, {signal: controller.signal});
            if (!controller.signal.aborted) setState({tracks, refreshing: false, error: ""});
        } catch (error) {
            if (!controller.signal.aborted) setState(source => ({...source, refreshing: false, error: error.message}));
        }
    };
    useLayoutEffect(() => {
        mounted.current = true;
        const updates = typeof BroadcastChannel === "function" ? new BroadcastChannel("studio-music-catalog") : null;
        channel.current = updates;
        if (updates) updates.onmessage = () => void reload();
        void reload();
        return () => { mounted.current = false; pending.current?.abort(); updates?.close(); channel.current = null; };
    }, []);
    return {...state, reload};
}

const MUSIC_PACES = {cuts: "按剪辑节拍", calm: "舒缓", lively: "动感", intense: "强烈"};
const MUSIC_MOODS = {calm: "舒缓", lively: "动感", intense: "强烈", dramatic: "戏剧", playful: "俏皮", electronic: "电子"};
function secondsUs(value) {
    if (value === "") return null;
    const seconds = Number(value);
    return seconds >= 0 ? Math.round(seconds * 1e6) : NaN;
}
const optionalPoint = (us, limit) => us === null || (Number.isSafeInteger(us) && us >= 0 && us < limit);

function annotationDraft(track) {
    const annotation = track.annotation;
    return {
        receipt: track.trackReceiptSha256, expected: annotation?.annotationSha256 ?? null,
        moods: annotation?.moods || [], energy: String(annotation?.energy ?? ""),
        drop: annotation?.dropUs == null ? "" : String(annotation.dropUs / 1e6),
    };
}

function MusicAnnotations({music}) {
    const [trackId, setTrackId] = useState("");
    const [drafts, setDrafts] = useState({});
    const [status, setStatus] = useState(null);
    const preview = useRef(null), pending = useRef(false), mounted = useRef(false);
    useLayoutEffect(() => {
        mounted.current = true;
        return () => { mounted.current = false; };
    }, []);
    const track = music.tracks.find(row => row.trackId === trackId);
    const saved = track && annotationDraft(track);
    const draft = drafts[trackId] || saved;
    const stale = !!(saved && draft && (saved.receipt !== draft.receipt || saved.expected !== draft.expected));
    const blocked = !track || track.annotationIssue || stale || !!status?.busy;
    const energy = draft?.energy === "" ? null : Number(draft?.energy);
    const dropUs = secondsUs(draft?.drop);
    const valid = draft && (energy === null || (Number.isInteger(energy) && energy >= 0 && energy <= 100))
        && optionalPoint(dropUs, track?.durationUs);
    const patch = change => setDrafts(current => ({...current, [trackId]: {...(current[trackId] || saved), ...change}}));
    const reset = () => {
        setDrafts(current => { const next = {...current}; delete next[trackId]; return next; });
        setStatus(null);
    };
    const save = async () => {
        if (blocked || !valid || music.refreshing || music.error || !drafts[trackId] || pending.current) return;
        pending.current = true;
        setStatus({trackId, busy: true});
        try {
            const annotation = await client.api("/api/creation/music-annotations", {}, {body: {
                trackId, trackReceiptSha256: draft.receipt, expectedAnnotationSha256: draft.expected,
                moods: draft.moods, energy, dropUs,
            }});
            if (mounted.current) {
                reset();
                setStatus({trackId, message: "已保存曲库标注。"});
            }
            await music.reload({...track, annotation});
        } catch (error) {
            if (mounted.current) setStatus({trackId, message: error.message});
            await music.reload();
        } finally {
            pending.current = false;
        }
    };
    const usePreviewTime = () => {
        const player = preview.current;
        const time = player?.readyState ? Math.round(player.currentTime * 1e6) : NaN;
        if (optionalPoint(time, track.durationUs)) patch({drop: String(time / 1e6)});
        else setStatus({trackId, message: "请先试听并将进度移到曲目中的高潮。"});
    };
    return html`<details class="group"><summary>曲库标注</summary>
        <label class="form-row">标注曲目<select class="select" value=${trackId} disabled=${!!status?.busy}
            onChange=${event => { setTrackId(event.currentTarget.value); setStatus(null); }}>
            <option value="">选择已登记曲目</option>
            ${trackId && !track && html`<option value=${trackId} disabled>当前曲目不可用</option>`}
            ${music.tracks.map(row => html`<option key=${row.trackId} value=${row.trackId}>${row.title}</option>`)}
        </select></label>
        <button class="btn ghost" type="button" disabled=${music.refreshing || status?.busy} onClick=${() => music.reload()}>刷新曲库</button>
        ${music.error && html`<p class="note" role="status">曲库读取失败。${music.error}</p>`}
        ${track && html`<${MusicAnnotationFields} track=${track} draft=${draft} preview=${preview} blocked=${blocked} stale=${stale}
            saving=${!!status?.busy} patch=${patch} reset=${reset} usePreviewTime=${usePreviewTime} />`}
        ${track && html`<button class="btn" type="button" disabled=${blocked || !valid || music.refreshing || !!music.error || !drafts[trackId]} onClick=${save}>保存曲库标注</button>`}
        ${track && !valid && html`<p class="note">力度须为 0–100 的整数，高潮须在曲目时长内。</p>`}
        ${status?.trackId === trackId && html`<p role="status">${status.busy ? "正在保存曲库标注…" : status.message}</p>`}
    </details>`;
}

function MusicAnnotationFields({track, draft, preview, blocked, stale, saving, patch, reset, usePreviewTime}) {
    return html`<div>
        <audio key=${track.trackReceiptSha256} ref=${preview} src=${musicUrl(track)} controls preload="none" aria-label="试听原音" style="width:100%"></audio>
        ${track.annotationIssue && html`<p class="note" role="alert">曲库标注记录已损坏，无法覆盖。</p>`}
        ${stale && html`<p class="note" role="status">曲目或标注已在别处更新，当前草稿已保留。</p>
            <button class="btn ghost" type="button" disabled=${saving} onClick=${reset}>放弃草稿并载入当前标注</button>`}
        <div role="group" aria-label="曲目情绪">
            ${Object.entries(MUSIC_MOODS).map(([mood, label]) => html`<label class="check" key=${mood}>
                <input type="checkbox" checked=${draft.moods.includes(mood)} disabled=${blocked}
                    onChange=${event => patch({moods: event.currentTarget.checked ? [...draft.moods, mood] : draft.moods.filter(value => value !== mood)})} />${label}
            </label>`)}
        </div>
        <label class="form-row">力度（选填）<input class="input" type="number" min="0" max="100" step="1"
            value=${draft.energy} disabled=${blocked} onInput=${event => patch({energy: event.currentTarget.value})} /></label>
        <label class="form-row">曲目高潮（秒，选填）<input class="input" type="number" min="0" step="0.000001"
            value=${draft.drop} disabled=${blocked} onInput=${event => patch({drop: event.currentTarget.value})} /></label>
        <button class="btn ghost" type="button" disabled=${blocked} onClick=${usePreviewTime}>用试听当前时刻</button>
    </div>`;
}

function useMusicMatches(body, timeline, scope, tracks, disabled) {
    const [state, setState] = useState(null);
    const inputs = [JSON.stringify(body), timeline, scope,
        JSON.stringify(tracks.map(t => [t.trackId, t.trackReceiptSha256, t.annotation?.annotationSha256, t.annotationIssue])), disabled];
    const view = useRef({inputs, generation: 0}), request = useRef(null);
    if (inputs.some((input, i) => input !== view.current.inputs[i])) {
        view.current = {inputs, generation: view.current.generation + 1};
    }
    const {generation} = view.current;
    useLayoutEffect(() => () => {
        request.current?.abort();
        request.current = null;
    }, [generation]);
    const isCurrent = () => !disabled && view.current.generation === generation;
    const analyze = async () => {
        if (!isCurrent() || request.current || !body.tracks.length) return;
        const controller = new AbortController();
        request.current = controller;
        const current = () => request.current === controller && !controller.signal.aborted && view.current.generation === generation;
        setState({generation, busy: true});
        try {
            const data = await client.api("/api/creation/ad-music-matches", {}, {body, signal: controller.signal});
            if (current()) {
                const same = data.pace === body.pace && data.mood === body.mood && data.highlightUs === body.highlightUs;
                setState({generation, suggestions: same ? data.suggestions : []});
            }
        } catch (error) {
            if (current()) setState({generation, error: error.message});
        } finally {
            if (request.current === controller) request.current = null;
        }
    };
    return {...(state?.generation === generation ? state : {}), analyze, isCurrent};
}

function musicMatchText({bpm, nearCuts, checkedCuts, totalCuts}) {
    if (!Number.isFinite(bpm)) return "节拍可信度不足";
    const comparison = !totalCuts ? "无剪辑切换点"
        : !checkedCuts ? `未覆盖任何切换点（共 ${totalCuts} 个）`
        : `近拍点 ${nearCuts}/${checkedCuts} 个切换${checkedCuts < totalCuts ? `（共 ${totalCuts} 个）` : ""}`;
    return `约 ${Math.round(bpm)} BPM · ${comparison}`;
}

function musicAnnotationText({moods, energy, dropUs, dropGapUs, moodMatch}) {
    const facts = moods.map(mood => MUSIC_MOODS[mood]).filter(Boolean);
    if (energy != null) facts.push(`力度 ${energy}`);
    if (dropUs != null) facts.push(`曲目高潮 ${dropUs / 1e6} 秒`);
    if (!facts.length) return "";
    const match = [moodMatch === true && "情绪匹配", dropGapUs != null && `高潮相差 ${(dropGapUs / 1e6).toFixed(2)} 秒`].filter(Boolean);
    return [`创作者标注（${facts.join("、")}）`, ...match].join(" · ");
}

function musicCandidates(durationOrdered, mood, highlightUs, durationUs) {
    const hasMood = track => !!mood && !!track.annotation?.moods.includes(mood);
    const hasDrop = track => highlightUs !== null && track.annotation?.dropUs != null
        && track.annotation.dropUs < Math.min(durationUs, 45_000_000);
    const weight = track => Number(hasMood(track)) + Number(hasDrop(track));
    const ranked = [...durationOrdered].sort((a, b) => weight(b) - weight(a));
    const representatives = [ranked.find(hasMood), ranked.find(hasDrop)].filter(Boolean);
    const shortlist = [...new Set([...representatives, ...ranked])].slice(0, 6);
    return ranked.filter(track => shortlist.includes(track));
}

function AdMusicSuggestions({tracks, durationUs, cutUs, timeline, scope, selectedId, disabled, onSelect}) {
    const [pace, setPace] = useState("cuts");
    const [mood, setMood] = useState("");
    const [highlight, setHighlight] = useState("");
    const highlightUs = secondsUs(highlight);
    const valid = optionalPoint(highlightUs, durationUs);
    const eligible = tracks.filter((track) => track.licenseStatus === "user_declared");
    const covering = eligible.filter((track) => track.durationUs >= durationUs).sort((a, b) => a.durationUs - b.durationUs);
    const looping = eligible.filter((track) => track.durationUs < durationUs).sort((a, b) => b.durationUs - a.durationUs);
    const durationOrdered = [...covering, ...looping];
    const candidates = musicCandidates(durationOrdered, mood, valid ? highlightUs : null, durationUs);
    const match = useMusicMatches({
        durationUs, cutUs, pace, mood: mood || null, highlightUs,
        tracks: candidates.map(({trackId, trackReceiptSha256}) => ({trackId, trackReceiptSha256})),
    }, timeline, scope, tracks, disabled || !valid || durationUs <= 0);
    if (durationUs <= 0) return null;
    const ranked = (match.suggestions || []).flatMap(result => {
        const track = candidates.find(t => t.trackId === result.trackId && t.trackReceiptSha256 === result.trackReceiptSha256
            && (t.annotation?.annotationSha256 ?? null) === result.annotationSha256);
        return track ? [{track, result}] : [];
    });
    const catalogChanged = ranked.length !== (match.suggestions?.length || 0);
    const matched = !catalogChanged && ranked.some(({result}) => Number.isFinite(result.bpm) || result.moodMatch === true
        || result.dropGapUs != null || (pace !== "cuts" && Number.isFinite(result.energy)));
    const suggestions = matched ? ranked : durationOrdered.slice(0, 3).map(track => ({track}));
    const select = (track, result) => { if (!disabled && (!result || match.isCurrent())) onSelect(track); };
    return html`<div class="field">
        <div class="k">广告配乐建议</div>
        ${suggestions.length ? html`
            <p class="hint">${matched ? "按节奏、情绪和高潮匹配排序。" : `按当前 ${(durationUs / 1e6).toFixed(1)} 秒成片匹配时长，优先选一次播完即可覆盖的音乐。`}选用后可随画面试听。</p>
            <label class="form-row">节奏偏好<select class="select" value=${pace} disabled=${disabled}
                onChange=${event => setPace(event.currentTarget.value)}>
                ${Object.entries(MUSIC_PACES).map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
            </select></label>
            <label class="form-row">情绪偏好<select class="select" value=${mood} disabled=${disabled} onChange=${event => setMood(event.currentTarget.value)}>
                <option value="">不限</option>
                ${Object.entries(MUSIC_MOODS).map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
            </select></label>
            <label class="form-row">成片高潮（秒，选填）<input class="input" type="number" min="0" step="0.000001"
                value=${highlight} disabled=${disabled} onInput=${event => setHighlight(event.currentTarget.value)} /></label>
            ${!valid && html`<p class="note">高潮时间须在成片时长内。</p>`}
            <p class="hint">最多分析 6 首已声明使用权的本机音乐，优先覆盖所选情绪和已标注高潮，再按时长选曲。</p>
            <button class="btn ghost" type="button" disabled=${disabled || !valid || match.busy} onClick=${match.analyze}>分析本机配乐节拍</button>
            ${match.busy && html`<p class="note" role="status">正在分析本机配乐节拍…</p>`}
            ${catalogChanged ? html`<p class="note" role="status">曲库标注已更新。请在「曲库标注」中刷新曲库后重新分析。</p>`
                : match.suggestions && !matched && html`<p class="note" role="status">没有可信节拍或可用标注匹配，仍按时长推荐。你也可以手工选用曲目。</p>`}
            ${match.error && html`<p class="note" role="status">节拍分析失败，仍按时长推荐。${match.error}</p>`}
            <ul>${suggestions.map(({track, result}) => html`<li key=${track.trackId}>
                <button class="btn ghost" type="button" style="max-width:100%;overflow-wrap:anywhere" disabled=${disabled || selectedId === track.trackId}
                    onClick=${() => select(track, result)}>${selectedId === track.trackId ? "已选用" : "选用"} ${track.title}</button>
                <span class="hint"> ${track.durationUs >= durationUs ? "单次覆盖" : "需要循环"} · ${(track.durationUs / 1e6).toFixed(1)} 秒</span>
                ${result && html`<span class="hint"> · ${musicMatchText(result)}</span>`}
                ${(result?.moods || track.annotation) && html`<div class="hint">${musicAnnotationText(result || track.annotation)}</div>`}
            </li>`)}</ul>` : html`<p class="hint">上传音乐并声明有权使用后，可按成片时长获得建议。</p>`}
    </div>`;
}

// Same upper bound as the server's fee gate: CJK characters count twice.
const billedCharacters = (text) => [...text].reduce((n, c) => n + ((c >= "\u2e80" && c <= "\u9fff") || (c >= "\uf900" && c <= "\uffef") ? 2 : 1), 0);
const costOf = (text, voice) => (voice?.paid ? Math.round(billedCharacters(text) * voice.yuanPer10kCharacters) / 10000 : 0);

export function AudioPanel({commandPreview = false, adMusicDurationUs = 0, adMusicCutsUs = [], adMusicTimeline, adMusicScope, musicSuggestionsDisabled = false,
    editing, project, game = "", fps, totalUs, music, onBusy}) {
    const {audio} = editing;
    const [voices, setVoices] = useState([]);
    const [billing, setBilling] = useState({spent: 0, cap: 0});
    const [voiceId, setVoiceId] = useState("");
    const [script, setScript] = useState(null);
    const [text, setText] = useState("");
    const [note, setNote] = useState("");
    const [working, setWorking] = useState("");
    const [declared, setDeclared] = useState(false);
    const [draftMode, setDraftMode] = useState("");
    const [original, setOriginal] = useState(null);
    const [revisionOpen, setRevisionOpen] = useState(false);
    const [revisionText, setRevisionText] = useState("");
    const [revisionVoiceId, setRevisionVoiceId] = useState("");
    const [revisionNote, setRevisionNote] = useState("");
    const busyEpoch = useRef(0);
    const draftEpoch = useRef(0);
    const synthEpoch = useRef(0);
    const revisionEpoch = useRef(0);
    const mounted = useRef(true);
    const scopeRef = useRef({project: "", jobId: "", planId: "", assetJobId: ""});
    const editGeneration = useRef({clips: editing.clips, audio, version: 0});
    if (editGeneration.current.clips !== editing.clips || editGeneration.current.audio !== audio) {
        editGeneration.current = {clips: editing.clips, audio, version: editGeneration.current.version + 1};
    }

    const baseJobId = editing.base?.jobId || "";
    const planId = editing.base?.planId || "";
    const attachedAssetJobId = audio.narration?.assetJobId || "";
    const currentDraftKey = draftKey(project, baseJobId, planId, revisionOpen ? attachedAssetJobId : "");
    const attachedDraftKey = draftKey(project, baseJobId, planId, attachedAssetJobId || "");

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            busyEpoch.current += 1;
            draftEpoch.current += 1;
            synthEpoch.current += 1;
            revisionEpoch.current += 1;
        };
    }, []);

    useEffect(() => {
        client.api("/api/creation/voices").then((data) => {
            setVoices(data.voices || []);
            setBilling({spent: data.spentThisMonthYuan || 0, cap: data.monthlyCapYuan || 0});
            const chinese = (data.voices || []).find((v) => !v.paid && (v.language === "804" || /chinese|中文/i.test(v.description)));
            const preferred = (data.voices || []).find((v) => v.voiceId === data.defaultVoiceId && !v.paid);
            setVoiceId((preferred || chinese || (data.voices || []).find((v) => !v.paid))?.voiceId || "");
        }).catch(() => setVoices([]));
    }, []);

    // Scope change: bump epochs; do not write old text into the new key.
    useEffect(() => {
        draftEpoch.current += 1;
        synthEpoch.current += 1;
        revisionEpoch.current += 1;
        scopeRef.current = {project, jobId: baseJobId, planId, assetJobId: attachedAssetJobId};
        busyEpoch.current += 1;
        setScript(null);
        setText("");
        setNote("");
        setDraftMode("");
        setOriginal(null);
        setWorking("");
        setRevisionOpen(false);
        setRevisionText("");
        setRevisionNote("");
        onBusy(false);
        // Restore free-draft (no attached asset scope) if present.
        const freeKey = draftKey(project, baseJobId, planId, "");
        const loaded = readDraft(localStorage, freeKey);
        if (loaded.ok && loaded.draft) {
            setText(loaded.draft.text);
            if (loaded.draft.voiceId) setVoiceId(loaded.draft.voiceId);
            setDraftMode("handwritten");
            setNote("已恢复本机未合成文字，来源需重新核对");
        } else if (!loaded.ok) {
            setNote(loaded.reason || "本机草稿异常");
        }
    }, [editing.base?.jobId, editing.base?.planId, project, attachedAssetJobId]);

    useEffect(() => {
        scopeRef.current = {project, jobId: baseJobId, planId, assetJobId: attachedAssetJobId};
    }, [project, baseJobId, planId, attachedAssetJobId]);

    const busy = (value) => { setWorking(value); onBusy(!!value); return ++busyEpoch.current; };

    const persistFreeDraft = (nextText, nextVoice) => {
        const key = draftKey(project, baseJobId, planId, "");
        const result = writeDraft(localStorage, key, nextText, nextVoice);
        if (!result.ok) setNote(result.reason);
    };

    const persistAttachedDraft = (nextText, nextVoice) => {
        const key = draftKey(project, baseJobId, planId, attachedAssetJobId || "");
        const result = writeDraft(localStorage, key, nextText, nextVoice);
        if (!result.ok) setRevisionNote(result.reason);
    };

    const fillAttachedDraft = (data) => {
        const loaded = readDraft(localStorage, attachedDraftKey);
        if (!loaded.ok) { setRevisionNote(loaded.reason); return; }
        const previous = revisionOpen ? revisionText : loaded.draft?.text || "";
        if (previous.trim() && previous !== data.text
            && !confirm("替换当前待合成稿？当前修改将丢失，正在使用的音轨保持原样。")) return;
        const chosen = voices.find(v => v.voiceId === (revisionOpen ? revisionVoiceId : loaded.draft?.voiceId || voiceId) && !v.paid)
            || voices.find(v => v.voiceId === audio.asset?.voice?.voiceId && !v.paid)
            || voices.find(v => !v.paid && (v.language === "804" || /chinese|中文/i.test(v.description)))
            || voices.find(v => !v.paid);
        setRevisionText(data.text);
        setRevisionVoiceId(chosen?.voiceId || "");
        setRevisionOpen(true);
        setOriginal({text: data.text, citations: data.citations || []});
        persistAttachedDraft(data.text, chosen?.voiceId || "");
        setRevisionNote("已填入待合成稿；请核对来源，再明确点击本机重新合成。旧音轨仍有效。");
    };

    const draft = async () => {
        const editVersion = editGeneration.current.version;
        const token = ++draftEpoch.current;
        const task = busy("script"); setNote("");
        try {
            const data = await client.api(`/api/creation/jobs/${encodeURIComponent(editing.base.jobId)}/narration-script`, {planId: editing.base.planId});
            if (draftEpoch.current !== token || !mounted.current) return;
            if (editGeneration.current.version !== editVersion) return;
            if (audio.narration) { fillAttachedDraft(data); return; }
            const citations = Array.isArray(data.citations) ? data.citations : [];
            setScript(data);
            setText(data.text);
            setDraftMode("drafted");
            setOriginal({text: data.text, citations});
            persistFreeDraft(data.text, voiceId);
        } catch (error) {
            if (draftEpoch.current === token && mounted.current) setNote(error.message);
        } finally {
            if (busyEpoch.current === task && mounted.current) busy("");
        }
    };

    const ai = useNarrationAI({editing, commandPreview, working: !!working, project,
        text: audio.narration ? revisionText : text, fallback: draft, adopt: (data) => {
        draftEpoch.current += 1;
        if (audio.narration) { fillAttachedDraft(data); return; }
        setScript(data); setText(data.text); setDraftMode("ai");
        setOriginal({text: data.text, citations: data.citations || []});
        persistFreeDraft(data.text, voiceId);
        setNote("已填入 AI 旁白草稿，请核对后用本机声音试听。");
    }});

    const startHandwritten = () => {
        draftEpoch.current += 1;
        setDraftMode("handwritten");
        setScript(null);
        setText("");
        setOriginal(null);
        setNote("手写旁白稿：不会自动起草，也不会发起语音任务。");
        busy("");
        persistFreeDraft("", voiceId);
    };

    const restoreOriginal = () => {
        if (draftMode !== "drafted" || !original) return;
        if (!confirm("恢复起草原文？当前修改将丢失。")) return;
        setText(original.text);
        setScript((prev) => prev ? {...prev, text: original.text, citations: original.citations} : {text: original.text, citations: original.citations, charactersPerSecond: 3.5});
        setNote("已恢复起草原文（未发起网络请求）。");
        persistFreeDraft(original.text, voiceId);
    };

    const synthesize = async () => {
        const chosen = voices.find((v) => v.voiceId === voiceId), body = text.trim();
        const token = ++synthEpoch.current;
        busy("voice"); setNote(chosen?.paid ? "正在用云端语音合成…" : "正在用本机语音合成…");
        try {
            const accepted = await client.submit("narration", {projectId: project, text: body, voiceId, ...(chosen?.paid ? {costConfirmationYuan: costOf(body, chosen)} : {})});
            if (synthEpoch.current !== token || !mounted.current) return;
            const done = await client.settle(accepted.jobId);
            if (synthEpoch.current !== token || !mounted.current) return;
            if (done.status !== "completed" || !done.narrationAsset) throw new Error(`合成失败：${done.error?.message || done.status}`);
            client.forgetIntent("narration");
            const asset = done.narrationAsset;
            editing.ops.narration({assetJobId: asset.assetJobId, receiptSha256: asset.receiptSha256, startFrame: 0, gainDb: 0, ducking: "narration-v1"}, asset);
            setNote(`已合成 ${asset.durationSeconds.toFixed(1)} 秒旁白，播放预览可以试听；满意后保存版本。`);
            if (chosen?.paid) void client.api("/api/creation/voices").then((data) => setBilling({spent: data.spentThisMonthYuan || 0, cap: data.monthlyCapYuan || 0})).catch(() => {});
        } catch (error) {
            if (synthEpoch.current === token && mounted.current) setNote(error.message);
        } finally {
            if (synthEpoch.current === token && mounted.current) busy("");
        }
    };

    const openRevision = () => {
        if (!audio.narration || !audio.asset) return;
        setOriginal(null);
        const initial = String(audio.asset.text ?? "");
        const key = draftKey(project, baseJobId, planId, attachedAssetJobId || "");
        const loaded = readDraft(localStorage, key);
        let nextText = initial;
        let nextVoice = voiceId;
        let msg = "待合成稿已打开；旧音轨仍有效，直到本机重合成成功并适配当前时间线。";
        if (loaded.ok && loaded.draft) {
            nextText = loaded.draft.text;
            if (loaded.draft.voiceId) nextVoice = loaded.draft.voiceId;
            msg = "已恢复本机未合成文字，来源需重新核对";
        } else if (!loaded.ok) {
            msg = loaded.reason || msg;
        } else {
            writeDraft(localStorage, key, initial, nextVoice);
        }
        setRevisionText(nextText);
        setRevisionVoiceId(nextVoice);
        setRevisionOpen(true);
        setRevisionNote(msg);
    };

    const cancelRevision = () => {
        // Keep local unfinished text; do not remove old track.
        setRevisionOpen(false);
        setRevisionNote("已取消文字编辑；旧音轨未移除，本机未合成文字仍保留。");
    };

    const clearRevisionDraft = () => {
        if (!confirm("清除本机草稿？仅删除当前条目的未合成文字，不会移除已保存音轨。")) return;
        const key = draftKey(project, baseJobId, planId, attachedAssetJobId || "");
        const result = clearDraft(localStorage, key);
        if (!result.ok) {
            setRevisionNote(result.reason);
            return;
        }
        setRevisionText(String(audio.asset?.text ?? ""));
        setOriginal(null);
        setRevisionNote("已清除本机草稿；已保存音轨保持原样。");
    };

    const clearFreeDraft = () => {
        if (!confirm("清除本机草稿？仅删除当前条目的未合成文字。")) return;
        const key = draftKey(project, baseJobId, planId, "");
        const result = clearDraft(localStorage, key);
        if (!result.ok) {
            setNote(result.reason);
            return;
        }
        setNote("已清除本机草稿。");
    };

    const resynthesize = async () => {
        const chosen = voices.find((v) => v.voiceId === revisionVoiceId);
        if (!chosen) {
            setRevisionNote("请选择声音。");
            return;
        }
        if (chosen.paid) {
            setRevisionNote("新增编辑/重合成路径仅支持本机免费声音；付费音色请使用原有付费合成流程。");
            return;
        }
        const body = String(revisionText ?? "");
        if (!body.trim()) {
            setRevisionNote("待合成稿为空。");
            return;
        }
        const token = ++revisionEpoch.current;
        const editVersion = editGeneration.current.version;
        const scopeSnapshot = {
            project,
            jobId: baseJobId,
            planId,
            assetJobId: attachedAssetJobId,
            startFrame: audio.narration?.startFrame ?? 0,
            gainDb: audio.narration?.gainDb ?? 0,
            ducking: audio.narration?.ducking ?? "off",
            mix: audio.mix,
        };
        busy("revise");
        setRevisionNote("正在用本机语音重新合成…");
        try {
            const payload = {projectId: project, text: body.trim(), voiceId: revisionVoiceId};
            const accepted = await client.submit("narration", payload, `revise:${attachedAssetJobId || "none"}`);
            if (revisionEpoch.current !== token || !mounted.current) return;
            const done = await client.settle(accepted.jobId);
            if (revisionEpoch.current !== token || !mounted.current) return;
            // Still same attached scope?
            if (
                scopeRef.current.project !== scopeSnapshot.project
                || scopeRef.current.jobId !== scopeSnapshot.jobId
                || scopeRef.current.planId !== scopeSnapshot.planId
                || scopeRef.current.assetJobId !== scopeSnapshot.assetJobId
            ) {
                return;
            }
            if (done.status !== "completed" || !done.narrationAsset) {
                throw new Error(`重合成失败：${done.error?.message || done.status}`);
            }
            const asset = done.narrationAsset;
            if (editGeneration.current.version !== editVersion) {
                setRevisionNote("时间线或声音设置已改变，已保留当前音轨；请重新合成。");
                return;
            }
            const trial = {
                narration: {
                    assetJobId: asset.assetJobId,
                    receiptSha256: asset.receiptSha256,
                    startFrame: scopeSnapshot.startFrame,
                    gainDb: scopeSnapshot.gainDb,
                    ducking: scopeSnapshot.ducking,
                },
                asset,
            };
            const problem = narrationProblem(trial, totalUs, fps);
            if (problem) {
                setRevisionNote(`新旁白不适配当前时间线，已保留旧音轨：${problem}`);
                return;
            }
            client.forgetIntent("narration", `revise:${scopeSnapshot.assetJobId || "none"}`);
            editing.ops.narration(trial.narration, asset);
            setRevisionNote(`已用新旁白替换音轨（${asset.durationSeconds.toFixed(1)} 秒），位置/增益/闪避与配乐保持不变。`);
            setRevisionOpen(false);
        } catch (error) {
            if (revisionEpoch.current === token && mounted.current) {
                setRevisionNote(`重合成失败，已保留旧音轨：${error.message}`);
            }
        } finally {
            if (revisionEpoch.current === token && mounted.current) busy("");
        }
    };

    const upload = async (file) => {
        if (!file) return;
        if (file.size > 30 * 1048576) { setNote("音乐文件不能超过 30 MB。"); return; }
        const token = ++synthEpoch.current;
        busy("music"); setNote("正在登记音乐…");
        try {
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
                reader.onerror = () => reject(new Error("读取文件失败"));
                reader.readAsDataURL(file);
            });
            if (synthEpoch.current !== token || !mounted.current) return;
            const track = await client.api("/api/creation/music", {}, {body: {fileName: file.name, dataBase64: data, title: file.name.replace(/\.[^.]+$/, ""), licenseStatus: declared ? "user_declared" : "unknown"}});
            if (synthEpoch.current !== token || !mounted.current) return;
            await music.reload();
            editing.ops.mix({bgm: {trackId: track.trackId, trackReceiptSha256: track.trackReceiptSha256, gainDb: -12}});
            setNote(`已加入音乐“${track.title}”（${(track.durationUs / 1e6).toFixed(0)} 秒）。`);
        } catch (error) {
            if (synthEpoch.current === token && mounted.current) setNote(error.message);
        } finally {
            if (synthEpoch.current === token && mounted.current) busy("");
        }
    };

    const n = audio.narration, asset = audio.asset, bgm = audio.mix.bgm;
    const selectMusic = (track) => editing.ops.mix({bgm: track ? {
        trackId: track.trackId, trackReceiptSha256: track.trackReceiptSha256, gainDb: bgm?.gainDb ?? -12,
    } : null});
    const selected = voices.find((v) => v.voiceId === voiceId), paid = !!selected?.paid, cost = costOf(text.trim(), selected);
    const revisionVoice = voices.find((v) => v.voiceId === revisionVoiceId);
    const estimate = text.trim() ? text.trim().length / (script?.charactersPerSecond || 3.5) : 0;
    const charCount = codepoints(text);
    const citations = ["drafted", "ai"].includes(draftMode) ? (original?.citations || script?.citations || []) : [];
    const editedAway = ["drafted", "ai"].includes(draftMode) && original && text !== original.text;
    const showEditor = !n && !!draftMode;
    const revising = working === "revise";
    const paramsLocked = revising;
    const gainSelect = (value, onChange, label, locked = false) => html`<label class="form-row">${label}<select class="select" value=${String(value ?? 0)} disabled=${locked} onChange=${(e) => onChange(Number(e.currentTarget.value))}>
        ${GAINS.map((g) => html`<option value=${String(g)}>${g === 0 ? "原音量" : `${g} dB`}</option>`)}</select></label>`;

    const toolButtons = (value, labelPrefix) => {
        const usable = String(value ?? "").trim().length > 0;
        return html`<div class="actions-row">
            <button type="button" class="btn ghost" disabled=${!usable} aria-label=${`${labelPrefix}复制旁白稿`}
                onClick=${() => void client.copyText(value, () => setNote("已复制旁白稿到剪贴板"), () => setNote("无法自动复制，请手动选择旁白文字复制"))}>复制旁白稿</button>
            <button type="button" class="btn ghost" disabled=${!usable} aria-label=${`${labelPrefix}下载旁白TXT`}
                onClick=${() => { downloadTxt(value); setNote("已下载 narration-draft.txt"); }}>下载旁白TXT</button>
        </div>`;
    };

    return html`<div class="field audio-panel"><div class="k">旁白</div>
        ${n && asset ? html`
            <div class="v">${asset.voice?.description || "本机语音"} · ${asset.durationSeconds.toFixed(1)} 秒</div>
            ${asset.captionCueCount > 0 ? html`<p class="hint">${asset.captionCueCount} 段旁白字幕随音轨移动，在导出设置开启字幕即可查看。</p>`
                : asset.captionCueCount === 0 ? html`<p class="hint">可在「编辑旁白文字」中用本机重新合成，生成旁白字幕。</p>` : null}
            <p class="hint clamp" aria-label="正在使用的旁白文字">${asset.text}</p>
            ${toolButtons(asset.text || "", "已挂接")}
            <div class="pair even">
                <label class="form-row">起点（成片秒）<input class="input" type="number" min="0" step="0.5" max=${(maxNarrationStart(Math.round((totalUs * fps) / 1e6), fps, asset) / fps).toFixed(1)} disabled=${paramsLocked} value=${(n.startFrame / fps).toFixed(1)}
                    onChange=${(e) => editing.ops.narration({...n, startFrame: Math.max(0, Math.min(maxNarrationStart(Math.round((totalUs * fps) / 1e6), fps, asset), Math.round(Number(e.currentTarget.value) * fps)))})} /></label>
                ${gainSelect(n.gainDb, (g) => editing.ops.narration({...n, gainDb: g}), "旁白音量", paramsLocked)}
            </div>
            <label class="check"><input type="checkbox" disabled=${paramsLocked} checked=${n.ducking === "narration-v1"} onChange=${(e) => editing.ops.narration({...n, ducking: e.currentTarget.checked ? "narration-v1" : "off"})} /> 旁白响起时压低原声和音乐</label>
            <div class="actions-row">
                <button type="button" class="btn ghost" disabled=${revising} aria-label="编辑旁白文字" onClick=${openRevision}>编辑旁白文字</button>
                <button type="button" class="btn ghost" disabled=${!!working || ai.busy || commandPreview || editing.dirty || editing.status !== "ready"} onClick=${ai.start}>AI重新起草旁白</button>
                <button type="button" class="btn ghost" disabled=${!!working || ai.busy || commandPreview || editing.dirty || editing.status !== "ready"} onClick=${draft}>用本机起草</button>
                <button type="button" class="btn ghost danger" disabled=${paramsLocked} onClick=${() => editing.ops.narration(null)}>移除旁白</button>
            </div>
            ${revisionOpen && html`<div class="rules-result" aria-label="旁白待合成稿区域">
                <p class="hint">待合成稿（与正在使用的音轨区分；旧音轨仍有效）</p>
                <textarea class="input" rows="6" value=${revisionText} disabled=${revising} aria-label="旁白待合成稿"
                    onInput=${(e) => {
                        const value = e.currentTarget.value;
                        draftEpoch.current += 1;
                        setRevisionText(value);
                        persistAttachedDraft(value, revisionVoiceId);
                    }}></textarea>
                <p class="hint" aria-label="待合成稿字符数">${codepoints(revisionText)} 字</p>
                ${original?.citations?.length > 0 && html`<details aria-label="待合成旁白知识引用"><summary>起草时参考资料（正文修改后请重新核对）</summary>
                    <ul>${original.citations.map(row => html`<li>${row.text}<div class="hint">${row.citation || row.title || ""}</div></li>`)}</ul></details>`}
                ${toolButtons(revisionText, "待合成")}
                <label class="form-row">声音（仅本机）<select class="select" value=${revisionVoiceId} disabled=${revising} aria-label="待合成声音"
                    onChange=${(e) => {
                        const value = e.currentTarget.value;
                        setRevisionVoiceId(value);
                        persistAttachedDraft(revisionText, value);
                    }}>
                    ${voices.filter((v) => !v.paid).map((v) => html`<option value=${v.voiceId}>${v.description}</option>`)}
                    ${voices.some((v) => v.paid) ? html`<option value="" disabled=${true}>付费音色不可用于本路径</option>` : null}
                </select></label>
                ${revisionVoice?.paid ? html`<p class="note warn">付费音色已禁用该新增重合成路径。</p>` : html`<p class="hint">本机 Windows 语音重合成，免费离线。</p>`}
                <div class="actions-row">
                    <button type="button" class="btn" disabled=${revising || !!revisionVoice?.paid || !String(revisionText).trim()} onClick=${() => void resynthesize()}>${revising ? "正在重合成…" : "本机重新合成"}</button>
                    <button type="button" class="btn ghost" disabled=${revising} onClick=${cancelRevision}>取消文字编辑</button>
                    <button type="button" class="btn ghost" disabled=${revising} onClick=${clearRevisionDraft}>清除本机草稿</button>
                </div>
                <p class="note" role="status" aria-label="旁白修订状态">${revisionNote}</p>
            </div>`}`
        : showEditor ? html`<p class="hint">${draftMode === "handwritten"
                ? "手写旁白稿（非模板起草）。"
                : draftMode === "ai" ? `AI 草稿待核对，约 ${estimate.toFixed(0)} 秒。` : `离线模板稿，请先改一遍再合成。约 ${estimate.toFixed(0)} 秒 / 成片 ${(totalUs / 1e6).toFixed(0)} 秒${estimate > totalUs / 1e6 ? "：太长了，请删减" : ""}`}</p>
                <textarea class="input" rows="6" value=${text} onInput=${(e) => {
                    const value = e.currentTarget.value;
                    draftEpoch.current += 1;
                    setText(value);
                    persistFreeDraft(value, voiceId);
                }} aria-label="旁白稿"></textarea>
                <p class="hint" aria-label="旁白字符数">${charCount} 字</p>
                ${toolButtons(text, "草稿")}
                ${["drafted", "ai"].includes(draftMode) && editedAway && html`<p class="note warn" role="status">起草时参考资料，正文已编辑，请核对</p>`}
                ${draftMode === "drafted" && ["offline-commentary-evidence-v1", "offline-ad-evidence-v1"].includes(script?.generator) && script.lines.length > 0 && html`<details class="group"><summary>${script.generator === "offline-ad-evidence-v1" ? "卖点对应画面" : "解说对应画面"}（${script.lines.length}）</summary>
                    <ul class="facts">${script.lines.map(line => html`<li>${(line.outputStartFrame / fps).toFixed(2)} 秒 · ${line.topic}<div class="hint">${line.observationQuote}</div></li>`)}</ul></details>`}
                ${["drafted", "ai"].includes(draftMode) && citations.length > 0 && html`<details class="group" aria-label="旁白知识引用"><summary>起草时参考资料（${citations.length}）</summary>
                    <ul class="facts">${citations.map((row) => html`<li key=${row.entryId}>
                        <div>${row.text}</div>
                        <div class="hint">${row.citation || ""}</div>
                        <details><summary>条目 ID</summary><code style=${{overflowWrap: "anywhere"}}>${row.entryId}</code></details>
                    </li>`)}</ul>
                </details>`}
                <div class="actions-row">
                    <button type="button" class="btn ghost" disabled=${draftMode !== "drafted" || !editedAway} aria-label="恢复起草原文" onClick=${restoreOriginal}>恢复起草原文</button>
                    <button type="button" class="btn ghost" aria-label="清除本机草稿" onClick=${clearFreeDraft}>清除本机草稿</button>
                </div>
                <label class="form-row">声音<select class="select" value=${voiceId} onChange=${(e) => {
                    const value = e.currentTarget.value;
                    setVoiceId(value);
                    persistFreeDraft(text, value);
                }}>
                    ${!voiceId && html`<option value="">未找到本机声音，请选择声音</option>`}
                    ${voices.map((v) => html`<option value=${v.voiceId} disabled=${v.paid && !v.available}>${v.description}${v.paid && !v.available ? "（未配置）" : ""}</option>`)}</select></label>
                ${paid ? html`<p class="hint">云端付费，约 ￥${cost.toFixed(4)}（${billedCharacters(text.trim())} 计费字符上限）。本月已用约 ￥${billing.spent.toFixed(2)} / 上限 ￥${billing.cap.toFixed(0)}；同样的文字和音色不会重复付费。</p>`
                    : html`<p class="hint">本机 Windows 语音，免费离线，听感偏机械。${voices.some((v) => v.paid && !v.available) ? "云端音色需在启动工作台的终端里设置 DASHSCOPE_API_KEY 后重启。" : ""}</p>`}
                <div class="actions-row"><button type="button" class="btn" disabled=${!!working || !text.trim() || !voiceId} onClick=${synthesize}>${working === "voice" ? "正在合成…" : paid ? `确认付费合成（约 ￥${cost.toFixed(4)}）` : "合成旁白"}</button></div>`
            : html`<div class="actions-row">
                <button type="button" class="btn ghost" disabled=${!!working || ai.busy || commandPreview || editing.dirty || editing.status !== "ready"} onClick=${ai.start}>${working === "script" ? "正在起草…" : "起草旁白稿"}</button>
                <button type="button" class="btn ghost" disabled=${!!working || ai.busy || commandPreview || editing.dirty || editing.status !== "ready"} onClick=${draft}>用本机起草</button>
                <button type="button" class="btn ghost" disabled=${!!working} aria-label="手写旁白稿" onClick=${startHandwritten}>手写旁白稿</button>
            </div>`}
        ${ai.view}
        </div>
        <${KnowledgePanel} key=${`${project}:${String(game || "")}`} project=${project} game=${game || ""} />
        <div class="field audio-panel"><div class="k">配乐与原声</div>
            <${AdMusicSuggestions} tracks=${music.tracks} durationUs=${adMusicDurationUs} cutUs=${adMusicCutsUs}
                timeline=${adMusicTimeline} scope=${adMusicScope} selectedId=${bgm?.trackId}
                disabled=${!!working || musicSuggestionsDisabled || music.refreshing || !!music.error} onSelect=${selectMusic} />
            <label class="form-row">配乐<select class="select" value=${bgm?.trackId || ""} onChange=${(e) => {
                selectMusic(music.tracks.find((track) => track.trackId === e.currentTarget.value));
            }}><option value="">不加配乐</option>${music.tracks.map((t) => html`<option value=${t.trackId}>${t.title}（${(t.durationUs / 1e6).toFixed(0)} 秒）</option>`)}</select></label>
            <div class="pair even">
                ${bgm ? gainSelect(bgm.gainDb, (g) => editing.ops.mix({bgm: {...bgm, gainDb: g}}), "配乐音量") : null}
                ${gainSelect(audio.mix.sourceGainDb, (g) => editing.ops.mix({sourceGainDb: g}), "原声音量")}
            </div>
            ${bgm && html`<label class="check"><input type="checkbox" checked=${audio.mix.ducking === "source-v1"} onChange=${(e) => editing.ops.mix({ducking: e.currentTarget.checked ? "source-v1" : "off"})} /> 游戏声音大时自动压低配乐</label>`}
            <label class="check"><input type="checkbox" checked=${declared} onChange=${(e) => setDeclared(e.currentTarget.checked)} /> 我有权使用要上传的音乐</label>
            <label class="btn ghost file-btn">${working === "music" ? "正在登记…" : "上传音乐"}<input type="file" accept=".mp3,.wav,.flac,.ogg,.m4a,.aac,audio/*" hidden disabled=${!!working}
                onChange=${(e) => { void upload(e.currentTarget.files?.[0]); e.currentTarget.value = ""; }} /></label>
            <p class="hint">音乐只存本机；版权由你声明，工具不做核验。配乐从成片开头播放，比成片短时循环。</p>
            <${MusicAnnotations} music=${music} />
        </div>
        ${note && html`<p class="note" role="status">${note}</p>`}`;
}
