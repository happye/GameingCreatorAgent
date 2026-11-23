// Publish workspace: pick a finished video, write its title, description and tags, pick the
// cover from candidate frames before saving, save that as a publication version, then build a platform package to
// download. Nothing is posted to any platform from here.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {CampaignChecks, campaignTags} from "./activity.js";
import {publicationErrorFields, publicationFieldErrors} from "./publication_form.js";
import {PublicationFeedback} from "./publication_feedback.js";
import {usePackageBatches} from "./package_batches.js";
import {EnterpriseTeam, PackageReview} from "./enterprise.js";

const html = htm.bind(h);
const PLATFORMS = {bilibili: "B站", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书"};
const CHECKS = {width: "视频宽度", height: "视频高度", codec: "编码", pixelFormat: "像素格式", frames: "帧数", fps: "帧率", maxBytes: "文件大小", minDurationMs: "最短时长", maxDurationMs: "最长时长", titleMaxChars: "标题字数", descriptionMaxChars: "简介字数", tagMaxCount: "标签数量", requiredTags: "必需标签"};
const STATUS = {pass: "通过", fail: "未通过", unknown: "未知", not_configured: "未配置"};
const jobPath = (id) => `/api/creation/jobs/${encodeURIComponent(id)}`;
const when = (iso) => new Date(iso).toLocaleString("zh-CN", {hour12: false});
const parseTags = (text) => text.split(/[,，\n]/).map((tag) => tag.trim()).filter(Boolean);
const publicationCopyDraft = (pub) => ({title: pub.title, description: pub.description, tags: pub.tags.join("\n")});
const COVER_TITLE_LIMIT = 18;
const COVER_TITLE_INVALID = /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u;
const COPY_CLOSING = {
    bilibili: "弹幕聊聊，你最想回看哪一幕？",
    douyin: "这一段，你最记得哪个画面？",
    kuaishou: "评论区说说你看到的亮点",
    xiaohongshu: "先收藏，下次回来对照看",
};
const frameLine = (line) => [...line.replace(/[{}\\<>\p{C}\u2028\u2029]/gu, " ").replace(/\s+/g, " ").trim()].slice(0, 24).join("").trimEnd();

function draftPlatformCopy(pub, profile, keyword) {
    const variant = profile.Fields.variant;
    const start = variant?.startFrame || 0;
    const end = start + (variant?.durationFrames || pub.frames);
    const observation = pub.contentShots?.find(shot => shot.startFrame >= start && shot.endFrame <= end)?.description;
    const theme = keyword.trim() || (!variant ? pub.title : observation?.split(/[；。]/, 1)[0]) || "实机剪辑";
    return {
        opening: frameLine(`${profile.Platform === "bilibili" ? "本期看点" : "实机看点"}｜${theme}`),
        closing: COPY_CLOSING[profile.Platform],
    };
}

const spanLabel = ({startFrame, endFrame}, fps) => `${(startFrame / fps).toFixed(2)}–${(endFrame / fps).toFixed(2)} 秒`;

function mergeShotRanges(picked, cap) {
    const ranges = [];
    for (const shot of [...picked].sort((a, b) => a.startFrame - b.startFrame)) {
        const last = ranges.at(-1);
        if (last && shot.startFrame <= last.endFrame) last.endFrame = Math.max(last.endFrame, shot.endFrame);
        else ranges.push({startFrame: shot.startFrame, endFrame: shot.endFrame});
    }
    const durationFrames = ranges.reduce((total, span) => total + span.endFrame - span.startFrame, 0);
    if (durationFrames > cap) return {error: "选段总时长超过上限，请增加时长或减少选择。"};
    return {ranges, durationFrames};
}

function joinedKeywordRanges(terms, shots, cap) {
    if (terms.length > 8) return {error: "最多可输入 8 个关键词。"};
    const picked = terms.map(term => shots.find(shot => shot.description.toLowerCase().includes(term)));
    const missing = terms.find((term, index) => !picked[index]);
    return missing ? {error: `没有找到「${missing}」的镜头，请更换关键词。`} : mergeShotRanges(picked, cap);
}

function configuredProfiles(profiles, selected, drafts, fps, pub) {
    const totalFrames = pub?.frames || 0, shots = pub?.contentShots || [];
    let error = "";
    let copyError = "";
    const matches = {};
    const chosen = selected.map(key => profiles.find(p => p.Platform === key)).filter(Boolean).map(profile => {
        const {duration = "", content = "", opening = "", closing = "", themeCut, publicationCopy} = drafts[profile.Platform] || {};
        const fields = {...profile.Fields};
        delete fields.publicationCopy;
        const terms = [...new Set(content.toLowerCase().split(/[、，,]/).map(term => term.trim()).filter(Boolean))];
        const joined = terms.length > 1 || !!themeCut;
        let frames = totalFrames;
        if (duration) {
            const requested = Number(duration) * fps;
            frames = joined ? Math.floor(requested) : Math.round(requested);
            if (!/^\d+(?:\.\d+)?$/.test(duration) || !Number.isSafeInteger(frames) || frames < 1 || (!joined && frames >= totalFrames)) {
                error ||= joined
                    ? `${PLATFORMS[profile.Platform]}请输入至少一帧的时长上限，或留空。`
                    : `${PLATFORMS[profile.Platform]}请输入短于原成片的秒数，例如 15 或 12.5；留空保留全片。`;
            } else if (!joined) {
                fields.variant = {durationFrames: frames};
            }
        }
        const keyword = terms[0];
        if (joined) {
            const cut = themeCut ? mergeShotRanges(themeCut.shots, frames) : joinedKeywordRanges(terms, shots, frames);
            if (cut.error) error ||= `${PLATFORMS[profile.Platform]}${cut.error}`;
            else if (cut.durationFrames >= totalFrames) error ||= `${PLATFORMS[profile.Platform]}所选区间覆盖全片，请减少关键词或清空保留全片。`;
            else {
                frames = cut.durationFrames;
                if (cut.ranges.length > 1) fields.variant = {durationFrames: frames, ranges: cut.ranges};
                else {
                    const [{startFrame}] = cut.ranges;
                    fields.variant = {durationFrames: frames, ...(startFrame ? {startFrame} : {})};
                }
                matches[profile.Platform] = {...cut, label: themeCut?.theme || terms.join("、")};
            }
        } else if (keyword) {
            const matching = shots.filter(shot => shot.description.toLowerCase().includes(keyword));
            const match = matching.find(shot => shot.endFrame - shot.startFrame <= frames);
            if (!fields.variant) error ||= `${PLATFORMS[profile.Platform]}先填写短版时长，再按内容选段。`;
            else if (matching.length && !match) error ||= `${PLATFORMS[profile.Platform]}时长不足以保留匹配镜头，请增加时长。`;
            else if (!match) error ||= `${PLATFORMS[profile.Platform]}的成片镜头里找不到「${content.trim()}」，请换个关键词。`;
            else {
                const startFrame = Math.min(match.startFrame, totalFrames - frames);
                if (startFrame > 0) fields.variant.startFrame = startFrame;
                matches[profile.Platform] = {startFrame, endFrame: startFrame + frames, label: match.description};
            }
        }
        const publicationText = {};
        for (const [key, raw] of Object.entries({opening, closing})) {
            const text = raw.trim();
            if ([...text].length > 24 || /[{}\\<>\p{C}\u2028\u2029]/u.test(raw)) {
                error ||= `${PLATFORMS[profile.Platform]}的开场文案和结尾提示各限 24 字，请使用单行纯文本。`;
            } else if (text) {
                publicationText[key] = text;
            }
        }
        if (publicationText.opening && publicationText.closing && frames < 2) {
            error ||= `${PLATFORMS[profile.Platform]}时长太短，无法同时显示开场文案和结尾提示。`;
        }
        if (Object.keys(publicationText).length) fields.publicationText = publicationText;
        if (publicationCopy) {
            const {title, description, tags: tagText} = publicationCopy;
            const tags = tagText.split("\n").filter(tag => tag.trim());
            const copy = {title, description, tags};
            const problem = Object.values(publicationFieldErrors(copy))[0]
                || ([title, description, ...tags].some(text => /\p{Cs}/u.test(text)) ? "发布文案包含无效字符。" : "");
            if (problem) copyError ||= `${PLATFORMS[profile.Platform]} ${problem}`;
            fields.publicationCopy = copy;
        }
        return {...profile, Fields: fields};
    });
    return {chosen, error, copyError, matches};
}

function PlatformPublicationCopy({platform, draft, fallback, disabled, onChange}) {
    const update = (field, value) => onChange({...draft, [field]: value});
    return html`<div>
        <label><input type="checkbox" checked=${!!draft} disabled=${disabled}
            onChange=${e => onChange(e.currentTarget.checked ? fallback : null)} />${platform} 单独编辑发布文案</label>
        ${draft && html`<div>
            <label class="form-row">${platform} 标题<input class="input" value=${draft.title} disabled=${disabled}
                onInput=${e => update("title", e.currentTarget.value)} /></label>
            <label class="form-row">${platform} 简介<textarea class="input" rows="3" value=${draft.description} disabled=${disabled}
                onInput=${e => update("description", e.currentTarget.value)}></textarea></label>
            <label class="form-row">${platform} 标签（每行一个）<textarea class="input" rows="3" value=${draft.tags} disabled=${disabled}
                onInput=${e => update("tags", e.currentTarget.value)}></textarea></label>
            <button type="button" class="btn ghost" disabled=${disabled} onClick=${() => onChange(null)}>恢复使用已保存的发布文案</button>
        </div>`}
    </div>`;
}

function ThemeRecommendations({pub, platform, fps, disabled, applied, onApply}) {
    const [theme, setTheme] = useState("");
    const [shots, setShots] = useState([]);
    const [picked, setPicked] = useState([]);
    const [status, setStatus] = useState("");
    const [busy, setBusy] = useState(false);
    const active = useRef(null);
    useEffect(() => () => active.current?.abort(), []);
    const search = async () => {
        if (disabled || busy || !theme.trim()) return;
        const controller = new AbortController();
        active.current = controller;
        setShots([]); setPicked([]); setStatus(""); setBusy(true);
        try {
            const result = await client.api("/api/creation/publication-shot-recommendations", {}, {
                signal: controller.signal,
                body: {publicationJobId: pub.publicationJobId, expectedPublicationReceiptSha256: pub.publicationReceiptSha256, theme: theme.trim()},
            });
            if (controller.signal.aborted) return;
            if (result.publicationJobId !== pub.publicationJobId || result.publicationReceiptSha256 !== pub.publicationReceiptSha256) {
                throw Error("发布版本已更改，请重新推荐。");
            }
            setShots(result.shots);
            if (!result.shots.length) setStatus("当前成片没有可用于主题推荐的镜头描述。");
        } catch (error) {
            if (!controller.signal.aborted) setStatus(error.message);
        } finally {
            if (!controller.signal.aborted) setBusy(false);
        }
    };
    return html`<details class="field">
        <summary>${platform}按主题选段</summary>
        <div class="actions-row">
            <label>${platform}主题<input class="input" value=${theme} maxlength="160" disabled=${disabled || busy}
                placeholder="例如：有哪些招式打出了伤害？" onInput=${e => {
                    setTheme(e.currentTarget.value); setShots([]); setPicked([]); setStatus("");
                }} /></label>
            <button type="button" class="btn ghost" disabled=${disabled || busy || !theme.trim()} onClick=${search}>${busy ? "本机排序中…" : `推荐${platform}镜头`}</button>
        </div>
        ${status && html`<p class="hint" role="status">${status}</p>`}
        ${!!shots.length && html`<ol>${shots.map((shot, index) => html`<li key=${index}>
            <label><input type="checkbox" disabled=${disabled} checked=${picked.includes(index)} onChange=${e => {
                const checked = e.currentTarget.checked;
                setPicked(previous => checked ? [...previous, index] : previous.filter(i => i !== index));
            }} />
                ${spanLabel(shot, fps)} · ${shot.description}</label>
        </li>`)}</ol>
            <button type="button" class="btn ghost" disabled=${disabled || !picked.length}
                onClick=${() => onApply({theme: theme.trim(), shots: picked.map(i => shots[i])})}>使用选中镜头</button>`}
        ${applied && html`<button type="button" class="btn ghost" disabled=${disabled} onClick=${() => onApply(null)}>清除主题选段</button>`}
    </details>`;
}

function previewCaption({text, frames}, fps, relative) {
    if (!text) return null;
    const window = Math.min(Math.floor(2 * fps), Object.keys(text).length === 2 ? Math.floor(frames / 2) : frames);
    if (relative >= 0 && relative < window && text.opening) return {position: "opening", text: text.opening};
    if (relative >= frames - window && relative < frames && text.closing) return {position: "closing", text: text.closing};
    return null;
}

// J1 2026-11-11: the cover is chosen before saving. Candidates are grabbed in the browser from a
// hidden copy of the video (preview only); saving still extracts the cover with FFmpeg.
const COVER_POINTS = [0.08, 0.22, 0.36, 0.5, 0.64, 0.78, 0.92];
function grabFrame(video, width = 240) {
    const canvas = document.createElement("canvas");
    canvas.width = width; canvas.height = Math.round(width * (video.videoHeight || 9) / (video.videoWidth || 16));
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.82);
}
function useCoverCandidates(src, frames, fps) {
    const [thumbs, setThumbs] = useState([]);
    const generation = useRef(0);
    useEffect(() => {
        const mine = ++generation.current;
        const live = () => generation.current === mine;
        setThumbs([]);
        if (!src || !frames) return;
        const video = document.createElement("video");
        video.muted = true; video.preload = "auto"; video.src = src;
        const seek = (frame) => new Promise((resolve, reject) => { video.onseeked = resolve; video.onerror = reject; video.currentTime = (frame + 0.5) / fps; });
        video.addEventListener("loadeddata", async () => {
            if (!live()) return;
            const found = [{frame: 0, url: grabFrame(video), src}];
            setThumbs((rows) => live() ? [...found] : rows);
            const candidates = new Set(COVER_POINTS.map((r) => Math.min(frames - 1, Math.floor(frames * r))));
            candidates.delete(0);
            for (const frame of candidates) {
                try { await seek(frame); } catch { return; }
                if (!live()) return;
                found.push({frame, url: grabFrame(video), src});
                setThumbs((rows) => live() ? [...found] : rows);
            }
        }, {once: true});
        video.addEventListener("error", () => { if (live()) setThumbs([]); });
        return () => { if (live()) generation.current++; video.removeAttribute("src"); video.load(); };
    }, [src, frames, fps]);
    return thumbs.filter(thumb => thumb.src === src);
}

// Stage B (2026-11-11): AI writes title, description and tags from the brief and the rendered
// shots (text only). Within the monthly AI budget one click sends; past it the user ticks a
// consent box for that one call. A recovery entry is stored before any send, so a lost
// response is read back instead of paid again. The result only fills the form.
const COPY_STORE = "studio-copy-reasoning-v1";
function copyRecord(renderJobId, quote) {
    try {
        const all = JSON.parse(localStorage.getItem(COPY_STORE) || "{}");
        if (quote === undefined) return all[renderJobId] || null;
        all[renderJobId] = {preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint, at: new Date().toISOString()};
        localStorage.setItem(COPY_STORE, JSON.stringify(all)); return true;
    } catch { return quote === undefined ? null : false; }
}

function AiCopy({renderJobId, disabled, onCopy}) {
    const [state, setState] = useState({busy: "", quote: null, message: "", sent: false, consent: false});
    const [available, setAvailable] = useState(false);
    const alive = useRef(true);
    useEffect(() => () => { alive.current = false; }, []);
    useEffect(() => { client.api("/api/creation/reasoning/config").then((d) => { if (alive.current) setAvailable(d.available === true); }).catch(() => {}); }, []);
    const patch = (value) => { if (alive.current) setState((s) => ({...s, ...value})); };
    const post = (body) => client.api("/api/creation/reasoning", {}, {body});
    const saved = copyRecord(renderJobId);
    const take = (result) => {
        if (!alive.current) return; // another video is shown now: never fill its form
        if (result.status === "completed" && result.copy) { onCopy(result.copy); patch({busy: "", message: "AI 文案已填入，可以修改后保存。"}); }
        else patch({busy: "", message: `AI 没有写出可用文案（${result.status}），不会自动重试。`});
    };
    const send = async (quote, explicit) => {
        if (!copyRecord(renderJobId, quote)) return patch({message: "无法保存结果恢复入口，已阻止发送，请允许浏览器本地存储"});
        patch({busy: "send", sent: true, consent: false, message: "AI 正在写…"});
        try {
            take(await post(explicit ? {action: "execute", preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint, confirmedMaxCny: quote.maxCostCny}
                : {action: "execute_budget", preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint}));
        } catch (error) {
            const refused = error.status >= 400 && error.status < 500;
            patch({busy: "", sent: !refused, message: refused ? `${error.message}（本次未发送）` : `${error.message}。可点“读取上次 AI 结果”，不会重复付费。`});
        }
    };
    const start = async () => {
        patch({busy: "prepare", quote: null, message: "", sent: false, consent: false});
        try {
            const quote = await post({action: "prepare_copy", jobId: renderJobId});
            patch({busy: "", quote});
            if (quote.budget?.eligible) await send(quote, false);
            else patch({message: `${quote.budget?.reason || "超出 AI 预算"}，需要你确认这一次。`});
        } catch (error) { patch({busy: "", message: error.message}); }
    };
    const recover = async () => {
        patch({busy: "send"});
        try { take(await post({action: "result", preparedHash: saved.preparedHash})); }
        catch (error) { patch({busy: "", message: error.message}); }
    };
    const {quote, busy, sent} = state;
    return html`<div class="field ai-copy" aria-label="AI文案">
        <div class="actions-row"><button type="button" class="btn" disabled=${disabled || !!busy || !available} onClick=${start}>${busy ? "AI 正在写…" : "让 AI 写标题、简介和标签"}</button>
            ${saved && !busy ? html`<button type="button" class="btn ghost" onClick=${recover}>读取上次 AI 结果（不重新调用）</button>` : null}</div>
        ${!available ? html`<p class="hint">未配置 DEEPSEEK_API_KEY，暂不能让 AI 写文案。</p>` : null}
        ${quote?.budget ? html`<p class="hint" aria-label="AI预算">${client.budgetText(quote.budget)}</p>` : null}
        ${quote && !quote.budget?.eligible && !sent ? html`<details><summary>本次将发送的文字</summary><pre>${JSON.stringify(quote.payloadPreview, null, 2)}</pre></details>
            <label class="check"><input type="checkbox" aria-label="同意本次AI文案费用" checked=${state.consent} onChange=${(e) => patch({consent: e.currentTarget.checked})} />同意发送以上文字，并确认本次费用上限</label>
            <button type="button" class="btn ghost" disabled=${!state.consent || !!busy} onClick=${() => send(quote, true)}>确认本次调用（最高 ¥${quote.maxCostCny}）</button>` : null}
        ${state.message ? html`<p class="hint" role="status" aria-label="AI文案状态">${state.message}</p>` : null}
        <p class="hint">AI 只读需求和每段镜头的文字描述，没有看画面；发出前请核对。</p></div>`;
}

function CoverField({savedSrc, preview, thumbs, coverFrame, coverTitle, titleError, fps, onPick, onTitle}) {
    const shown = savedSrc || preview || thumbs.find((t) => t.frame === coverFrame)?.url;
    const title = !savedSrc && !titleError ? coverTitle.trim() : "";
    return html`<div class="field cover-field"><div class="k">封面（保存前可选）</div>
        <label class="form-row">封面标题（可选，${[...coverTitle].length}/${COVER_TITLE_LIMIT} 字）
            <input class="input" value=${coverTitle} aria-invalid=${titleError ? "true" : "false"}
                aria-describedby=${titleError ? "cover-title-error" : null} onInput=${e => onTitle(e.currentTarget.value)} />
        </label>
        ${titleError && html`<p class="hint" id="cover-title-error" data-field="coverTitle">${titleError}</p>`}
        ${shown ? html`<div class="cover-preview"><img class="cover" src=${shown} alt="封面" />
            ${title && html`<span class="cover-preview-title">${title}</span>`}</div>`
            : html`<p class="hint">保存后可查看第 ${coverFrame} 帧的封面。也可以选一张候选图，或在视频里停到想要的画面后点“用当前画面做封面”。</p>`}
        <div class="cover-picks" aria-label="封面候选">${thumbs.map((t) => html`<button type="button" class="cover-pick" aria-pressed=${t.frame === coverFrame}
            data-video-src=${t.src || ""}
            title=${`第 ${t.frame} 帧（${(t.frame / fps).toFixed(1)} 秒）`} onClick=${() => onPick(t.frame, t.url)}><img src=${t.url} alt=${`封面候选 ${(t.frame / fps).toFixed(1)} 秒`} /></button>`)}</div>
        <p class="hint">好封面：人物或技能特写、画面清晰不糊、没有转场残影；横版 16:9，留出放标题的位置。</p></div>`;
}

function LocalPackageFiles({project, pkg}) {
    const [saved, setSaved] = useState(null), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
    const path = saved?.path || pkg.localPath;
    const save = async () => {
        setBusy(true); setMessage("");
        try {
            setSaved(await client.api("/api/creation/package-export", {}, {body: {projectId: project, jobId: pkg.jobId}}));
            setMessage("已保存到本机导出目录。");
        } catch (error) { setMessage(error.message); }
        finally { setBusy(false); }
    };
    return html`<div class="field">
        ${path && html`<p class="hint" style=${{overflowWrap: "anywhere"}}>${saved ? "导出文件" : "本机生成文件"} ${path}</p>`}
        <div class="actions-row">
            <button type="button" class="btn" disabled=${busy} onClick=${save}>${busy ? "正在保存…" : "保存到本机导出目录"}</button>
            ${path && html`<button type="button" class="btn ghost" onClick=${() => void client.copyText(
                saved?.directory || path, () => setMessage("已复制本机路径。"), () => setMessage(saved?.directory || path)
            )}>${saved ? "复制导出目录" : "复制文件路径"}</button>`}
        </div>
        ${message && html`<p class="hint" role="status">${message}</p>`}
    </div>`;
}

export function PublishWorkspace({project, workId, works, open, leave, onWorksChanged, layout, filterControls = null, onDirtyChange = () => {}, onOpenReference = () => {}}) {
    const renders = works.filter((j) => j.kind === "render" && j.status === "completed");
    const savedPublications = workId ? works.filter(job => job.kind === "publication" && job.status === "completed") : [];
    const savedPackages = workId ? works.filter(job => job.kind === "package" && job.status === "completed") : [];
    const [renderId, setRenderId] = useState("");
    const [pub, setPub] = useState(null); // the snapshot shown: a draft from the render or a saved publication
    const [form, setForm] = useState({title: "", description: "", tags: "", coverFrame: 0, coverTitle: ""});
    const [profiles, setProfiles] = useState([]);
    const [platform, setPlatform] = useState("");
    const [packages, setPackages] = useState([]);
    const [selected, setSelected] = useState([]);
    const defaultedRender = useRef("");
    const [platformDraft, setPlatformDraft] = useState({key: null, values: {}});
    const [previewPackage, setPreviewPackage] = useState("");
    const [teamVersion, setTeamVersion] = useState(0);
    const epoch = useRef(0);
    const polling = useRef(new AbortController());
    const activeProject = useRef(project);
    const shownProject = useRef(null);
    const shownOpen = useRef(null);
    const rejectedOpen = useRef(null);
    if (activeProject.current !== project) { activeProject.current = project; epoch.current++; polling.current.abort(); polling.current = new AbortController(); }
    useEffect(() => () => { epoch.current++; polling.current.abort(); }, []);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [fieldError, setFieldError] = useState({});
    const video = useRef(null);
    const shortEnd = useRef(null);
    const [frameCopy, setFrameCopy] = useState(null);
    const [coverPreview, setCoverPreview] = useState(null);
    const selectionKey = project && pub ? JSON.stringify([project, pub.renderJobId]) : "";
    const selectionReady = !!selectionKey && defaultedRender.current === selectionKey;

    useEffect(() => {
        client.api("/api/creation/platform-profiles").then((data) => setProfiles(data.profiles || [])).catch(() => setProfiles([]));
    }, []);
    useLayoutEffect(() => {
        if (!selectionKey || selectionReady || !profiles.length) return;
        defaultedRender.current = selectionKey;
        const available = profiles.map(p => p.Platform);
        const allowed = pub.campaignRules?.fields.platforms?.map(item => item.value) || [];
        const requested = pub.targetPlatforms?.length ? pub.targetPlatforms : [pub.campaignPlatform].filter(Boolean);
        const picked = [...new Set(requested)].filter(key => available.includes(key) && (!allowed.length || allowed.includes(key)));
        if (!picked.length) {
            const fallback = allowed.length ? allowed.find(key => available.includes(key))
                : requested.length ? undefined : available[0];
            if (fallback) picked.push(fallback);
        }
        setSelected(picked); setPlatform(picked[0] || "");
    }, [selectionKey, selectionReady, profiles, pub]);
    // Open what was asked for (a video, publication or package from the bin), else the newest video.
    useEffect(() => {
        const changedProject = shownProject.current !== null && shownProject.current !== project;
        if (changedProject && open === shownOpen.current) rejectedOpen.current = open;
        const requestedOpen = open !== shownOpen.current || shownProject.current !== project;
        if (open !== rejectedOpen.current && open && ["render", "publication", "package"].includes(open.kind)) {
            if (requestedOpen) void show(open.id, open.kind);
        }
        else if ((!renderId || shownProject.current !== project) && renders[0]) void show(renders[0].jobId, "render");
        else if (changedProject) { setPub(null); setPackages([]); setRenderId(""); setBusy(""); setMessage(""); setFieldError({}); }
        shownProject.current = project; shownOpen.current = open;
    }, [open, project, renders.length]);

    const show = useCallback(async (id, kind) => {
        polling.current.abort(); polling.current = new AbortController();
        const generation = ++epoch.current;
        const current = () => generation === epoch.current;
        setMessage(""); setFieldError({}); setPackages([]); setPub(null); setBusy(""); setPreviewPackage("");
        try {
            const detail = kind === "package" ? await client.api(`${jobPath(id)}/package`) : null;
            if (!current()) return;
            const publicationId = detail?.publicationJobId || id;
            const data = await client.api(`${jobPath(publicationId)}/publication`);
            if (!current()) return;
            setRenderId(data.renderJobId); setPub(data);
            setForm({title: data.title, description: data.description, tags: data.tags.join("，"),
                coverFrame: data.coverFrame, coverTitle: data.coverTitle ?? ""});
            if (data.publicationJobId) await restore(data, generation, detail ? {id, detail} : null);
            return generation;
        } catch (error) { if (current()) setMessage(error.message); }
    }, [project]);

    const fps = pub ? pub.fps.numerator / pub.fps.denominator : 30;
    const rawTags = pub && form.tags === pub.tags.join("，") ? pub.tags : parseTags(form.tags);
    const formTags = [...new Set(rawTags)];
    const coverTitle = form.coverTitle.trim() ? form.coverTitle : "";
    const savedCoverTitle = pub?.coverTitle?.trim() ? pub.coverTitle : "";
    const coverTitleError = COVER_TITLE_INVALID.test(form.coverTitle) ? "封面标题包含无效字符。"
        : /[{}\\]/u.test(form.coverTitle) ? "封面标题不能包含半角花括号或反斜杠。"
        : [...form.coverTitle].length > COVER_TITLE_LIMIT ? `封面标题不能超过 ${COVER_TITLE_LIMIT} 字。` : "";
    const coverChanged = pub && (form.coverFrame !== pub.coverFrame || coverTitle !== savedCoverTitle || !!coverTitleError);
    const dirty = pub && (form.title !== pub.title || form.description !== pub.description
        || formTags.length !== pub.tags.length || formTags.some((tag, i) => tag !== pub.tags[i])
        || coverChanged);
    useLayoutEffect(() => { onDirtyChange(!!dirty); }, [dirty, onDirtyChange]);
    useLayoutEffect(() => () => onDirtyChange(false), [onDirtyChange]);
    const videoSrc = pub ? client.sameOrigin(pub.videoUrl, `${jobPath(pub.renderJobId)}/video`) || "" : "";
    const thumbs = useCoverCandidates(videoSrc, pub?.frames || 0, fps);
    const useFrame = () => {
        const el = video.current; if (!el || !pub) return;
        const frame = Math.max(0, Math.min(pub.frames - 1, Math.floor(el.currentTime * fps)));
        setForm(current => ({...current, coverFrame: frame}));
        try { setCoverPreview({frame, url: grabFrame(el), src: videoSrc}); } catch { setCoverPreview(null); }
    };
    const save = async () => {
        if (!pub) return;
        const generation = epoch.current;
        const current = () => generation === epoch.current;
        const next = publicationFieldErrors({title: form.title.trim(), description: form.description, tags: rawTags});
        if (coverTitleError) next.coverTitle = coverTitleError;
        if (Object.keys(next).length) { setFieldError(next); setMessage(""); return; }
        setFieldError({});
        setBusy("publication"); setMessage("正在保存发布信息并截取封面…");
        try {
            const accepted = await client.submit("publication", {renderJobId: pub.renderJobId, expectedRenderReceiptSha256: pub.expectedRenderReceiptSha256,
                coverFrame: form.coverFrame, title: form.title.trim(), description: form.description, tags: formTags,
                ...(coverTitle ? {coverTitle} : {})});
            if (!current()) return;
            const done = await client.settle(accepted.jobId);
            if (!current()) return;
            if (done.status !== "completed") throw new Error(`保存失败：${done.error?.message || done.status}`);
            client.forgetIntent("publication"); onWorksChanged();
            setBusy("");
            const shown = await show(done.jobId, "publication"); if (epoch.current !== shown) return; setMessage("已保存。可以生成平台包了。");
        } catch (error) {
            if (current()) {
                const shown = publicationErrorFields(error.message);
                const isCoverTitle = shown.message.startsWith("封面标题");
                setFieldError(isCoverTitle ? {coverTitle: shown.message} : shown.fields);
                setMessage(isCoverTitle ? "" : shown.message);
            }
        } finally { if (current()) setBusy(""); }
    };
    const restore = async (snapshot, generation, opened = null) => {
        const data = await client.api(`${jobPath(snapshot.publicationJobId)}/packages`, {projectId: project});
        if (generation !== epoch.current) return [];
        const selected = opened && data.jobs.find(row => row.jobId === opened.id && row.status === "completed"
            && row.parentReceiptSha256 === opened.detail.expectedPublicationReceiptSha256);
        if (opened && !selected) setMessage("链接中的平台包目前不可用。");
        if (selected) setPreviewPackage(selected.jobId);
        setPackages(current => {
            const loaded = new Map(current.filter(row => row.generationStatus === "completed").map(row => [row.jobId, row]));
            return data.jobs.map(row => {
                if (row === selected) return {...row, ...opened.detail, error: undefined};
                const old = loaded.get(row.jobId);
                return old && row.status === "completed" && row.parentReceiptSha256
                    && row.parentReceiptSha256 === old.parentReceiptSha256 ? {...old, ...row} : row;
            });
        });
        for (const row of data.jobs) {
            if (generation !== epoch.current) return data.jobs;
            if (["pending", "running"].includes(row.status)) {
                void client.settle(row.jobId, polling.current.signal, (state) => {
                    if (generation === epoch.current) setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, ...state} : r));
                }).then(() => loadDetail(row, generation)).catch((error) => { if (generation === epoch.current) setMessage(error.message); });
            } else if (row.status === "completed" && row !== selected) void loadDetail(row, generation).catch((error) => { if (generation === epoch.current) setMessage(error.message); });
        }
        return data.jobs;
    };
    const loadDetail = async (row, generation) => {
        try {
            const data = await client.api(`${jobPath(row.jobId)}/package`);
            if (generation === epoch.current) setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, ...data, error: undefined} : r));
        } catch (error) {
            if (generation === epoch.current) {
                setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, generationStatus: "", artifacts: undefined, error: {code: error.code || "creation.artifact_invalid", message: error.message}} : r));
                setMessage(error.message);
            }
            throw error;
        }
    };
    const buildPackage = async (retry = null) => {
        if (!pub?.publicationJobId) return;
        const generation = epoch.current, snapshot = pub;
        const current = () => generation === epoch.current;
        const chosen = retry ? [retry.profile] : profiles.filter((p) => selected.includes(p.Platform));
        setBusy("package"); setMessage("");
        try {
            const existing = await restore(snapshot, generation);
            for (const profile of chosen) {
                if (!current()) return;
                const scope = JSON.stringify([project, snapshot.publicationJobId, snapshot.publicationReceiptSha256, profile]);
                const attempts = existing.filter((r) => JSON.stringify(r.profile) === JSON.stringify(profile));
                const running = attempts.find((r) => ["pending", "running"].includes(r.status));
                if (running) {
                    const done = await client.settle(running.jobId, polling.current.signal, (state) => {
                        if (current()) setPackages((rows) => rows.map((r) => r.jobId === running.jobId ? {...r, ...state} : r));
                    });
                    if (!current()) return;
                    if (done.status === "completed") await loadDetail(running, generation);
                    continue;
                }
                if (attempts.some((r) => r.status === "completed")) continue;
                if (retry) {
                    if (!attempts.some((r) => r.jobId === retry.jobId && ["failed", "interrupted"].includes(r.status))) continue;
                    client.retryPackageIntent(scope, attempts);
                } else if (attempts.length) continue;
                let accepted;
                try {
                    accepted = await client.submit("package", {publicationJobId: snapshot.publicationJobId, expectedPublicationReceiptSha256: snapshot.publicationReceiptSha256, profile}, scope);
                } catch (error) {
                    if (!current()) return;
                    // Unknown transport outcome retains this scope's request id. Reconcile before any resubmit.
                    await restore(snapshot, generation);
                    if (!current()) return;
                    setMessage(error.message);
                    if (!error.status) return;
                    setPackages((rows) => [...rows, {jobId: scope, profile, status: "denied", error: {message: error.message}}]);
                    continue;
                }
                if (!current()) return;
                const row = {...accepted, profile};
                setPackages((rows) => [...rows.filter((r) => r.jobId !== row.jobId), row]);
                const done = await client.settle(accepted.jobId, polling.current.signal, (state) => {
                    if (current()) setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, ...state} : r));
                });
                if (!current()) return;
                onWorksChanged();
                if (done.status === "completed") {
                    try { await loadDetail(row, generation); }
                    catch (error) { if (current()) setMessage(error.message); }
                }
            }
        } catch (error) { if (current()) setMessage(error.message); }
        finally { if (current()) setBusy(""); }
    };

    const saved = !!pub?.publicationJobId && !dirty;
    const draftKey = JSON.stringify([project, pub?.publicationJobId, pub?.publicationReceiptSha256]);
    const drafts = platformDraft.key === draftKey ? platformDraft.values : {};
    const resetPlatformPreview = () => {
        shortEnd.current = null;
        setFrameCopy(null);
    };
    const updateDraft = (platformId, patch) => {
        if (shortEnd.current) {
            video.current?.pause();
            resetPlatformPreview();
        }
        setPlatformDraft(previous => {
            const values = previous.key === draftKey ? previous.values : {};
            return {key: draftKey, values: {...values, [platformId]: {...values[platformId], ...patch}}};
        });
    };
    const {chosen, error: variantError, copyError, matches} = configuredProfiles(profiles, selected, drafts, fps, pub);
    const packageError = variantError || copyError;
    const updatePreview = (player, time) => {
        const range = shortEnd.current;
        if (!range || player.seeking) return;
        const span = range.spans[range.index];
        if (time >= span.endFrame / fps) {
            const next = range.spans[range.index + 1];
            if (!next) {
                resetPlatformPreview();
                player.pause();
                player.currentTime = Math.max(0, span.endFrame / fps - 0.001);
                return;
            }
            range.elapsed += span.endFrame - span.startFrame;
            range.index++;
            player.currentTime = next.startFrame / fps;
            setFrameCopy(previewCaption(range, fps, range.elapsed));
        } else if (time >= span.startFrame / fps) {
            const outputFrame = range.elapsed + Math.floor(time * fps + 1e-6) - span.startFrame;
            const caption = previewCaption(range, fps, outputFrame);
            setFrameCopy(old => old?.position === caption?.position && old?.text === caption?.text ? old : caption);
        }
    };
    const seekPlatformPreview = (player) => {
        const range = shortEnd.current;
        if (!range) return;
        const start = range.spans[range.index].startFrame / fps;
        if (player.currentTime < start - 0.001) player.currentTime = start;
        else updatePreview(player, player.currentTime);
    };
    const previewShort = (fields) => {
        const player = video.current;
        if (!player) return;
        const startFrame = fields.variant?.startFrame || 0;
        const frames = fields.variant?.durationFrames || pub.frames;
        const spans = fields.variant?.ranges || [{startFrame, endFrame: startFrame + frames}];
        const range = {spans, frames, index: 0, elapsed: 0, text: fields.publicationText};
        shortEnd.current = range;
        setFrameCopy(previewCaption(range, fps, 0));
        const watchFrame = (_now, frame) => {
            if (shortEnd.current !== range || video.current !== player) return;
            if (!player.seeking) updatePreview(player, frame.mediaTime + 1e-6);
            if (shortEnd.current === range) player.requestVideoFrameCallback(watchFrame);
        };
        player.currentTime = spans[0].startFrame / fps;
        player.requestVideoFrameCallback?.(watchFrame);
        void player.play().catch(error => {
            if (shortEnd.current !== range) return;
            resetPlatformPreview();
            setMessage(error.message);
        });
    };
    const suggestCopy = (profile) => {
        const id = profile.Platform;
        const draft = drafts[id] || {};
        const copy = draftPlatformCopy(pub, profile, draft.themeCut?.theme || draft.content || "");
        updateDraft(id, {
            opening: draft.opening?.trim() ? draft.opening : copy.opening,
            closing: draft.closing?.trim() ? draft.closing : copy.closing,
        });
    };
    const queue = usePackageBatches({project, pub, profiles: chosen, selected, disabled: !!busy || !saved, startBlocked: !selectionReady || !!packageError,
        onChanged: () => { const generation = epoch.current; if (pub?.publicationJobId) void restore(pub, generation).catch(e => { if (epoch.current === generation) setMessage(e.message); }); }});
    const coverSrc = pub?.publicationJobId && !coverChanged ? `${jobPath(pub.publicationJobId)}/publication-files/cover.png` : null;
    const localCover = coverPreview?.src === videoSrc && coverPreview.frame === form.coverFrame ? coverPreview.url : "";
    const limits = profiles.find((p) => p.Platform === platform)?.Fields?.limits || {};
    const cls = `work${layout.bin ? "" : " no-bin"}${layout.insp ? "" : " no-insp"}`;
    const chooseJob = (job) => leave(() => { void show(job.jobId, job.kind); });
    const visibleEpoch = epoch.current;
    const canApplyTemplate = !!pub && !busy && shownProject.current === project && shownOpen.current === open;
    const applyBrandTemplate = template => {
        if (!canApplyTemplate || epoch.current !== visibleEpoch || activeProject.current !== project
            || shownOpen.current !== open) return;
        const changes = {
            ...(template.title ? {title: template.title} : {}),
            ...(template.description ? {description: template.description} : {}),
            ...(template.tags.length ? {tags: campaignTags(pub.campaignRules, template.tags).join("，")} : {}),
        };
        setForm(current => ({...current, ...changes}));
        setFieldError(current => {
            const errors = {...current};
            for (const name of Object.keys(changes)) delete errors[name];
            return errors;
        });
        setMessage("已套用品牌文案模板。请核对后保存发布信息。");
    };
    const historyRows = (rows, rowLabel, isCurrent, renderOf) => rows.map(job => {
        const source = renders.find(render => render.jobId === renderOf(job));
        return html`<button key=${job.jobId} type="button" class="row" aria-current=${isCurrent(job)} onClick=${() => chooseJob(job)}>
            <span class="dot ok"></span><span class="name" title=${source?.name || ""}>${source?.name || when(job.createdAt)}</span><span class="meta">${rowLabel(job)}</span></button>`;
    });
    return html`<div class=${cls}>
        <aside class="panel" hidden=${!layout.bin} aria-label="成片列表">
            <div class="panel-head">成片</div>
            <div class="panel-body">
                ${filterControls}
                ${renders.map((job) => html`<button class="row" aria-current=${job.jobId === renderId} onClick=${() => chooseJob(job)}>
                    <span class="dot ok"></span><span class="name">${job.name || when(job.createdAt)}</span><span class="meta">成片</span></button>`)}
                ${!renders.length && html`<p class="note">还没有成片。先在剪辑区导出一个视频。</p>`}
                ${savedPublications.length > 0 && html`<details class="group"><summary>已保存发布信息（${savedPublications.length}）</summary>
                    ${historyRows(savedPublications, () => "发布信息", job => job.jobId === pub?.publicationJobId, job => job.parentJobId)}</details>`}
                ${savedPackages.length > 0 && html`<details class="group" open><summary>已生成平台包（${savedPackages.length}）</summary>
                    ${historyRows(savedPackages, job => PLATFORMS[job.platform] || "平台包", job => job.jobId === previewPackage,
                        job => savedPublications.find(publication => publication.jobId === job.parentJobId)?.parentJobId)}</details>`}
            </div>
        </aside>
        <div class="center">
            <section class="viewer" aria-label="成片预览">
                <div class="stage">${pub ? html`<video ref=${video} src=${videoSrc} controls playsinline preload="metadata"
                    onLoadStart=${resetPlatformPreview} onEnded=${resetPlatformPreview}
                    onSeeked=${e => seekPlatformPreview(e.currentTarget)}
                    onTimeUpdate=${e => updatePreview(e.currentTarget, e.currentTarget.currentTime)}></video>
                    ${frameCopy && html`<span class=${`platform-frame-copy ${frameCopy.position}`}>${frameCopy.text}</span>`}` : html`<div class="empty">在左侧选一个成片</div>`}</div>
                <div class="transport">
                    <button class="btn ghost" disabled=${!pub} onClick=${useFrame}>用当前画面做封面</button>
                    <span class="tc">封面：第 ${form.coverFrame} 帧（${(form.coverFrame / fps).toFixed(2)} 秒）</span>
                    <span class="spacer"></span>
                    ${pub && html`<span class="badge">${pub.width}×${pub.height} · ${(pub.frames / fps).toFixed(1)} 秒</span>`}
                </div>
            </section>
            <section class="timeline publish-pkg" aria-label="平台包">
                <div class="panel-head">平台包<span class="track-label">${saved ? "按平台预设转码、截封面、打包；不会自动发布" : "先保存右侧的发布信息"}</span></div>
                <div class="track-area">
                    <div class="actions-row">
                        ${profiles.map((p) => html`<label><input type="checkbox" checked=${selectionReady && selected.includes(p.Platform)} disabled=${!selectionReady || !!busy} onChange=${(e) => { setPlatform(p.Platform); setSelected(e.currentTarget.checked ? [...selected, p.Platform] : selected.filter((v) => v !== p.Platform)); }} />${PLATFORMS[p.Platform] || p.Platform}${selectionReady && selected.includes(p.Platform) && !packages.some((r) => r.profile?.Platform === p.Platform) ? " · 尚未提交" : ""}</label>`)}
                        <button class="btn" disabled=${!selectionReady || !saved || !!busy || queue.busy || queue.running || !selected.length || !!packageError} onClick=${queue.start}>${queue.busy ? "正在加入队列…" : "生成平台包"}</button>
                        ${saved && !selected.length ? html`<span class="hint" role="status" aria-label="平台包状态">至少勾选一个平台</span>` : null}
                        <span class="hint">${["titleMaxChars", "descriptionMaxChars", "tagMaxCount"].filter((k) => limits[k]).map((k) => `${CHECKS[k]}≤${limits[k]}`).join(" · ")}</span>
                    </div>
                    ${saved && selected.length > 0 && html`<details>
                        <summary>调整各平台时长和文案（可选）</summary>
                        <p class="hint">用顿号分隔多个关键词可拼接对应镜头，时长设为上限，留空采用匹配镜头总时长。开场和结尾各最多显示 2 秒。</p>
                        ${chosen.map(profile => {
                            const {Platform: id, Fields: fields} = profile;
                            const canDraft = !variantError && !busy && !queue.busy && !queue.running
                                && (fields.variant?.durationFrames || pub.frames) >= 2
                                && (!drafts[id]?.opening?.trim() || !drafts[id]?.closing?.trim());
                            return html`<div class="actions-row" key=${id}>
                            <label>${PLATFORMS[id]} 时长（秒）
                                <input class="input" inputmode="decimal" placeholder="保留全片" value=${drafts[id]?.duration || ""}
                                    disabled=${!!busy || queue.busy || queue.running} onInput=${e => updateDraft(id, {duration: e.currentTarget.value})} />
                            </label>
                            ${!!pub?.contentShots?.length && html`<label>${PLATFORMS[id]} 内容关键词
                                <input class="input" placeholder="可留空或用顿号分隔" maxlength="60" value=${drafts[id]?.content || ""}
                                    disabled=${!!busy || queue.busy || queue.running} onInput=${e => updateDraft(id, {content: e.currentTarget.value, themeCut: null})} />
                            </label>
                            <${ThemeRecommendations} key=${draftKey + id} pub=${pub} platform=${PLATFORMS[id]} fps=${fps}
                                disabled=${!!busy || queue.busy || queue.running} applied=${!!drafts[id]?.themeCut}
                                onApply=${themeCut => updateDraft(id, {themeCut, content: ""})} />`}
                            ${matches[id] && html`<div>
                                <span class="hint">${(matches[id].ranges || [matches[id]]).map(span => spanLabel(span, fps)).join(" ＋ ")} · ${matches[id].label}</span>
                                <button class="btn ghost" disabled=${!!variantError} onClick=${() => previewShort(fields)}>预览${PLATFORMS[id]}所选区间</button>
                            </div>`}
                            ${[["opening", "开场文案"], ["closing", "结尾提示"]].map(([field, label]) => html`<label key=${field}>${PLATFORMS[id]} ${label}
                                <input class="input" placeholder="可留空" value=${drafts[id]?.[field] || ""}
                                    disabled=${!!busy || queue.busy || queue.running} onInput=${e => updateDraft(id, {[field]: e.currentTarget.value})} />
                            </label>`)}
                            <button type="button" class="btn ghost" disabled=${!canDraft} onClick=${() => suggestCopy(profile)}>起草${PLATFORMS[id]}画面文案</button>
                            ${!matches[id] && fields.publicationText && html`<button type="button" class="btn ghost" disabled=${!!variantError}
                                onClick=${() => previewShort(fields)}>试听${PLATFORMS[id]}画面文案</button>`}
                            <${PlatformPublicationCopy} platform=${PLATFORMS[id]} draft=${drafts[id]?.publicationCopy}
                                fallback=${publicationCopyDraft(pub)} disabled=${!!busy || queue.busy || queue.running}
                                onChange=${publicationCopy => updateDraft(id, {publicationCopy})} />
                        </div>`;})}
                    </details>`}
                    ${packageError && html`<p class="hint warn" role="status">${packageError}</p>`}
                    ${saved && queue.view}
                    ${packages.map((pkg) => html`<div class="pkg-result" key=${pkg.jobId}>
                        <p>${PLATFORMS[pkg.profile?.Platform] || ""}${pkg.profile?.Fields?.variant ? ` · 短版 ${(pkg.profile.Fields.variant.durationFrames / fps).toFixed(2)} 秒` : ""} · ${client.jobStatus(pkg.status)} ${pkg.error?.message || ""}</p>
                        ${pkg.profile?.Fields?.variant?.startFrame && html`<p class="hint">原成片区间 ${(pkg.profile.Fields.variant.startFrame / fps).toFixed(2)}–${((pkg.profile.Fields.variant.startFrame + pkg.profile.Fields.variant.durationFrames) / fps).toFixed(2)} 秒</p>`}
                        ${pkg.profile?.Fields?.variant?.ranges && html`<p class="hint">原成片区间 ${pkg.profile.Fields.variant.ranges.map(span => spanLabel(span, fps)).join(" ＋ ")}</p>`}
                        ${pkg.profile?.Fields?.publicationText?.opening && html`<p class="hint">开场：${pkg.profile.Fields.publicationText.opening}</p>`}
                        ${pkg.profile?.Fields?.publicationText?.closing && html`<p class="hint">结尾：${pkg.profile.Fields.publicationText.closing}</p>`}
                        ${["failed", "interrupted"].includes(pkg.status) && html`<button class="btn ghost" disabled=${!!busy || !saved} onClick=${() => buildPackage(pkg)}>重试此平台</button>`}
                        ${pkg.generationStatus === "completed" && !pkg.error && html`<div>
                        <p class="v">${PLATFORMS[pkg.profile?.Platform] || ""}：${pkg.generationStatus === "completed" ? "已生成" : "未完成"}；本地检查${STATUS[pkg.localChecks] || "未知"}${pkg.publicationEligibility === "blocked" ? "；发布受阻（含仅供测试的音乐等）" : ""}${pkg.watermark ? "；含水印" : ""}。平台官方规则、素材权利尚未核实。</p>
                        ${pkg.profile?.Fields?.publicationCopy && html`<p class="hint">发布标题：${pkg.profile.Fields.publicationCopy.title}</p>`}
                        <p class="hint">${Object.entries(pkg.validation?.checks || {}).map(([k, s]) => `${CHECKS[k] || k}：${STATUS[s] || "未知"}`).join("　")}</p>
                        <${CampaignChecks} rules=${pub.campaignRules} media=${pkg.validation?.facts} tags=${pkg.profile?.Fields?.publicationCopy?.tags ?? pub.tags}
                            platforms=${[pkg.profile?.Platform]} platformNames=${PLATFORMS} title="平台包活动要求" />
                        <${LocalPackageFiles} key=${pkg.jobId} project=${project} pkg=${pkg} />
                        <div class="actions-row"><a class="btn ghost" href=${`${jobPath(pkg.jobId)}/package-files/package.zip?download=1`} download=${pkg.downloadName || "package.zip"}>下载平台包（zip）</a>
                            <a class="btn ghost" href=${`${jobPath(pkg.jobId)}/package-files/video.mp4?download=1`} download="video.mp4">只下载视频</a>
                            <button type="button" class="btn ghost" onClick=${() => {
                                const link = client.studioJobLink(project, pkg.jobId);
                                void client.copyText(link, () => setMessage("已复制平台包链接。"), () => setMessage(link));
                            }}>复制平台包链接</button>
                            <button class="btn ghost" aria-expanded=${previewPackage === pkg.jobId} onClick=${() => setPreviewPackage(id => id === pkg.jobId ? "" : pkg.jobId)}>${previewPackage === pkg.jobId ? "收起预览" : `预览${PLATFORMS[pkg.profile?.Platform] || "平台"}成片`}</button></div>
                        ${previewPackage === pkg.jobId && html`<video class="package-video" aria-label="平台成片预览" src=${`${jobPath(pkg.jobId)}/package-files/video.mp4`} controls playsinline preload="metadata"></video>`}
                        <${PackageReview} key=${`${project}:${pkg.jobId}`} project=${project} pkg=${pkg} teamVersion=${teamVersion} />
                        ${pkg.artifacts?.["video.mp4"]?.sha256 && html`<${PublicationFeedback}
                            key=${`${project}:${pub.publicationJobId}:${pkg.artifacts["video.mp4"].sha256}`}
                            project=${project} publicationId=${pub.publicationJobId} packageId=${pkg.jobId} videoSha256=${pkg.artifacts["video.mp4"].sha256}
                            onOpenReference=${onOpenReference} />`}
                    </div>`}
                    </div>`)}
                </div>
            </section>
        </div>
        <aside class="panel" hidden=${!layout.insp} aria-label="发布信息">
            <div class="panel-head">发布信息</div>
            <div class="panel-body">
                ${project && html`<${EnterpriseTeam} key=${project} project=${project} onSaved=${() => setTeamVersion(n => n + 1)}
                    onApplyTemplate=${canApplyTemplate ? applyBrandTemplate : null} />`}
                ${message && html`<p class="note" role="status">${message}</p>`}
                ${pub ? html`
                    <p class="hint">${pub.publicationJobId ? (dirty ? "有未保存的修改" : "已保存的版本") : "按需求自动起草的模板，请改一遍再保存。"}</p>
                    <${AiCopy} key=${pub.renderJobId} renderJobId=${pub.renderJobId} disabled=${!!busy}
                        onCopy=${(copy) => setForm((f) => ({...f, title: copy.title, description: copy.description, tags: campaignTags(pub.campaignRules, copy.tags).join("，")}))} />
                    <label class="form-row">标题（${form.title.length} 字）<input class="input" value=${form.title} maxLength="200" onInput=${(e) => { setForm({...form, title: e.currentTarget.value}); setFieldError((cur) => ({...cur, title: ""})); }} />${fieldError.title ? html`<p class="hint" data-field="title">${fieldError.title}</p>` : null}</label>
                    <label class="form-row">简介（${form.description.length} 字）<textarea class="input" rows="6" value=${form.description} onInput=${(e) => { setForm({...form, description: e.currentTarget.value}); setFieldError((cur) => ({...cur, description: ""})); }}></textarea>${fieldError.description ? html`<p class="hint" data-field="description">${fieldError.description}</p>` : null}</label>
                    <label class="form-row">标签（逗号分隔，${formTags.length} 个）<input class="input" value=${form.tags} onInput=${(e) => { setForm({...form, tags: e.currentTarget.value}); setFieldError((cur) => ({...cur, tags: ""})); }} />${fieldError.tags ? html`<p class="hint" data-field="tags">${fieldError.tags}</p>` : null}</label>
                    ${saved && chosen.some(profile => profile.Fields.publicationCopy)
                        ? chosen.map(({Platform: id, Fields: fields}) => html`<${CampaignChecks} key=${id} rules=${pub.campaignRules} media=${pub}
                            tags=${fields.publicationCopy?.tags ?? pub.tags} platforms=${[id]} platformNames=${PLATFORMS} title=${`${PLATFORMS[id]}活动要求核对`} />`)
                        : html`<${CampaignChecks} rules=${pub.campaignRules} media=${pub} tags=${formTags} platforms=${selected} platformNames=${PLATFORMS} title="活动要求核对" />`}
                    <p class="hint">简介里可以补一句作者的话和相关链接（官网、下载、活动页）。</p>
                    <${CoverField} savedSrc=${coverSrc} preview=${localCover} thumbs=${thumbs} coverFrame=${form.coverFrame} fps=${fps}
                        coverTitle=${form.coverTitle} titleError=${coverTitleError || fieldError.coverTitle}
                        onPick=${(frame, url) => {
                            setForm(current => ({...current, coverFrame: frame}));
                            setCoverPreview({frame, url, src: videoSrc});
                        }}
                        onTitle=${value => {
                            setForm(current => ({...current, coverTitle: value}));
                            setFieldError(current => ({...current, coverTitle: ""}));
                        }} />
                    <div class="actions-row"><button class="btn" disabled=${!!busy || !form.title.trim() || (pub.publicationJobId && !dirty)} onClick=${save}>${busy === "publication" ? "正在保存…" : "保存发布信息"}</button></div>`
                : html`<p class="note">选中成片后，在这里写标题、简介和标签。</p>`}
            </div>
        </aside>
    </div>`;
}
