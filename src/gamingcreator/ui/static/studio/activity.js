// Local activity rules: extraction is read-only until the user explicitly applies it.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api} from "./api.js";
const html = htm.bind(h);
const NAMES = {name: "活动名称", period: "活动时间", platforms: "平台", minDurationSeconds: "最短时长", maxDurationSeconds: "最长时长", orientation: "画面方向", requiredTopics: "必带话题", forbidden: "禁止事项"};
const show = (field, value) => field === "period" ? `${value.start} 至 ${value.end}` : field === "orientation" ? (value === "vertical" ? "竖屏" : "横屏") : /Seconds$/.test(field) ? `${value} 秒` : String(value);
const SUBMISSION_FIELDS = ["name", "period", "orientation", "minDurationSeconds", "maxDurationSeconds", "platforms", "requiredTopics", "forbidden"];

function mapping(fields, draft) {
    const patch = {contentType: "campaign"}, notes = [];
    const platform = fields.platforms?.map(p => p.value).find(v => ["bilibili", "douyin", "kuaishou", "xiaohongshu"].includes(v));
    if (platform) patch.platform = platform;
    else if (fields.platforms?.length) notes.push("平台无法填入，请人工核对");
    const min = fields.minDurationSeconds?.value, max = fields.maxDurationSeconds?.value;
    if (min != null || max != null) {
        const lower = Math.max(1, Math.ceil(min ?? 1)), upper = Math.min(86400, Math.floor(max ?? 86400));
        const current = Number(draft.targetDuration);
        if (lower <= upper && Number.isFinite(current) && current > 0) patch.targetDuration = String(Math.max(lower, Math.min(upper, current)));
        else notes.push("时长范围矛盾或无法填入，请人工核对");
    }
    const submission = Object.fromEntries(SUBMISSION_FIELDS.filter(key => fields[key] != null).map(key => [key, fields[key]]));
    patch.campaignRules = Object.keys(submission).length ? {schemaVersion: "campaign-submission-rules-v1", fields: submission} : null;
    if (fields.name && !draft.objective.trim()) patch.objective = `${fields.name.value} 活动投稿`;
    return {patch, notes};
}

export function ActivityRules({draft, update}) {
    const [text, setText] = useState(""), [file, setFile] = useState(null), [url, setUrl] = useState("");
    const [result, setResult] = useState(null), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
    const epoch = useRef(0), request = useRef(null);
    useEffect(() => () => { epoch.current++; request.current?.abort(); }, []);
    const invalidate = () => { epoch.current++; request.current?.abort(); setResult(null); setMessage(""); setBusy(false); };
    const parse = async () => {
        invalidate(); const token = epoch.current, controller = new AbortController(); request.current = controller;
        setBusy(true); setMessage(!file && url.trim() ? "正在读取网页…" : "正在本机提取…");
        try {
            let body;
            if (file) {
                if (file.size > 10 * 1024 * 1024) throw new Error("文件超过10MB。");
                const bytes = new Uint8Array(await file.arrayBuffer()); let binary = "";
                for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
                body = {fileName: file.name, dataBase64: btoa(binary)};
            } else if (url.trim()) body = {url: url.trim()};
            else if (text.trim()) body = {text};
            else throw new Error("请粘贴规则文字、填写网页地址或选择文件。");
            if (epoch.current !== token) return;
            const parsed = await api("/api/creation/activity-rules", {}, {body, signal: controller.signal});
            if (epoch.current !== token) return;
            setResult(parsed); setMessage(`识别到 ${parsed.knownFields}/${parsed.totalFields} 项`);
        } catch (error) { if (epoch.current === token) setMessage(`未能解析：${error.message}`); }
        finally { if (epoch.current === token) setBusy(false); }
    };
    const apply = () => {
        if (!result) return;
        const {patch, notes} = mapping(result.fields, draft); update(patch);
        setMessage(`已填入未来创作需求。${notes.join("；")} 新方案会保留规则及原文，供发布前核对。`);
    };
    return html`<details class="group activity-rules"><summary>活动规则（可选）</summary>
        <p class="note">粘贴文字、填写活动网页地址，或选择本地 txt/md/html/截图/PDF（≤10MB）。只在你填写地址时读取该网页一次；提取在本机完成，不调用模型；核对后再填入未来需求。</p>
        <label class="form-row">规则文字<textarea class="input" rows="4" maxlength="200000" value=${text} onInput=${e => { invalidate(); setText(e.currentTarget.value); }} /></label>
        <label class="form-row">或网页地址<input class="input" type="url" placeholder="https://…" value=${url} onInput=${e => { invalidate(); setUrl(e.currentTarget.value); }} /></label>
        <label class="form-row">或选择文件<input type="file" accept=".txt,.md,.html,.htm,.png,.jpg,.jpeg,.bmp,.pdf" onChange=${e => { invalidate(); setFile(e.currentTarget.files?.[0] || null); }} /></label>
        ${file ? html`<p class="note">将解析文件：${file.name}（优先于网页地址和文字）</p>` : url.trim() ? html`<p class="note">将读取网页（优先于文字）</p>` : null}
        <button type="button" class="btn ghost" onClick=${parse}>${busy ? "重新解析规则" : "解析规则"}</button>
        <p class="note" role="status">${message}</p>
        ${draft.campaignRules && html`<p class="hint">已应用到下一份活动投稿方案 <button type="button" class="btn ghost" onClick=${() => { update({campaignRules: null}); setMessage("已清除未来方案的活动发布要求。"); }}>清除已应用要求</button></p>`}
        ${result && html`<div class="rules-result">
            <p class="note">来源：${{pasted: "粘贴文字", text: "文本文件", html: "网页文件", image: "截图OCR", pdf: "PDF逐页OCR", web: "网页"}[result.source.sourceKind] || result.source.sourceKind}${result.source.url ? `（${result.source.url}，读取于 ${result.source.fetchedAt}）` : ""}${result.source.pagesRead ? `，读取 ${result.source.pagesRead}/${result.source.pages} 页` : ""}。行号指提取文字，截图/PDF请对照原件。</p>
            ${result.warnings?.map(warning => html`<p class="note">${warning}</p>`)}
            ${Object.entries(NAMES).map(([field, label]) => html`<div class="field"><strong>${label}：</strong>${result.fields[field] == null ? "未识别" : html`<ul class="facts">${(Array.isArray(result.fields[field]) ? result.fields[field] : [result.fields[field]]).map(item => html`<li>${show(field, item.value)} 〔第${item.line}行：${item.text}〕</li>`)}</ul>`}</div>`)}
            <p class="note">必带话题会加入发布标签。发布时可按规则原文核对日期和禁止事项。</p>
            <button type="button" class="btn ghost" onClick=${apply}>填入创作需求</button>
        </div>`}
    </details>`;
}

export const campaignTags = (rules, tags) => rules ? [...new Set([
    ...(rules?.fields?.requiredTopics || []).map(item => item.value), ...tags,
])].slice(0, 20) : tags;

export function CampaignChecks({rules, media, tags, platforms, platformNames, title}) {
    if (!rules?.fields || !media) return null;
    const {name, period, forbidden, orientation, minDurationSeconds, maxDurationSeconds, requiredTopics, platforms: requiredPlatforms} = rules.fields;
    const seconds = media.frames * media.fps.denominator / media.fps.numerator;
    const normalize = text => text.normalize("NFKC").replace(/^#+|#+$/g, "").trim().toLowerCase();
    const tagSet = new Set(tags.map(normalize));
    const rows = [
        ...(orientation ? [["画幅", orientation, orientation.value === (media.width < media.height ? "vertical" : media.width > media.height ? "horizontal" : "square")]] : []),
        ...(minDurationSeconds ? [["最短时长", minDurationSeconds, seconds >= minDurationSeconds.value]] : []),
        ...(maxDurationSeconds ? [["最长时长", maxDurationSeconds, seconds <= maxDurationSeconds.value]] : []),
        ...(requiredTopics || []).map(item => [`标签 #${item.value}`, item, tagSet.has(normalize(item.value))]),
    ];
    if (requiredPlatforms?.length) {
        const allowed = requiredPlatforms.map(item => item.value);
        const platformTitle = allowed.map(key => platformNames[key] || key).join("、");
        rows.push([`投稿平台 ${platformTitle}`, requiredPlatforms[0], platforms.length > 0 && platforms.every(key => allowed.includes(key))]);
    }
    const manual = [
        ...(period ? [[`活动日期 ${show("period", period.value)}`, period]] : []),
        ...(forbidden || []).map(item => [`禁止事项 ${item.value}`, item]),
    ];
    const status = rows.some(([, , ok]) => !ok) ? " · 有待核对"
        : manual.length ? " · 待人工核对" : rows.length ? " · 已匹配" : "";
    const citation = item => html`<div class="hint">第${item.line}行 ${item.text}</div>`;
    return html`<details class="group campaign-checks" aria-label=${title} open><summary>${title}${status}</summary>
        <ul class="facts">
            ${name && html`<li>活动 ${name.value}${citation(name)}</li>`}
            ${rows.map(([label, item, ok]) => html`<li>${label} · ${ok ? "符合" : "待调整"}${citation(item)}</li>`)}
            ${manual.map(([label, item]) => html`<li>${label} · 待人工核对${citation(item)}</li>`)}
        </ul>
    </details>`;
}
