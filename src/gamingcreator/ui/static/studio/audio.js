// Sound for the Edit workspace: narration (draft script → local or paid cloud voice → placed in the output),
// background music (pick or upload, level), and a preview that plays both in
// step with the plan player. Everything here becomes part of the next saved version.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {AudioPreviewGraph} from "./audio-preview-graph.js";
import {KnowledgePanel} from "./knowledge.js";
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

// Narration that does not fit after its start point is refused by the server; say so before saving.
export function narrationProblem(audio, totalUs, fps) {
    const {narration, asset} = audio;
    if (!narration || !asset || !totalUs) return "";
    const room = totalUs / 1e6 - narration.startFrame / fps;
    return asset.durationSeconds > room ? `旁白 ${asset.durationSeconds.toFixed(1)} 秒，起点后只剩 ${Math.max(0, room).toFixed(1)} 秒：请改短文字或提前起点（不会自动截断）` : "";
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
        graph.current?.configure(audio);
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
            if (el.paused && Math.abs(el.currentTime - offsetS) > 0.015) el.currentTime = offsetS;
            if (el.paused) void el.play().catch(() => {});
        };
        const out = player.outUs / 1e6;
        sync(voice.current, voiceSrc, out - (audio.narration?.startFrame || 0) / fps, audio.narration?.gainDb);
        sync(music.current, musicSrc, out, audio.mix.bgm?.gainDb, true);
    }, [player.playing, player.buffering, player.outUs, voiceSrc, musicSrc, audio, fps]);
    return html`${audioError && html`<p class="note warn" role="alert">${audioError}</p>`}<audio ref=${voice} preload="auto" hidden></audio><audio ref=${music} preload="auto" hidden></audio>`;
}

export function useMusicCatalog() {
    const [tracks, setTracks] = useState([]);
    const reload = () => client.api("/api/creation/music").then((data) => setTracks(data.tracks || [])).catch(() => setTracks([]));
    useEffect(() => { void reload(); }, []);
    return {tracks, reload};
}

// Same upper bound as the server's fee gate: CJK characters count twice.
const billedCharacters = (text) => [...text].reduce((n, c) => n + ((c >= "\u2e80" && c <= "\u9fff") || (c >= "\uf900" && c <= "\uffef") ? 2 : 1), 0);
const costOf = (text, voice) => (voice?.paid ? Math.round(billedCharacters(text) * voice.yuanPer10kCharacters) / 10000 : 0);

export function AudioPanel({editing, project, game = "", fps, totalUs, music, onBusy}) {
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

    const busy = (value) => { setWorking(value); onBusy(!!value); };

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

    const draft = async () => {
        const token = ++draftEpoch.current;
        busy("script"); setNote("");
        try {
            const data = await client.api(`/api/creation/jobs/${encodeURIComponent(editing.base.jobId)}/narration-script`, {planId: editing.base.planId});
            if (draftEpoch.current !== token || !mounted.current) return;
            const citations = Array.isArray(data.citations) ? data.citations : [];
            setScript(data);
            setText(data.text);
            setDraftMode("drafted");
            setOriginal({text: data.text, citations});
            persistFreeDraft(data.text, voiceId);
        } catch (error) {
            if (draftEpoch.current === token && mounted.current) setNote(error.message);
        } finally {
            if (draftEpoch.current === token && mounted.current) busy("");
        }
    };

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
    const selected = voices.find((v) => v.voiceId === voiceId), paid = !!selected?.paid, cost = costOf(text.trim(), selected);
    const revisionVoice = voices.find((v) => v.voiceId === revisionVoiceId);
    const estimate = text.trim() ? text.trim().length / (script?.charactersPerSecond || 3.5) : 0;
    const charCount = codepoints(text);
    const citations = draftMode === "drafted" ? (original?.citations || script?.citations || []) : [];
    const editedAway = draftMode === "drafted" && original && text !== original.text;
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
            <p class="hint clamp" aria-label="正在使用的旁白文字">${asset.text}</p>
            ${toolButtons(asset.text || "", "已挂接")}
            <div class="pair even">
                <label class="form-row">起点（成片秒）<input class="input" type="number" min="0" step="0.5" disabled=${paramsLocked} value=${(n.startFrame / fps).toFixed(1)}
                    onChange=${(e) => editing.ops.narration({...n, startFrame: Math.max(0, Math.round(Number(e.currentTarget.value) * fps))})} /></label>
                ${gainSelect(n.gainDb, (g) => editing.ops.narration({...n, gainDb: g}), "旁白音量", paramsLocked)}
            </div>
            <label class="check"><input type="checkbox" disabled=${paramsLocked} checked=${n.ducking === "narration-v1"} onChange=${(e) => editing.ops.narration({...n, ducking: e.currentTarget.checked ? "narration-v1" : "off"})} /> 旁白响起时压低原声和音乐</label>
            <div class="actions-row">
                <button type="button" class="btn ghost" disabled=${revising} aria-label="编辑旁白文字" onClick=${openRevision}>编辑旁白文字</button>
                <button type="button" class="btn ghost danger" disabled=${paramsLocked} onClick=${() => editing.ops.narration(null)}>移除旁白</button>
            </div>
            ${revisionOpen && html`<div class="rules-result" aria-label="旁白待合成稿区域">
                <p class="hint">待合成稿（与正在使用的音轨区分；旧音轨仍有效）</p>
                <textarea class="input" rows="6" value=${revisionText} disabled=${revising} aria-label="旁白待合成稿"
                    onInput=${(e) => {
                        const value = e.currentTarget.value;
                        setRevisionText(value);
                        persistAttachedDraft(value, revisionVoiceId);
                    }}></textarea>
                <p class="hint" aria-label="待合成稿字符数">${codepoints(revisionText)} 字</p>
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
                : `离线模板稿，请先改一遍再合成。约 ${estimate.toFixed(0)} 秒 / 成片 ${(totalUs / 1e6).toFixed(0)} 秒${estimate > totalUs / 1e6 ? "：太长了，请删减" : ""}`}</p>
                <textarea class="input" rows="6" value=${text} onInput=${(e) => {
                    const value = e.currentTarget.value;
                    setText(value);
                    persistFreeDraft(value, voiceId);
                }} aria-label="旁白稿"></textarea>
                <p class="hint" aria-label="旁白字符数">${charCount} 字</p>
                ${toolButtons(text, "草稿")}
                ${draftMode === "drafted" && editedAway && html`<p class="note warn" role="status">起草时参考资料，正文已编辑，请核对</p>`}
                ${draftMode === "drafted" && citations.length > 0 && html`<details class="group" aria-label="旁白知识引用"><summary>起草时参考资料（${citations.length}）</summary>
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
                <button type="button" class="btn ghost" disabled=${!!working} onClick=${draft}>${working === "script" ? "正在起草…" : "起草旁白稿"}</button>
                <button type="button" class="btn ghost" disabled=${!!working} aria-label="手写旁白稿" onClick=${startHandwritten}>手写旁白稿</button>
            </div>`}
        </div>
        <${KnowledgePanel} key=${`${project}:${String(game || "")}`} project=${project} game=${game || ""} />
        <div class="field audio-panel"><div class="k">配乐与原声</div>
            <label class="form-row">配乐<select class="select" value=${bgm?.trackId || ""} onChange=${(e) => {
                const t = music.tracks.find((x) => x.trackId === e.currentTarget.value);
                editing.ops.mix({bgm: t ? {trackId: t.trackId, trackReceiptSha256: t.trackReceiptSha256, gainDb: bgm?.gainDb ?? -12} : null});
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
        </div>
        ${note && html`<p class="note" role="status">${note}</p>`}`;
}
