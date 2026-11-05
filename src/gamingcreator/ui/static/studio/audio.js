// Sound for the Edit workspace: narration (draft script → local or paid cloud voice → placed in the output),
// background music (pick or upload, level), source level, and a preview that plays both in
// step with the plan player. Everything here becomes part of the next saved version.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const GAINS = [0, -3, -6, -12, -18, -24];
const level = (db) => Math.pow(10, (db || 0) / 20);
const sameOrigin = (url) => { try { const u = new URL(url, location.origin); return u.origin === location.origin ? u.pathname + u.search : null; } catch { return null; } };
export const musicUrl = (track) => `/api/creation/music/${encodeURIComponent(track.trackId)}/audio?${new URLSearchParams({receipt: track.trackReceiptSha256})}`;

// Narration that does not fit after its start point is refused by the server; say so before saving.
export function narrationProblem(audio, totalUs, fps) {
    const {narration, asset} = audio;
    if (!narration || !asset || !totalUs) return "";
    const room = totalUs / 1e6 - narration.startFrame / fps;
    return asset.durationSeconds > room ? `旁白 ${asset.durationSeconds.toFixed(1)} 秒，起点后只剩 ${Math.max(0, room).toFixed(1)} 秒：请改短文字或提前起点（不会自动截断）` : "";
}

// Keep narration and music in step with the plan player; the source video follows its level.
export function useAudioPreview(player, audio, fps, video, tracks) {
    const voice = useRef(null), music = useRef(null);
    const track = tracks.find((t) => t.trackId === audio.mix.bgm?.trackId);
    const voiceSrc = audio.asset ? sameOrigin(audio.asset.audioUrl) : null;
    const musicSrc = track ? musicUrl(track) : null;
    useEffect(() => {
        const elements = [voice.current, music.current];
        return () => elements.forEach((el) => el?.pause());
    }, []);
    useEffect(() => { if (video.current) video.current.volume = level(audio.mix.sourceGainDb); });
    useEffect(() => {
        const sync = (el, src, offsetS, gainDb, loop = false) => {
            if (!el) return;
            if (!src || !player.playing || player.buffering || offsetS < 0) { el.pause(); return; }
            if (!el.src.endsWith(src)) el.src = src;
            el.volume = level(gainDb);
            // Music loops in the render; narration plays once.
            if (Number.isFinite(el.duration) && el.duration > 0 && offsetS >= el.duration) {
                if (!loop) { el.pause(); return; }
                offsetS %= el.duration;
            }
            el.loop = loop;
            // Align once after a pause/seek; never rewind a running track on each frame.
            if (el.paused && Math.abs(el.currentTime - offsetS) > 0.015) el.currentTime = offsetS;
            if (el.paused) void el.play().catch(() => {});
        };
        const out = player.outUs / 1e6;
        sync(voice.current, voiceSrc, out - (audio.narration?.startFrame || 0) / fps, audio.narration?.gainDb);
        sync(music.current, musicSrc, out, audio.mix.bgm?.gainDb, true);
    }, [player.playing, player.buffering, player.outUs, voiceSrc, musicSrc, audio, fps]);
    return html`<audio ref=${voice} preload="auto" hidden></audio><audio ref=${music} preload="auto" hidden></audio>`;
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

export function AudioPanel({editing, project, fps, totalUs, music, onBusy}) {
    const {audio} = editing;
    const [voices, setVoices] = useState([]);
    const [billing, setBilling] = useState({spent: 0, cap: 0});
    const [voiceId, setVoiceId] = useState("");
    const [script, setScript] = useState(null);
    const [text, setText] = useState("");
    const [note, setNote] = useState("");
    const [working, setWorking] = useState("");
    const [declared, setDeclared] = useState(false);
    useEffect(() => {
        client.api("/api/creation/voices").then((data) => {
            setVoices(data.voices || []);
            setBilling({spent: data.spentThisMonthYuan || 0, cap: data.monthlyCapYuan || 0});
            const chinese = (data.voices || []).find((v) => !v.paid && (v.language === "804" || /chinese|中文/i.test(v.description)));
            const preferred = (data.voices || []).find((v) => v.voiceId === data.defaultVoiceId && !v.paid);
            setVoiceId((preferred || chinese || (data.voices || []).find((v) => !v.paid))?.voiceId || "");
        }).catch(() => setVoices([]));
    }, []);
    useEffect(() => { setScript(null); setText(""); setNote(""); }, [editing.base?.jobId, editing.base?.planId]);
    const busy = (value) => { setWorking(value); onBusy(!!value); };

    const draft = async () => {
        busy("script"); setNote("");
        try {
            const data = await client.api(`/api/creation/jobs/${encodeURIComponent(editing.base.jobId)}/narration-script`, {planId: editing.base.planId});
            setScript(data); setText(data.text);
        } catch (error) { setNote(error.message); } finally { busy(""); }
    };
    const synthesize = async () => {
        const chosen = voices.find((v) => v.voiceId === voiceId), body = text.trim();
        busy("voice"); setNote(chosen?.paid ? "正在用云端语音合成…" : "正在用本机语音合成…");
        try {
            // A paid voice carries the cost the user just confirmed by clicking; the server re-checks it.
            const accepted = await client.submit("narration", {projectId: project, text: body, voiceId, ...(chosen?.paid ? {costConfirmationYuan: costOf(body, chosen)} : {})});
            const done = await client.settle(accepted.jobId);
            if (done.status !== "completed" || !done.narrationAsset) throw new Error(`合成失败：${done.error?.message || done.status}`);
            client.forgetIntent("narration");
            const asset = done.narrationAsset;
            editing.ops.narration({assetJobId: asset.assetJobId, receiptSha256: asset.receiptSha256, startFrame: 0, gainDb: 0, ducking: "narration-v1"}, asset);
            setNote(`已合成 ${asset.durationSeconds.toFixed(1)} 秒旁白，播放预览可以试听；满意后保存版本。`);
            if (chosen?.paid) void client.api("/api/creation/voices").then((data) => setBilling({spent: data.spentThisMonthYuan || 0, cap: data.monthlyCapYuan || 0})).catch(() => {});
        } catch (error) { setNote(error.message); } finally { busy(""); }
    };
    const upload = async (file) => {
        if (!file) return;
        if (file.size > 30 * 1048576) { setNote("音乐文件不能超过 30 MB。"); return; }
        busy("music"); setNote("正在登记音乐…");
        try {
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
                reader.onerror = () => reject(new Error("读取文件失败"));
                reader.readAsDataURL(file);
            });
            const track = await client.api("/api/creation/music", {}, {body: {fileName: file.name, dataBase64: data, title: file.name.replace(/\.[^.]+$/, ""), licenseStatus: declared ? "user_declared" : "unknown"}});
            await music.reload();
            editing.ops.mix({bgm: {trackId: track.trackId, trackReceiptSha256: track.trackReceiptSha256, gainDb: -12}});
            setNote(`已加入音乐“${track.title}”（${(track.durationUs / 1e6).toFixed(0)} 秒）。`);
        } catch (error) { setNote(error.message); } finally { busy(""); }
    };

    const n = audio.narration, asset = audio.asset, bgm = audio.mix.bgm;
    const selected = voices.find((v) => v.voiceId === voiceId), paid = !!selected?.paid, cost = costOf(text.trim(), selected);
    const estimate = text.trim() ? text.trim().length / (script?.charactersPerSecond || 3.5) : 0;
    const gainSelect = (value, onChange, label) => html`<label class="form-row">${label}<select class="select" value=${String(value ?? 0)} onChange=${(e) => onChange(Number(e.currentTarget.value))}>
        ${GAINS.map((g) => html`<option value=${String(g)}>${g === 0 ? "原音量" : `${g} dB`}</option>`)}</select></label>`;
    return html`<div class="field audio-panel"><div class="k">旁白</div>
        ${n && asset ? html`
            <div class="v">${asset.voice?.description || "本机语音"} · ${asset.durationSeconds.toFixed(1)} 秒</div>
            <p class="hint clamp">${asset.text}</p>
            <div class="pair even">
                <label class="form-row">起点（成片秒）<input class="input" type="number" min="0" step="0.5" value=${(n.startFrame / fps).toFixed(1)}
                    onChange=${(e) => editing.ops.narration({...n, startFrame: Math.max(0, Math.round(Number(e.currentTarget.value) * fps))})} /></label>
                ${gainSelect(n.gainDb, (g) => editing.ops.narration({...n, gainDb: g}), "旁白音量")}
            </div>
            <label class="check"><input type="checkbox" checked=${n.ducking === "narration-v1"} onChange=${(e) => editing.ops.narration({...n, ducking: e.currentTarget.checked ? "narration-v1" : "off"})} /> 旁白响起时压低原声和音乐</label>
            <div class="actions-row"><button class="btn ghost danger" onClick=${() => editing.ops.narration(null)}>移除旁白</button></div>`
        : html`
            ${script ? html`<p class="hint">离线模板稿，请先改一遍再合成。约 ${estimate.toFixed(0)} 秒 / 成片 ${(totalUs / 1e6).toFixed(0)} 秒${estimate > totalUs / 1e6 ? "：太长了，请删减" : ""}</p>
                <textarea class="input" rows="6" value=${text} onInput=${(e) => setText(e.currentTarget.value)} aria-label="旁白稿"></textarea>
                <label class="form-row">声音<select class="select" value=${voiceId} onChange=${(e) => setVoiceId(e.currentTarget.value)}>
                    ${!voiceId && html`<option value="">未找到本机声音，请选择声音</option>`}
                    ${voices.map((v) => html`<option value=${v.voiceId} disabled=${v.paid && !v.available}>${v.description}${v.paid && !v.available ? "（未配置）" : ""}</option>`)}</select></label>
                ${paid ? html`<p class="hint">云端付费，约 ¥${cost.toFixed(4)}（${billedCharacters(text.trim())} 计费字符上限）。本月已用约 ¥${billing.spent.toFixed(2)} / 上限 ¥${billing.cap.toFixed(0)}；同样的文字和音色不会重复付费。</p>`
                    : html`<p class="hint">本机 Windows 语音，免费离线，听感偏机械。${voices.some((v) => v.paid && !v.available) ? "云端音色需在启动工作台的终端里设置 DASHSCOPE_API_KEY 后重启。" : ""}</p>`}
                <div class="actions-row"><button class="btn" disabled=${!!working || !text.trim() || !voiceId} onClick=${synthesize}>${working === "voice" ? "正在合成…" : paid ? `确认付费合成（约 ¥${cost.toFixed(4)}）` : "合成旁白"}</button></div>`
            : html`<div class="actions-row"><button class="btn ghost" disabled=${!!working} onClick=${draft}>${working === "script" ? "正在起草…" : "起草旁白稿"}</button></div>`}`}
        </div>
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
